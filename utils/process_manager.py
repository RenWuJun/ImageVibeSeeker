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

def start_task(command_list, env_vars=None):
    """
    Starts a task, writing output to a log file and PID to a lock file.
    Supports injecting custom environment variables (e.g. for database passwords).
    """
    if get_current_task_status():
        return False, "A task is already running."

    # Prepare log file
    os.makedirs("logs", exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"--- Starting Task: {' '.join(command_list)} ---\n")

    # Prepare Environment
    current_env = os.environ.copy()
    if env_vars:
        current_env.update(env_vars)

    # Launch process
    full_cmd = [sys.executable] + command_list
    
    with open(LOG_FILE, "a", encoding="utf-8") as f_out:
        process = subprocess.Popen(
            full_cmd,
            stdout=f_out,
            stderr=subprocess.STDOUT,
            env=current_env, # Inject environment variables here
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )

    # Write Lock File
    with open(LOCK_FILE, "w") as f:
        f.write(str(process.pid))
    
    return True, f"Started with PID {process.pid}"

def get_current_task_status():
    if not os.path.exists(LOCK_FILE):
        return None
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if is_process_running(pid):
            return pid, True
        else:
            return pid, False
    except Exception:
        return None

def clear_task():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

def read_log_tail(n=20):
    if not os.path.exists(LOG_FILE):
        return "Waiting for logs..."
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return "".join(lines[-n:])
    except Exception as e:
        return f"Error reading log: {e}"