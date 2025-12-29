# C:\Projects\ImageVibeSeeker\pages\image_leaderboard.py
import streamlit as st
import pandas as pd
import os
import subprocess
from psycopg2 import Error as psycopg2_Error
from psycopg2 import Error as psycopg2_Error

from config_loader import config
from db_manager import db_manager
from components import render_image_card, delete_image, recompute_affected
from utils.logger import get_logger

# MUST BE FIRST
st.set_page_config(page_title="Image Leaderboard", layout="wide")

logger = get_logger(__name__)

# Extract values
score_rules = config.scores.rules
score_range = config.get('score_range', {'above': 10, 'below': 0})

# Score options
score_options = [None] + sorted(set(rule['score'] for rule in score_rules), reverse=True)

def get_read_conn():
    """Create a new connection for reads"""
    return db_manager.get_conn()

def get_leaderboard_df(sort_mode, max_score, min_score, exclude_none_score, limit=20):
    conn = None
    try:
        conn = get_read_conn()
        cur = conn.cursor()
    
        base_query = """
            SELECT id, file_name, file_path, score, min_distance, density
            FROM images
            WHERE min_distance IS NOT NULL
            AND embedding IS NOT NULL
            AND (score IS NULL OR score <= %s) AND (score IS NULL OR score >= %s)
            {exclude_none}
            ORDER BY {order}
            LIMIT %s
        """
        
        if sort_mode == "shortest_nearest":
            order = "min_distance ASC, density DESC NULLS LAST"
        elif sort_mode == "longest_nearest":
            order = "min_distance DESC, density ASC NULLS FIRST"
        elif sort_mode == "highest_density":
            order = "density DESC NULLS LAST, min_distance ASC"
        else:  # lowest_density
            order = "density ASC NULLS FIRST, min_distance ASC"
        
        exclude_none = "AND score IS NOT NULL" if exclude_none_score else ""
        query = base_query.format(exclude_none=exclude_none, order=order)
        
        # FIXED: Correct parameter order (max_score, min_score, limit)
        cur.execute(query, (max_score, min_score, limit))
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=['id', 'file_name', 'file_path', 'score', 'min_distance', 'density'])
        logger.info(f"Leaderboard fetched with sort_mode={sort_mode}, max_score={max_score}, min_score={min_score}: {len(df)} images.")
    except psycopg2.Error as e:
        logger.error(f"Database error fetching leaderboard: {e}")
        st.error(f"Database error: {e}")
        df = pd.DataFrame()
    finally:
        if conn: db_manager.put_conn(conn)
    
    return df



# Streamlit UI
st.title("🏆 Image Leaderboard (Top 20)")

# Initialize session state for batch delete
if 'batch_processing' not in st.session_state:
    st.session_state['batch_processing'] = False

# FIXED: Load from CONFIG first, then query_params
score_range = config.get('score_range', {'above': 10, 'below': 0})
query_params = st.experimental_get_query_params()
max_score = int(query_params.get("max_score", [str(score_range['above'])] )[0])  # Config > query > 10
min_score = int(query_params.get("min_score", [str(score_range['below'])] )[0])  # Config > query > 0

# Row 1: Filters (Clear labels)
col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    sort_mode = st.selectbox(
        "Sort by:", 
        ["shortest_nearest", "longest_nearest", "highest_density", "lowest_density"], 
        key="image_leaderboard_sort_mode",
        format_func=lambda x: {
            "shortest_nearest": "Closest to Any Image",
            "longest_nearest": "Most Isolated", 
            "highest_density": "Tightest Clusters",
            "lowest_density": "Most Spread Out"
        }[x]
    )
with col2:
    new_max_score = st.number_input(
        "Max score to include:", 
        value=max_score, 
        min_value=0, 
        max_value=10, 
        key="image_leaderboard_max_score",
        help="Default from config.json"
    )
with col3:
    new_min_score = st.number_input(
        "Min score to include:", 
        value=min_score, 
        min_value=0, 
        max_value=10, 
        key="image_leaderboard_min_score",
        help="Default from config.json"
    )
with col4:
    exclude_none_score = st.checkbox("Hide unscored images", key="image_leaderboard_exclude_none")

if new_max_score != score_range.get('above', 10) or new_min_score != score_range.get('below', 0):
    config.update_section('score_range', {'above': new_max_score, 'below': new_min_score})
    st.experimental_set_query_params(max_score=str(new_max_score), min_score=str(new_min_score))
    st.success("Score range saved!")
    logger.info(f"Score range saved: max_score={new_max_score}, min_score={new_min_score}")
    st.rerun() # Explicit rerun to show new results

# Get and display leaderboard
with st.spinner("Fetching leaderboard data..."):
    df = get_leaderboard_df(sort_mode, new_max_score, new_min_score, exclude_none_score)

if df.empty:
    st.warning("No images match the current filters.")
    st.info("**Try:** Lower score limits or uncheck 'Hide unscored images'")
    logger.info("No images found for current leaderboard filters.")
else:
    sort_display = {
        "shortest_nearest": "Closest to Any Image",
        "longest_nearest": "Most Isolated", 
        "highest_density": "Tightest Clusters",
        "lowest_density": "Most Spread Out"
    }[sort_mode]
    
    st.subheader(f"📊 Top 20: {sort_display}")
    
    # Show metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Best", f"{df['min_distance'].min():.4f}")
    with col2: st.metric("Worst", f"{df['min_distance'].max():.4f}")
    with col3: st.metric("Avg Density", f"{df['density'].mean():.2f}")
    with col4: st.metric("Total", len(df))
    
    for idx, row in df.iterrows():
        render_image_card(row, show_detail=True, show_delete=True, idx=idx)
        st.divider()
