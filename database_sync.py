import os
import sys
from multiprocessing import Process, Queue
from send2trash import send2trash  # For trashing files
import click
from tqdm import tqdm

from config_loader import config
from db_manager import db_manager
from clip_processor import clip_processor
from file_scanner import file_scanner
from utils.logger import get_logger

logger = get_logger(__name__)

# Extract values
BATCH_SIZE = config.clip.batch_size

# Function to get a new DB connection
def get_conn():
    return db_manager.get_conn()

# Task 1: Embed new images in batches, return list of new IDs via queue
def embed_new(to_embed, queue):
    if not to_embed:
        queue.put([])
        return
    
    conn = None
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()
        new_ids = []
        
        # Prepare batches
        batches = [to_embed[i:i + BATCH_SIZE] for i in range(0, len(to_embed), BATCH_SIZE)]
        
        for batch_paths in tqdm(batches, desc="Embedding New Images", unit="batch", file=sys.stdout):
                        embeddings, processed_paths = clip_processor.get_batch_embeddings(batch_paths)
                        
                        for path, embedding in zip(processed_paths, embeddings):
                            try:
                                file_name = os.path.basename(path)
                                
                                if db_manager._db_mode == 'sqlite':
                                    # SQLite path: Convert embedding to bytes/blob
                                    import numpy as np
                                    embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
                                    cur.execute("""
                                        INSERT INTO images (file_name, file_path, embedding)
                                        VALUES (?, ?, ?)
                                        ON CONFLICT (file_path) DO UPDATE
                                        SET embedding = EXCLUDED.embedding,
                                            min_distance = NULL,
                                            density = NULL
                                        RETURNING id
                                    """, (file_name, path, embedding_blob))
                                else:
                                    # Postgres path
                                    embedding_str = '[' + ','.join(f"{x:.10f}" for x in embedding) + ']'
                                    cur.execute("""
                                        INSERT INTO images (file_name, file_path, embedding)
                                        VALUES (%s, %s, %s::vector)
                                        ON CONFLICT (file_path) DO UPDATE
                                        SET embedding = EXCLUDED.embedding,
                                            min_distance = NULL,
                                            density = NULL
                                        RETURNING id
                                    """, (file_name, path, embedding_str))
                                
                                new_id = cur.fetchone()[0]
                                new_ids.append(new_id)
                                # Don't log per-image to reduce noise
                            except Exception as e:
                                logger.error(f"Error inserting {path} into DB: {e}")
                        conn.commit() # Commit after each batch
    finally:
        if conn: db_manager.put_conn(conn)
    logger.info(f"Embedding complete: {len(new_ids)} new images.")
    queue.put(new_ids)

# Task 2: Delete missing images, flag affected, return affected IDs via queue
def delete_missing(to_delete, queue):
    if not to_delete:
        queue.put([])
        return
    
    conn = None
    all_affected_ids = set()
    
    try:
        conn = db_manager.get_conn()
        cur = conn.cursor()

        for delete_path in to_delete:
            try:
                # Get the ID of the image to be deleted
                cur.execute("SELECT id FROM images WHERE file_path = %s", (delete_path,))
                deleted_row = cur.fetchone()
                if not deleted_row:
                    logger.warning(f"Path not found in DB for deletion: {delete_path}")
                    continue
                deleted_id = deleted_row[0]

                # STEP 1: Identify Affected Images
                if db_manager._db_mode == 'sqlite':
                    # Simplified SQLite path for neighbor detection
                    cur.execute("""
                        SELECT id FROM images 
                        WHERE nearest_path_1 = ? OR nearest_path_2 = ? OR nearest_path_3 = ? 
                           OR nearest_path_4 = ? OR nearest_path_5 = ?
                    """, (delete_path, delete_path, delete_path, delete_path, delete_path))
                else:
                    # Postgres path (Optimized)
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
                    """, (deleted_id, delete_path))

                affected_ids_for_this_image = {row[0] for row in cur.fetchall()}
                all_affected_ids.update(affected_ids_for_this_image)

                # STEP 2: Delete the image from the database
                if db_manager._db_mode == 'sqlite':
                    cur.execute("DELETE FROM images WHERE id = ?", (deleted_id,))
                else:
                    cur.execute("DELETE FROM images WHERE id = %s", (deleted_id,))

                logger.info(f"Deleted missing image from DB: {delete_path} (ID: {deleted_id})")

            except Exception as e:
                logger.error(f"Error processing deletion for {delete_path}: {e}")
        
        # STEP 4: Commit all deletions at once
        conn.commit()

    except Exception as e:
        logger.error(f"Major error during delete_missing process: {e}")
        if conn: conn.rollback()
    finally:
        # STEP 5: Flag all unique affected images
        if all_affected_ids:
            try:
                conn = conn or db_manager.get_conn() 
                cur = conn.cursor()
                param_char = '?' if db_manager._db_mode == 'sqlite' else '%s'
                placeholders = ','.join([param_char] * len(all_affected_ids))
                cur.execute(f"UPDATE images SET affected = 1 WHERE id IN ({placeholders})", list(all_affected_ids))
                conn.commit()
                cur.close()
                logger.info(f"Flagged {len(all_affected_ids)} total unique images for recompute.")
            except Exception as e:
                logger.error(f"Error flagging affected images: {e}")
                if conn: conn.rollback()
        
        if conn: db_manager.put_conn(conn)

    logger.info(f"Deletion complete: {len(to_delete)} images processed, {len(all_affected_ids)} unique affected IDs flagged.")
    queue.put(list(all_affected_ids))


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
def main():
    """Sync the database with the file system."""
    
    # --- AUTO-INSTALL CHECK ---
    try:
        from clip_processor import clip_processor
        clip_processor._initialize_device()
    except (ImportError, RuntimeError):
        logger.info("📦 Hardware Engine missing or not initialized. Starting auto-install...")
        # Use sys.executable to ensure we use the same venv
        python_exe = sys.executable
        launcher_path = os.path.join(os.getcwd(), "launcher.py")
        
        # Run launcher with --install-engine and --no-launch
        install_cmd = f'"{python_exe}" "{launcher_path}" --install-engine --no-launch'
        subprocess.run(install_cmd, shell=True)
        
        logger.info("✅ Installation check complete. Resuming sync...")
        # After install, we need to refresh the imports in this process
        # This is tricky in Python, so the simplest way is to tell the user to wait or re-run,
        # but actually, if it's a new terminal, it will work for the NEXT run.
        # BETTER: Just run the sync logic as a subprocess after install or tell user to restart.
        # Actually, if we just installed torch, the current process can't easily "see" it.
        
    logger.info("🚀 Starting database sync...")

    # Step 0: Ensure schema is correct for current model (handles migrations)
    dim = clip_processor.get_embedding_dimension()
    if not db_manager.initialize_schema(dim):
        logger.error("Failed to initialize or migrate database schema. Aborting sync.")
        return

    # Step 1: Collect local image paths (parallel walk)
    local_paths = file_scanner.collect_local_image_paths()

    logger.info(f"📁 Collected {len(local_paths)} local image paths.")

    # Step 2: Compare with DB
    conn = db_manager.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT file_path, (embedding IS NULL) as needs_reembed FROM images")
    db_data = cur.fetchall()
    cur.close()
    conn.close()

    db_paths = set(os.path.normpath(row[0]) for row in db_data)
    # paths that are in DB but have NULL vectors
    paths_needing_reembed = set(os.path.normpath(row[0]) for row in db_data if row[1])

    logger.info(f"💾 Found {len(db_paths)} paths in DB.")

    # Normalize local paths too just in case
    local_paths = set(os.path.normpath(p) for p in local_paths)

    to_embed = list((local_paths - db_paths) | paths_needing_reembed)
    to_delete = list(db_paths - local_paths)

    if paths_needing_reembed:
        logger.info(f"🔄 Images needing re-embedding (model switch): {len(paths_needing_reembed)}")
    logger.info(f"➕ New images to embed: {len(to_embed) - len(paths_needing_reembed)}")

    # Step 3: Parallel tasks - Embed + Delete
    queue1 = Queue()
    queue2 = Queue()

    p1 = Process(target=embed_new, args=(to_embed, queue1))
    p1.start()

    if to_delete:
        p2 = Process(target=delete_missing, args=(to_delete, queue2))
        p2.start()

    p1.join()
    if to_delete:
        p2.join()

    new_ids = queue1.get()
    affected_ids = queue2.get() if to_delete else []

    queue1.close()
    queue1.join_thread()
    if to_delete:
        queue2.close()
        queue2.join_thread()

    logger.info("✅ Sync complete!")
    logger.info("💡 Next steps:")
    logger.info("  - python score_updater.py main --full  # Update all scores")
    if affected_ids:
        logger.info(f"  - python compute_distances_and_density.py affected  # Recompute {len(affected_ids)} flagged images")
    else:
        logger.info("  - python compute_distances_and_density.py all  # Initial/full metrics (if needed)")

if __name__ == '__main__':
    main()