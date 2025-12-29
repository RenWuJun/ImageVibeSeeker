# C:\Projects\ImageVibeSeeker\pages\basic_search.py
import streamlit as st
import pandas as pd
import os

from config_loader import config
from db_manager import db_manager
from components import render_image_card
from utils.logger import get_logger

# MUST BE FIRST
st.set_page_config(page_title="Basic Search", layout="wide")

logger = get_logger(__name__)

# Extract values
score_range = config.get('score_range', {'above': 10, 'below': 0})  # Default if not in config

def get_read_conn():
    """Create a new connection for reads"""
    return db_manager.get_conn()

def get_search_results(search_query, sort_mode, score_above, score_below, exclude_none_score, limit=20):
    conn = None
    try:
        conn = get_read_conn()
        cur = conn.cursor()
    
        base_query = """
            SELECT id, file_name, file_path, score, min_distance, density
            FROM images
            WHERE file_path ILIKE %s
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
        elif sort_mode == "lowest_density":
            order = "density ASC NULLS FIRST, min_distance ASC"
        elif sort_mode == "file name: A → Z":
            order = "file_name ASC"
        else:  # file name: Z → A
            order = "file_name DESC"
        
        exclude_none = "AND score IS NOT NULL" if exclude_none_score else ""
        query = base_query.format(exclude_none=exclude_none, order=order)
        search_pattern = f"%{search_query}%"
        cur.execute(query, (search_pattern, score_above, score_below, limit))
        df = pd.DataFrame(cur.fetchall(), columns=['id', 'file_name', 'file_path', 'score', 'min_distance', 'density'])
        logger.info(f"Search results for '{search_query}': {len(df)} images found.")
    except Exception as e:
        logger.error(f"Error fetching search results for '{search_query}': {e}")
        df = pd.DataFrame()
    finally:
        if conn: db_manager.put_conn(conn)
    return df

# Streamlit UI
st.title("Basic Image Search")

# Initialize session state
if 'basic_search_query' not in st.session_state:
    st.session_state['basic_search_query'] = ""
if 'basic_search_triggered' not in st.session_state:
    st.session_state['basic_search_triggered'] = False

# Row 1: Search bar and Search button
col_search_input, col_search_button = st.columns([3, 1])
with col_search_input:
    search_query = st.text_input("Search by file name or path", value=st.session_state['basic_search_query'], key="search_query")
with col_search_button:
    if st.button("Search", key="search_button"):
        st.session_state['basic_search_triggered'] = True
        st.session_state['basic_search_query'] = search_query
        logger.info(f"Basic search triggered for query: {search_query}")

# Update session state with current search query
if search_query != st.session_state['basic_search_query']:
    st.session_state['basic_search_query'] = search_query
    st.session_state['basic_search_triggered'] = True if search_query else False

# Row 2: Filters
query_params = st.experimental_get_query_params()
score_above = int(query_params.get("score_above", [str(score_range['above'])])[0])
score_below = int(query_params.get("score_below", [str(score_range['below'])])[0])

col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    sort_mode = st.selectbox(
        "Sort by:",
        ["shortest_nearest", "longest_nearest", "highest_density", "lowest_density", "file name: A → Z", "file name: Z → A"],
        key="sort_mode"
    )
with col2:
    new_score_above = st.number_input("Exclude scores above:", value=score_above, min_value=0, max_value=10, key="score_above")
with col3:
    new_score_below = st.number_input("Exclude scores below:", value=score_below, min_value=0, max_value=10, key="score_below")
with col4:
    exclude_none_score = st.checkbox("Exclude none score", key="exclude_none_score")

# Save score_range to config
if new_score_above != score_range['above'] or new_score_below != score_range['below']:
    config.update_section('score_range', {'above': new_score_above, 'below': new_score_below})
    config.save_config()
    st.experimental_set_query_params(score_above=str(new_score_above), score_below=str(new_score_below))
    st.success("Score range saved to config.")
    logger.info(f"Score range saved: above={new_score_above}, below={new_score_below}")

# Process search
if st.session_state['basic_search_triggered'] and st.session_state['basic_search_query']:
    with st.spinner("Searching..."):
        df = get_search_results(st.session_state['basic_search_query'], sort_mode, new_score_above, new_score_below, exclude_none_score)
    if df.empty:
        st.info("No images match the search query or filters.")
        logger.info(f"No images found for basic search query: {st.session_state['basic_search_query']}")
    else:
        st.subheader(f"Search Results for '{st.session_state['basic_search_query']}' (Max 20)")
        for idx, row in df.iterrows():
            render_image_card(row, show_detail=True, show_delete=True, idx=idx)
            st.divider()
else:
    st.info("Enter a search query and click 'Search' to find images by file name or path.")