import streamlit as st
import os
import sys
import pandas as pd
from config_loader import config
from db_manager import db_manager
from utils.logger import get_logger

# MUST BE FIRST
st.set_page_config(page_title="Score Management", layout="wide")

logger = get_logger(__name__)

st.title("🎯 Score Management")

st.info("💡 Scores are primarily managed via **Markdown sidecar files** (.md) and keywords in **filenames**. Use this page to synchronize them with the database.")

# --- UTILS ---
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
            os.system(f"osascript -e 'tell application \"Terminal\" to do script \"{full_cmd}\"'")
        else:  # Linux
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

# --- SECTION 1: KEYWORD SYNC ---
st.header("1. Sync via Filenames/Sidecars")
st.write("Automatically assign scores by scanning filenames and .md files for keywords defined in your config.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Incremental Sync")
    st.write("Only check images that **don't have a score** in the database yet.")
    if st.button("🔍 Sync Missing Scores", use_container_width=True):
        launch_terminal_task("score_updater.py", "--incremental")

with col2:
    st.subheader("Full Force Sync")
    st.write("Re-scan **every image** and overwrite DB scores if sidecar/filename keywords have changed.")
    if st.button("🔥 Overwrite All Scores", use_container_width=True):
        launch_terminal_task("score_updater.py", "--full")

st.divider()

# --- SECTION 2: VIEW CURRENT RULES ---
st.header("2. Current Scoring Rules")
st.write("These rules are loaded from your `config.json`. To change them, edit the config file.")

rules = config.scores.rules
if rules:
    # Convert rules list to a more readable format for a table
    rules_data = [{"Keyword": r['keyword'], "Score": r['score']} for r in rules]
    st.table(rules_data)
else:
    st.warning("No scoring rules found in config.json")

# --- SECTION 3: DB TOOLS ---
st.header("3. Database Tools")
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Reset All Scores")
    st.write("Wipe all scores from the database (Does NOT delete .md files).")
    if st.button("🗑️ Clear DB Scores", type="primary", use_container_width=True):
        # We handle simple SQL directly for speed
        conn = None
        try:
            conn = db_manager.get_conn()
            cur = conn.cursor()
            cur.execute("UPDATE images SET score = NULL")
            conn.commit()
            st.success(f"✅ Cleared scores for {cur.rowcount} images.")
            logger.info("Manual score reset triggered from UI.")
        except Exception as e:
            st.error(f"Error: {e}")
        finally:
            if conn: db_manager.put_conn(conn)

with col_b:
    st.subheader("Statistics")
    conn = None
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM images WHERE score IS NOT NULL")
        count = cur.fetchone()[0]
        cur.execute("SELECT score, COUNT(*) FROM images WHERE score IS NOT NULL GROUP BY score ORDER BY score DESC")
        distribution = cur.fetchall()
        
        st.metric("Total Scored Images", count)
        if distribution:
            dist_df = pd.DataFrame(distribution, columns=["Score", "Count"])
            st.bar_chart(dist_df.set_index("Score"))
    except Exception as e:
        st.error(f"Stats error: {e}")
    finally:
        if conn: db_manager.put_conn(conn)

st.divider()
st.caption("Image Vibe Seeker - Score Management v0.5.0")
