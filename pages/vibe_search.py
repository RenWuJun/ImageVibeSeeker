# C:\Projects\ImageVibeSeeker\pages\vibe_search.py
import streamlit as st
import pandas as pd
import numpy as np
import os
import gc

from config_loader import config
from db_manager import db_manager
from clip_processor import clip_processor
from components import render_image_card, render_login_gate
from utils.logger import get_logger

# LOGIN GATE
render_login_gate()

logger = get_logger(__name__)

def get_search_results(embedding, sort_mode, max_score, min_score, exclude_none_score, limit=20):
    """Get vibe search results using embedding (text or image)"""
    conn = None
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()
        p = db_manager.p

        exclude_none = "AND score IS NOT NULL" if exclude_none_score else ""
        order_dir = "ASC" if sort_mode == "most similar" else "DESC"

        if db_manager._db_mode == 'sqlite':
            embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
            query = f"""
                SELECT id, file_name, file_path, score, min_distance, density,
                       vec_distance_cosine(embedding, {p}) AS dist
                FROM images
                WHERE embedding IS NOT NULL
                AND (score IS NULL OR score <= {p}) AND (score IS NULL OR score >= {p})
                {exclude_none}
                ORDER BY dist {order_dir}
                LIMIT {p}
            """
            params = [embedding_blob, max_score, min_score, limit]
        else:
            query = f"""
                SELECT id, file_name, file_path, score, min_distance, density,
                       (embedding <=> {p}::vector) AS dist
                FROM images
                WHERE embedding IS NOT NULL
                AND (score IS NULL OR score <= {p}) AND (score IS NULL OR score >= {p})
                {exclude_none}
                ORDER BY embedding <=> {p}::vector {order_dir}
                LIMIT {p}
            """
            params = [embedding, max_score, min_score, embedding, limit]

        cur.execute(query, params)
        rows = cur.fetchall()
        
        # In SQLite, rows are Row objects. In Postgres, they are tuples.
        if db_manager._db_mode == 'sqlite':
            df = pd.DataFrame([dict(r) for r in rows])
        else:
            df = pd.DataFrame(rows, columns=['id', 'file_name', 'file_path', 'score', 'min_distance', 'density', 'dist'])
        
        logger.info(f"Vibe search results for {sort_mode} query: {len(df)} images found.")
    except Exception as e:
        logger.error(f"Database error fetching vibe search results: {e}")
        st.error(f"Database error: {e}")
        df = pd.DataFrame()
    finally:
        if conn: db_manager.put_conn(conn)

    return df

# Streamlit UI
st.title("🖼️ Vibe Image Search")

# Row 1: Search mode toggle
search_mode = st.radio(
    "Search by:",
    ["Text Description", "Uploaded Image", "Both"],
    key="vibe_search_mode"
)

# Row 2: Input based on mode
col_text, col_image = st.columns(2)

with col_text:
    search_query = st.text_input(
        "Enter vibe description (e.g., 'sunset beach')",
        placeholder="Describe the vibe...",
        key="vibe_search_query",
        disabled=search_mode == "Uploaded Image"
    )

with col_image:
    uploaded_file = st.file_uploader(
        "Upload an image to search similar vibes",
        type=['png', 'jpg', 'jpeg'],
        key="vibe_image_uploader",
        disabled=search_mode == "Text Description"
    )

# Sidebar Filters
st.sidebar.header("Search Settings")
sort_mode = st.sidebar.selectbox("Sort by:", ["most similar", "most dissimilar"], key="vibe_sort_mode")
limit = st.sidebar.slider("Results Limit:", 10, 100, 20)

st.sidebar.header("Score Filters")
score_range_cfg = config.get('score_range', {'above': 10, 'below': 0})
max_score = st.sidebar.number_input("Max score:", 0, 10, score_range_cfg['above'])
min_score = st.sidebar.number_input("Min score:", 0, 10, score_range_cfg['below'])
exclude_none_score = st.sidebar.checkbox("Hide unscored images", value=False)

if st.sidebar.button("💾 Save Filters as Default"):
    config.update_section('score_range', {'above': max_score, 'below': min_score})
    config.save_config()
    st.sidebar.success("Default filters updated!")

if st.sidebar.button("🗑️ Unload Model (WIP)"):
    clip_processor.unload_model()
    st.success("✅ Model UNLOADED from Memory/GPU!")

# Execution Logic
if st.button("🔍 Search", key="vibe_search_btn", use_container_width=True):
    embedding = None
    query_type = ""
    has_text = bool(search_query.strip())
    has_image = uploaded_file is not None

    with st.spinner("Processing Vibe..."):
        try:
            if search_mode == "Text Description" and has_text:
                embedding = clip_processor.get_text_embedding(search_query)
                query_type = f"text: '{search_query}'"
            elif search_mode == "Uploaded Image" and has_image:
                embedding = clip_processor.get_image_embedding_from_file(uploaded_file)
                query_type = "uploaded image"
            elif search_mode == "Both":
                if has_image:
                    embedding = clip_processor.get_image_embedding_from_file(uploaded_file)
                    query_type = "uploaded image"
                elif has_text:
                    embedding = clip_processor.get_text_embedding(search_query)
                    query_type = f"text: '{search_query}'"

            if embedding is not None:
                df = get_search_results(embedding, sort_mode, max_score, min_score, exclude_none_score, limit=limit)

                if df.empty:
                    st.info(f"😔 No images match your vibe ({query_type}).")
                else:
                    st.subheader(f"🎯 Results for {query_type}")
                    for idx, row in df.iterrows():
                        render_image_card(row, idx=idx)
                        st.divider()
            else:
                st.warning("⚠️ Please provide a valid query (text or image) for the selected mode.")

        except Exception as e:
            st.error(f"❌ Error during search: {e}")
            logger.error(f"Vibe search error: {e}")

else:
    st.info(
        "👋 **Welcome to Vibe Search!**\n\n"
        "1. Enter a description or upload an image.\n"
        "2. Adjust filters in the sidebar.\n"
        "3. Click **Search** to find similar visual vibes in your library."
    )
