import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import click

from config_loader import config
from db_manager import db_manager
from file_scanner import file_scanner
from score_manager import score_manager
from utils.logger import get_logger

logger = get_logger(__name__)

# Extract values
ROOT_FOLDER = config.paths.root_folder

@click.command()
@click.option('--paths', default="", help="Comma-separated list of paths to update (targeted mode).")
@click.option('--full', is_flag=True, help="Update all images in the root folder.")
@click.option('--incremental', is_flag=True, help="Only update images with NULL scores in DB.")
@click.pass_context
def main(ctx, paths, full, incremental):
    if not paths and not full and not incremental:
        click.echo(ctx.get_help())
        return

    logger.info("Starting score update...")
    
    target_paths = [p.strip() for p in paths.split(",") if p.strip()] if paths else None
    
    if target_paths:
        # Targeted mode: Update only provided paths
        logger.info(f"Targeted update for {len(target_paths)} paths.")
        local_paths = set(target_paths)
    elif incremental:
        # Incremental mode: Get NULL score paths from DB
        conn = db_manager.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT file_path FROM images WHERE score IS NULL")
        local_paths = set(row[0] for row in cur.fetchall())
        cur.close()
        db_manager.put_conn(conn)
        logger.info(f"Incremental mode: Found {len(local_paths)} unscored images in DB.")
    elif full:
        # Full mode: Collect all local paths
        local_paths = file_scanner.collect_local_image_paths()
        logger.info(f"Full mode: Collected {len(local_paths)} local image paths.")
    else:
        logger.error("Please specify either --paths or --full.")
        return

    if not score_manager.rules:
        logger.info("No score rules defined in config.json. Skipping updates.")
    else:
        # Multi-threaded score computation
        path_scores = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(score_manager.compute_score_for_path, path) for path in local_paths]
            for future in as_completed(futures):
                try:
                    path, score = future.result()
                    path_scores[path] = score
                except Exception as e:
                    logger.error(f"Error computing score for {future}: {e}")

        # Update only if different
        updated_count = score_manager.update_scores_in_db(path_scores)
        logger.info(f"Score updates complete! Updated {updated_count} images.")

    logger.info("Score update done!")

if __name__ == '__main__':
    main()
