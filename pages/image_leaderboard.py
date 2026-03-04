# C:\Projects\ImageVibeSeeker\pages\image_leaderboard.py
import streamlit as st
import pandas as pd
import os

from config_loader import config
from db_manager import db_manager
from components import render_image_card, render_login_gate
from utils.logger import get_logger

# LOGIN GATE
render_login_gate()

logger = get_logger(__name__)

def get_leaderboard_df(sort_mode, max_score, min_score, exclude_none_score, limit=20):
    conn = None
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()
        p = db_manager.p

        if db_manager._db_mode == 'sqlite':
            if sort_mode == "shortest_nearest":
                order = "min_distance ASC, density DESC"
            elif sort_mode == "longest_nearest":
                order = "min_distance DESC, density ASC"
            elif sort_mode == "highest_density":
                order = "density DESC, min_distance ASC"
            else:  # lowest_density
                order = "density ASC, min_distance ASC"
        else:
            if sort_mode == "shortest_nearest":
                order = "min_distance ASC, density DESC NULLS LAST"
            elif sort_mode == "longest_nearest":
                order = "min_distance DESC, density ASC NULLS FIRST"
            elif sort_mode == "highest_density":
                order = "density DESC NULLS LAST, min_distance ASC"
            else:  # lowest_density
                order = "density ASC NULLS FIRST, min_distance ASC"

        exclude_none = "AND score IS NOT NULL" if exclude_none_score else ""
        query = f"""
            SELECT id, file_name, file_path, score, min_distance, density
            FROM images
            WHERE min_distance IS NOT NULL
            AND embedding IS NOT NULL
            AND (score IS NULL OR score <= {p}) AND (score IS NULL OR score >= {p})
            {exclude_none}
            ORDER BY {order}
            LIMIT {p}
        """

        cur.execute(query, (max_score, min_score, limit))
        rows = cur.fetchall()
        
        if db_manager._db_mode == 'sqlite':
            df = pd.DataFrame([dict(r) for r in rows])
        else:
            df = pd.DataFrame(rows, columns=['id', 'file_name', 'file_path', 'score', 'min_distance', 'density'])
        
        logger.info(f"Leaderboard fetched: {len(df)} images.")
    except Exception as e:
        logger.error(f"Database error fetching leaderboard: {e}")
        st.error(f"Database error: {e}")
        df = pd.DataFrame()
    finally:
        if conn: db_manager.put_conn(conn)

    return df

# Streamlit UI
st.title("🏆 Image Leaderboard (Top 20)")

# Load from CONFIG first
score_range = config.get('score_range', {'above': 10, 'below': 0})
query_params = st.query_params
max_score = int(query_params.get("max_score", score_range['above']))
min_score = int(query_params.get("min_score", score_range['below']))

# Row 1: Filters
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
        "Max score:",
        value=max_score,
        min_value=0,
        max_value=10,
        key="image_leaderboard_max_score"
    )
with col3:
    new_min_score = st.number_input(
        "Min score:",
        value=min_score,
        min_value=0,
        max_value=10,
        key="image_leaderboard_min_score"
    )
with col4:
    exclude_none_score = st.checkbox("Hide unscored", key="image_leaderboard_exclude_none")

if new_max_score != score_range.get('above', 10) or new_min_score != score_range.get('below', 0):
    config.update_section('score_range', {'above': new_max_score, 'below': new_min_score})
    st.query_params.max_score=str(new_max_score)
    st.query_params.min_score=str(new_min_score)
    st.success("Default score range updated!")
    st.rerun()

# Get and display leaderboard
with st.spinner("Fetching leaderboard data..."):
    df = get_leaderboard_df(sort_mode, new_max_score, new_min_score, exclude_none_score)

if df.empty:
    st.warning("No images match current filters.")
else:
    sort_display = {
        "shortest_nearest": "Closest to Any Image",
        "longest_nearest": "Most Isolated",
        "highest_density": "Tightest Clusters",
        "lowest_density": "Most Spread Out"
    }[sort_mode]

    st.subheader(f"📊 Top 20: {sort_display}")

    # Show metrics
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1: st.metric("Best", f"{df['min_distance'].min():.4f}")
    with col_m2: st.metric("Worst", f"{df['min_distance'].max():.4f}")
    with col_m3: st.metric("Avg Density", f"{df['density'].mean():.2f}")
    with col_m4: st.metric("Total", len(df))

    for idx, row in df.iterrows():
        render_image_card(row, idx=idx)
        st.divider()
