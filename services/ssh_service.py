import subprocess
import threading
import time
import os

# Hardcoded SSH tunnel settings (from config.properties [ssh])
SSH_ENABLED = True
SSH_HOST = "34.232.20.123"
SSH_USER = "ubuntu"
SSH_KEY_PATH = os.path.expanduser("/home/mritunjay/.ssh/id_rsa_thingsboard")
SSH_REMOTE_PORT = "2222"


class SshService:
    """
    Service to maintain a reverse SSH tunnel to a remote EC2 instance.
    This allows remote access to the device even if it's behind a NAT/firewall.
    """
    
    def __init__(self, config_path=None):
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
                if not SSH_ENABLED:
                    time.sleep(60)
                    continue

                if not os.path.exists(SSH_KEY_PATH):
                    self._log(f"SSH Key not found: {SSH_KEY_PATH}", error=True)
                    time.sleep(60)
                    continue

                cmd = [
                    'ssh',
                    '-N',
                    '-o', 'ServerAliveInterval=30',
                    '-o', 'ServerAliveCountMax=3',
                    '-o', 'ExitOnForwardFailure=yes',
                    '-o', 'StrictHostKeyChecking=no',
                    '-R', f'{SSH_REMOTE_PORT}:localhost:22',
                    f'{SSH_USER}@{SSH_HOST}',
                    '-i', SSH_KEY_PATH
                ]

                self._log(f"Initiating reverse SSH tunnel to {SSH_USER}@{SSH_HOST}:{SSH_REMOTE_PORT}...")
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


def main():
    """Run SSH service as a standalone process."""
    service = SshService()
    service.start()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        service.stop()


if __name__ == "__main__":
    main()
