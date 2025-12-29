# C:\Projects\ImageVibeSeeker\streamlit_app.py
import streamlit as st

from config_loader import config
from db_manager import db_manager
from utils.logger import get_logger

logger = get_logger(__name__)

st.set_page_config(page_title="Image Vibe Seeker v0.5.0", layout="wide")

st.title("Image Vibe Seeker v0.5.0")

# Feature: Database Statistics
st.header("Database Statistics")

conn = None
try:
    conn = db_manager.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM images")
    total_images = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM images WHERE score IS NOT NULL")
    scored_images = cur.fetchone()[0]
    cur.close()
    st.write(f"**Total Images:** {total_images}")
    st.write(f"**Scored Images:** {scored_images} ({(scored_images/total_images*100):.1f}% scored)" if total_images > 0 else "**Scored Images:** 0 (0.0% scored)")
    logger.info(f"Database statistics: Total={total_images}, Scored={scored_images}")
except Exception as e:
    logger.error(f"Database error fetching statistics: {e}")
    st.error(f"Database error: {e}")
finally:
    if conn: db_manager.put_conn(conn)
