// Acceptance test of the owned, packaged application through loopback CDP.
// Native chooser overrides are scoped to this test process and temp fixtures.
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const net = require('node:net');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const bundle = path.join(root, 'dist/Mathematics Notebook-darwin-arm64/Mathematics Notebook.app');
const executable = path.join(bundle, 'Contents/MacOS/Mathematics Notebook');
const reportPath = path.join(root, 'build/application-smoke.json');
const report = { startedAt: new Date().toISOString(), bundle, checks: [], rendererErrors: [], rendererWarnings: [], mainStderr: '' };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let child, renderer, mainInspector, exited;

async function availableLoopbackPort() {
  return new Promise((resolve, reject) => {
    const server=net.createServer(); server.once('error',reject);
    server.listen(0,'127.0.0.1',() => {
      const port=server.address().port;
      server.close(error => error ? reject(error) : resolve(port));
    });
  });
}

class Connection {
  constructor(socket) {
    this.socket = socket; this.sequence = 0; this.pending = new Map(); this.listeners = new Map();
    socket.addEventListener('message', event => {
      const packet = JSON.parse(event.data);
      if (packet.id) {
        const pending = this.pending.get(packet.id);
        if (!pending) return;
        this.pending.delete(packet.id); clearTimeout(pending.timer);
        packet.error ? pending.reject(new Error(JSON.stringify(packet.error))) : pending.resolve(packet.result);
      } else for (const callback of this.listeners.get(packet.method) || []) callback(packet.params);
    });
    socket.addEventListener('close', () => {
      for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(new Error('Inspector connection closed.')); }
      this.pending.clear();
    });
  }
  static async open(url) {
    const socket = new WebSocket(url);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('WebSocket connection timeout.')), 10000);
      socket.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
      socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('WebSocket connection failed.')); }, { once: true });
    });
    return new Connection(socket);
  }
  on(method, callback) { this.listeners.set(method, [...(this.listeners.get(method) || []), callback]); }
  send(method, params = {}) {
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`${method} timed out.`)); }, 60000);
      this.pending.set(id, { resolve, reject, timer });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async evaluate(expression) {
    const response = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
    return response.result?.value;
  }
  close() { this.socket.close(); }
}

async function waitFor(label, check, timeout = 60000) {
  const started = Date.now(); let lastError;
  while (Date.now() - started < timeout) {
    try { const result = await check(); if (result) return result; } catch (error) { lastError = error; }
    await sleep(100);
  }
  throw new Error(`${label} timed out.${lastError ? ' ' + lastError.message : ''}`);
}
function record(name, details = {}) {
  report.checks.push({ name, passed: true, ...details });
  console.log(JSON.stringify({ step: name, passed: true }));
}
async function saveScreenshot(name) {
  const screenshot = await renderer.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  const destination = path.join(root, 'build', name);
  await fs.writeFile(destination, Buffer.from(screenshot.data, 'base64'));
  return destination;
}
const inputSnapshot = `Array.from(document.querySelectorAll('.input-cell')).map(cell => ({
  id:cell.dataset.cellId, source:cell.querySelector('textarea').value,
  inputLabel:cell.querySelector('.input-label')?.textContent,
  outputLabel:cell.querySelector('.output-label')?.textContent,
  outputText:cell.querySelector('.result-body')?.textContent,
  tex:cell.querySelector('annotation[encoding="application/x-tex"]')?.textContent,
  error:!!cell.querySelector('.error-result'), svg:!!cell.querySelector('.result-svg svg'),
  graphics3d:!!cell.querySelector('.graphics3d-canvas'),
  controls:Array.from(cell.querySelectorAll('.interactive-controls input[data-control-symbol]')).map(input=>({symbol:input.dataset.controlSymbol,value:input.value})),
  interactiveState:cell.querySelector('.interactive-state')?.textContent
}))`;

async function editAndRun(index, source) {
  await renderer.evaluate(`(() => {const cell=document.querySelectorAll('.input-cell')[${index}];
    const input=cell.querySelector('textarea'); input.value=${JSON.stringify(source)};
    input.dispatchEvent(new Event('input',{bubbles:true})); cell.querySelector('.cell-run').click(); return true;})()`);
  await waitFor(`cell ${index} completion`, () => renderer.evaluate(`!document.querySelector('#run-all-button').disabled && !document.querySelectorAll('.input-cell')[${index}].querySelector('.result-stale:not([hidden])')`));
  const outputs = await renderer.evaluate(inputSnapshot);
  assert.equal(outputs[index].error, false, JSON.stringify(outputs[index]));
  return outputs[index];
}

async function openThroughUI(file, title) {
  await mainInspector.evaluate(`globalThis.__acceptanceOpenPath=${JSON.stringify(file)}; true`);
  await renderer.evaluate(`document.querySelector('[data-action="open"]').click(); true`);
  await waitFor(`open ${path.basename(file)} through file IPC`, () => renderer.evaluate(`(() => {
    const confirmation=document.querySelector('#confirm-dialog');
    if(confirmation?.open) confirmation.querySelector('[data-confirm="discard"]').click();
    return document.querySelector('#document-title').value===${JSON.stringify(title)} && document.querySelector('#toast').textContent.includes('已打开');
  })()`));
  await waitFor('fresh kernel after import', () => renderer.evaluate(`document.querySelector('#engine-label').textContent.includes('已就绪')`));
  return renderer.evaluate(inputSnapshot);
}

async function canvasSnapshot(index) {
  return renderer.evaluate(`(() => {
    const canvas=document.querySelectorAll('.input-cell')[${index}].querySelector('.graphics3d-canvas');
    if(!canvas || !canvas.dataset.viewYaw || !canvas.width || !canvas.height) return null;
    const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
    let hash=2166136261, coloredPixels=0;
    for(let i=0;i<pixels.length;i++) hash=Math.imul(hash^pixels[i],16777619)>>>0;
    for(let i=0;i<pixels.length;i+=4) if(pixels[i+3] && (Math.abs(pixels[i]-252)>8 || Math.abs(pixels[i+1]-253)>8 || Math.abs(pixels[i+2]-249)>8)) coloredPixels++;
    return {pixelHash:hash.toString(16).padStart(8,'0'),coloredPixels,width:canvas.width,height:canvas.height,
      yaw:canvas.dataset.viewYaw,pitch:canvas.dataset.viewPitch,zoom:canvas.dataset.viewZoom,label:canvas.getAttribute('aria-label')};
  })()`);
}

async function changeInteractiveParameter(index, value) {
  await renderer.evaluate(`(() => {
    const cell=document.querySelectorAll('.input-cell')[${index}];
    const slider=cell.querySelector('.interactive-controls input[data-control-symbol]');
    if(!slider) throw new Error('Interactive parameter slider missing.');
    slider.value=${JSON.stringify(String(value))}; slider.dispatchEvent(new Event('input',{bubbles:true})); return true;
  })()`);
  await waitFor(`interactive parameter ${value} result`, () => renderer.evaluate(`(() => {
    const cell=document.querySelectorAll('.input-cell')[${index}];
    return cell.querySelector('.interactive-state')?.textContent==='已更新 · 局部参数' &&
      cell.querySelector('.interactive-value')?.textContent===${JSON.stringify(String(value))} && !document.querySelector('#run-all-button').disabled;
  })()`));
  const output = (await renderer.evaluate(inputSnapshot))[index];
  assert.equal(output.error, false, JSON.stringify(output));
  return output;
}

async function sizeOfTree(directory) {
  let bytes = 0;
  for (const item of await fs.readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, item.name);
    if (item.isDirectory()) bytes += await sizeOfTree(file);
    else if (item.isFile()) bytes += (await fs.stat(file)).size;
  }
  return bytes;
}

async function run() {
  await fs.mkdir(path.dirname(reportPath), { recursive: true });
  await fs.access(executable);
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'mathematics-app-smoke-'));
  const userData = path.join(temporary, 'user-data');
  await fs.mkdir(userData);
  const notebookFile = path.join(temporary, 'acceptance.mnb');
  const exportFile = path.join(temporary, 'acceptance.wl');
  const nbExportFile = path.join(temporary, 'roundtrip.nb');
  const nbMenuExportFile = path.join(temporary, 'menu-export.nb');
  const nbFixtureFile = path.join(temporary, 'rowbox-acceptance.nb');
  await fs.writeFile(nbFixtureFile, '(* Independent acceptance fixture. *)\nNotebook[{Cell["RowBox acceptance", "Title"],Cell[BoxData[RowBox[{"nbSentinel","=","91"}]],"Input",InitializationCell->True],Cell[BoxData[RowBox[{"1","+","1"}]],"Input"]}]\n');
  report.fixtures = { temporary, userData, notebookFile, exportFile, nbExportFile, nbMenuExportFile, nbFixtureFile };
  const rendererPort=await availableLoopbackPort();
  let inspectorPort=await availableLoopbackPort();
  while(inspectorPort===rendererPort) inspectorPort=await availableLoopbackPort();
  report.inspectorPorts={renderer:rendererPort,main:inspectorPort};
  child = spawn(executable, [`--remote-debugging-address=127.0.0.1`,`--remote-debugging-port=${rendererPort}`, `--inspect=127.0.0.1:${inspectorPort}`], {
    cwd: temporary, env: { ...process.env, MATHEMATICS_USER_DATA: userData }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  report.applicationPid = child.pid;
  const exitPromise = new Promise(resolve => child.once('exit', (code, signal) => { exited = { code, signal }; resolve(exited); }));
  child.stderr.setEncoding('utf8'); child.stdout.setEncoding('utf8');
  child.stderr.on('data', value => { report.mainStderr += value; });
  child.stdout.on('data', value => { report.mainStdout = (report.mainStdout || '') + value; });
  child.on('error', error => { report.spawnError = error.message; });

  const rendererTarget = await waitFor('renderer endpoint', async () => {
    const targets = await (await fetch(`http://127.0.0.1:${rendererPort}/json/list`)).json();
    return targets.find(target => target.type === 'page' && target.url.includes('renderer/index.html'));
  });
  const mainTarget = await waitFor('main inspector endpoint', async () => (await (await fetch(`http://127.0.0.1:${inspectorPort}/json/list`)).json())[0]);
  renderer = await Connection.open(rendererTarget.webSocketDebuggerUrl);
  mainInspector = await Connection.open(mainTarget.webSocketDebuggerUrl);
  renderer.on('Runtime.exceptionThrown', event => report.rendererErrors.push({ kind: 'exception', details: event.exceptionDetails }));
  renderer.on('Runtime.consoleAPICalled', event => {
    const details = { kind: 'console', level: event.type, text: event.args.map(arg => arg.value ?? arg.description ?? '').join(' ') };
    if (event.type === 'error') report.rendererErrors.push(details);
    else if (event.type === 'warning') report.rendererWarnings.push(details);
  });
  renderer.on('Log.entryAdded', event => {
    if (event.entry.level === 'error') report.rendererErrors.push({ kind: 'log', ...event.entry });
    else if (event.entry.level === 'warning') report.rendererWarnings.push({ kind: 'log', ...event.entry });
  });
  await renderer.send('Runtime.enable'); await renderer.send('Log.enable'); await renderer.send('Page.enable');
  await mainInspector.send('Runtime.enable');
  report.inspectedApplicationPid=await mainInspector.evaluate('process.pid');
  assert.equal(report.inspectedApplicationPid, child.pid, 'Inspector is not attached to the test application process.');
  await mainInspector.evaluate(`globalThis.__acceptanceElectron = process.mainModule.require('electron'); true`);
  const preferences = await mainInspector.evaluate(`(() => {const p=__acceptanceElectron.BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences();return {sandbox:p.sandbox,nodeIntegration:p.nodeIntegration,contextIsolation:p.contextIsolation};})()`);
  assert.deepEqual(preferences, { sandbox: true, nodeIntegration: false, contextIsolation: true });
  report.rendererPreferences = preferences;
  report.csp = await renderer.evaluate(`document.querySelector('meta[http-equiv="Content-Security-Policy"]').content`);
  assert.ok(report.csp.includes("script-src 'self'"));
  await waitFor('bundled Mathics readiness', () => renderer.evaluate(`document.querySelector('#engine-label').textContent.includes('已就绪')`));
  record('packaged-startup-and-renderer-isolation');

  await renderer.evaluate(`document.querySelector('#run-all-button').click(); true`);
  await waitFor('five example computations', () => renderer.evaluate(`document.querySelectorAll('.input-cell .cell-result').length===5 && !document.querySelector('#run-all-button').disabled`));
  report.initialOutputs = await renderer.evaluate(inputSnapshot);
  assert.equal(report.initialOutputs.length, 5);
  assert.equal(report.initialOutputs.some(result => result.error), false);
  assert.ok(report.initialOutputs[0].tex.includes('x'));
  assert.ok(report.initialOutputs[1].tex.includes('2') && report.initialOutputs[1].tex.includes('3'));
  assert.ok(report.initialOutputs[2].tex.toLowerCase().includes('cos'));
  assert.ok(report.initialOutputs[3].tex.includes('pi'));
  assert.ok(report.initialOutputs[4].svg);
  record('run-all-five-real-outputs-and-sanitized-plot-svg', { outputs: report.initialOutputs });
  await renderer.evaluate(`document.querySelector('#notebook-scroll').scrollTop=0; true`);
  report.screenshot = await saveScreenshot('application-smoke-results.png');
  await renderer.evaluate(`document.querySelector('#notebook-scroll').scrollTop=document.querySelector('#notebook-scroll').scrollHeight; true`);
  await sleep(100);
  report.plotScreenshot = await saveScreenshot('application-smoke-plot.png');

  const extendedFactor = await editAndRun(0, 'Factor[x^4+1,Extension->Sqrt[2]]');
  assert.ok(extendedFactor.tex?.includes('\\sqrt{2}'), JSON.stringify(extendedFactor));
  assert.equal((extendedFactor.tex.match(/x\^\{?2\}?/g) || []).length, 2, JSON.stringify(extendedFactor));
  assert.equal((extendedFactor.tex.match(/\\sqrt\{2\}/g) || []).length, 2, JSON.stringify(extendedFactor));
  record('factor-over-sqrt-two-extension-produces-two-quadratic-factors', { output: extendedFactor });

  const assigned = await editAndRun(0, 'a = 7');
  const squared = await editAndRun(1, 'a^2');
  assert.equal(assigned.tex, '7'); assert.equal(squared.tex, '49');
  record('stateful-variable-assign-and-square', { assigned, squared });

  await mainInspector.evaluate(`globalThis.__acceptanceOpenPath=${JSON.stringify(notebookFile)};
    globalThis.__acceptanceNBExportPath=${JSON.stringify(nbExportFile)};
    __acceptanceElectron.dialog.showSaveDialog=async (_window,options)=>({canceled:false,filePath:options.filters[0].extensions.includes('wl')?${JSON.stringify(exportFile)}:options.filters[0].extensions.includes('nb')?__acceptanceNBExportPath:${JSON.stringify(notebookFile)}});
    __acceptanceElectron.dialog.showOpenDialog=async ()=>({canceled:false,filePaths:[__acceptanceOpenPath]}); true`);
  await renderer.evaluate(`document.querySelector('[data-action="save"]').click(); true`);
  await waitFor('native file IPC save', async () => {
    try { return (await fs.readFile(notebookFile, 'utf8')).includes('a = 7'); } catch { return false; }
  });
  await waitFor('save UI idle', () => renderer.evaluate(`document.querySelector('#save-indicator').textContent==='已保存'`));
  const saved = JSON.parse(await fs.readFile(notebookFile, 'utf8'));
  assert.equal(saved.cells.filter(cell => cell.type === 'input')[1].result.text, '49');
  record('save-via-real-renderer-preload-and-main-file-ipc', { documentId: saved.id, bytes: (await fs.stat(notebookFile)).size });

  await renderer.evaluate(`document.querySelector('[data-action="open"]').click(); true`);
  await waitFor('open UI and historical-output notice', () => renderer.evaluate(`!document.querySelector('#session-notice').hidden && document.querySelector('#session-notice-text').textContent.includes('历史结果') && document.querySelector('#toast').textContent.includes('已打开')`));
  const reopened = await editAndRun(1, 'a^2');
  assert.equal(reopened.tex.replace(/[{}\s]/g, ''), 'a^2', JSON.stringify(reopened));
  assert.equal(reopened.outputLabel, 'Out[1]=');
  record('reopen-same-id-resets-kernel-session', { documentId: saved.id, output: reopened });

  await renderer.evaluate(`document.querySelector('[data-action="export"]').click(); true`);
  const exported = await waitFor('WL file export', async () => { try { return await fs.readFile(exportFile, 'utf8'); } catch { return false; } });
  assert.ok(exported.includes('a = 7')); assert.ok(exported.includes('a^2'));
  record('export-wl-through-ui-file-ipc', { bytes: Buffer.byteLength(exported) });

  await renderer.evaluate(`document.querySelector('[data-action="export-nb"]').click(); true`);
  const nbExported = await waitFor('NB file export through button', async () => { try { return await fs.readFile(nbExportFile, 'utf8'); } catch { return false; } });
  assert.match(nbExported, /Notebook\[\{/);
  assert.ok(nbExported.includes('a = 7') && nbExported.includes('a^2'));
  assert.ok(nbExported.includes('InitializationCell -> False'));
  const nbImported = await openThroughUI(nbExportFile, 'roundtrip');
  assert.equal(nbImported.length, 5);
  assert.equal(nbImported[0].source, 'a = 7'); assert.equal(nbImported[1].source, 'a^2');
  assert.notEqual(nbImported[0].id, saved.cells.find(cell => cell.type === 'input').id);
  assert.ok(nbImported.every(cell => cell.inputLabel==='In[·]:=' && !cell.tex));
  assert.ok(await renderer.evaluate(`document.querySelector('#session-notice-text').textContent.includes('子集')`));
  await mainInspector.evaluate(`globalThis.__acceptanceNBExportPath=${JSON.stringify(nbMenuExportFile)};
    (()=>{const menu=__acceptanceElectron.Menu.getApplicationMenu().items.find(item=>item.label==='文件').submenu;
      const item=menu.items.find(item=>item.label==='导出 .nb…'); if(!item)throw new Error('NB export menu missing.'); item.click();})(); true`);
  const nbMenuExported = await waitFor('NB export through native menu action', async () => { try { return await fs.readFile(nbMenuExportFile, 'utf8'); } catch { return false; } });
  assert.ok(nbMenuExported.includes('a = 7') && nbMenuExported.includes('a^2'));
  record('export-nb-button-native-menu-and-reimport-through-file-ipc', { bytes: Buffer.byteLength(nbExported), menuBytes: Buffer.byteLength(nbMenuExported), inputs: nbImported });

  const rowboxInputs = await openThroughUI(nbFixtureFile, 'rowbox-acceptance');
  assert.deepEqual(rowboxInputs.map(cell=>cell.source), ['nbSentinel=91','1+1']);
  assert.ok(rowboxInputs.every(cell=>cell.inputLabel==='In[·]:=' && !cell.tex));
  assert.equal(await renderer.evaluate(`document.querySelectorAll('.input-cell .cell-result').length`), 0);
  assert.ok(await renderer.evaluate(`document.querySelector('#session-notice-text').textContent.includes('初始化')`));
  const uninitialized = await editAndRun(1, 'nbSentinel');
  assert.equal(uninitialized.outputLabel, 'Out[1]=');
  assert.ok(uninitialized.tex?.includes('nbSentinel') && !uninitialized.tex.includes('91'), JSON.stringify(uninitialized));
  const rowboxComputed = await editAndRun(1, '1+1');
  assert.equal(rowboxComputed.tex, '2');
  assert.equal((await renderer.evaluate(inputSnapshot))[0].inputLabel, 'In[·]:=');
  record('import-rowbox-subset-without-initialization-and-manual-evaluation', { imported: rowboxInputs, uninitialized, computed: rowboxComputed });

  const plot3d = await editAndRun(0, 'Plot3D[Sin[x] Cos[y],{x,-2,2},{y,-2,2},PlotPoints->12,MaxRecursion->0]');
  assert.equal(plot3d.graphics3d, true, JSON.stringify(plot3d));
  await renderer.evaluate(`document.querySelectorAll('.input-cell')[0].querySelector('.graphics3d-canvas').scrollIntoView({block:'center'}); true`);
  const beforeRotate = await waitFor('3D canvas pixels', () => canvasSnapshot(0));
  assert.ok(beforeRotate.coloredPixels>1000, JSON.stringify(beforeRotate));
  assert.match(beforeRotate.label, /[1-9]\d* 个面/);
  const point = await renderer.evaluate(`(() => {const rect=document.querySelectorAll('.input-cell')[0].querySelector('.graphics3d-canvas').getBoundingClientRect();return {x:rect.x+rect.width/2,y:rect.y+rect.height/2};})()`);
  await renderer.send('Input.dispatchMouseEvent', { type:'mousePressed', button:'left', buttons:1, clickCount:1, ...point });
  await renderer.send('Input.dispatchMouseEvent', { type:'mouseMoved', buttons:1, x:point.x+72, y:point.y+28 });
  await renderer.send('Input.dispatchMouseEvent', { type:'mouseReleased', button:'left', buttons:0, clickCount:1, x:point.x+72, y:point.y+28 });
  const afterRotate = await waitFor('3D rotation changes pixels', async () => {const snapshot=await canvasSnapshot(0);return snapshot?.pixelHash!==beforeRotate.pixelHash && snapshot?.yaw!==beforeRotate.yaw && snapshot;});
  await renderer.send('Input.dispatchMouseEvent', { type:'mouseWheel', deltaX:0, deltaY:-180, ...point });
  const afterZoom = await waitFor('3D zoom changes pixels', async () => {const snapshot=await canvasSnapshot(0);return snapshot?.pixelHash!==afterRotate.pixelHash && snapshot?.zoom!==afterRotate.zoom && snapshot;});
  report.graphics3dScreenshot = await saveScreenshot('application-smoke-graphics3d.png');
  record('plot3d-real-canvas-rendering-pointer-rotation-and-wheel-zoom', { source: plot3d.source, beforeRotate, afterRotate, afterZoom });

  const manipulation = await editAndRun(0, 'Manipulate[a^2,{a,0,5}]');
  assert.equal(manipulation.tex, '0'); assert.equal(manipulation.controls.length, 1);
  assert.equal(manipulation.controls[0].value, '0');
  const manipulated = await changeInteractiveParameter(0, 3);
  assert.equal(manipulated.tex, '9');
  record('manipulate-slider-zero-to-three-recomputes-nine', { initial: manipulation, updated: manipulated });

  const combined = await editAndRun(0, 'Manipulate[Plot3D[Sin[a x] Cos[y],{x,-2,2},{y,-2,2},PlotPoints->12,MaxRecursion->0],{a,1,3}]');
  assert.equal(combined.graphics3d, true); assert.equal(combined.controls.length, 1);
  await renderer.evaluate(`document.querySelectorAll('.input-cell')[0].querySelector('.graphics3d-canvas').scrollIntoView({block:'center'}); true`);
  const combinedBefore = await waitFor('initial Manipulate Plot3D canvas', () => canvasSnapshot(0));
  const combinedUpdated = await changeInteractiveParameter(0, 2);
  assert.equal(combinedUpdated.graphics3d, true);
  const combinedAfter = await waitFor('Manipulate Plot3D changes canvas pixels', async () => {const snapshot=await canvasSnapshot(0);return snapshot?.pixelHash!==combinedBefore.pixelHash && snapshot;});
  assert.ok(combinedAfter.coloredPixels>1000);
  assert.equal(combinedAfter.yaw, combinedBefore.yaw); assert.equal(combinedAfter.zoom, combinedBefore.zoom);
  report.interactiveScreenshot = await saveScreenshot('application-smoke-manipulate-plot3d.png');
  record('manipulate-and-plot3d-combined-parameter-recomputation', { initial: combined, updated: combinedUpdated, before: combinedBefore, after: combinedAfter });

  await renderer.evaluate(`document.querySelector('[data-action="compatibility"]').click(); true`);
  await waitFor('feature compatibility dialog', () => renderer.evaluate(`document.querySelector('.compatibility-dialog')?.open`));
  const allCases = await renderer.evaluate(`document.querySelectorAll('.compatibility-dialog tbody tr').length`);
  assert.ok(allCases>0);
  const gaps = await renderer.evaluate(`(() => {const dialog=document.querySelector('.compatibility-dialog'),select=dialog.querySelector('.compatibility-search select');select.value='gap';select.dispatchEvent(new Event('change',{bubbles:true}));return {rows:dialog.querySelectorAll('tbody tr').length,passes:dialog.querySelectorAll('tbody .compatibility-pass').length,gaps:dialog.querySelectorAll('tbody .compatibility-gap').length,id:dialog.querySelector('tbody small')?.textContent};})()`);
  assert.ok(gaps.rows>0); assert.equal(gaps.passes, 0); assert.equal(gaps.gaps, gaps.rows);
  const searchedGap = await renderer.evaluate(`(() => {const dialog=document.querySelector('.compatibility-dialog'),search=dialog.querySelector('.compatibility-search input');search.value=${JSON.stringify(gaps.id)};search.dispatchEvent(new Event('input',{bubbles:true}));return {rows:dialog.querySelectorAll('tbody tr').length,text:dialog.querySelector('tbody')?.textContent,note:dialog.querySelector('.compatibility-note')?.textContent};})()`);
  assert.equal(searchedGap.rows, 1); assert.ok(searchedGap.text.includes(gaps.id)); assert.ok(searchedGap.note.includes('不代表 Mathematica 全部功能'));
  report.compatibilityScreenshot = await saveScreenshot('application-smoke-compatibility-gaps.png');
  await renderer.evaluate(`document.querySelector('.compatibility-dialog header button').click(); true`);
  assert.equal(await renderer.evaluate(`document.querySelector('.compatibility-dialog').open`), false);
  record('feature-coverage-dialog-gap-filter-and-search', { allCases, gaps, searchedGap });

  // .nb import creates a fresh document ID. Save this latest document before
  // testing close-time draft flushing, rather than expecting the first .mnb ID.
  await renderer.evaluate(`document.querySelector('[data-action="save"]').click(); true`);
  await waitFor('latest imported notebook save', async () => {
    try {const value=JSON.parse(await fs.readFile(notebookFile,'utf8'));return value.cells.some(cell=>cell.source===combined.source) && value;} catch {return false;}
  });
  await waitFor('latest save UI idle', () => renderer.evaluate(`document.querySelector('#save-indicator').textContent==='已保存'`));
  const latestSaved = JSON.parse(await fs.readFile(notebookFile, 'utf8'));
  assert.notEqual(latestSaved.id, saved.id);
  report.latestDocumentId = latestSaved.id;

  assert.equal(report.rendererErrors.length, 0, JSON.stringify(report.rendererErrors));
  assert.equal(/Renderer:/.test(report.mainStderr), false, report.mainStderr);
  record('no-renderer-exceptions-console-errors-or-csp-errors', { warnings: report.rendererWarnings });

  const marker = `immediate-close-marker-${crypto.randomUUID()}`;
  const editedAt = Date.now();
  await renderer.evaluate(`(() => {const input=document.querySelector('.input-cell textarea');input.value=${JSON.stringify('(* ' + marker + ' *) a^2')};input.dispatchEvent(new Event('input',{bubbles:true}));return true;})()`);
  await mainInspector.evaluate(`__acceptanceElectron.BrowserWindow.getAllWindows()[0].close(); true`);
  report.closeRequestedWithinMs = Date.now() - editedAt;
  assert.ok(report.closeRequestedWithinMs < 450, `Close was delayed ${report.closeRequestedWithinMs} ms, so debounce exclusion was not tested.`);
  mainInspector.close(); mainInspector = null;
  let exitTimer;
  await Promise.race([exitPromise, new Promise((_, reject) => {
    exitTimer = setTimeout(() => reject(new Error('Application did not exit gracefully after close.')), 20000);
  })]).finally(() => clearTimeout(exitTimer));
  assert.equal(exited.code, 0, JSON.stringify(exited));
  const finalDraft = JSON.parse(await fs.readFile(path.join(userData, 'draft.mnb'), 'utf8'));
  assert.ok(finalDraft.cells.some(cell => cell.source.includes(marker)));
  assert.equal(finalDraft.id, latestSaved.id);
  const residues = (await fs.readdir(userData)).filter(name => name.includes('.tmp-'));
  assert.deepEqual(residues, []);
  record('immediate-close-flushes-latest-draft-and-exits', { marker, closeRequestedWithinMs: report.closeRequestedWithinMs, exit: exited, temporaryResidues: residues });
  report.bundleBytes = await sizeOfTree(bundle);
  report.sha256 = {};
  for (const relative of ['main.cjs', 'kernel-client.cjs', 'disk-storage.cjs', 'notebook-nb.cjs', 'backend/kernel.py', 'renderer/app.js', 'renderer/graphics3d.js', 'renderer/dynamic-coordinator.js', 'renderer/compatibility.js']) report.sha256[relative] = crypto.createHash('sha256').update(await fs.readFile(path.join(root, relative))).digest('hex');
  report.sha256['Contents/Resources/app.asar'] = crypto.createHash('sha256').update(await fs.readFile(path.join(bundle, 'Contents/Resources/app.asar'))).digest('hex');
  report.passed = true;
}

(async () => {
  try { await run(); }
  catch (error) { report.passed = false; report.failure = { message: error.message, stack: error.stack }; process.exitCode = 1; console.error(error.stack); }
  finally {
    renderer?.close(); mainInspector?.close();
    if (child && !exited) { child.kill('SIGTERM'); await sleep(500); if (!exited) child.kill('SIGKILL'); }
    report.finishedAt = new Date().toISOString();
    report.gpuDiagnostics = report.mainStderr.split('\n').filter(line => /GPU|EGL|GL Driver|OpenGL|gl_surface|viz_main/i.test(line));
    await fs.mkdir(path.dirname(reportPath), { recursive: true });
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify({ passed: report.passed, reportPath, screenshot: report.screenshot }));
  }
})();
