# C:\Projects\ImageVibeSeeker\pages\image_details.py
import streamlit as st
import pandas as pd
import os

from config_loader import config
from db_manager import db_manager
from tag_manager import tag_manager
from components import render_image_card, delete_image, recompute_affected
from utils.logger import get_logger

# MUST BE FIRST
st.set_page_config(page_title="Image Details", layout="wide")

logger = get_logger(__name__)

# Extract values
score_rules = config.scores.rules

# Score options
score_options = [None] + sorted(set(rule['score'] for rule in score_rules), reverse=True)

def get_read_conn():
    """Create a new connection for reads"""
    return db_manager.get_conn()

def get_image_details(image_id, sort_mode="most similar"):
    conn = None
    try:
        conn = get_read_conn()
        cur = conn.cursor()
    
        # Fetch main image details
        cur.execute("""
            SELECT file_name, file_path, score, min_distance, density,
                   nearest_path_1, nearest_path_2, nearest_path_3, nearest_path_4,
                   nearest_path_5, nearest_path_6, nearest_path_7, nearest_path_8,
                   nearest_path_9, nearest_path_10, embedding
            FROM images
            WHERE id = %s
        """, (image_id,))
        main_row = cur.fetchone()
        
        if not main_row:
            logger.warning(f"Image ID {image_id} not found in database.")
            return None, None
        
        main_details = {
            'id': image_id,
            'file_name': main_row[0],
            'file_path': main_row[1],
            'score': main_row[2],
            'min_distance': main_row[3],
            'density': main_row[4]
        }
        main_embedding = main_row[15]
        
        nearest_details = []
        if sort_mode == "most similar":
            # Use precomputed nearest paths for "most similar"
            nearest_paths = [p for p in main_row[5:15] if p is not None]
            if nearest_paths:
                placeholders = ','.join(['%s'] * len(nearest_paths))
                cur.execute(f"""
                    SELECT id, file_name, file_path, score, min_distance, density,
                           (embedding <=> %s::vector) AS dist
                    FROM images
                    WHERE file_path IN ({placeholders})
                    ORDER BY (embedding <=> %s::vector) ASC
                """, [main_embedding] + nearest_paths + [main_embedding])
                nearest_details = cur.fetchall()
        else:  # most dissimilar
            # Search entire database for 10 most dissimilar images
            cur.execute("""
                SELECT id, file_name, file_path, score, min_distance, density,
                       (embedding <=> %s::vector) AS dist
                FROM images
                WHERE id != %s
                ORDER BY (embedding <=> %s::vector) DESC
                LIMIT 10
            """, (main_embedding, image_id, main_embedding))
            nearest_details = cur.fetchall()
        logger.info(f"Fetched details for image ID {image_id} with {len(nearest_details)} nearest images.")
    except Exception as e:
        logger.error(f"Error fetching image details for ID {image_id}: {e}")
        return None, None
    finally:
        if conn: db_manager.put_conn(conn)
    return main_details, nearest_details

# Get image_id
query_params = st.experimental_get_query_params()
image_id = query_params.get("image_id", [None])[0]
if image_id is None:
    logger.warning(f"No image ID provided in query params: {query_params}")
    st.error("No image ID provided.")
    st.stop()

try:
    image_id = int(image_id)
except (ValueError, TypeError):
    logger.error(f"Invalid image ID provided: {image_id}")
    st.error("Invalid image ID.")
    st.stop()

st.title(f"Image Details (ID: {image_id})")

# Initialize sort_mode in session state
if 'sort_mode' not in st.session_state:
    st.session_state['sort_mode'] = "most similar"

# Fetch details with current sort_mode
with st.spinner("Fetching image details..."):
    main_details, nearest_details = get_image_details(image_id, st.session_state['sort_mode'])

if main_details is None:
    st.error("Image not found.")
    st.stop()

# Render main image
if os.path.exists(main_details['file_path']):
    st.image(main_details['file_path'], caption=main_details['file_name'], width=600)
else:
    logger.warning(f"File missing for display: {main_details['file_path']}")
    st.warning(f"File missing: {main_details['file_name']}")

# Info and buttons
st.write(f"**File:** {main_details['file_name']}")
original_score = main_details['score'] if main_details['score'] is not None else None
new_score = st.selectbox(
    "**Score:**",
    options=score_options,
    index=score_options.index(original_score) if original_score in score_options else 0,
    key=f"main_score_{image_id}"
)
if new_score != original_score:
    tag_manager.update_score(image_id, new_score, main_details['file_path'], original_score, streamlit=True)
    st.rerun()

min_distance_display = f"{main_details['min_distance']:.4f}" if pd.notna(main_details['min_distance']) else "N/A"
density_display = f"{main_details['density']:.4f}" if pd.notna(main_details['density']) else "N/A"

st.write(f"**Nearest Distance:** {min_distance_display}")
st.write(f"**Density:** {density_display}")
st.write(f"**Path:** {main_details['file_path']}")

col_detail, col_open, col_delete = st.columns(3)
with col_open:
    if st.button("Open in default app", key=f"main_open_{image_id}"):
        if os.path.exists(main_details['file_path']):
            os.startfile(main_details['file_path'])
            st.success(f"Opened {main_details['file_name']} in default app.")
            logger.info(f"Opened {main_details['file_name']} in default app.")
        else:
            st.error(f"File not found: {main_details['file_path']}")
            logger.error(f"File not found for opening: {main_details['file_path']}")
with col_delete:
    # Initialize delete confirmation state
    if f'delete_confirm_{image_id}' not in st.session_state:
        st.session_state[f'delete_confirm_{image_id}'] = False

    if st.button("Delete", key=f"main_del_{image_id}"):
        st.session_state[f'delete_confirm_{image_id}'] = True
        st.rerun() # Rerun to show confirmation

    if st.session_state[f'delete_confirm_{image_id}']:
        st.warning(f"Are you sure you want to delete {main_details['file_name']}? This action cannot be undone.")
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("Confirm Deletion", key=f"confirm_del_{image_id}"):
                delete_image(image_id, main_details['file_path'])
                st.success(f"Image {main_details['file_name']} deleted successfully.")
                st.session_state[f'delete_confirm_{image_id}'] = False # Reset state
                st.rerun()
        with col_cancel:
            if st.button("Cancel", key=f"cancel_del_{image_id}"):
                st.session_state[f'delete_confirm_{image_id}'] = False # Reset state
                st.info("Deletion cancelled.")
                st.rerun()


# Top 10 nearest or most dissimilar
st.subheader(f"Top 10 {'Most Similar' if st.session_state['sort_mode'] == 'most similar' else 'Most Dissimilar'} Images")

# Sort by dropdown
new_sort_mode = st.selectbox("Sort by:", ["most similar", "most dissimilar"], key="nearest_sort_mode")
if new_sort_mode != st.session_state['sort_mode']:
    st.session_state['sort_mode'] = new_sort_mode
    st.rerun()

for idx, nearest in enumerate(nearest_details, 1):
    nid, nfile_name, nfile_path, nscore, nmin_distance, ndensity, ndist = nearest
    nearest_row = pd.Series({
        'id': nid,
        'file_name': nfile_name,
        'file_path': nfile_path,
        'score': nscore,
        'min_distance': nmin_distance,
        'density': ndensity
    })
    render_image_card(nearest_row, show_detail=True, show_delete=True, idx=idx)
    st.divider()