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
from distance_calculator import distance_calculator
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

def render_login_gate():
    """Intercepts app execution and shows a login screen if not authenticated."""
    # Check if already authenticated or connected
    if st.session_state.get('demo_mode_active'):
        db_manager._db_mode = 'sqlite'
        return True
    
    # Only allow passthrough if not in demo mode and postgres is connected
    if db_manager._db_mode != 'sqlite' and hasattr(db_manager, '_pg_pool') and db_manager._pg_pool is not None:
        return True

    st.title("🛡️ Database Login")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("PostgreSQL (Professional)")
        # Session state to track if we've checked the DB
        if 'db_check_result' not in st.session_state:
            st.session_state['db_check_result'] = 'unchecked'

        target_db = config.database.name
        target_user = config.database.user
        st.info(f"Connecting to: **{config.database.host}** | User: **{target_user}**")

        with st.form("login_form"):
            if st.session_state['db_check_result'] == 'not_found':
                st.warning(f"⚠️ Database '{target_db}' not found.")
                password_label = "Confirm password to create database"
                button_label = "✨ Create & Initialize"
            else:
                st.write("Enter your PostgreSQL password.")
                password_label = "PostgreSQL Password"
                button_label = "Connect"

            password = st.text_input(password_label, type="password")
            submit = st.form_submit_button(button_label)

            if submit:
                if not password:
                    st.error("Please enter a password.")
                else:
                    import db_manager as db_m
                    db_m.runtime_password = password
                    # Force postgres path for this submit
                    db_manager._db_mode = 'postgres'
                    
                    # Check if DB exists
                    db_exists = db_manager.check_database_exists(password)

                    if not db_exists and st.session_state['db_check_result'] == 'unchecked':
                        st.session_state['db_check_result'] = 'not_found'
                        st.rerun()
                    else:
                        with st.spinner("Initializing Postgres..."):
                            if db_manager.ensure_ready(password=password):
                                st.session_state['authenticated'] = True
                                st.session_state['db_pass'] = password
                                st.success("Postgres Connected!")
                                st.rerun()
                            else:
                                st.error("❌ Connection failed.")

    with col2:
        st.subheader("Demo Mode (Zero-setup and slow)")
        st.info("Uses a local file database (`ivs_local.db`). No installation required.")
        if st.button("🚀 Start Demo Mode", use_container_width=True):
            # DO NOT save to config. Use session state and environment.
            import os
            os.environ['IVS_DB_MODE'] = 'sqlite'
            db_manager._db_mode = 'sqlite' 
            db_manager.init_db()
            st.session_state['demo_mode_active'] = True
            st.session_state['authenticated'] = True
            st.success("Demo Mode Ready!")
            st.rerun()

    st.stop()
    return False

def delete_image_and_get_affected_ids(image_id, file_path):
    """Delete image from DB, trash file, and return affected IDs WITHOUT recomputing."""
    image_id = int(image_id)
    conn = None
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()

        cur.execute("SELECT file_path FROM images WHERE id = %s", (image_id,))
        path_row = cur.fetchone()
        
        if path_row is None:
            logger.error(f"❌ Image ID {image_id} not found in database for deletion.")
            st.error(f"❌ Image ID {image_id} not found in database")
            return []
        
        delete_path = path_row[0]
        logger.info(f"Deleting {image_id}, path: {delete_path}")
        
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

        cur.execute("DELETE FROM images WHERE id = %s", (image_id,))
        conn.commit()
        logger.info(f"Image ID {image_id} deleted from database.")
        
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
        return []
    finally:
        if conn: db_manager.put_conn(conn)

def delete_image(image_id, file_path):
    affected_ids = delete_image_and_get_affected_ids(image_id, file_path)
    if affected_ids:
        recompute_affected(affected_ids)
    return affected_ids

def recompute_affected(affected_ids):
    if not affected_ids:
        return False
    logger.info(f"Starting in-process recomputation for {len(affected_ids)} affected IDs.")
    try:
        results = distance_calculator.compute_batch(affected_ids)
        updated_count = sum(1 for r in results if r is not None)
        logger.info(f"In-process recomputation complete. Updated {updated_count}/{len(affected_ids)} IDs.")
        return True
    except Exception as e:
        logger.error(f"❌ In-process recompute error: {e}")
        st.error(f"❌ Recompute error: {e}")
        return False

def render_image_card(row, show_detail=True, show_delete=True, is_main=False, idx=None):
    # Adjust column ratio based on importance
    # Main image gets more space (2:1), list items get less (1:2)
    col_ratio = [2, 1] if is_main else [1, 2]
    col1, col2 = st.columns(col_ratio)
    
    with col1:
        if os.path.exists(row['file_path']):
            # Use container width for dynamic sizing
            st.image(row['file_path'], caption=row['file_name'], use_container_width=True)
        else:
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
        
        col_detail, col_open, col_delete = st.columns(3)
        if show_detail:
            with col_detail:
                st.write(
                    f'<a href="/image_details?image_id={row["id"]}" target="_self">'
                    f'<button style="background-color: #f0f0f0; padding: 5px 10px; border: 1px solid #ccc; cursor: pointer;">Details</button></a>',
                    unsafe_allow_html=True
                )
        with col_open:
            if st.button("Open", key=f"open_{row['id']}_{idx if idx is not None else 0}"):
                if os.path.exists(row['file_path']):
                    open_file_cross_platform(row['file_path'])
        if show_delete:
            with col_delete:
                del_key = f"del_{row['id']}" if idx is None else f"del_{row['id']}_{idx}"
                if st.button("Delete", key=del_key):
                    delete_image(row['id'], row['file_path'])
                    st.rerun()
