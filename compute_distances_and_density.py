import psycopg2
import numpy as np
import argparse
import os
import time
from multiprocessing import Pool
from tqdm import tqdm
import psycopg2.extras
import click

from config_loader import config
from db_manager import db_manager
from distance_calculator import distance_calculator
from utils.logger import get_logger

logger = get_logger(__name__)

# Extract values from config
BATCH_SIZE = config.clip.batch_size # Re-using batch size from clip config

def create_hnsw_index():
    """Create HNSW index for 100x faster k-NN (run ONCE)"""
    if db_manager._db_mode == 'sqlite':
        logger.info("⚡ Local Mode (SQLite) uses native sqlite-vec structures. Manual HNSW indexing is not required.")
        return

    conn = db_manager.get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS images_embedding_hnsw 
            ON images USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """
        )
        conn.commit()
        logger.info("HNSW index created/verified (100x faster k-NN!).")
    except Exception as e:
        logger.error(f"HNSW index error: {e}")
    finally:
        cur.close()
        db_manager.put_conn(conn)

def compute_for_ids(id_list, batch_size=1000):
    """OPTIMIZED: Batch processing + progress for 100k+"""
    if not id_list:
        logger.info("No IDs provided.")
        return
    
    logger.info(f"Processing {len(id_list)} IDs in batches of {batch_size} (sequentially for debugging)...")
    
    # Smart chunking
    batches = [id_list[i:i + batch_size] for i in range(0, len(id_list), batch_size)]
    
    total_updated = 0
    with tqdm(total=len(batches), desc="Batches") as pbar:
        for batch in batches:
            batch_result = distance_calculator.compute_batch(batch)
            updated_in_batch = sum(1 for r in batch_result if r is not None)
            total_updated += updated_in_batch
            pbar.update(1)
    
    logger.info(f"Recompute COMPLETE! Updated {total_updated}/{len(id_list)} IDs")
    return total_updated

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """CLI for computing image distances and density."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

@cli.command()
@click.option('--ids', default="", help="Comma-separated IDs to recompute.")
def ids(ids):
    """Recompute specific images by ID."""
    id_list = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
    if id_list:
        compute_for_ids(id_list, batch_size=100)
        logger.info("Specific IDs recompute complete!")
    else:
        logger.info("No valid IDs provided.")

@cli.command()
def all():
    """Recompute ALL images."""
    logger.info("=== 100K+ OPTIMIZED RECOMPUTE ===")
    conn = db_manager.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM images WHERE embedding IS NOT NULL")
    id_list = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    
    logger.info(f"Found {len(id_list)} images to recompute...")
    compute_for_ids(id_list, batch_size=1000)
    
    # Reset all flags
    conn = db_manager.get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE images SET affected = 0")
    affected_count = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    if affected_count > 0:
        logger.info(f"Cleared {affected_count} affected flags.")
    logger.info("Full recompute complete!")

@cli.command()
def affected():
    """Recompute images flagged as affected=1."""
    logger.info("Targeting affected images...")
    conn = db_manager.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM images WHERE affected = 1")
    id_list = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    if id_list:
        logger.info(f"Targeting {len(id_list)} affected images for recomputation: {id_list}")
        compute_for_ids(id_list, batch_size=500)
        # Reset flags
        conn = db_manager.get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE images SET affected = 0 WHERE affected = 1")
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Reset {len(id_list)} affected flags.")
    else:
        logger.info("No affected images found to recompute.")
    logger.info("Affected recompute complete!")

@cli.command('create-index')
def create_index_cmd():
    """Create HNSW index (run ONCE)."""
    create_hnsw_index()
    logger.info("HNSW index ready! Run 'all' for 100x faster recompute.")

if __name__ == "__main__":
    start_time = time.time()
    cli()
    elapsed = time.time() - start_time
    logger.info(f"TOTAL TIME: {elapsed:.1f}s ({elapsed/60:.1f}min)")