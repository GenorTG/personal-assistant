const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // Service management
  listServices: () => ipcRenderer.invoke('service:list'),
  getServiceStatus: (serviceName) => ipcRenderer.invoke('service:status', serviceName),
  startService: (serviceName, devMode) => ipcRenderer.invoke('service:start', serviceName, devMode),
  stopService: (serviceName) => ipcRenderer.invoke('service:stop', serviceName),
  restartService: (serviceName, devMode) => ipcRenderer.invoke('service:restart', serviceName, devMode),
  getServiceLogs: (serviceName, lines) => ipcRenderer.invoke('service:logs', serviceName, lines),
});
