import sys
import os
import pty
import select
import termios
import time

HOST = "192.168.2.6"
USER = "paimon"
PASSWORD = "44pLGNfU"

def run_ssh_command(cmd_to_run):
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=5",
        f"{USER}@{HOST}",
        cmd_to_run
    ]
    
    pid, fd = pty.fork()
    if pid == 0:
        # Child process
        os.execvp("ssh", ssh_cmd)
    else:
        # Parent process
        output = b""
        password_sent = False
        while True:
            try:
                r, _, _ = select.select([fd], [], [], 1.0)
                if fd in r:
                    chunk = os.read(fd, 1024)
                    if not chunk:
                        break
                    output += chunk
                    # Check for password prompt
                    if b"assword:" in chunk and not password_sent:
                        time.sleep(0.1)
                        os.write(fd, (PASSWORD + "\n").encode())
                        password_sent = True
                    # Check for fingerprint prompt
                    elif b"yes/no" in chunk:
                        time.sleep(0.1)
                        os.write(fd, b"yes\n")
            except OSError:
                break
        _, status = os.waitpid(pid, 0)
        return status, output.decode('utf-8', errors='replace')

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "uname -a; cat /etc/os-release"
    print(f"Running on Pi ({USER}@{HOST}): {cmd}")
    status, out = run_ssh_command(cmd)
    print(out)
