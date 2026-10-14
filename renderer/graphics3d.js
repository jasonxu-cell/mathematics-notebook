/* Local Canvas geometry viewer. It renders geometry returned by the open-source kernel. */
(() => {
  'use strict';
  const finitePoint = (value) => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);
  function normalizeGeometry(raw) {
    if (!raw || typeof raw !== 'object') throw new Error('三维几何数据无效。');
    const sourceVertices = Array.isArray(raw.vertices) ? raw.vertices : [];
    const sourceFaces = Array.isArray(raw.faces) ? raw.faces : [];
    const sourceLines = Array.isArray(raw.lines) ? raw.lines : [];
    const sourcePoints = Array.isArray(raw.points) ? raw.points : [];
    if (sourceVertices.length > 50000 || sourceFaces.length > 30000 || sourceLines.length > 10000 || sourcePoints.length > 10000) throw new Error('三维几何超过本地查看器的显示上限。');
    const vertices = sourceVertices.map((point) => finitePoint(point) ? point.slice() : null);
    const faces = [], faceColors = [];
    sourceFaces.forEach((face, index) => {
      if (Array.isArray(face) && face.length >= 3 && face.length <= 32 && face.every((i) => Number.isInteger(i) && i >= 0 && i < vertices.length && vertices[i])) {
        faces.push(face.slice()); faceColors.push(raw.colors?.faces?.[index]);
      }
    });
    let linePointCount = 0;
    const lines = [], lineColors = [];
    sourceLines.forEach((line, index) => {
      if (!Array.isArray(line)) return;
      linePointCount += line.length;
      if (linePointCount > 50000) throw new Error('三维折线超过显示上限。');
      if (line.length >= 2 && line.every(finitePoint)) { lines.push(line.map((point) => point.slice())); lineColors.push(raw.colors?.lines?.[index]); }
    });
    const points = [], pointColors = [];
    sourcePoints.forEach((point, index) => { if (finitePoint(point)) { points.push(point.slice()); pointColors.push(raw.colors?.points?.[index]); } });
    const bounds = [[Infinity, -Infinity], [Infinity, -Infinity], [Infinity, -Infinity]];
    const include = (point) => point.forEach((value, i) => { bounds[i][0] = Math.min(bounds[i][0], value); bounds[i][1] = Math.max(bounds[i][1], value); });
    vertices.filter(Boolean).forEach(include); lines.forEach((line) => line.forEach(include)); points.forEach(include);
    if (!bounds.every((pair) => pair.every(Number.isFinite)) || (!faces.length && !lines.length && !points.length)) throw new Error('当前结果没有可显示的三维面、线或点。');
    if (Array.isArray(raw.bounds) && raw.bounds.length === 3 && raw.bounds.every((pair) => Array.isArray(pair) && pair.length === 2 && pair.every(Number.isFinite) && pair[1] > pair[0])) {
      raw.bounds.forEach((pair, i) => { bounds[i][0] = Math.min(bounds[i][0], pair[0]); bounds[i][1] = Math.max(bounds[i][1], pair[1]); });
    }
    bounds.forEach((pair) => { if (pair[0] === pair[1]) { pair[0] -= .5; pair[1] += .5; } });
    return { vertices, faces, lines, points, bounds, colors: { faces: faceColors, lines: lineColors, points: pointColors } };
  }
  function mount(host, raw, savedState = {}) {
    const data = normalizeGeometry(raw);
    const canvas = document.createElement('canvas'); canvas.className = 'graphics3d-canvas'; canvas.tabIndex = 0;
    canvas.setAttribute('aria-label', `三维图形：${data.faces.length} 个面，${data.lines.length} 条线，${data.points.length} 个点。拖动旋转，滚轮缩放，方向键旋转。`);
    canvas.setAttribute('role', 'img');
    const footer = document.createElement('div'); footer.className = 'graphics3d-footer';
    const hint = document.createElement('span'); hint.textContent = '拖动旋转 · 滚轮缩放';
    const reset = document.createElement('button'); reset.type = 'button'; reset.textContent = '重置视角';
    footer.append(hint, reset); host.append(canvas, footer);
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Canvas 三维显示不可用。');
    const controller = new AbortController(), options = { signal: controller.signal };
    let yaw = Number.isFinite(savedState.yaw) ? savedState.yaw : -.65;
    let pitch = Number.isFinite(savedState.pitch) ? savedState.pitch : .68;
    let zoom = Number.isFinite(savedState.zoom) ? savedState.zoom : 1;
    let width = 520, height = 320, frame = null, drag = null;
    const center = data.bounds.map(([min, max]) => (min + max) / 2);
    const unit = Math.max(...data.bounds.map(([min, max]) => max - min)) / 2 || 1;
    const normalize = (point) => point.map((value, i) => (value - center[i]) / unit);
    function project(point) {
      const [x, y, z] = normalize(point), sy = Math.sin(yaw), cy = Math.cos(yaw), sp = Math.sin(pitch), cp = Math.cos(pitch);
      const horizontal = x * cy - y * sy, rotatedY = x * sy + y * cy;
      const depth = rotatedY * cp + z * sp, perspective = 4.8 / (4.8 - depth);
      const scale = Math.min(width * .29, height * .36) * zoom;
      return [width / 2 + horizontal * scale * perspective, height / 2 + (rotatedY * sp - z * cp) * scale * perspective, depth];
    }
    const rgb = (color, fallback, light = 1) => {
      const value = finitePoint(color) ? color.map((part) => Math.min(1, Math.max(0, part)) * 255) : fallback;
      return `rgb(${value.map((part) => Math.round(Math.min(255, Math.max(0, part * light)))).join(',')})`;
    };
    function path(points) {
      context.beginPath(); points.forEach((point, i) => { const p = project(point); if (!i) context.moveTo(p[0], p[1]); else context.lineTo(p[0], p[1]); });
    }
    function draw() {
      frame = null; context.clearRect(0, 0, width, height);
      canvas.dataset.viewYaw = yaw.toFixed(4); canvas.dataset.viewPitch = pitch.toFixed(4); canvas.dataset.viewZoom = zoom.toFixed(4);
      context.fillStyle = '#fcfdf9'; context.fillRect(0, 0, width, height);
      const [bx, by, bz] = data.bounds, floor = bz[0];
      context.lineWidth = 1; context.strokeStyle = '#dce4d640';
      for (let i = 0; i <= 6; i++) {
        const x = bx[0] + (bx[1] - bx[0]) * i / 6, y = by[0] + (by[1] - by[0]) * i / 6;
        path([[x, by[0], floor], [x, by[1], floor]]); context.stroke();
        path([[bx[0], y, floor], [bx[1], y, floor]]); context.stroke();
      }
      const primitives = [];
      data.faces.forEach((face, i) => {
        const vertices = face.map((index) => data.vertices[index]);
        const a = vertices[0], b = vertices[1], c = vertices[2];
        const ab = b.map((v, axis) => v - a[axis]), ac = c.map((v, axis) => v - a[axis]);
        const normal = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]];
        const length = Math.hypot(...normal) || 1;
        const light = .7 + .27 * Math.abs((normal[0] * .3 + normal[1] * .4 + normal[2] * .85) / length);
        const averageZ = vertices.reduce((sum, p) => sum + p[2], 0) / vertices.length;
        const t = (averageZ - bz[0]) / (bz[1] - bz[0]);
        const base = [104 + 129 * t, 157 - 4 * t, 163 - 61 * t];
        primitives.push({ depth: vertices.reduce((sum, p) => sum + project(p)[2], 0) / vertices.length, draw: () => { path(vertices); context.closePath(); context.fillStyle = rgb(data.colors.faces[i], base, light); context.fill(); context.strokeStyle = '#334f541a'; context.lineWidth = .45; context.stroke(); } });
      });
      data.lines.forEach((line, i) => primitives.push({ depth: line.reduce((sum, p) => sum + project(p)[2], 0) / line.length, draw: () => { path(line); context.strokeStyle = rgb(data.colors.lines[i], [70, 109, 132]); context.lineWidth = 1.8; context.stroke(); } }));
      data.points.forEach((point, i) => primitives.push({ depth: project(point)[2], draw: () => { const p = project(point); context.beginPath(); context.arc(p[0], p[1], 3.1, 0, Math.PI * 2); context.fillStyle = rgb(data.colors.points[i], [217, 123, 72]); context.fill(); } }));
      primitives.sort((a, b) => a.depth - b.depth).forEach((primitive) => primitive.draw());
      context.strokeStyle = '#a6b59c'; context.fillStyle = '#829575'; context.font = '10px -apple-system, sans-serif'; context.lineWidth = 1;
      const origin = [bx[0], by[0], bz[0]];
      [[bx[1], by[0], bz[0]], [bx[0], by[1], bz[0]], [bx[0], by[0], bz[1]]].forEach((endpoint, i) => { path([origin, endpoint]); context.stroke(); const p = project(endpoint); context.fillText(['x', 'y', 'z'][i], p[0] + 7, p[1] - 4); });
      context.fillStyle = '#a0ac96'; context.font = '9px -apple-system, sans-serif'; context.fillText(`${data.faces.length} 面 · ${data.lines.length} 线 · ${data.points.length} 点`, 12, height - 12);
    }
    function redraw() { if (frame === null) frame = requestAnimationFrame(draw); }
    function resize() {
      width = Math.max(230, host.clientWidth || 520); height = Math.max(235, Math.min(360, width * .65));
      const ratio = Math.min(2, globalThis.devicePixelRatio || 1);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); canvas.style.height = `${height}px`;
      context.setTransform(ratio, 0, 0, ratio, 0, 0); redraw();
    }
    const restore = () => { yaw = -.65; pitch = .68; zoom = 1; redraw(); };
    canvas.addEventListener('pointerdown', (event) => { if (event.button !== 0) return; drag = [event.clientX, event.clientY]; try { canvas.setPointerCapture(event.pointerId); } catch {} canvas.classList.add('dragging'); }, options);
    canvas.addEventListener('pointermove', (event) => { if (!drag) return; yaw += (event.clientX - drag[0]) * .008; pitch = Math.max(-1.4, Math.min(1.4, pitch + (event.clientY - drag[1]) * .006)); drag = [event.clientX, event.clientY]; redraw(); }, options);
    const endDrag = () => { drag = null; canvas.classList.remove('dragging'); };
    canvas.addEventListener('pointerup', endDrag, options); canvas.addEventListener('pointercancel', endDrag, options); canvas.addEventListener('lostpointercapture', endDrag, options);
    canvas.addEventListener('wheel', (event) => { event.preventDefault(); zoom = Math.max(.45, Math.min(3, zoom * Math.exp(-event.deltaY * .0015))); redraw(); }, { ...options, passive: false });
    canvas.addEventListener('dblclick', restore, options); reset.addEventListener('click', restore, options);
    canvas.addEventListener('keydown', (event) => { if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '-', '='].includes(event.key)) return; event.preventDefault(); if (event.key === 'ArrowLeft') yaw -= .1; else if (event.key === 'ArrowRight') yaw += .1; else if (event.key === 'ArrowUp') pitch = Math.min(1.4, pitch + .1); else if (event.key === 'ArrowDown') pitch = Math.max(-1.4, pitch - .1); else zoom = Math.max(.45, Math.min(3, zoom * (event.key === '-' ? .9 : 1.1))); redraw(); }, options);
    const observer = new ResizeObserver(resize); observer.observe(host); resize();
    return { getState: () => ({ yaw, pitch, zoom }), dispose: () => { observer.disconnect(); controller.abort(); if (frame !== null) cancelAnimationFrame(frame); } };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { normalizeGeometry };
  else globalThis.NotebookGraphics3D = { mount, normalizeGeometry };
})();
