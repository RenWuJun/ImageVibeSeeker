import os
import psycopg2
from config_loader import config
from db_manager import db_manager
from utils.logger import get_logger

logger = get_logger(__name__)

class ScoreManager:
    def __init__(self):
        self.rules = config.scores.rules

    def compute_score_for_path(self, path):
        md_path = os.path.splitext(path)[0] + '.md'
        score = None
        if os.path.exists(md_path):
            try:
                with open(md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if content.startswith('---\n'):
                    end_idx = content.find('\n---\n', 4)
                    if end_idx > 0:
                        fm = content[4:end_idx]
                        for rule in self.rules:  # Ordered: first match wins (highest score first)
                            if rule['keyword'] in fm:
                                score = rule['score']
                                break
            except Exception as e:
                logger.warning(f"Could not read or parse MD file {md_path}: {e}")
        return path, score

    def update_scores_in_db(self, path_scores):
        conn = None
        updated_count = 0

        if not self.rules:
            logger.info("No score rules defined in config.json. Skipping score updates.")
            return 0

        if not path_scores:
            return 0

        try:
            conn = db_manager.get_conn()
            cur = conn.cursor()

            # Fetch current DB scores in bulk for the paths we are updating
            placeholders = ','.join(['%s'] * len(path_scores))
            try:
                cur.execute(f"SELECT file_path, score FROM images WHERE file_path IN ({placeholders})", list(path_scores.keys()))
                db_scores = {os.path.normpath(row[0]): row[1] for row in cur.fetchall()}
            except psycopg2.Error as e:
                logger.error(f"Database error fetching current scores: {e}")
                cur.close()
                raise # Re-raise to trigger outer rollback

            for path, new_score in path_scores.items():
                current_score = db_scores.get(os.path.normpath(path))
                if new_score != current_score:
                    try:
                        cur.execute("UPDATE images SET score = %s WHERE file_path = %s", (new_score, path))
                        updated_count += 1
                        logger.info(f"Updated score to {new_score} for {path}")
                    except psycopg2.Error as e:
                        logger.error(f"Database error updating score for {path}: {e}")
                        raise # Re-raise to trigger outer rollback

            conn.commit()
            cur.close()
        except Exception as e:
            logger.error(f"Major error during update_scores_in_db: {e}")
            if conn: conn.rollback()
            updated_count = 0 # Indicate failure
        finally:
            if conn: db_manager.put_conn(conn)
        return updated_count

# Global instance for easy access
score_manager = ScoreManager()

# Example usage (for testing/demonstration)
if __name__ == "__main__":
    logger.info("Testing ScoreManager...")
    # Example of how to use it (requires a running DB and images)
    # from file_scanner import file_scanner
    # paths = file_scanner.collect_local_image_paths()
    # path_scores = {}
    # for path in paths:
    #     p, s = score_manager.compute_score_for_path(path)
    #     path_scores[p] = s
    # updated = score_manager.update_scores_in_db(path_scores)
    # logger.info(f"Updated {updated} scores.")
