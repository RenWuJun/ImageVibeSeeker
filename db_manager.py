import psycopg2
from psycopg2 import pool, extensions
from config_loader import config
from utils.logger import get_logger
import os
import sys
from getpass import getpass

logger = get_logger(__name__)

class DBManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBManager, cls).__new__(cls)
            cls._instance.connection_pool = None
        return cls._instance

    def _initialize_pool(self):
        """Initializes the thread-safe connection pool."""
        if self.connection_pool:
            return

        try:
            self.connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                host=config.database.host,
                database=config.database.name,
                user=config.database.user,
                password=config.database['pass']
            )
            logger.info("Threaded Database connection pool initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise

    def get_conn(self):
        """Borrow a connection from the pool. Ensures pool is initialized."""
        if not self.connection_pool:
            self._initialize_pool()
        try:
            return self.connection_pool.getconn()
        except Exception as e:
            logger.error(f"Failed to get connection from pool: {e}")
            raise

    def put_conn(self, conn):
        """Return a connection to the pool."""
        if conn and self.connection_pool:
            self.connection_pool.putconn(conn)

    def ensure_ready(self):
        """
        High-level entry point for the Launcher.
        Ensures Database exists, Schema is applied, and Pool is ready.
        """
        target_db = config.database.name
        target_user = config.database.user
        target_pass = config.database['pass']
        host = config.database.host

        print(f"--- Checking Database: {target_db} ---")

        # 1. Try to connect to the target DB directly
        try:
            conn = psycopg2.connect(dbname=target_db, user=target_user, password=target_pass, host=host)
            conn.close()
            logger.info(f"Database '{target_db}' is accessible.")
        except psycopg2.OperationalError:
            # 2. If fails, try to create it
            print(f"⚠️  Database '{target_db}' not found. Attempting to create...")
            if not self._create_database(target_db, target_user, target_pass, host):
                return False

        # 3. Now that it exists, apply the schema
        from clip_processor import clip_processor
        dim = clip_processor.get_embedding_dimension()
        return self.initialize_schema(dim)

    def _create_database(self, dbname, user, password, host):
        """Connects to system 'postgres' DB to create the target database."""
        con_system = None
        try:
            # Try connecting with config credentials first
            con_system = psycopg2.connect(dbname='postgres', user=user, password=password, host=host)
            con_system.set_isolation_level(extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        except psycopg2.Error:
            print("❌ Access Denied. Please provide PostgreSQL Admin credentials (usually 'postgres').")
            admin_user = input("Admin Username (default 'postgres'): ") or 'postgres'
            admin_pass = getpass("Admin Password: ")
            try:
                con_system = psycopg2.connect(dbname='postgres', user=admin_user, password=admin_pass, host=host)
                con_system.set_isolation_level(extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            except Exception as e:
                logger.error(f"Failed to connect as admin: {e}")
                return False

        try:
            cur = con_system.cursor()
            cur.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{dbname}'")
            if not cur.fetchone():
                cur.execute(f"CREATE DATABASE {dbname};")
                print(f"✅ Database '{dbname}' created.")
            cur.close()
            con_system.close()
            return True
        except Exception as e:
            logger.error(f"Error during DB creation: {e}")
            return False

    def initialize_schema(self, dimension):
        """Creates or verifies the images table, performing migration if dimensions changed."""
        conn = None
        try:
            conn = self.get_conn()
            cur = conn.cursor()
            
            # Check if table exists
            cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'images');")
            table_exists = cur.fetchone()[0]
            
            if not table_exists:
                self._execute_schema_logic(conn, dimension)
            else:
                # Check for dimension mismatch
                current_dim = self.get_current_dimension()
                if current_dim and current_dim != dimension:
                    print(f"⚠️  Model Dimension Mismatch! DB: {current_dim}, Config: {dimension}")
                    print("🔄 Migrating database to new model (preserving scores/tags)...")
                    self._migrate_embeddings(conn, dimension)
                else:
                    # Just run standard logic to ensure indexes/extensions exist
                    self._execute_schema_logic(conn, dimension)
            
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize/migrate schema: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if conn: self.put_conn(conn)

    def get_current_dimension(self):
        """Queries the database to find the current dimension of the embedding column."""
        conn = None
        try:
            conn = self.get_conn()
            cur = conn.cursor()
            # This query gets the dimension from pgvector's type modifier
            cur.execute("""
                SELECT atttypmod 
                FROM pg_attribute 
                WHERE attrelid = 'images'::regclass AND attname = 'embedding';
            """)
            result = cur.fetchone()
            return result[0] if result else None
        except Exception:
            return None
        finally:
            if conn: self.put_conn(conn)

    def _migrate_embeddings(self, conn, new_dimension):
        """Drops old embeddings and indexes, prepares table for new model size while keeping metadata."""
        cur = conn.cursor()
        try:
            # 1. Drop the HNSW index (it's tied to the old dimension)
            cur.execute("DROP INDEX IF EXISTS images_embedding_hnsw;")
            
            # 2. Drop and recreate the embedding column
            # (In Postgres/pgvector, you can't easily change dimension of an existing column with data)
            cur.execute("ALTER TABLE images DROP COLUMN IF EXISTS embedding;")
            cur.execute(f"ALTER TABLE images ADD COLUMN embedding vector({new_dimension});")
            
            # 3. Reset metrics that were specific to the old model
            cur.execute("""
                UPDATE images SET 
                    min_distance = NULL, 
                    density = NULL,
                    nearest_path_1 = NULL, nearest_path_2 = NULL, nearest_path_3 = NULL,
                    nearest_path_4 = NULL, nearest_path_5 = NULL, nearest_path_6 = NULL,
                    nearest_path_7 = NULL, nearest_path_8 = NULL, nearest_path_9 = NULL,
                    nearest_path_10 = NULL;
            """)
            
            conn.commit()
            logger.info(f"✅ Migration to vector({new_dimension}) complete. Metadata preserved.")
        finally:
            cur.close()

    def _execute_schema_logic(self, conn, dimension):
        """Internal logic to apply the schema to a provided connection."""
        cur = conn.cursor()
        try:
            logger.info(f"Applying schema with vector dimension: {dimension}")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS images (
                    id SERIAL PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL UNIQUE,
                    embedding vector({dimension}),
                    score INTEGER,
                    min_distance FLOAT,
                    density FLOAT,
                    nearest_path_1 TEXT,
                    nearest_path_2 TEXT,
                    nearest_path_3 TEXT,
                    nearest_path_4 TEXT,
                    nearest_path_5 TEXT,
                    nearest_path_6 TEXT,
                    nearest_path_7 TEXT,
                    nearest_path_8 TEXT,
                    nearest_path_9 TEXT,
                    nearest_path_10 TEXT,
                    affected INTEGER DEFAULT 0
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_path ON images(file_path);")
            conn.commit()
            logger.info("✅ Database schema applied successfully.")
        finally:
            cur.close()

    def close_all_conns(self):
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("Database connection pool closed.")

db_manager = DBManager()

if __name__ == "__main__":
    # This allows launcher.py to call this file using the venv python
    if not db_manager.ensure_ready():
        sys.exit(1)
    sys.exit(0)