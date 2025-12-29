import streamlit as st
import pandas as pd
import os
from psycopg2 import Error as psycopg2_Error

from config_loader import config
from db_manager import db_manager
from components import delete_image_and_get_affected_ids, recompute_affected
from utils.logger import get_logger

# MUST BE FIRST
st.set_page_config(page_title="Batch Recursive Delete", layout="wide")

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
    """Get leaderboard data with proper filtering"""
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
    except psycopg2_Error as e:
        logger.error(f"Database error fetching leaderboard: {e}")
        st.error(f"Database error: {e}")
        df = pd.DataFrame()
    finally:
        if conn: db_manager.put_conn(conn)
    
    return df

# Streamlit UI
st.title("⚡ Batch Recursive Delete")

# Initialize session state for batch delete
if 'batch_processing' not in st.session_state:
    st.session_state['batch_processing'] = False
if 'batch_deleted_count' not in st.session_state:
    st.session_state['batch_deleted_count'] = 0

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
        key="batch_recursive_delete_sort_mode",
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
        key="batch_recursive_delete_max_score",
        help="Default from config.json"
    )
with col3:
    new_min_score = st.number_input(
        "Min score to include:", 
        value=min_score, 
        min_value=0, 
        max_value=10, 
        key="batch_recursive_delete_min_score",
        help="Default from config.json"
    )
with col4:
    exclude_none_score = st.checkbox("Hide unscored images", key="batch_recursive_delete_exclude_none")

if new_max_score != score_range.get('above', 10) or new_min_score != score_range.get('below', 0):
    config.update_section('score_range', {'above': new_max_score, 'below': new_min_score})
    config.save_config()
    st.experimental_set_query_params(max_score=str(new_max_score), min_score=str(new_min_score))
    st.success("Score range saved!")
    logger.info(f"Score range saved: max_score={new_max_score}, min_score={new_min_score}")

# Batch mode selection
batch_mode = st.selectbox(
    "Delete Mode:", 
    ["number", "distance"],
    key="batch_recursive_delete_batch_mode_select",
    format_func=lambda x: "Stop After N Deletes" if x == "number" else "Stop at Distance Threshold"
)

if batch_mode == "number":
    batch_n = st.number_input(
        "Number of images to delete:", 
        min_value=1, 
        value=1, 
        key="batch_recursive_delete_batch_n"
    )
    threshold_input = st.empty()
else:
    batch_n = st.empty()
    threshold_input = st.number_input(
        "Stop when Nearest Distance >=:", 
        min_value=0.0001, 
        format="%.4f", 
        value=0.0004, 
        step=0.0001, 
        key="batch_recursive_delete_batch_threshold"
    )

# New: Batch Size input
batch_iteration_size = st.selectbox(
    "Images to process per iteration (Batch Size):",
    [1, 2],
    index=0,
    key="batch_recursive_delete_iteration_size",
    help="Number of images (Top 1, Top 3, etc.) to attempt to delete in a single step."
)

# Control buttons
col_start, col_stop = st.columns([1, 1])

with col_start:
    if st.button("🚀 Start Batch", key="batch_recursive_delete_start_batch", disabled=st.session_state.get('batch_processing', False)):
        # Fetch total images once at the start
        conn = None
        try:
            conn = get_read_conn()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM images")
            st.session_state['total_images_at_start'] = cur.fetchone()[0]
            cur.close()
        except Exception as e:
            logger.error(f"Error fetching total image count: {e}")
            st.session_state['total_images_at_start'] = "N/A"
        finally:
            if conn: db_manager.put_conn(conn)

        # Check if distance threshold is already met before starting
        if batch_mode == "distance":
            current_df = get_leaderboard_df(sort_mode, new_max_score, new_min_score, exclude_none_score, limit=1)
            if not current_df.empty and current_df.iloc[0]['min_distance'] >= threshold_input:
                st.info(f"Threshold already met: {current_df.iloc[0]['min_distance']:.6f} >= {threshold_input:.6f}. Batch will not start.")
                logger.info("Batch delete not started: Distance threshold already met.")
                st.session_state['batch_processing'] = False # Ensure it doesn't start
                st.rerun()

        st.session_state['batch_processing'] = True
        st.session_state['batch_mode'] = batch_mode
        st.session_state['batch_deleted_count'] = 0 # Reset count on start
        st.session_state['batch_iteration_size'] = batch_iteration_size # Store batch size

        if batch_mode == "number":
            st.session_state['batch_remaining'] = batch_n
            st.session_state['batch_n'] = batch_n # Store original n
        else:
            st.session_state['batch_remaining'] = float('inf')
            st.session_state['batch_threshold'] = threshold_input
        logger.info(f"Batch delete started: mode={batch_mode}, n={batch_n}, threshold={threshold_input}, iteration_size={batch_iteration_size}")
        st.rerun()

with col_stop:
    if st.button("⏹️ Stop Batch", key="batch_recursive_delete_stop_batch", disabled=not st.session_state.get('batch_processing', False)):
        st.session_state['stop_requested'] = True
        logger.info("Stop request received. Finishing current iteration before stopping.")
        st.info("Stop request received. The batch will stop after the current deletion finishes.")

# Automated batch delete logic
if st.session_state.get('batch_processing', False):
    # Check for stop request at the beginning of the iteration
    if st.session_state.get('stop_requested', False):
        st.session_state['batch_processing'] = False
        st.session_state['stop_requested'] = False # Reset flag
        for key in ['batch_remaining', 'batch_mode', 'batch_threshold', 'batch_n', 'batch_deleted_count', 'current_top_min_distance', 'total_images_at_start', 'batch_iteration_size']:
            if key in st.session_state:
                del st.session_state[key]
        st.success("Batch delete stopped!")
        logger.info("Batch delete stopped by user request.")
        st.rerun()

    # Display progress/status
    if st.session_state['batch_mode'] == "number":
        total_to_delete = st.session_state.get('batch_n', 0)
        progress_text = f"Deleting {st.session_state['batch_deleted_count']}/{total_to_delete} images..."
        progress_value = (st.session_state['batch_deleted_count'] / total_to_delete) if total_to_delete > 0 else 0
        st.progress(progress_value, text=progress_text)
    else: # distance mode
        # Only display current top image min_distance
        current_top_min_distance = st.session_state.get('current_top_min_distance')
        if current_top_min_distance is not None:
            st.info(f"Current top image min_distance: {current_top_min_distance:.6f} (Threshold: {st.session_state['batch_threshold']:.6f})")
        else:
            st.info(f"Current top image min_distance: N/A (Threshold: {st.session_state['batch_threshold']:.6f})")

    with st.spinner("🔄 Deleting..."):
        # New batch deletion logic
        batch_size = st.session_state.get('batch_iteration_size', 1)
        limit = 3 if batch_size == 2 else 1
        df = get_leaderboard_df(sort_mode, new_max_score, new_min_score, exclude_none_score, limit=limit)

        if df.empty:
            st.session_state['batch_processing'] = False
            st.warning("No more images to delete.")
            logger.info("Batch delete auto-step stopped: No more images to delete.")
            st.rerun()

        deleted_count_this_iteration = 0
        combined_affected_ids = set()
        messages = []

        if batch_size == 1:
            if not df.empty:
                image_to_delete = df.iloc[0]
                image_id = image_to_delete['id']
                image_path = image_to_delete['file_path']
                affected = delete_image_and_get_affected_ids(image_id, image_path)
                if affected:
                    combined_affected_ids.update(affected)
                messages.append(f"Deleted: {image_to_delete['file_name']}")
                deleted_count_this_iteration += 1
        elif batch_size == 2:
            # Process Top 1 (Image A)
            if len(df) > 0:
                top_1_row = df.iloc[0]
                top_1_id = top_1_row['id']
                top_1_path = top_1_row['file_path']
                affected_by_top_1 = delete_image_and_get_affected_ids(top_1_id, top_1_path)
                if affected_by_top_1:
                    combined_affected_ids.update(affected_by_top_1)
                messages.append(f"Deleted: {top_1_row['file_name']}")
                deleted_count_this_iteration += 1

            # Process Top 3 (Image B), if it exists and is not already affected by Top 1
            if len(df) >= 3:
                top_3_row = df.iloc[2]
                top_3_id = top_3_row['id']
                if top_3_id not in combined_affected_ids:
                    top_3_path = top_3_row['file_path']
                    affected_by_top_3 = delete_image_and_get_affected_ids(top_3_id, top_3_path)
                    if affected_by_top_3:
                        combined_affected_ids.update(affected_by_top_3)
                    messages.append(f"Deleted: {top_3_row['file_name']}")
                    deleted_count_this_iteration += 1

        if combined_affected_ids:
            # Exclude the deleted images themselves from the recomputation list
            deleted_ids_in_batch = {df.iloc[i*2]['id'] for i in range(batch_size) if i*2 < len(df)}
            final_affected_ids = list(combined_affected_ids - deleted_ids_in_batch)
            recompute_success = recompute_affected(final_affected_ids)
            if recompute_success:
                st.success(f"🔄 Recomputed {len(final_affected_ids)} images.")

        st.success("; ".join(messages))
        logger.info(f"Batch delete auto-step: {'; '.join(messages)}")
        st.session_state['batch_deleted_count'] += deleted_count_this_iteration

        # Get new top min_distance for display and stop condition
        new_df = get_leaderboard_df(sort_mode, new_max_score, new_min_score, exclude_none_score, limit=1)
        new_top_min_distance = new_df.iloc[0]['min_distance'] if not new_df.empty else None
        st.session_state['current_top_min_distance'] = new_top_min_distance

        # CHECK STOP CONDITIONS
        if st.session_state.get('batch_mode') == "number":
            st.session_state['batch_remaining'] -= deleted_count_this_iteration
            if st.session_state['batch_remaining'] <= 0:
                st.session_state['batch_processing'] = False
                st.success(f"✅ Batch complete! Deleted {st.session_state.get('batch_n', 'N')} images.")
                logger.info(f"Batch delete complete: Deleted {st.session_state.get('batch_n', 'N')} images.")
                for key in ['batch_remaining', 'batch_mode', 'batch_threshold', 'batch_n', 'batch_deleted_count', 'current_top_min_distance', 'total_images_at_start', 'batch_iteration_size']:
                    if key in st.session_state:
                        del st.session_state[key]
        else:  # distance mode
            if new_top_min_distance is not None and new_top_min_distance >= st.session_state['batch_threshold']:
                st.session_state['batch_processing'] = False
                st.success(f"✅ Stopped at threshold: {new_top_min_distance:.6f} >= {st.session_state['batch_threshold']:.6f}")
                logger.info(f"Batch delete stopped at threshold: {new_top_min_distance:.6f} >= {st.session_state['batch_threshold']:.6f}")
                for key in ['batch_remaining', 'batch_mode', 'batch_threshold', 'batch_n', 'batch_deleted_count', 'current_top_min_distance', 'batch_iteration_size']:
                    if key in st.session_state:
                        del st.session_state[key]
    
    st.rerun()

# Instructions
with st.expander("📖 How Batch Delete Works"):
    st.markdown("""
    **Recursive Top-1 Deletion:**
    1. Delete current #1 image
    2. Recompute distances for affected images  
    3. Refresh leaderboard
    4. Repeat until stop condition
    
    **Use Cases:**
    - **Number mode**: Clean exactly N outliers
    - **Distance mode**: Remove until collection is "cohesive" (min_distance >= threshold)
    """)

# Footer
st.markdown("---")
st.markdown("*Fast recomputation keeps leaderboard accurate after every delete*")
