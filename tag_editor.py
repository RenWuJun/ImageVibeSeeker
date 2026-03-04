# C:\Projects\ImageVibeSeeker\tag_editor.py
import os
import sys
import click

from config_loader import config
from db_manager import db_manager
from tag_manager import tag_manager
from utils.logger import get_logger

logger = get_logger(__name__)

def bulk_update_scores(image_ids, new_scores):
    """Update multiple images at once"""
    if len(image_ids) != len(new_scores):
        logger.error("IDs and scores must match in length.")
        raise ValueError("IDs and scores must match in length")
    
    conn = db_manager.get_conn()
    cur = conn.cursor()
    p = db_manager.p
    
    try:
        for image_id, new_score in zip(image_ids, new_scores):
            cur.execute(f"SELECT file_path, score FROM images WHERE id = {p}", (image_id,))
            result = cur.fetchone()
            if result:
                if db_manager._db_mode == 'sqlite':
                    file_path, original_score = result['file_path'], result['score']
                else:
                    file_path, original_score = result
                tag_manager.update_score(image_id, new_score, file_path, original_score, streamlit=False)
        conn.commit()
    except Exception as e:
        logger.error(f"Error during bulk update: {e}")
        if db_manager._db_mode != 'sqlite': conn.rollback()
    finally:
        db_manager.put_conn(conn)

@click.command()
@click.option('--test-id', type=int, help="Test single image ID.")
def main(test_id):
    """CLI for testing tag editor functionality."""
    if test_id:
        conn = db_manager.get_conn()
        cur = conn.cursor()
        p = db_manager.p
        cur.execute(f"SELECT file_path, score FROM images WHERE id = {p}", (test_id,))
        result = cur.fetchone()
        db_manager.put_conn(conn)

        if result:
            if db_manager._db_mode == 'sqlite':
                file_path, original_score = result['file_path'], result['score']
            else:
                file_path, original_score = result
            success = tag_manager.update_score(test_id, 10, file_path, original_score, streamlit=False)
            logger.info(f"Test {'PASSED' if success else 'FAILED'}")
        else:
            logger.warning(f"Test image ID {test_id} not found.")

if __name__ == "__main__":
    main()
