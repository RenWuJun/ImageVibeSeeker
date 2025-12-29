import streamlit as st
import sys
import os
from config_loader import config

# MUST BE FIRST
st.set_page_config(page_title="Maintenance & Setup", layout="wide")

st.title("🛠️ Maintenance & Setup")

# --- SECTION 1: CONFIGURATION ---
st.header("1. Configuration")
with st.expander("Edit Config Settings", expanded=True):
    col1, col2 = st.columns(2)
    
    with col1:
        current_root = config.paths.root_folder
        new_root_input = st.text_input("Images Root Folder:", value=current_root, help="Full path to your image library.")
        
        available_models = config.clip.get('available_models', {})
        current_label = config.clip.get('current_model_label')
        model_options = list(available_models.keys()) or ["None"]
        
        try:
            default_idx = model_options.index(current_label)
        except ValueError:
            default_idx = 0
            
        new_model_label = st.selectbox("CLIP Model Configuration:", model_options, index=default_idx)
    
    with col2:
        new_batch = st.number_input("Batch Size:", min_value=1, max_value=100, value=int(config.clip.batch_size))
        
        device_options = ["cuda", "dml", "mps", "cpu"]
        try:
            default_idx = device_options.index(config.clip.device)
        except ValueError:
            default_idx = device_options.index("cpu")
            
        new_device = st.selectbox("Device:", device_options, index=default_idx, help="Select compute device. 'dml' is for AMD/Intel on Windows, 'mps' for Mac.")

    if st.button("💾 Save Configuration"):
        # Use normpath to handle separators correctly for the current OS
        safe_root = os.path.normpath(new_root_input)
        config.update_section('paths', {'root_folder': safe_root})
        
        old_device = config.clip.device
        config.update_section('clip', {'current_model_label': new_model_label, 'batch_size': new_batch, 'device': new_device})
        config.save_config()
        
        st.success(f"✅ Configuration updated! Root set to: `{safe_root}`")
        
        if old_device != new_device:
            st.warning("⚠️ **Device Changed:** You must **restart the app** to install the necessary drivers for the new device.")
        else:
            st.info("🔄 Restart the application for model changes to take effect.")

# --- SECTION 2: ACTIONS ---
st.header("2. Actions")
st.info("💡 Clicking these buttons will open a **new terminal window** to perform the task.")

def launch_terminal_task(script_name, args=""):
    """Launches a python script in a new visible terminal window (Cross-platform)."""
    python_path = sys.executable
    script_path = os.path.join(os.getcwd(), script_name)
    full_cmd = f'"{python_path}" "{script_path}" {args}'
    
    system = sys.platform
    try:
        if system == "win32":
            os.system(f'start cmd /k "{full_cmd}"')
        elif system == "darwin":  # macOS
            # Use AppleScript to open a new terminal and run the command
            os.system(f"osascript -e 'tell application \"Terminal\" to do script \"{full_cmd}\"'")
        else:  # Linux (Assume x-terminal-emulator or similar)
            # Try a few common linux terminals
            for term in ["x-terminal-emulator", "gnome-terminal", "konsole", "xterm"]:
                if os.system(f"which {term} > /dev/null 2>&1") == 0:
                    if term == "gnome-terminal":
                        os.system(f'{term} -- bash -c "{full_cmd}; exec bash"')
                    else:
                        os.system(f'{term} -e "bash -c \'{full_cmd}; exec bash\'" &')
                    break
        st.success(f"🚀 Launched {script_name} in a new window.")
    except Exception as e:
        st.error(f"Failed to launch terminal: {e}")

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.subheader("Database Sync")
    st.write("Scan folders and generate embeddings.")
    if st.button("🚀 Start Sync & Embed"):
        launch_terminal_task("database_sync.py")

with col_b:
    st.subheader("Search Index")
    st.write("Create the HNSW search index.")
    if st.button("⚡ Create Index"):
        launch_terminal_task("compute_distances_and_density.py", "create-index")

with col_c:
    st.subheader("Leaderboard Metrics")
    st.write("Recompute distances for the leaderboard.")
    if st.button("📊 Recompute All"):
        launch_terminal_task("compute_distances_and_density.py", "all")

st.divider()
st.info("💡 **Getting Started:** Set your folder above, then run **Sync**, then **Create Index**, then **Recompute All**.")
