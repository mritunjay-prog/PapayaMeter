import subprocess
import threading
import time
import os
import configparser
import logging

# Setup basic logging to match the project's style
class SshService:
    """
    Service to maintain a reverse SSH tunnel to a remote EC2 instance.
    This allows remote access to the device even if it's behind a NAT/firewall.
    """
    
    def __init__(self, config_path):
        self.config_path = config_path
        self._stop_event = threading.Event()
        self._thread = None
        self._process = None

    def _log(self, message, error=False):
        prefix = "[SSH_SERVICE] 🛡️" if not error else "[SSH_ERROR] ⚠️"
        print(f"{prefix} {message}")

    def start(self):
        """Start the SSH tunnel management thread."""
        if self._thread and self._thread.is_alive():
            self._log("SSH Service is already running.")
            return
            
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._log("SSH Service thread started.")

    def stop(self):
        """Stop the SSH tunnel and management thread."""
        self._stop_event.set()
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except:
                if self._process:
                    self._process.kill()
        self._log("SSH Service stopped.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                config = configparser.ConfigParser()
                config.read(self.config_path)
                
                if not config.has_section('ssh'):
                    self._log("No [ssh] section in config. Waiting...", error=True)
                    time.sleep(30)
                    continue
                    
                enabled = config.getboolean('ssh', 'enabled', fallback=False)
                if not enabled:
                    time.sleep(60)
                    continue
                    
                host = config.get('ssh', 'host')
                user = config.get('ssh', 'user')
                key_path = config.get('ssh', 'key_path')
                remote_port = config.get('ssh', 'remote_port', fallback='2222')
                
                key_path = os.path.expanduser(key_path)
                
                if not os.path.exists(key_path):
                    self._log(f"SSH Key not found: {key_path}", error=True)
                    time.sleep(60)
                    continue

                cmd = [
                    'ssh', 
                    '-N', 
                    '-o', 'ServerAliveInterval=30', 
                    '-o', 'ServerAliveCountMax=3',
                    '-o', 'ExitOnForwardFailure=yes',
                    '-o', 'StrictHostKeyChecking=no',
                    '-R', f'{remote_port}:localhost:22',
                    f'{user}@{host}',
                    '-i', key_path
                ]
                
                self._log(f"Initiating reverse SSH tunnel to {user}@{host}:{remote_port}...")
                self._process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # Monitor stderr in real-time
                def monitor_stderr(pipe):
                    for line in iter(pipe.readline, ''):
                        if line:
                            self._log(line.strip(), error=True)
                
                threading.Thread(target=monitor_stderr, args=(self._process.stderr,), daemon=True).start()

                # Wait for process to end
                while self._process.poll() is None and not self._stop_event.is_set():
                    time.sleep(1)
                
                if self._process.poll() is not None:
                    self._log(f"SSH Tunnel exited with code {self._process.returncode}", error=True)
                
            except Exception as e:
                self._log(f"Unexpected error in SSH Service: {e}", error=True)
                
            if not self._stop_event.is_set():
                time.sleep(15)
