# C:\Projects\ImageVibeSeeker\streamlit_app.py
import streamlit as st
import os

from config_loader import config
from db_manager import db_manager
from components import render_login_gate
from utils.logger import get_logger

logger = get_logger(__name__)

def show_home():
    st.title(f"Image Vibe Seeker {config.version}")
    st.header("🏠 Database Overview")

    conn = None
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM images")
        total_images = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM images WHERE score IS NOT NULL")
        scored_images = cur.fetchone()[0]
        cur.close()
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Images", total_images)
        with col2:
            st.metric("Scored Images", scored_images, f"{(scored_images/total_images*100):.1f}%" if total_images > 0 else "0%")
            
        logger.info(f"Database statistics: Total={total_images}, Scored={scored_images}")
    except Exception as e:
        logger.error(f"Database error fetching statistics: {e}")
        st.error(f"Database error: {e}")
    finally:
        if conn: db_manager.put_conn(conn)
    
    st.divider()
    st.info("💡 **Getting Started:** Navigate to **Maintenance** to scan your library, or use **Vibe Search** to find images by description.")

# --- PAGE DEFINITIONS ---
# We use functions or script paths
pg_home = st.Page(show_home, title="Home", icon="🏠", default=True)
pg_basic = st.Page("pages/basic_search.py", title="Basic Search", icon="🔍")
pg_vibe = st.Page("pages/vibe_search.py", title="Vibe Search", icon="🖼️")
pg_leaderboard = st.Page("pages/image_leaderboard.py", title="Leaderboard", icon="🏆")
pg_details = st.Page("pages/image_details.py", title="Image Details", icon="ℹ️")
pg_batch = st.Page("pages/batch_recursive_delete.py", title="Batch Delete", icon="⚡")
pg_maint = st.Page("pages/maintenance.py", title="Maintenance", icon="🛠️")
pg_score = st.Page("pages/score_management.py", title="Score Management", icon="⚖️")

# --- NAVIGATION ---
pg = st.navigation({
    "Main": [pg_home, pg_vibe, pg_leaderboard, pg_basic],
    "Tools": [pg_batch, pg_score, pg_maint],
    "System": [pg_details]
})

# --- GLOBAL CONFIG ---
# Must be called BEFORE pg.run()
st.set_page_config(page_title=f"Image Vibe Seeker {config.version}", layout="wide")

# --- EXECUTION ---
# STEP 1: LOGIN GATE
# Ensures no database calls happen until the password is provided.
render_login_gate()

# STEP 2: RUN SELECTED PAGE
pg.run()