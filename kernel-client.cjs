const { spawn } = require('node:child_process');

class KernelClient {
  // Evaluations get 5 minutes of wall-clock time before the kernel is reset.
  constructor({ command, args = [], cwd, env = {}, timeoutMs = 5 * 60 * 1000, startupMs = 60000 }) {
    this.options = { command, args, cwd, env, timeoutMs, startupMs };
    this.child = null;
    this.state = 'idle';
    this.version = null;
    this.pending = new Map();
    this.sequence = 0;
    this.generation = 0;
    this.log = '';
  }

  start() {
    if (this.child) return this.readyPromise;
    const generation = ++this.generation;
    this.state = 'starting';
    this.log = '';
    this.readyPromise = new Promise((resolve, reject) => {
      this.resolveReady = resolve;
      this.rejectReady = reject;
    });
    let child;
    try {
      child = spawn(this.options.command, this.options.args, {
        cwd: this.options.cwd,
        env: { ...process.env, PYTHONUNBUFFERED: '1', MPLBACKEND: 'Agg', ...this.options.env },
        stdio: ['pipe', 'pipe', 'pipe'],
      });
    } catch (error) {
      this._stop(error);
      return this.readyPromise;
    }
    this.child = child;
    let buffer = '';
    this.startTimer = setTimeout(() => this._stop(new Error('计算内核启动超时，请重启应用。')), this.options.startupMs);
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', data => { this.log = (this.log + data).slice(-6000); });
    child.stdout.on('data', chunk => {
      if (generation !== this.generation) return;
      buffer += chunk;
      if (buffer.length > 32 * 1024 * 1024) {
        this._stop(new Error('计算结果过大，内核已重置，会话变量已清空。'));
        return;
      }
      let newline;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        if (!line.trim()) continue;
        let message;
        try { message = JSON.parse(line); }
        catch { this._stop(new Error('计算内核返回了无效数据。')); return; }
        if (message.event === 'ready') {
          clearTimeout(this.startTimer);
          this.version = message.version || message.mathics_version || null;
          this.state = 'ready';
          this.resolveReady({ ready: true, status: this.state, version: this.version });
          this.resolveReady = this.rejectReady = null;
          continue;
        }
        const pending = this.pending.get(String(message.id));
        if (!pending) continue;
        clearTimeout(pending.timer);
        this.pending.delete(String(message.id));
        if (pending.op === 'evaluate') this.state = 'ready';
        if (message.ok) pending.resolve(message.result);
        else {
          const error = new Error(message.error?.message || '表达式求值失败。');
          error.code = message.error?.code || 'evaluation_error';
          pending.reject(error);
        }
      }
    });
    child.on('error', error => {
      if (generation === this.generation) this._stop(new Error(`无法启动计算内核：${error.message}`));
    });
    child.on('close', (code, signal) => {
      if (generation !== this.generation) return;
      const detail = this.log.trim().slice(-1200);
      this._stop(new Error(`计算内核已退出（${signal || code}）。会话变量已清空。${detail ? '\n' + detail : ''}`));
    });
    child.stdin.on('error', error => {
      if (generation === this.generation) this._stop(new Error(`计算内核通信失败：${error.message}`));
    });
    return this.readyPromise;
  }

  async request(op, fields = {}) {
    await this.start();
    if (op === 'evaluate' && this.state === 'busy') throw new Error('已有单元格正在求值。');
    const id = String(++this.sequence);
    if (op === 'evaluate') this.state = 'busy';
    return new Promise((resolve, reject) => {
      const timeout = op === 'evaluate' ? this.options.timeoutMs : 15000;
      const timer = setTimeout(() => {
        const seconds = Math.round(timeout / 1000);
        const limit = seconds >= 60 && seconds % 60 === 0 ? `${seconds / 60} 分钟` : `${seconds} 秒`;
        this._stop(new Error(`计算超时（${limit}）。内核已重置，会话变量已清空。`));
      }, timeout);
      this.pending.set(id, { resolve, reject, timer, op });
      this.child.stdin.write(JSON.stringify({ id, op, ...fields }) + '\n', error => {
        if (error) this._stop(new Error(`无法发送计算请求：${error.message}`));
      });
    });
  }

  async status() {
    await this.start();
    // Never queue a health request behind an evaluation: its shorter timeout
    // could otherwise terminate a valid computation before the watchdog.
    return { ready: true, status: this.state, version: this.version };
  }

  async cancel() {
    this._stop(new Error('计算已取消。内核已重置，会话变量已清空。'));
    return this.start();
  }

  _stop(error) {
    clearTimeout(this.startTimer);
    ++this.generation;
    const child = this.child;
    this.child = null;
    this.state = 'idle';
    if (this.rejectReady) this.rejectReady(error);
    this.resolveReady = this.rejectReady = null;
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
    if (child && child.exitCode === null) {
      child.kill('SIGTERM');
      const timer = setTimeout(() => { if (child.exitCode === null) child.kill('SIGKILL'); }, 1500);
      timer.unref();
    }
  }

  dispose() { this._stop(new Error('应用已关闭。')); }
}

module.exports = { KernelClient };
