# C:\Projects\ImageVibeSeeker\tag_editor.py
import os
import sys
import click

from config_loader import config
from db_manager import db_manager
from tag_manager import tag_manager
from utils.logger import get_logger

logger = get_logger(__name__)

# UTILITY: Bulk update scores from CLI
def bulk_update_scores(image_ids, new_scores):
    """Update multiple images at once"""
    if len(image_ids) != len(new_scores):
        logger.error("IDs and scores must match in length for bulk update.")
        raise ValueError("IDs and scores must match in length")
    
    conn = db_manager.get_conn()
    cur = conn.cursor()
    
    try:
        for image_id, new_score in zip(image_ids, new_scores):
            # Get file_path for MD update
            cur.execute("SELECT file_path, score FROM images WHERE id = %s", (image_id,))
            result = cur.fetchone()
            if result:
                file_path, original_score = result
                tag_manager.update_score(image_id, new_score, file_path, original_score, streamlit=False)
            else:
                logger.warning(f"Image ID {image_id} not found for bulk update.")
        conn.commit()
        logger.info(f"Bulk update committed for {len(image_ids)} images.")
    except Exception as e:
        logger.error(f"Error during bulk update: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

@click.command()
@click.option('--test-id', type=int, help="Test single image ID.")
def main(test_id):
    """CLI for testing tag editor functionality."""
    if test_id:
        logger.info(f"Testing single update for image ID: {test_id}")
        conn = db_manager.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT file_path, score FROM images WHERE id = %s", (test_id,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            file_path, original_score = result
            logger.info(f"Testing ID {test_id}: {file_path}, score={original_score}")
            success = tag_manager.update_score(test_id, 10, file_path, original_score, streamlit=False)
            logger.info(f"Test {'PASSED' if success else 'FAILED'}")
        else:
            logger.warning(f"Test image ID {test_id} not found.")
            logger.info("Test FAILED: Image ID not found.")
    else:
        logger.info("Usage: python tag_editor.py --test-id 1")

if __name__ == "__main__":
    main()