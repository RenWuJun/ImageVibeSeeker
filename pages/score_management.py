# C:\Projects\ImageVibeSeeker\pages\score_management.py
import streamlit as st
import sys
import os
from config_loader import config
from components import render_login_gate

# MUST BE FIRST
# st.set_page_config removed

# LOGIN GATE
render_login_gate()

st.title("⚖️ Score & Tag Management")

st.info("💡 Use this page to run mass scoring rules or clean up tag data.")

def launch_terminal_task(script_name, args=""):
    """Launches a python script in a new visible terminal window (Cross-platform)."""
    python_path = sys.executable
    script_path = os.path.normpath(os.path.join(os.getcwd(), script_name))
    db_pass = st.session_state.get('db_pass', '')
    
    # Get current environment variables that need to be passed down
    from db_manager import db_manager
    db_mode = db_manager._db_mode
    china_mirror = os.environ.get('IVS_CHINA_MIRROR', '0')
    
    system = sys.platform
    try:
        if system == "win32":
            cmd = f'set IVS_DB_PASS={db_pass}&& set IVS_DB_MODE={db_mode}&& set IVS_CHINA_MIRROR={china_mirror}&& "{python_path}" "{script_path}" {args}'
            os.system(f'start cmd /k "{cmd}"')
        elif system == "darwin":  # macOS
            cmd = f'export IVS_DB_PASS={db_pass} IVS_DB_MODE={db_mode} IVS_CHINA_MIRROR={china_mirror} && "{python_path}" "{script_path}" {args}'
            os.system(f"osascript -e 'tell application \"Terminal\" to do script \"{cmd}\"'")
        else:  # Linux
            cmd = f'export IVS_DB_PASS={db_pass} IVS_DB_MODE={db_mode} IVS_CHINA_MIRROR={china_mirror} && "{python_path}" "{script_path}" {args}'
            for term in ["x-terminal-emulator", "gnome-terminal", "konsole", "xterm"]:
                if os.system(f"which {term} > /dev/null 2>&1") == 0:
                    if term == "gnome-terminal":
                        os.system(f'{term} -- bash -c "{cmd}; exec bash"')
                    else:
                        os.system(f'{term} -e "bash -c \'{cmd}; exec bash\'" &')
                    break
        st.success(f"🚀 Launched {script_name} in a new window.")
    except Exception as e:
        st.error(f"Failed to launch terminal: {e}")

# --- SECTION 1: MASS SCORING ---
st.header("1. Mass Scoring")
st.write("Apply score rules defined in `config.json` to all images based on their file paths.")

if st.button("📈 Run Mass Scoring"):
    launch_terminal_task("score_updater.py", "--full")

st.divider()

# --- SECTION 2: TAG CLEANUP ---
st.header("2. Metadata Cleanup")
st.write("Verify that all `.md` sidecar files match the database scores.")

if st.button("🧹 Verify & Sync Sidecars"):
    st.warning("Sidecar sync script is coming in v0.7.0.")

st.divider()

# --- SECTION 3: CONFIG OVERVIEW ---
st.header("3. Current Scoring Rules")
score_rules = config.scores.rules
if score_rules:
    for rule in score_rules:
        st.code(f"Keyword: '{rule['keyword']}' -> Score: {rule['score']}")
else:
    st.warning("No scoring rules found in config.json.")
