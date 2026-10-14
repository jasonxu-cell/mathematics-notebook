const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('notebook', {
  kernel: {
    evaluate: args => ipcRenderer.invoke('kernel:evaluate', args),
    reset: args => ipcRenderer.invoke('kernel:reset', args),
    cancel: () => ipcRenderer.invoke('kernel:cancel'),
    status: () => ipcRenderer.invoke('kernel:status'),
  },
  files: {
    open: () => ipcRenderer.invoke('files:open'),
    save: args => ipcRenderer.invoke('files:save', args),
    exportWL: args => ipcRenderer.invoke('files:export-wl', args),
    exportNB: args => ipcRenderer.invoke('files:export-nb', args),
  },
  storage: {
    loadDraft: () => ipcRenderer.invoke('storage:load'),
    saveDraft: document => ipcRenderer.invoke('storage:save', document),
  },
  onMenuAction: callback => {
    const listener = (_, action) => callback(action);
    ipcRenderer.on('menu-action', listener);
    return () => ipcRenderer.removeListener('menu-action', listener);
  },
  onCloseRequested: callback => {
    const listener = () => callback();
    ipcRenderer.on('close-request', listener);
    return () => ipcRenderer.removeListener('close-request', listener);
  },
  completeClose: args => ipcRenderer.send('window:complete-close', args),
});
