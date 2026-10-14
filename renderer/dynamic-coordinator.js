/* Serial, latest-value scheduling for local numeric notebook controls. */
(() => {
  'use strict';
  class DynamicCoordinator {
    constructor({ run, canRun, valid, onStart, onResult, onError, onFinish, delay = 160 }) {
      Object.assign(this, { run, canRun, valid, onStart, onResult, onError, onFinish, delay });
      this.pending = new Map(); this.revisions = new Map(); this.running = null; this.timer = null;
    }
    request(job) {
      const revision = (this.revisions.get(job.key) || 0) + 1;
      this.revisions.set(job.key, revision);
      this.pending.delete(job.key);
      this.pending.set(job.key, { ...job, controls: { ...job.controls }, revision });
      this.schedule(this.delay);
      return revision;
    }
    current(job) { return this.revisions.get(job.key) === job.revision && this.valid(job); }
    schedule(delay = 0) {
      clearTimeout(this.timer);
      this.timer = setTimeout(() => { this.timer = null; this.flush(); }, delay);
    }
    async flush() {
      if (this.running || !this.canRun() || !this.pending.size) return;
      const [key, job] = this.pending.entries().next().value;
      this.pending.delete(key);
      if (!this.current(job)) { if (this.pending.size) this.schedule(); return; }
      this.running = job;
      try {
        this.onStart(job);
        const result = await this.run(job);
        if (this.current(job)) this.onResult(job, result);
      } catch (error) { this.onError(job, error, this.current(job)); }
      finally {
        this.running = null;
        this.onFinish(job);
        if (this.pending.size) this.schedule();
      }
    }
    clear(key) {
      const keys = key ? [key] : new Set([...this.pending.keys(), ...(this.running ? [this.running.key] : [])]);
      for (const entry of keys) { this.revisions.set(entry, (this.revisions.get(entry) || 0) + 1); this.pending.delete(entry); }
      if (!this.pending.size) { clearTimeout(this.timer); this.timer = null; }
    }
    dispose() { this.clear(); clearTimeout(this.timer); }
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { DynamicCoordinator };
  else globalThis.NotebookDynamic = { DynamicCoordinator };
})();
