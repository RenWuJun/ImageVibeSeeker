import os
import sys
import subprocess
import venv
import platform
import json
from pathlib import Path

# --- CONFIGURATION ---
MINIMAL_REQS = [
    "streamlit",
    "pandas",
    "psycopg2-binary",
    "numpy",
    "Pillow",
    "click",
    "tqdm",
    "send2trash",
    "PyYAML",
    "psutil",
    "filelock",
    "sqlite-vec"
]

HEAVY_REQS = [
    "torch",
    "open_clip_torch",
    "timm",
    "transformers",
    "huggingface-hub",
    "sentencepiece"
]

def run_command(command, cwd=None, capture_output=False):
    """Executes a shell command."""
    if capture_output:
        result = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)
        return result.stdout.strip()
    return subprocess.run(command, shell=True, cwd=cwd)

def get_gpu_brand():
    """Detects the GPU brand (nvidia, amd, intel, apple)."""
    system = platform.system()
    try:
        if system == "Windows":
            output = run_command("wmic path win32_VideoController get name,AdapterCompatibility", capture_output=True).lower()
            if "nvidia" in output: return "nvidia"
            if "amd" in output or "radeon" in output: return "amd"
            if "intel" in output: return "intel"
        elif system == "Linux":
            output = run_command("lspci | grep -i 'vga\\|display'", capture_output=True).lower()
            if "nvidia" in output: return "nvidia"
            if "amd" in output: return "amd"
        elif system == "Darwin":
            return "apple"
    except Exception:
        pass
    return "unknown"

def ensure_portable_python(base_path):
    """Ensures a isolated Python 3.10 exists locally."""
    system = platform.system()
    python_local = base_path / "python_local"
    if system == "Windows":
        python_exe = python_local / "python.exe"
    else:
        python_exe = python_local / "bin" / "python3"

    if python_exe.exists():
        return str(python_exe)

    # Simplified download/install logic for this rewrite
    print(f"--- Installing Isolated Python 3.10 for {system}... ---")
    if system == "Windows":
        installer = base_path / "python_installer.exe"
        url = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
        run_command(f'powershell -Command "Invoke-WebRequest -Uri {url} -OutFile {installer}"')
        run_command(f'"{installer}" /quiet InstallAllUsers=0 TargetDir="{python_local}" Include_test=0 Include_doc=0 PrependPath=0')
        if installer.exists(): os.remove(installer)
    else:
        # Standard Unix download
        url = f"https://github.com/indygreg/python-build-standalone/releases/download/20230507/cpython-3.10.11+20230507-{platform.machine()}-apple-darwin-install_only.tar.gz" if system == "Darwin" else "https://github.com/indygreg/python-build-standalone/releases/download/20230507/cpython-3.10.11+20230507-x86_64-unknown-linux-gnu-install_only.tar.gz"
        archive = base_path / "python_bundle.tar.gz"
        run_command(f'curl -L {url} -o "{archive}"')
        os.makedirs(python_local, exist_ok=True)
        run_command(f'tar -xzf "{archive}" -C "{python_local}" --strip-components=1')
        if archive.exists(): os.remove(archive)

    return str(python_exe)

def get_pip_args(pip_exe):
    """Detects environment and returns pip install base command with mirrors if needed."""
    is_china = False
    try:
        # Check system locale AND timezone (UTC+8 is -28800 seconds)
        import locale
        import time
        loc = locale.getdefaultlocale()[0]
        is_zh_locale = loc and "zh" in loc.lower()
        is_china_tz = time.timezone == -28800 or time.altzone == -28800
        
        if is_zh_locale and is_china_tz:
            is_china = True
    except: pass

    if os.environ.get("IVS_CHINA_MIRROR") == "1":
        is_china = True

    base_cmd = [f'"{pip_exe}"', "install"]
    if is_china:
        print("🇨🇳 检测到中国大陆网络环境，正在使用清华大学镜像源加速下载...")
        base_cmd += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
    return base_cmd
def setup():
    base_path = Path(__file__).parent.absolute()
    venv_path = base_path / "venv"
    system = platform.system()

    # 1. Ensure Python & Venv
    base_python = ensure_portable_python(base_path)
    if not venv_path.exists():
        run_command(f'"{base_python}" -m venv "{venv_path}"')

    if system == "Windows":
        python_exe = venv_path / "Scripts" / "python.exe"
        pip_exe = venv_path / "Scripts" / "pip.exe"
    else:
        python_exe = venv_path / "bin" / "python"
        pip_exe = venv_path / "bin" / "pip"

    # 2. Check Flags
    install_engine = "--install-engine" in sys.argv
    pip_base = get_pip_args(pip_exe)

    # 3. Minimal Install (Always run)
    print("--- Verifying UI dependencies... ---")
    run_command(f'{" ".join(pip_base)} {" ".join(MINIMAL_REQS)}')

    # 4. Heavy Install (Engine)
    if install_engine:
        print("--- Installing Hardware Engine (AI Libraries)... ---")
        gpu_brand = get_gpu_brand()

        # Load config to check device preference
        from config_loader import config
        requested_device = config.clip.get('device', 'cpu')

        if system == "Windows" and (gpu_brand == "amd" or requested_device == "dml"):
            print("--- Installing DirectML Backend... ---")
            run_command(f'{" ".join(pip_base)} torch-directml torchvision torchaudio')
        elif system == "Linux" and (gpu_brand == "amd" or requested_device == "rocm"):
            print("--- Installing ROCm Backend... ---")
            run_command(f'{" ".join(pip_base)} torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/rocm6.0')
        else:
            print("--- Installing Standard Torch Backend... ---")
            run_command(f'{" ".join(pip_base)} torch torchvision torchaudio')

        # Install remaining heavy AI libs
        run_command(f'{" ".join(pip_base)} {" ".join(HEAVY_REQS[1:])}')

        print("✅ Hardware Engine installed successfully.")
        if not "--no-launch" in sys.argv:
            print("Restarting app...")
            return

    # 5. Launch
    if "--no-launch" in sys.argv:
        print("--- Installation Complete. Exiting as requested. ---")
        return

    print("--- Launching WebUI... ---")
    run_command(f'"{python_exe}" -m streamlit run streamlit_app.py --server.address=127.0.0.1', cwd=base_path)

if __name__ == "__main__":
    setup()