# C:\Projects\ImageVibeSeeker\pages\basic_search.py
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

def get_search_results(query, max_score, min_score, exclude_none_score, limit=50):
    conn = None
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()
        p = db_manager.p

        like_op = "LIKE" if db_manager._db_mode == 'sqlite' else "ILIKE"
        
        base_query = f"""
            SELECT id, file_name, file_path, score, min_distance, density
            FROM images
            WHERE (file_name {like_op} {p} OR file_path {like_op} {p})
            AND (score IS NULL OR score <= {p}) AND (score IS NULL OR score >= {p})
            {{exclude_none}}
            ORDER BY id DESC
            LIMIT {p}
        """
        exclude_none = "AND score IS NOT NULL" if exclude_none_score else ""
        query_sql = base_query.format(exclude_none=exclude_none)

        search_term = f"%{query}%"
        cur.execute(query_sql, (search_term, search_term, max_score, min_score, limit))
        rows = cur.fetchall()
        
        if db_manager._db_mode == 'sqlite':
            df = pd.DataFrame([dict(r) for r in rows])
        else:
            df = pd.DataFrame(rows, columns=['id', 'file_name', 'file_path', 'score', 'min_distance', 'density'])
        
        logger.info(f"Basic search for '{query}': {len(df)} images.")
    except Exception as e:
        logger.error(f"Database error: {e}")
        st.error(f"Database error: {e}")
        df = pd.DataFrame()
    finally:
        if conn: db_manager.put_conn(conn)
    return df

st.title("🔍 Basic Search")
search_query = st.text_input("Search filename or path:", placeholder="Keywords...", key="basic_search_input")

score_range = config.get('score_range', {'above': 10, 'below': 0})
max_score = int(st.query_params.get("max_score", score_range['above']))
min_score = int(st.query_params.get("min_score", score_range['below']))

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    new_max_score = st.number_input("Max score:", value=max_score, min_value=0, max_value=10, key="basic_max_score")
with col2:
    new_min_score = st.number_input("Min score:", value=min_score, min_value=0, max_value=10, key="basic_min_score")
with col3:
    exclude_none_score = st.checkbox("Hide unscored", key="basic_exclude_none")

if new_max_score != score_range.get('above', 10) or new_min_score != score_range.get('below', 0):
    config.update_section('score_range', {'above': new_max_score, 'below': new_min_score})
    st.success("Score range updated!")
    st.rerun()

if search_query:
    df = get_search_results(search_query, new_max_score, new_min_score, exclude_none_score)
    if df.empty:
        st.info("No images match.")
    else:
        for idx, row in df.iterrows():
            render_image_card(row, idx=idx)
            st.divider()
else:
    st.info("Enter keywords to search.")
