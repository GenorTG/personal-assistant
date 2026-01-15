const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// Get project root (assume electron-app is in project root)
const PROJECT_ROOT = path.resolve(__dirname, '..');

const SERVICES = {
  gateway: {
    name: 'Gateway',
    port: 8000,
    directory: path.join(PROJECT_ROOT, 'services', 'gateway'),
    venv: path.join(PROJECT_ROOT, 'services', '.core_venv'),
    description: 'Main API Gateway (includes LLM, Memory, Tools, STT, TTS)',
  },
  frontend: {
    name: 'Frontend',
    port: 8002,
    directory: path.join(PROJECT_ROOT, 'services', 'frontend'),
    venv: null,
    description: 'Next.js web interface',
  },
  chatterbox: {
    name: 'Chatterbox TTS',
    port: 8004,
    directory: path.join(PROJECT_ROOT, 'services', 'tts-chatterbox'),
    venv: path.join(PROJECT_ROOT, 'services', 'tts-chatterbox', 'venv'),
    description: 'Optional TTS service (Python 3.11)',
  },
};

class ServiceManager {
  constructor() {
    this.processes = new Map();
    this.logs = new Map();
    
    // Initialize logs
    Object.keys(SERVICES).forEach(serviceName => {
      this.logs.set(serviceName, []);
    });
  }

  getServiceStatus(serviceName) {
    if (!SERVICES[serviceName]) {
      return { status: 'unknown', error: 'Service not found' };
    }

    const process = this.processes.get(serviceName);
    const config = SERVICES[serviceName];

    if (process && !process.killed) {
      // Check if process is still alive
      try {
        process.kill(0); // Signal 0 doesn't kill, just checks if process exists
        return {
          status: 'running',
          pid: process.pid,
          port: config.port,
        };
      } catch (e) {
        // Process died
        this.processes.delete(serviceName);
        return { status: 'stopped', port: config.port };
      }
    }

    // Check if port is in use (might be started externally)
    return { status: 'stopped', port: config.port };
  }

  async startService(serviceName, devMode = false) {
    if (!SERVICES[serviceName]) {
      throw new Error(`Unknown service: ${serviceName}`);
    }

    // Check if already running
    const status = this.getServiceStatus(serviceName);
    if (status.status === 'running') {
      return true;
    }

    const config = SERVICES[serviceName];
    let command;
    let args = [];

    if (serviceName === 'gateway') {
      const pythonPath = config.venv 
        ? path.join(config.venv, 'bin', 'python')
        : 'python3';
      
      command = pythonPath;
      args = [
        '-m', 'uvicorn',
        'src.main:app',
        '--host', '0.0.0.0',
        '--port', config.port.toString(),
        '--no-access-log',
      ];
    } else if (serviceName === 'frontend') {
      // Use shell for npm commands on Linux
      command = process.platform === 'win32' ? 'npm.cmd' : 'npm';
      // Always use dev mode for auto-start
      args = ['run', 'dev'];
    } else if (serviceName === 'chatterbox') {
      const pythonPath = config.venv
        ? path.join(config.venv, 'bin', 'python')
        : 'python3.11';
      
      command = pythonPath;
      args = [
        '-m', 'uvicorn',
        'main:app',
        '--host', '0.0.0.0',
        '--port', config.port.toString(),
      ];
    } else {
      throw new Error(`Unknown service: ${serviceName}`);
    }

    // Check if command exists
    if (!fs.existsSync(config.directory)) {
      throw new Error(`Service directory does not exist: ${config.directory}`);
    }
    
    // For Python services, check if venv exists
    if (serviceName === 'gateway' || serviceName === 'chatterbox') {
      if (config.venv && !fs.existsSync(config.venv)) {
        throw new Error(`Virtual environment not found: ${config.venv}`);
      }
    }
    
    // Spawn process - use shell for npm commands on Linux
    const useShell = serviceName === 'frontend' && process.platform !== 'win32';
    const spawnOptions = {
      cwd: config.directory,
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: useShell,
      env: { ...process.env, PATH: process.env.PATH },
      detached: false, // Keep attached so we can track it
    };
    
    const childProcess = spawn(command, args, spawnOptions);
    
    // For frontend on Linux/Mac, create a new process group after spawn
    // This allows us to kill the entire process tree (npm + node children)
    if (serviceName === 'frontend' && process.platform !== 'win32' && childProcess.pid) {
      try {
        // Create new process group using setsid (only works if not already a group leader)
        // Since we're spawning with shell, the shell will be the group leader
        // We'll handle killing the process tree in stopService
      } catch (e) {
        // Ignore - process group creation is best-effort
      }
    }
    
    // Handle spawn errors
    childProcess.on('error', (error) => {
      console.error(`Failed to spawn ${serviceName}:`, error);
      const logs = this.logs.get(serviceName) || [];
      logs.push(`ERROR: Failed to start - ${error.message}`);
      if (logs.length > 1000) logs.shift();
      this.logs.set(serviceName, logs);
      this.processes.delete(serviceName);
    });

    // Capture logs
    childProcess.stdout.on('data', (data) => {
      const logEntry = data.toString();
      const logs = this.logs.get(serviceName) || [];
      logs.push(logEntry);
      if (logs.length > 1000) logs.shift();
      this.logs.set(serviceName, logs);
    });

    childProcess.stderr.on('data', (data) => {
      const logEntry = data.toString();
      const logs = this.logs.get(serviceName) || [];
      logs.push(logEntry);
      if (logs.length > 1000) logs.shift();
      this.logs.set(serviceName, logs);
    });

    childProcess.on('exit', (code) => {
      this.processes.delete(serviceName);
      const logs = this.logs.get(serviceName) || [];
      logs.push(`Process exited with code ${code}`);
      if (logs.length > 1000) logs.shift();
      this.logs.set(serviceName, logs);
    });

    this.processes.set(serviceName, childProcess);
    
    // Wait a moment to see if process crashes immediately
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Check if process is still alive
    if (childProcess.killed || childProcess.exitCode !== null) {
      const logs = this.logs.get(serviceName) || [];
      logs.push(`ERROR: Process exited immediately with code ${childProcess.exitCode}`);
      if (logs.length > 1000) logs.shift();
      this.logs.set(serviceName, logs);
      this.processes.delete(serviceName);
      throw new Error(`Process exited immediately with code ${childProcess.exitCode}`);
    }
    
    return true;
  }

  async stopService(serviceName) {
    const proc = this.processes.get(serviceName);
    if (!proc || proc.killed) {
      // Already stopped or doesn't exist
      this.processes.delete(serviceName);
      return true;
    }

    return new Promise((resolve) => {
      let forceKilled = false;
      
      // Handle process exit
      const onExit = () => {
        if (!forceKilled) {
          this.processes.delete(serviceName);
          console.log(`✓ ${serviceName} stopped gracefully`);
        }
        resolve(true);
      };
      
      // If process already exited, resolve immediately
      if (proc.exitCode !== null) {
        onExit();
        return;
      }
      
      // Set up exit handler
      proc.once('exit', onExit);
      
      // Try graceful shutdown first
      try {
        // For frontend (npm), we need to kill the process tree
        if (serviceName === 'frontend') {
          // On Linux/Mac, try to kill child processes (npm spawns node processes)
          if (process.platform !== 'win32') {
            try {
              // First try to kill the main process
              proc.kill('SIGTERM');
              
              // Also try to kill any child node processes spawned by npm
              // Use pkill to find and kill node processes running next dev
              const { exec } = require('child_process');
              exec(`pkill -f "next dev" || true`, () => {
                // Ignore errors - pkill may not find processes
              });
            } catch (e) {
              // Fallback to regular kill
              proc.kill('SIGTERM');
            }
          } else {
            // Windows - just kill the main process
            proc.kill('SIGTERM');
          }
        } else {
          // For Python services, send SIGTERM
          proc.kill('SIGTERM');
        }
      } catch (error) {
        console.error(`Error sending SIGTERM to ${serviceName}:`, error);
        // Try force kill
        try {
          proc.kill('SIGKILL');
          forceKilled = true;
        } catch (e) {
          // Process might already be dead
        }
        onExit();
        return;
      }
      
      // Force kill after 5 seconds if still running
      const forceKillTimeout = setTimeout(() => {
        if (proc && !proc.killed && proc.exitCode === null) {
          try {
            forceKilled = true;
            if (serviceName === 'frontend' && process.platform !== 'win32') {
              // Kill process group
              try {
                process.kill(-proc.pid, 'SIGKILL');
              } catch (e) {
                proc.kill('SIGKILL');
              }
            } else {
              proc.kill('SIGKILL');
            }
            console.log(`⚠ Force killed ${serviceName} after timeout`);
            this.processes.delete(serviceName);
            resolve(true);
          } catch (error) {
            // Process might already be dead
            this.processes.delete(serviceName);
            resolve(true);
          }
        }
      }, 5000);
      
      // Clear timeout if process exits before force kill
      proc.once('exit', () => {
        clearTimeout(forceKillTimeout);
      });
    });
  }

  getServiceLogs(serviceName, lines = 100) {
    const logs = this.logs.get(serviceName) || [];
    return logs.slice(-lines);
  }

  listServices() {
    return Object.keys(SERVICES);
  }

  async checkPort(port) {
    return new Promise((resolve) => {
      const net = require('net');
      const server = net.createServer();
      
      server.listen(port, () => {
        server.once('close', () => resolve(false));
        server.close();
      });
      
      server.on('error', () => resolve(true));
    });
  }
}

// Export singleton instance
const manager = new ServiceManager();
module.exports = manager;
