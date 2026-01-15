const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const serviceManager = require('./service-manager');
let mainWindow;
let splashWindow = null;

// Window load state to prevent reload loops
let windowLoadState = {
  hasLoaded: false,
  currentUrl: null,
  loadAttempts: 0,
  maxLoadAttempts: 1, // Only try loading once to prevent loops
};

// Auto-start services on app launch
const AUTO_START_SERVICES = ['gateway', 'frontend'];

async function startServices() {
  console.log('Starting required services...');
  
  for (const serviceName of AUTO_START_SERVICES) {
    try {
      console.log(`Attempting to start ${serviceName}...`);
      await serviceManager.startService(serviceName);
      console.log(`✓ Started ${serviceName}`);
      
      // Wait a bit for service to initialize
      await new Promise(resolve => setTimeout(resolve, 3000));
      
      // Verify it's still running
      const status = serviceManager.getServiceStatus(serviceName);
      if (status.status === 'running') {
        console.log(`✓ ${serviceName} is running (PID: ${status.pid || 'unknown'})`);
      } else {
        console.warn(`⚠ ${serviceName} started but status is: ${status.status}`);
      }
    } catch (error) {
      console.error(`✗ Failed to start ${serviceName}:`, error.message);
      console.error('Full error:', error);
    }
  }
  
  // Wait for frontend to be ready
  console.log('Waiting for frontend to be ready...');
  let frontendReady = false;
  let attempts = 0;
  const maxAttempts = 90; // 90 seconds (Next.js can take time to start, especially first time)
  
  while (!frontendReady && attempts < maxAttempts) {
    try {
      const http = require('http');
      const checkUrl = 'http://localhost:8002';
      
      await new Promise((resolve, reject) => {
        const req = http.get(checkUrl, { timeout: 3000 }, (res) => {
          // Any response means the server is up
          frontendReady = true;
          resolve();
        });
        
        req.on('error', () => reject());
        req.setTimeout(3000, () => {
          req.destroy();
          reject();
        });
      });
      
      frontendReady = true;
    } catch (error) {
      attempts++;
      if (attempts % 5 === 0) {
        console.log(`Still waiting for frontend... (${attempts}/${maxAttempts})`);
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  
  if (frontendReady) {
    console.log('✓ Frontend is ready!');
  } else {
    console.warn('⚠ Frontend did not become ready in time (will show service manager)');
  }
}

function createSplashWindow() {
  if (splashWindow) return; // Already created
  
  splashWindow = new BrowserWindow({
    width: 400,
    height: 300,
    frame: false,
    transparent: false, // Changed to false for better compatibility
    alwaysOnTop: true,
    backgroundColor: '#667eea',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });
  
  splashWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {
          margin: 0;
          padding: 0;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          height: 100vh;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .spinner {
          border: 4px solid rgba(255,255,255,0.3);
          border-top: 4px solid white;
          border-radius: 50%;
          width: 50px;
          height: 50px;
          animation: spin 1s linear infinite;
          margin-bottom: 20px;
        }
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        h1 { margin: 0; font-size: 24px; }
        p { margin: 10px 0 0 0; opacity: 0.9; }
      </style>
    </head>
    <body>
      <div class="spinner"></div>
      <h1>Personal Assistant</h1>
      <p>Starting services...</p>
    </body>
    </html>
  `)}`);
  
  splashWindow.center();
}

function createWindow() {
  // Reset load state for new window
  windowLoadState = {
    hasLoaded: false,
    currentUrl: null,
    loadAttempts: 0,
    maxLoadAttempts: 1,
  };
  
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    title: 'Personal Assistant',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    autoHideMenuBar: true,
    frame: true,
    show: false,
  });

  // Try to load the Next.js frontend, fallback to service manager
  const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:8002';
  
  // Check if frontend is ready, with retries (only load once to prevent loops)
  const tryLoadFrontend = (attempts = 0) => {
    if (windowLoadState.hasLoaded) {
      console.log('Window already loaded, skipping to prevent reload loop');
      return;
    }
    
    const maxAttempts = 30; // 30 seconds max wait
    
    const http = require('http');
    const checkReq = http.get(frontendUrl, { timeout: 2000 }, (res) => {
      // Any response means server is up
      if (!windowLoadState.hasLoaded && windowLoadState.loadAttempts < windowLoadState.maxLoadAttempts) {
        windowLoadState.hasLoaded = true;
        windowLoadState.currentUrl = frontendUrl;
        windowLoadState.loadAttempts++;
        console.log(`✓ Frontend is ready (status: ${res.statusCode}), loading...`);
        mainWindow.loadURL(frontendUrl);
      }
    });
    
    checkReq.on('error', (error) => {
      // Frontend not ready yet
      if (attempts < maxAttempts) {
        if (attempts % 5 === 0) {
          console.log(`Waiting for frontend... (${attempts}/${maxAttempts})`);
        }
        setTimeout(() => tryLoadFrontend(attempts + 1), 1000);
      } else {
        // Frontend not available, show service manager
        if (!windowLoadState.hasLoaded) {
          windowLoadState.hasLoaded = true;
          windowLoadState.currentUrl = 'service-manager';
          console.log('Frontend not ready after 30s, showing service manager');
          mainWindow.loadFile(path.join(__dirname, 'service-manager.html'));
        }
      }
    });
    
    checkReq.setTimeout(2000, () => {
      checkReq.destroy();
      if (attempts < maxAttempts) {
        if (attempts % 5 === 0) {
          console.log(`Waiting for frontend... (${attempts}/${maxAttempts})`);
        }
        setTimeout(() => tryLoadFrontend(attempts + 1), 1000);
      } else {
        // Frontend timeout, show service manager
        if (!windowLoadState.hasLoaded) {
          windowLoadState.hasLoaded = true;
          windowLoadState.currentUrl = 'service-manager';
          console.log('Frontend timeout after 30s, showing service manager');
          mainWindow.loadFile(path.join(__dirname, 'service-manager.html'));
        }
      }
    });
  };
  
  // Start checking after a short delay (services may already be starting)
  setTimeout(() => tryLoadFrontend(), 2000);

  // Show window when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.focus();
    
    // Close splash if it exists
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
      splashWindow = null;
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Handle navigation errors - show service management page (only once to prevent loops)
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    console.log('Failed to load:', errorCode, errorDescription, validatedURL);
    // Show service manager for any load failure (only if we haven't already loaded it)
    if (validatedURL && validatedURL.startsWith('http://localhost:8002') && windowLoadState.currentUrl !== 'service-manager') {
      windowLoadState.currentUrl = 'service-manager';
      console.log('Loading service manager due to frontend load failure');
      mainWindow.loadFile(path.join(__dirname, 'service-manager.html'));
    }
  });
  
  // Prevent infinite reloads - log navigation but don't reload
  mainWindow.webContents.on('did-navigate', (event, url) => {
    console.log('Navigated to:', url);
    windowLoadState.currentUrl = url;
  });
  
  mainWindow.webContents.on('did-navigate-in-page', (event, url) => {
    console.log('In-page navigation to:', url);
  });
  
  // Prevent reload loops
  mainWindow.webContents.on('will-navigate', (event, url) => {
    // Prevent navigation if we're already at that URL or if it's a reload loop
    if (windowLoadState.currentUrl === url || windowLoadState.loadAttempts >= windowLoadState.maxLoadAttempts) {
      console.log('Preventing navigation loop to:', url);
      event.preventDefault();
    }
  });

  // Open DevTools in development
  if (process.env.NODE_ENV === 'development') {
    mainWindow.webContents.openDevTools();
  }
}

// App lifecycle
app.whenReady().then(async () => {
  // IPC handlers for service management (must be registered after app is ready)
  ipcMain.handle('service:list', () => {
    return serviceManager.listServices();
  });

  ipcMain.handle('service:status', (event, serviceName) => {
    return serviceManager.getServiceStatus(serviceName);
  });

  ipcMain.handle('service:start', async (event, serviceName, devMode) => {
    try {
      await serviceManager.startService(serviceName, devMode);
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('service:stop', async (event, serviceName) => {
    try {
      await serviceManager.stopService(serviceName);
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('service:logs', (event, serviceName, lines) => {
    return serviceManager.getServiceLogs(serviceName, lines);
  });

  ipcMain.handle('service:restart', async (event, serviceName, devMode) => {
    try {
      await serviceManager.stopService(serviceName);
      await new Promise(resolve => setTimeout(resolve, 1000));
      await serviceManager.startService(serviceName, devMode);
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });
  
  // Show splash screen
  createSplashWindow();
  
  // Show splash screen
  createSplashWindow();
  
  // Start services first, then create window
  startServices().then(() => {
    console.log('✓ Services started, creating main window...');
    // Small delay to ensure services are fully ready
    setTimeout(() => {
      createWindow();
    }, 2000);
  }).catch((error) => {
    console.error('Error starting services:', error);
    // Still create window so user can manually start services
    createWindow();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Track if we're shutting down
let isShuttingDown = false;

// Stop all services gracefully
async function stopAllServices() {
  if (isShuttingDown) return; // Already shutting down
  isShuttingDown = true;
  
  console.log('Stopping all services...');
  const services = serviceManager.listServices();
  
  // Stop all services in parallel
  const stopPromises = services.map(async (serviceName) => {
    try {
      console.log(`Stopping ${serviceName}...`);
      await serviceManager.stopService(serviceName);
      console.log(`✓ Stopped ${serviceName}`);
    } catch (error) {
      console.error(`Error stopping ${serviceName}:`, error);
    }
  });
  
  // Wait for all services to stop (with timeout)
  await Promise.race([
    Promise.all(stopPromises),
    new Promise(resolve => setTimeout(resolve, 10000)) // 10 second timeout
  ]);
  
  console.log('All services stopped');
}

// Handle app quit - ensure services are stopped
app.on('before-quit', async (event) => {
  if (!isShuttingDown) {
    event.preventDefault(); // Prevent immediate quit
    await stopAllServices();
    app.exit(0); // Now quit
  }
});

app.on('window-all-closed', async () => {
  // Stop all services when all windows close
  await stopAllServices();
  
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Handle force quit (Ctrl+C, etc.)
process.on('SIGINT', async () => {
  console.log('\nReceived SIGINT, shutting down...');
  await stopAllServices();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.log('\nReceived SIGTERM, shutting down...');
  await stopAllServices();
  process.exit(0);
});

// Security: Prevent new window creation
app.on('web-contents-created', (event, contents) => {
  contents.on('new-window', (event, navigationUrl) => {
    event.preventDefault();
    require('electron').shell.openExternal(navigationUrl);
  });
});
