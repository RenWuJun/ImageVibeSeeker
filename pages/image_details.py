# C:\Projects\ImageVibeSeeker\pages\image_details.py
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

def get_image_details(image_id):
    conn = None
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()
        p = db_manager.p
        cur.execute(f"""
            SELECT id, file_name, file_path, score, min_distance, density,
                   nearest_path_1, nearest_path_2, nearest_path_3, nearest_path_4, nearest_path_5,
                   nearest_path_6, nearest_path_7, nearest_path_8, nearest_path_9, nearest_path_10
            FROM images WHERE id = {p}
        """, (image_id,))
        row = cur.fetchone()
        if row:
            if db_manager._db_mode == 'sqlite':
                return dict(row)
            else:
                cols = [desc[0] for desc in cur.description]
                return dict(zip(cols, row))
        return None
    except Exception as e:
        logger.error(f"Error fetching details for ID {image_id}: {e}")
        return None
    finally:
        if conn: db_manager.put_conn(conn)

def get_images_by_paths(paths):
    if not paths: return pd.DataFrame()
    conn = None
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()
        p = db_manager.p
        valid_paths = [p_ for p_ in paths if p_]
        if not valid_paths: return pd.DataFrame()

        if db_manager._db_mode == 'sqlite':
            placeholders = ','.join([p] * len(valid_paths))
            cur.execute(f"SELECT id, file_name, file_path, score, min_distance, density FROM images WHERE file_path IN ({placeholders})", valid_paths)
            rows = cur.fetchall()
            return pd.DataFrame([dict(r) for r in rows])
        else:
            cur.execute("SELECT id, file_name, file_path, score, min_distance, density FROM images WHERE file_path = ANY(%s)", (valid_paths,))
            rows = cur.fetchall()
            return pd.DataFrame(rows, columns=['id', 'file_name', 'file_path', 'score', 'min_distance', 'density'])
    except Exception as e:
        logger.error(f"Error fetching neighbor images: {e}")
        return pd.DataFrame()
    finally:
        if conn: db_manager.put_conn(conn)

st.title("🔍 Image Details")

query_params = st.query_params
image_id = query_params.get("image_id")

if image_id:
    details = get_image_details(int(image_id))
    if details:
        st.subheader(f"Main Image: {details['file_name']}")
        render_image_card(details, show_detail=False, show_delete=True, is_main=True)

        st.divider()
        st.subheader("🔗 Nearest Neighbors (Vibe Matches)")

        neighbor_paths = [details[f'nearest_path_{i}'] for i in range(1, 11)]
        neighbors_df = get_images_by_paths(neighbor_paths)

        if neighbors_df.empty:
            st.info("No neighbor data found. Run 'Recompute All' in Maintenance.")
        else:
            path_to_rank = {path: i for i, path in enumerate(neighbor_paths)}
            neighbors_df['rank'] = neighbors_df['file_path'].map(path_to_rank)
            neighbors_df = neighbors_df.sort_values('rank')

            for idx, row in neighbors_df.iterrows():
                render_image_card(row, show_detail=True, show_delete=True, idx=f"nb_{idx}")
                st.divider()
    else:
        st.error(f"Image ID {image_id} not found.")
else:
    st.info("No image selected.")
