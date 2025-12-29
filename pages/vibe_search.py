# C:\Projects\ImageVibeSeeker\pages\vibe_search.py
import streamlit as st
import pandas as pd
import os
import gc # For garbage collection
from psycopg2 import Error as psycopg2_Error
from psycopg2 import Error as psycopg2_Error

from config_loader import config
from db_manager import db_manager
from clip_processor import clip_processor
from components import render_image_card
from utils.logger import get_logger

# MUST BE FIRST
st.set_page_config(page_title="Vibe Search", layout="wide")

logger = get_logger(__name__)

# Extract values
score_range = config.get('score_range', {'above': 10, 'below': 0})

def get_read_conn():
    """Create a new connection for reads"""
    return db_manager.get_conn()

@st.cache_resource
def load_clip_model():
    """Load CLIP model once and cache it"""
    # Model is loaded internally by clip_processor when first used
    return clip_processor.model, clip_processor.preprocess, clip_processor.tokenizer

def unload_clip_model():
    """Unload model from memory/GPU - FULL UNLOAD"""
    clip_processor.unload_model()
    st.success("✅ Model UNLOADED from Memory/GPU!")
    st.info("Next search will reload it (~2-3s)")
    logger.info("CLIP model fully unloaded.")

def encode_text_query(query):
    """Encode text query to embedding"""
    return clip_processor.get_text_embedding(query)

def encode_image_query(uploaded_file):
    """Encode uploaded image to embedding"""
    return clip_processor.get_image_embedding_from_file(uploaded_file)

def get_search_results(embedding, sort_mode, max_score, min_score, exclude_none_score, limit=20):
    """Get vibe search results using embedding (text or image)"""
    conn = None
    try:
        conn = get_read_conn()
        cur = conn.cursor()
    
        base_query = """
            SELECT id, file_name, file_path, score, min_distance, density,
                   (embedding <=> %s::vector) AS dist
            FROM images
            WHERE embedding IS NOT NULL
            AND (score IS NULL OR score <= %s) AND (score IS NULL OR score >= %s)
            {exclude_none}
            ORDER BY {order}
            LIMIT %s
        """
        
        if sort_mode == "most similar":
            order = "(embedding <=> %s::vector) ASC"
            params = [embedding, max_score, min_score, embedding, limit]
        else:
            order = "(embedding <=> %s::vector) DESC"
            params = [embedding, max_score, min_score, embedding, limit]
        
        exclude_none = "AND score IS NOT NULL" if exclude_none_score else ""
        query = base_query.format(exclude_none=exclude_none, order=order)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=['id', 'file_name', 'file_path', 'score', 'min_distance', 'density', 'dist'])
        logger.info(f"Vibe search results for {sort_mode} query: {len(df)} images found.")
    except psycopg2.Error as e:
        logger.error(f"Database error fetching vibe search results: {e}")
        st.error(f"Database error: {e}")
        df = pd.DataFrame()
    finally:
        if conn: db_manager.put_conn(conn)
    
    return df

# Streamlit UI
st.title("🖼️ Vibe Image Search")

# Initialize ONLY trigger state
if 'vibe_search_triggered' not in st.session_state:
    st.session_state['vibe_search_triggered'] = False

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
        disabled=search_mode != "Text Description" and search_mode != "Both"
    )

with col_image:
    uploaded_file = st.file_uploader(
        "Upload an image to search similar vibes",
        type=['png', 'jpg', 'jpeg'],
        key="vibe_image_uploader",
        disabled=search_mode != "Uploaded Image" and search_mode != "Both"
    )

# Search button
if st.button("🔍 Search", key="vibe_search_button", use_container_width=True):
    valid_query = False
    if search_mode == "Text Description" or search_mode == "Both":
        if search_query.strip():
            valid_query = True
        else:
            st.warning("Please enter a text query.")
            logger.warning("Vibe search triggered without text query.")
    if search_mode == "Uploaded Image" or search_mode == "Both":
        if uploaded_file is not None:
            valid_query = True
        else:
            st.warning("Please upload an image.")
            logger.warning("Vibe search triggered without uploaded image.")
    
    if valid_query:
        st.session_state['vibe_search_triggered'] = True
        logger.info(f"Vibe search triggered: mode={search_mode}, query={search_query if search_mode != 'Uploaded Image' else '[uploaded image]'}")
        st.rerun()

# Row 3: Filters - Load from config first!
score_range = config.get('score_range', {'above': 10, 'below': 0})
query_params = st.experimental_get_query_params()
max_score = int(query_params.get("max_score", [str(score_range['above'])] )[0])
min_score = int(query_params.get("min_score", [str(score_range['below'])] )[0])

col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    sort_mode = st.selectbox("Sort by:", ["most similar", "most dissimilar"], key="vibe_search_sort_mode")
with col2:
    new_max_score = st.number_input(
        "Max score to include:", 
        value=max_score, 
        min_value=0, 
        max_value=10, 
        key="vibe_max_score"
    )
with col3:
    new_min_score = st.number_input(
        "Min score to include:", 
        value=min_score, 
        min_value=0, 
        max_value=10, 
        key="vibe_min_score"
    )
with col4:
    exclude_none_score = st.checkbox("Hide unscored images", key="vibe_exclude_none")

if new_max_score != score_range.get('above', 10) or new_min_score != score_range.get('below', 0):
    config.update_section('score_range', {'above': new_max_score, 'below': new_min_score})
    config.save_config()
    st.experimental_set_query_params(max_score=str(new_max_score), min_score=str(new_min_score))
    st.success("Score range saved!")
    logger.info(f"Score range saved: max_score={new_max_score}, min_score={new_min_score}")

# Row 4: UNLOAD BUTTON - FULL MEMORY CLEANUP
col_unload, _ = st.columns([1, 3])
with col_unload:
    if st.button("🗑️ Unload Model from Memory", key="vibe_unload_model"):
        unload_clip_model()
        st.rerun()

# Process search
if st.session_state['vibe_search_triggered']:
    with st.spinner("Searching..."):
        embedding = None
        query_type = ""
        try:
            if search_mode == "Text Description" or (search_mode == "Both" and search_query.strip()):
                embedding = encode_text_query(search_query)
                query_type = "text"
            elif search_mode == "Uploaded Image" or (search_mode == "Both" and uploaded_file):
                uploaded_file.seek(0)
                embedding = encode_image_query(uploaded_file)
                query_type = "image"
        except Exception as e:
            st.error(f"CLIP model failed to load or process query: {e}")
            logger.error(f"CLIP model failed to load or process query during vibe search: {e}")
            st.session_state['vibe_search_triggered'] = False
            st.rerun()

        if embedding is None:
            st.warning("No valid query provided.")
            logger.warning("No valid query provided for vibe search.")
            st.session_state['vibe_search_triggered'] = False
            st.rerun()
        
        df = get_search_results(
            embedding, sort_mode, new_max_score, new_min_score, exclude_none_score
        )
    
    if df.empty:
        st.info(f"😔 No images match your {query_type} query with current filters.")
        st.info("**Tips:** Try broader terms, adjust filters, or uncheck 'Hide unscored images'")
        logger.info(f"No images found for vibe search query: {search_query if query_type == 'text' else '[uploaded image]'}")
    else:
        sort_text = "Most Similar" if sort_mode == "most similar" else "Most Dissimilar"
        query_desc = search_query if query_type == "text" else "uploaded image"
        st.subheader(f"🎯 {sort_text} to '{query_desc}' ({len(df)} images)")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Best Match", f"{df['dist'].min():.4f}")
        with col2:
            st.metric("Worst Match", f"{df['dist'].max():.4f}")
        
        for idx, row in df.iterrows():
            render_image_card(row, show_detail=True, show_delete=True, idx=idx)
            st.divider()

    # Reset trigger
    st.session_state['vibe_search_triggered'] = False

else:
    st.info(
        "👋 **Welcome to Vibe Search!**\n\n"
        "Choose **Text**, **Image**, or **Both** to find similar vibes.\n\n"
        "**Text Examples:**\n"
        "• 'sunset beach'\n"
        "• 'dark cyberpunk'\n"
        "• 'cute animals'\n\n"
        "**Image:** Upload a photo to find look-alikes!\n\n"
        "**🗑️ Unload Button:** Frees GPU/RAM after use."
    )
    logger.info("Vibe search page loaded.")

# Footer
st.markdown("---")
st.markdown("*Powered by OpenCLIP + PostgreSQL pgvector*")