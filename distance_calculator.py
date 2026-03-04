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
            p = db_manager.p
            if db_manager._db_mode == 'sqlite':
                # SQLite with sqlite-vec
                # Convert embedding to blob for the query
                embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
                cur.execute(f"""
                    SELECT id, file_path, vec_distance_cosine(embedding, {p}) AS dist
                    FROM images
                    WHERE id != {p} AND embedding IS NOT NULL
                    ORDER BY dist ASC
                    LIMIT 10
                """, (embedding_blob, image_id))
            else:
                # Postgres
                cur.execute(f"""
                    SELECT id, file_path, (embedding <=> {p}::vector) AS dist
                    FROM images
                    WHERE id != {p} AND embedding IS NOT NULL
                    ORDER BY embedding <=> {p}::vector ASC
                    LIMIT 10
                """, (embedding, image_id, embedding))

            neighbors = cur.fetchall()
            if not neighbors:
                min_distance = 1.0
                density = 0.0
                nearest_paths = [None] * 10
            else:
                # In SQLite Row, neighbors are row objects
                dists = [row['dist'] if db_manager._db_mode == 'sqlite' else row[2] for row in neighbors]
                nearest_paths = [row['file_path'] if db_manager._db_mode == 'sqlite' else row[1] for row in neighbors]

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
        """Compute distances for BATCH of IDs sequentially."""
        conn = None
        results = []
        updates = []

        try:
            conn = db_manager.get_conn()
            cur = conn.cursor()
            p = db_manager.p

            placeholders = ','.join([p] * len(ids_batch))
            cur.execute(f"SELECT id, embedding FROM images WHERE id IN ({placeholders})", ids_batch)
            rows = cur.fetchall()
            
            id_to_embedding = {}
            for row in rows:
                image_id = row['id'] if db_manager._db_mode == 'sqlite' else row[0]
                raw_emb = row['embedding'] if db_manager._db_mode == 'sqlite' else row[1]
                
                if db_manager._db_mode == 'sqlite' and isinstance(raw_emb, bytes):
                    # Convert blob back to array
                    id_to_embedding[image_id] = np.frombuffer(raw_emb, dtype=np.float32)
                else:
                    id_to_embedding[image_id] = raw_emb
            
            cur.close()

            for image_id in ids_batch:
                embedding = id_to_embedding.get(image_id)
                if embedding is not None:
                    update_params = self._compute_single(image_id, embedding, conn)
                    if update_params:
                        updates.append(update_params)

            if updates:
                cur = conn.cursor()
                sql = f"""
                    UPDATE images SET
                        min_distance = {p}, density = {p},
                        nearest_path_1 = {p}, nearest_path_2 = {p}, nearest_path_3 = {p},
                        nearest_path_4 = {p}, nearest_path_5 = {p}, nearest_path_6 = {p},
                        nearest_path_7 = {p}, nearest_path_8 = {p}, nearest_path_9 = {p},
                        nearest_path_10 = {p}
                    WHERE id = {p}
                """
                if db_manager._db_mode == 'sqlite':
                    cur.executemany(sql, updates)
                else:
                    cur.executemany(sql, updates)
                conn.commit()
                cur.close()
                results = [1] * len(updates)
            else:
                results = [None] * len(ids_batch)

        except Exception as e:
            logger.error(f"BATCH ERROR: {e}")
            if conn and db_manager._db_mode != 'sqlite': conn.rollback()
            results = [None] * len(ids_batch)
        finally:
            if conn: db_manager.put_conn(conn)

        return results

# Global instance for easy access
distance_calculator = DistanceCalculator()
