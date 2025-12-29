import subprocess
import os
import sys
import psutil
import time
from pathlib import Path

LOCK_FILE = "process.lock"
LOG_FILE = os.path.join("logs", "task_output.log")

def is_process_running(pid):
    """Checks if a process with the given PID is running."""
    try:
        proc = psutil.Process(pid)
        return proc.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False

def start_task(command_list):
    """Starts a task, writing output to a log file and PID to a lock file."""
    if get_current_task_status():
        return False, "A task is already running."

    # Prepare log file
    os.makedirs("logs", exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"--- Starting Task: {' '.join(command_list)} ---\n")

    # Launch process
    # We use python executable from sys.executable
    full_cmd = [sys.executable] + command_list
    
    with open(LOG_FILE, "a", encoding="utf-8") as f_out:
        process = subprocess.Popen(
            full_cmd,
            stdout=f_out,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )

    # Write Lock File
    with open(LOCK_FILE, "w") as f:
        f.write(str(process.pid))
    
    return True, f"Started with PID {process.pid}"

def get_current_task_status():
    """Returns (PID, True/False is_running). Returns None if no task."""
    if not os.path.exists(LOCK_FILE):
        return None

    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        
        if is_process_running(pid):
            return pid, True
        else:
            # Process finished/died
            # Clean up lock file? Maybe wait for user to acknowledge?
            # For now, let's say if it's dead, we return it as 'not running'
            # but keep the lock file so we know something WAS running.
            return pid, False
    except Exception:
        return None

def clear_task():
    """Clears the lock file to allow new tasks."""
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

def read_log_tail(n=20):
    """Reads the last n lines of the log file."""
    if not os.path.exists(LOG_FILE):
        return "Waiting for logs..."
    
    # Simple tail implementation
    # For large logs, this is inefficient, but for this use case ( < 10MB), it's fine.
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return "".join(lines[-n:])
    except Exception as e:
        return f"Error reading log: {e}"
