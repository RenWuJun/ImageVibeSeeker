import streamlit as st
import os
import pandas as pd
import traceback
import platform
import subprocess
from send2trash import send2trash

from config_loader import config
from db_manager import db_manager
from tag_manager import tag_manager
from distance_calculator import distance_calculator # Import the calculator
from utils.logger import get_logger

logger = get_logger(__name__)

def open_file_cross_platform(file_path):
    """Opens a file using the system's default application in a cross-platform way."""
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(file_path)
        elif system == "Darwin":  # macOS
            subprocess.run(["open", file_path], check=True)
        else:  # Linux and others
            subprocess.run(["xdg-open", file_path], check=True)
        return True
    except Exception as e:
        logger.error(f"Failed to open file {file_path}: {e}")
        return False

# FIXED: Root path for subprocess
PROJECT_ROOT = os.path.dirname(__file__)

# Extract values from config
score_options = [None] + sorted(set(rule['score'] for rule in config.scores.rules), reverse=True)

def delete_image_and_get_affected_ids(image_id, file_path):
    """Delete image from DB, trash file, and return affected IDs WITHOUT recomputing."""
    image_id = int(image_id)
    conn = None
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()

        # STEP 1: Get EXACT delete_path from DB
        cur.execute("SELECT file_path FROM images WHERE id = %s", (image_id,))
        path_row = cur.fetchone()
        
        if path_row is None:
            logger.error(f"❌ Image ID {image_id} not found in database for deletion.")
            st.error(f"❌ Image ID {image_id} not found in database")
            return []
        
        delete_path = path_row[0]
        logger.info(f"Deleting {image_id}, path: {delete_path}")
        
        # STEP 2: Identify Affected Images (First-Hop and Second-Hop Neighbors)
        cur.execute("""
            WITH deleted_image_id_cte AS (
                SELECT %s AS id, %s AS file_path
            ),
            first_hop AS (
                SELECT i.id
                FROM images i, deleted_image_id_cte d
                WHERE i.id != d.id
                  AND d.file_path = ANY(ARRAY[i.nearest_path_1, i.nearest_path_2, i.nearest_path_3, i.nearest_path_4, i.nearest_path_5,
                                            i.nearest_path_6, i.nearest_path_7, i.nearest_path_8, i.nearest_path_9, i.nearest_path_10])
            ),
            second_hop_paths AS (
                SELECT UNNEST(ARRAY[i.nearest_path_1, i.nearest_path_2, i.nearest_path_3, i.nearest_path_4, i.nearest_path_5,
                                    i.nearest_path_6, i.nearest_path_7, i.nearest_path_8, i.nearest_path_9, i.nearest_path_10]) AS neighbor_path
                FROM images i
                WHERE i.id IN (SELECT id FROM first_hop)
            ),
            second_hop_ids AS (
                SELECT i.id
                FROM images i, second_hop_paths shp
                WHERE i.file_path = shp.neighbor_path AND shp.neighbor_path IS NOT NULL
            )
            SELECT DISTINCT id FROM first_hop
            UNION
            SELECT DISTINCT id FROM second_hop_ids;
        """, (image_id, delete_path))
        
        affected_ids = [row[0] for row in cur.fetchall()]
        logger.info(f"Total unique affected IDs for recomputation (combined query): {len(affected_ids)}")

        # STEP 3: DELETE FROM DB
        cur.execute("DELETE FROM images WHERE id = %s", (image_id,))
        conn.commit()
        logger.info(f"Image ID {image_id} deleted from database.")
        
        # STEP 4: Trash files
        md_path = os.path.splitext(delete_path)[0] + '.md'
        try:
            send2trash(delete_path)
            if os.path.exists(md_path):
                send2trash(md_path)
            logger.info(f"🗑️ Deleted {os.path.basename(delete_path)} to recycle bin.")
        except Exception as e:
            logger.warning(f"⚠️ Trash error for {delete_path}: {e}")
            st.warning(f"⚠️ Trash error for {os.path.basename(delete_path)}: {e}")
        
        return affected_ids
        
    except Exception as e:
        logger.error(f"❌ Delete error for image ID {image_id}: {e}")
        st.error(f"❌ Delete error: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        if conn: db_manager.put_conn(conn)

def delete_image(image_id, file_path):
    """High-level function to delete an image and trigger recomputation.
    This is for use in UIs where immediate recomputation is desired.
    """
    affected_ids = delete_image_and_get_affected_ids(image_id, file_path)
    if affected_ids:
        recompute_affected(affected_ids)
    return affected_ids

def recompute_affected(affected_ids):
    """Recompute distances/density for affected IDs by calling the calculator directly."""
    if not affected_ids:
        return False
    
    logger.info(f"Starting in-process recomputation for {len(affected_ids)} affected IDs: {affected_ids}")
    conn = None # Connection will be managed by distance_calculator.compute_batch
    try:
        # Call the distance calculator directly
        results = distance_calculator.compute_batch(affected_ids)
        updated_count = sum(1 for r in results if r is not None)
        logger.info(f"In-process recomputation complete. Updated {updated_count}/{len(affected_ids)} IDs.")
        
        return True
    except Exception as e:
        logger.error(f"❌ In-process recompute error: {e}")
        st.error(f"❌ Recompute error: {e}")
        if conn: conn.rollback()
        return False
    finally:
        # No need to put_conn here, as conn is managed by distance_calculator.compute_batch
        pass

def render_image_card(row, show_detail=True, show_delete=True, is_main=False, idx=None):
    """Reusable component for image layout."""
    col1, col2 = st.columns([1, 2])
    
    with col1:
        if os.path.exists(row['file_path']):
            st.image(row['file_path'], caption=row['file_name'], width=600 if is_main else 'stretch')
        else:
            logger.warning(f"File missing for display: {row['file_name']}")
            st.warning(f"File missing: {row['file_name']}")
    
    with col2:
        st.write(f"**File:** {row['file_name']}")
        original_score = row['score'] if pd.notna(row['score']) else None
        key = f"score_{row['id']}" if idx is None else f"score_{row['id']}_{idx}"
        new_score = st.selectbox(
            "**Score:**",
            options=score_options,
            index=score_options.index(original_score) if original_score in score_options else 0,
            key=key
        )
        if new_score != original_score:
            tag_manager.update_score(row['id'], new_score, row['file_path'], original_score, streamlit=True)
            st.rerun()
        
        min_distance_display = f"{row['min_distance']:.4f}" if pd.notna(row['min_distance']) else "N/A"
        density_display = f"{row['density']:.4f}" if pd.notna(row['density']) else "N/A"

        st.write(f"**Nearest Distance:** {min_distance_display}")
        st.write(f"**Density:** {density_display}")
        st.write(f"**Path:** {row['file_path']}")
        
        # Buttons in one row
        col_detail, col_open, col_delete = st.columns(3)
        if show_detail:
            with col_detail:
                st.write(
                    f'<a href="/image_details?image_id={row["id"]}" target="_self">'
                    f'<button style="background-color: #f0f0f0; padding: 5px 10px; border: 1px solid #ccc; cursor: pointer;">Details</button></a>',
                    unsafe_allow_html=True
                )
        
        with col_open:
            if st.button("Open in default app", key=f"open_{row['id']}_{idx if idx is not None else 0}"):
                if os.path.exists(row['file_path']):
                    if open_file_cross_platform(row['file_path']):
                        st.success(f"Opened {row['file_name']} in default app.")
                        logger.info(f"Opened {row['file_name']} in default app.")
                    else:
                        st.error(f"Could not open {row['file_name']}.")
                else:
                    st.error(f"File not found: {row['file_path']}")
                    logger.error(f"File not found for opening: {row['file_path']}")
        
        if show_delete:
            with col_delete:
                del_key = f"del_{row['id']}" if idx is None else f"del_{row['id']}_{idx}"
                if st.button("Delete", key=del_key):
                    delete_image(row['id'], row['file_path'])
                    st.rerun()