import os
import sys
import subprocess
import venv
import platform
import json
from pathlib import Path

def run_command(command, cwd=None, capture_output=False):

    """Executes a shell command."""
    if capture_output:
        result = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)
        return result.stdout.strip()
    return subprocess.run(command, shell=True, cwd=cwd)

def get_gpu_brand():
    """Detects the GPU brand (nvidia, amd, intel, apple) with improved robustness."""
    system = platform.system()
    try:
        if system == "Windows":
            # Get multiple fields to increase chance of detection
            output = run_command("wmic path win32_VideoController get name,AdapterCompatibility", capture_output=True)
            output = output.lower()
            if "nvidia" in output: return "nvidia"
            if "amd" in output or "radeon" in output or "ati " in output: return "amd"
            if "intel" in output or "arc(tm)" in output: return "intel"
        elif system == "Linux":
            output = run_command("lspci | grep -i 'vga\\|display'", capture_output=True).lower()
            if "nvidia" in output: return "nvidia"
            if "amd" in output or "radeon" in output: return "amd"
            if "intel" in output: return "intel"
        elif system == "Darwin":
            return "apple"
    except Exception:
        pass
    return "unknown"

def configure_hardware(python_exe, base_path):
    """Detects best available hardware and updates config.json, respecting manual overrides."""
    print("--- Auto-Configuring Hardware ---")
    from config_loader import config
    
    current_device = config.clip.get('device', 'cpu')
    gpu_brand = get_gpu_brand()
    system = platform.system()

    print(f"🔍 Current config device: {current_device}")
    print(f"🔍 System: {system}, GPU Brand: {gpu_brand}")

    # 1. Detect Hardware via Torch in Venv
    detection_script = (
        "import torch; "
        "try: "
        "  if torch.cuda.is_available(): print('cuda'); "
        "  elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available(): print('mps'); "
        "  else: "
        "    try: "
        "      import torch_directml; "
        "      print('dml' if torch_directml.is_available() else 'cpu'); "
        "    except ImportError: print('cpu'); "
        "except Exception as e: print('cpu')"
    )
    
    cmd = f'"{python_exe}" -c "{detection_script}"'
    
    try:
        detected_device = run_command(cmd, cwd=base_path, capture_output=True)
        if not detected_device or detected_device not in ['cuda', 'mps', 'cpu', 'dml']:
            detected_device = 'cpu'
    except Exception:
        detected_device = 'cpu'

    print(f"✅ Hardware Detection result: {detected_device.upper()}")

    # 2. Update logic: Don't downgrade. Only upgrade from CPU or set if missing.
    try:
        should_update = False
        
        # If current is CPU but we found something better, upgrade.
        if current_device == 'cpu' and detected_device != 'cpu':
            print(f"🚀 Upgrading device from CPU to {detected_device.upper()}...")
            should_update = True
        
        # If the user manually set a high-performance device, keep it!
        elif current_device in ['dml', 'cuda', 'mps']:
            print(f"📌 Respecting manual device setting: {current_device.upper()}")
            # We don't update back to CPU even if detection failed (to allow forced overrides)
            return

        if should_update or current_device == 'cpu':
            config.update_section('clip', {'device': detected_device})
            config.save_config()
            print(f"✅ Updated config.json to use {detected_device}.")
    except Exception as e:
        print(f"❌ Failed to update config.json: {e}")

def ensure_portable_python(base_path):
    """Ensures a isolated, compatible Python 3.10 exists locally in all cases."""
    system = platform.system()
    machine = platform.machine().lower() # x86_64 or arm64
    
    python_local = base_path / "python_local"
    
    if system == "Windows":
        python_exe = python_local / "python.exe"
    else:
        python_exe = python_local / "bin" / "python3"
    
    # If already installed, we're done
    if python_exe.exists():
        return str(python_exe)
    
    print(f"--- Creating isolated Python environment for {system} ({machine})... ---")
    
    if system == "Windows":
        print("--- Downloading portable Python 3.10.11 for Windows... ---")
        installer = base_path / "python_installer.exe"
        url = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
        try:
            run_command(f'powershell -Command "Invoke-WebRequest -Uri {url} -OutFile {installer}"')
            print("--- Installing Python 3.10.11 locally... ---")
            install_cmd = f'"{installer}" /quiet InstallAllUsers=0 TargetDir="{python_local}" Include_test=0 Include_doc=0 PrependPath=0'
            run_command(install_cmd)
            if installer.exists(): os.remove(installer)
        except Exception as e:
            print(f"❌ Failed to install Windows Python: {e}")
            return sys.executable

    else:
        # Linux / macOS (Use indygreg/python-build-standalone for true portability)
        print(f"--- Downloading portable Python 3.10.11 for {system}... ---")
        
        # Determine correct binary
        if system == "Darwin":
            if "arm" in machine or "aarch64" in machine:
                url = "https://github.com/indygreg/python-build-standalone/releases/download/20230507/cpython-3.10.11+20230507-aarch64-apple-darwin-install_only.tar.gz"
            else:
                url = "https://github.com/indygreg/python-build-standalone/releases/download/20230507/cpython-3.10.11+20230507-x86_64-apple-darwin-install_only.tar.gz"
        else: # Linux
            url = "https://github.com/indygreg/python-build-standalone/releases/download/20230507/cpython-3.10.11+20230507-x86_64-unknown-linux-gnu-install_only.tar.gz"
            
        archive = base_path / "python_bundle.tar.gz"
        try:
            # Download using curl (available on most Unix systems)
            run_command(f'curl -L {url} -o "{archive}"')
            
            # Extract
            print("--- Extracting local Python... ---")
            os.makedirs(python_local, exist_ok=True)
            # Use standard tar command
            run_command(f'tar -xzf "{archive}" -C "{python_local}" --strip-components=1')
            
            if archive.exists(): os.remove(archive)
        except Exception as e:
            print(f"❌ Failed to install portable Python: {e}")
            return sys.executable

    if python_exe.exists():
        print(f"✅ Isolated Python 3.10.11 installed at {python_local}")
        return str(python_exe)
    
    print("⚠️  Fallback to system Python.")
    return sys.executable

def setup():
    base_path = Path(__file__).parent.absolute()
    venv_path = base_path / "venv"
    system = platform.system() # 'Windows', 'Darwin' (Mac), 'Linux'
    
    print(f"--- Detected System: {system} ---")

    # 0. Ensure compatible Python
    base_python = ensure_portable_python(base_path)

    # 1. Create VENV if missing or if base python changed
    recreate_venv = False
    if venv_path.exists():
        # Check if venv is using the right version
        cfg_path = venv_path / "pyvenv.cfg"
        if cfg_path.exists():
            with open(cfg_path, 'r') as f:
                content = f.read()
                # If we have a local python but venv is pointing elsewhere, recreate
                if "python_local" not in content and "python_local" in base_python:
                    print("--- Venv version mismatch. Recreating venv... ---")
                    recreate_venv = True
                elif "version = 3.14" in content or "version = 3.13" in content:
                    if "python_local" in base_python:
                        print("--- Existing venv is 3.13/3.14. Recreating with 3.10... ---")
                        recreate_venv = True

    if recreate_venv:
        import shutil
        try:
            shutil.rmtree(venv_path)
        except Exception as e:
            print(f"⚠️  Could not delete old venv: {e}. Please delete 'venv' folder manually.")

    if not venv_path.exists():
        print(f"--- Creating local virtual environment (venv) using {base_python}... ---")
        # Use the base_python we identified (system or local)
        run_command(f'"{base_python}" -m venv "{venv_path}"')
    
    # Determine paths based on OS
    if system == "Windows":
        python_exe = venv_path / "Scripts" / "python.exe"
        pip_exe = venv_path / "Scripts" / "pip.exe"
    else:  # Mac or Linux
        python_exe = venv_path / "bin" / "python"
        pip_exe = venv_path / "bin" / "pip"

    # 2. Update Pip and Install Requirements
    print("--- Checking dependencies... ---")
    run_command(f'"{python_exe}" -m pip install --upgrade pip')
    run_command(f'"{python_exe}" -m pip install filelock') # Bootstrap filelock for config_loader
    
    gpu_brand = get_gpu_brand()
    requirements_file = base_path / "requirements.txt"
    specialized_install = False

    # Check if 'dml' or ROCm is already requested in config
    from config_loader import config
    requested_device = config.clip.get('device', 'cpu')

    if requirements_file.exists():
        # Handle specialized torch installs
        # Trigger DML install if AMD is detected OR if user manually set 'dml' in config
        if system == "Windows" and (gpu_brand == "amd" or requested_device == "dml"):
            print("--- DirectML (AMD/Intel) support requested or detected. Ensuring torch-directml is installed... ---")
            run_command(f'"{pip_exe}" install torch-directml torchvision torchaudio')
            specialized_install = True
        elif system == "Linux" and (gpu_brand == "amd" or requested_device == "rocm"):
            print("--- AMD GPU detected on Linux. Ensuring ROCm torch is installed... ---")
            run_command(f'"{pip_exe}" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.0')
            specialized_install = True
        
        # Install remaining requirements
        with open(requirements_file, 'r') as f:
            reqs = f.readlines()
        
        if specialized_install:
            to_skip = ['torch', 'torchvision', 'torchaudio']
            filtered_reqs = []
            for r in reqs:
                name = r.strip().split('==')[0].split('>=')[0].split('<=')[0].lower()
                if name in to_skip:
                    continue
                filtered_reqs.append(r.strip())
        else:
            filtered_reqs = [r.strip() for r in reqs]
        
        temp_reqs = base_path / "temp_requirements.txt"
        with open(temp_reqs, 'w') as f:
            f.write("\n".join(filtered_reqs))
        
        run_command(f'"{pip_exe}" install -r "{temp_reqs}"')
        if temp_reqs.exists():
            os.remove(temp_reqs)
    
    # 3. Auto-Configure Hardware
    configure_hardware(python_exe, base_path)

    # 4. Check and Setup Database
    print("--- Checking Database Configuration ---")
    setup_cmd = f'"{python_exe}" db_manager.py'
    result = run_command(setup_cmd, cwd=base_path)
    if result.returncode != 0:
        print("❌ Database setup failed. Exiting.")
        sys.exit(1)

    # 5. Launch Streamlit
    print("--- Launching Image Vibe Seeker... ---")
    
    # Security: Default to localhost (127.0.0.1). Only expose if requested.
    if "--share" in sys.argv:
        address = "0.0.0.0"
        print("⚠️  WARNING: App is exposed to the network (0.0.0.0)!")
    else:
        address = "127.0.0.1"
        print("🔒 App is running locally. Use '--share' to expose to network.")

    cmd = f'"{python_exe}" -m streamlit run streamlit_app.py --server.address={address}'
    run_command(cmd, cwd=base_path)

if __name__ == "__main__":
    try:
        setup()
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"\nError during startup: {e}")
        if platform.system() == "Windows":
            input("Press Enter to close...")
