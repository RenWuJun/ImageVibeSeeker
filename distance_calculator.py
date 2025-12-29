import psycopg2
import numpy as np
from db_manager import db_manager
from utils.logger import get_logger

logger = get_logger(__name__)

class DistanceCalculator:
    def __init__(self):
        pass

    def _get_conn(self):
        return db_manager.get_conn()

    def _compute_single(self, image_id, embedding, conn):
        """Computes metrics for a single image ID using a provided connection."""
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT id, file_path, (embedding <=> %s::vector) AS dist
                FROM images
                WHERE id != %s AND embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector ASC
                LIMIT 10
            """, (embedding, image_id, embedding))
            
            neighbors = cur.fetchall()
            if not neighbors:
                min_distance = 1.0
                density = 0.0
                nearest_paths = [None] * 10
            else:
                dists = [row[2] for row in neighbors]
                nearest_paths = [row[1] for row in neighbors]
                
                while len(dists) < 10:
                    dists.append(1.0)
                    nearest_paths.append(None)
                
                min_distance = dists[0]
                avg_top5 = sum(dists[:5]) / 5
                density = 10.0 / (avg_top5 + 1e-6)
            
            return (min_distance, density, *nearest_paths[:10], image_id)
        finally:
            cur.close()

    def compute_batch(self, ids_batch):
        """Compute distances for BATCH of IDs sequentially using connection pooling."""
        conn = None
        results = []
        updates = []
        
        try:
            conn = db_manager.get_conn()
            cur = conn.cursor()

            placeholders = ','.join(['%s'] * len(ids_batch))
            cur.execute(f"SELECT id, embedding FROM images WHERE id IN ({placeholders})", ids_batch)
            id_to_embedding = {row[0]: row[1] for row in cur.fetchall()}
            cur.close()

            for image_id in ids_batch:
                embedding = id_to_embedding.get(image_id)
                if embedding is not None:
                    update_params = self._compute_single(image_id, embedding, conn) # Pass the connection
                    if update_params:
                        updates.append(update_params)
                else:
                    logger.warning(f"Embedding not found for image ID {image_id}. Skipping recomputation.")

            if updates:
                logger.info(f"Committing batch update for {len(updates)} images. First 3 updates: {updates[:3]}")
                cur = conn.cursor()
                cur.executemany("""
                    UPDATE images SET
                        min_distance = %s, density = %s,
                        nearest_path_1 = %s, nearest_path_2 = %s, nearest_path_3 = %s,
                        nearest_path_4 = %s, nearest_path_5 = %s, nearest_path_6 = %s,
                        nearest_path_7 = %s, nearest_path_8 = %s, nearest_path_9 = %s,
                        nearest_path_10 = %s
                    WHERE id = %s
                """, updates)
                conn.commit()
                cur.close()
                results = [1] * len(updates)
                logger.info(f"Batch update for {len(updates)} images committed.")
            else:
                logger.info("No updates to commit for this batch.")

        except Exception as e:
            logger.error(f"BATCH ERROR for IDs {ids_batch[:3]}: {e}")
            if conn: conn.rollback()
            results = [None] * len(ids_batch)
        finally:
            if conn: db_manager.put_conn(conn)
        
        return results

# Global instance for easy access
distance_calculator = DistanceCalculator()



