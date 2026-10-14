const { app, BrowserWindow, ipcMain, dialog, Menu } = require('electron');
const fs = require('node:fs/promises');
const { existsSync } = require('node:fs');
const path = require('node:path');
const { KernelClient } = require('./kernel-client.cjs');
const { validateDocument, fromWolframLanguage, MAX_SOURCE } = require('./notebook-model.cjs');
const { fromNotebook, toNotebook } = require('./notebook-nb.cjs');
const { atomicWrite, serializeDocument, drainWrites, MAX_DOCUMENT_BYTES } = require('./disk-storage.cjs');

if (process.env.MATHEMATICS_USER_DATA) app.setPath('userData', process.env.MATHEMATICS_USER_DATA);
let window;
let kernel;
let allowClose = false;
let closeRequested = false;
const grantedFiles = new Set();

function kernelOptions() {
  if (app.isPackaged) {
    const command = path.join(process.resourcesPath, 'mathematics-kernel', 'mathematics-kernel');
    if (!existsSync(command)) throw new Error('应用缺少计算内核，请重新构建应用。');
    return { command, cwd: app.getPath('userData') };
  }
  const command = process.env.MATHEMATICS_PYTHON || path.join(__dirname, '.venv', 'bin', 'python');
  return { command, args: [path.join(__dirname, 'backend', 'kernel.py')], cwd: __dirname };
}

function validateSender(event) {
  if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) {
    throw new Error('请求来自未知窗口。');
  }
}

function handle(channel, fn) {
  ipcMain.handle(channel, (event, args) => { validateSender(event); return fn(args); });
}

function safeTitle(title) { return String(title || '未命名笔记本').replace(/[\/:*?"<>|]/g, '-').slice(0, 120); }

function installHandlers() {
  ipcMain.on('window:complete-close', (event, args) => {
    validateSender(event);
    if (args?.cancelled) { closeRequested = false; return { closed: false }; }
    drainWrites().then(() => { allowClose = true; window.close(); });
  });
  handle('kernel:status', () => kernel.status());
  handle('kernel:evaluate', args => {
    if (typeof args?.source !== 'string' || args.source.length > MAX_SOURCE || typeof args.notebookId !== 'string') {
      throw new Error('无效的求值请求。');
    }
    let controls;
    if (args.controls !== undefined) {
      if (!args.controls || typeof args.controls !== 'object' || Array.isArray(args.controls)) throw new Error('无效的动态参数。');
      const entries = Object.entries(args.controls);
      if (entries.length > 16 || entries.some(([name, value]) => !name || name.length > 128 || typeof value !== 'number' || !Number.isFinite(value))) throw new Error('动态参数必须是有限数值。');
      controls = Object.fromEntries(entries);
    }
    return kernel.request('evaluate', { source: args.source, notebook_id: args.notebookId.slice(0, 100), ...(controls ? { controls } : {}) });
  });
  handle('kernel:reset', async args => {
    if (typeof args?.notebookId !== 'string') throw new Error('缺少笔记本 ID。');
    if (kernel.state === 'busy') await kernel.cancel();
    return kernel.request('reset', { notebook_id: args.notebookId.slice(0, 100) });
  });
  handle('kernel:cancel', () => kernel.cancel());
  handle('files:open', async () => {
    const choice = await dialog.showOpenDialog(window, {
      title: '打开笔记本或 Wolfram Language 源文件', properties: ['openFile'],
      filters: [{ name: '笔记本与源文件', extensions: ['mnb', 'nb', 'wl', 'm'] }],
    });
    if (choice.canceled) return { canceled: true };
    const file = choice.filePaths[0];
    const stat = await fs.stat(file);
    if (stat.size > MAX_DOCUMENT_BYTES) throw new Error('文件过大（最多 8 MB）。');
    const source = await fs.readFile(file, 'utf8');
    const extension = path.extname(file).toLowerCase();
    const isSource = ['.wl', '.m'].includes(extension);
    if (extension === '.nb') {
      const imported = fromNotebook(source, path.basename(file, extension));
      serializeDocument(imported.document, true);
      return { canceled: false, document: imported.document, path: null, warnings: imported.warnings };
    }
    const document = isSource ? fromWolframLanguage(source, path.basename(file)) : validateDocument(JSON.parse(source));
    serializeDocument(document, true);
    if (!isSource) grantedFiles.add(file);
    return { canceled: false, document, path: isSource ? null : file };
  });
  handle('files:save', async args => {
    const document = validateDocument(args?.document);
    const data = serializeDocument(document, true);
    let destination = args?.path;
    if (!destination || args.saveAs || !grantedFiles.has(destination)) {
      const choice = await dialog.showSaveDialog(window, {
        title: '保存笔记本', defaultPath: `${safeTitle(document.title)}.mnb`,
        filters: [{ name: 'Mathematics Notebook', extensions: ['mnb'] }],
      });
      if (choice.canceled) return { canceled: true };
      destination = choice.filePath;
      if (!path.extname(destination)) destination += '.mnb';
      grantedFiles.add(destination);
    }
    await atomicWrite(destination, data);
    return { canceled: false, path: destination };
  });
  handle('files:export-wl', async args => {
    if (typeof args?.source !== 'string' || args.source.length > 8 * 1024 * 1024) throw new Error('无效的导出内容。');
    const choice = await dialog.showSaveDialog(window, {
      title: '导出 Wolfram Language 源文件', defaultPath: `${safeTitle(args.title)}.wl`,
      filters: [{ name: 'Wolfram Language', extensions: ['wl'] }],
    });
    if (choice.canceled) return { canceled: true };
    let destination = choice.filePath;
    if (!path.extname(destination)) destination += '.wl';
    await atomicWrite(destination, args.source);
    return { canceled: false, path: destination };
  });
  handle('files:export-nb', async args => {
    const document = validateDocument(args?.document);
    const data = toNotebook(document);
    if (Buffer.byteLength(data, 'utf8') > MAX_DOCUMENT_BYTES) throw new Error('导出的笔记本过大（最多 8 MB）。');
    const choice = await dialog.showSaveDialog(window, {
      title: '导出 Mathematica Notebook（基础兼容）', defaultPath: `${safeTitle(document.title)}.nb`,
      filters: [{ name: 'Wolfram Notebook', extensions: ['nb'] }],
    });
    if (choice.canceled) return { canceled: true };
    let destination = choice.filePath;
    if (!path.extname(destination)) destination += '.nb';
    await atomicWrite(destination, data);
    return { canceled: false, path: destination };
  });
  handle('storage:load', async () => {
    try { return validateDocument(JSON.parse(await fs.readFile(path.join(app.getPath('userData'), 'draft.mnb'), 'utf8'))); }
    catch (error) { if (error.code !== 'ENOENT') console.error('Draft load:', error.message); return null; }
  });
  handle('storage:save', async value => {
    const document = validateDocument(value);
    await atomicWrite(path.join(app.getPath('userData'), 'draft.mnb'), serializeDocument(document));
    return { saved: true };
  });
}

function send(action) { if (window && !window.isDestroyed()) window.webContents.send('menu-action', action); }

function installMenu() {
  const action = (label, name, accelerator) => ({ label, accelerator, click: () => send(name) });
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'Mathematics Notebook', submenu: [{ role: 'about' }, { type: 'separator' }, { role: 'hide' }, { role: 'hideOthers' }, { role: 'unhide' }, { type: 'separator' }, { role: 'quit' }] },
    { label: '文件', submenu: [action('新建笔记本', 'new', 'CmdOrCtrl+N'), action('打开…', 'open', 'CmdOrCtrl+O'), action('保存', 'save', 'CmdOrCtrl+S'), action('另存为…', 'save-as', 'CmdOrCtrl+Shift+S'), action('导出 .wl…', 'export'), action('导出 .nb…', 'export-nb')] },
    { label: '编辑', submenu: [{ role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }] },
    { label: '计算', submenu: [action('运行全部', 'run-all', 'CmdOrCtrl+Shift+Enter'), action('停止计算', 'cancel', 'CmdOrCtrl+.'), action('重置内核', 'reset'), { type: 'separator' }, action('添加输入单元格', 'add-input')] },
    { label: '窗口', submenu: [{ role: 'minimize' }, { role: 'zoom' }, { role: 'togglefullscreen' }] },
  ]));
}

function createWindow() {
  allowClose = false;
  closeRequested = false;
  window = new BrowserWindow({
    width: 1320, height: 900, minWidth: 950, minHeight: 640,
    title: 'Mathematics Notebook', backgroundColor: '#f4f3ef',
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', event => event.preventDefault());
  window.webContents.on('console-message', (_event, details) => {
    if (details.level === 'error') console.error('Renderer:', details.message);
  });
  window.on('close', event => {
    if (allowClose) return;
    if (window.webContents.isLoadingMainFrame()) { allowClose = true; return; }
    event.preventDefault();
    if (!closeRequested) { closeRequested = true; window.webContents.send('close-request'); }
  });
  window.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

app.whenReady().then(async () => {
  await fs.mkdir(app.getPath('userData'), { recursive: true });
  kernel = new KernelClient(kernelOptions());
  installHandlers();
  installMenu();
  createWindow();
  kernel.start().catch(error => console.error(error.message));
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
}).catch(error => { dialog.showErrorBox('启动失败', error.message); app.quit(); });

app.on('before-quit', event => {
  if (window && !window.isDestroyed() && !allowClose) {
    event.preventDefault();
    window.close();
    return;
  }
  kernel?.dispose();
});
app.on('window-all-closed', () => app.quit());
