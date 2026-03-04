import sqlite3
import psycopg2
from psycopg2 import pool
import os
import json
from config_loader import config
from utils.logger import get_logger

logger = get_logger(__name__)

runtime_password = None

class DatabaseManager:
    def __init__(self):
        self._pg_pool = None
        self._db_mode = os.environ.get("IVS_DB_MODE", config.database.get('mode', 'postgres'))
        self._sqlite_path = os.path.join(os.getcwd(), "ivs_local.db")

    @property
    def p(self):
        """Returns the appropriate parameter placeholder."""
        return '?' if self._db_mode == 'sqlite' else '%s'

    def _get_pg_config(self):
        global runtime_password
        return {
            "host": config.database.get('host', 'localhost'),
            "database": config.database.get('name', 'imagevibeseeker'),
            "user": config.database.get('user', 'postgres'),
            "password": runtime_password or os.environ.get("IVS_DB_PASS")
        }

    def get_conn(self):
        if self._db_mode == 'sqlite':
            conn = sqlite3.connect(self._sqlite_path)
            conn.row_factory = sqlite3.Row
            # Load sqlite-vec extension if available
            try:
                import sqlite_vec
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
            except Exception as e:
                logger.warning(f"Could not load sqlite-vec: {e}. Vector search will use slow fallback.")
            return conn
        else:
            if not self._pg_pool:
                cfg = self._get_pg_config()
                self._pg_pool = pool.SimpleConnectionPool(1, 10, **cfg)
            return self._pg_pool.getconn()

    def put_conn(self, conn):
        if self._db_mode == 'sqlite':
            conn.close()
        else:
            if self._pg_pool:
                self._pg_pool.putconn(conn)

    def check_database_exists(self, password):
        """Checks if the PostgreSQL database exists."""
        temp_conn = None
        try:
            temp_conn = psycopg2.connect(
                host=config.database.host,
                user=config.database.user,
                password=password,
                dbname='postgres'
            )
            temp_conn.autocommit = True
            cur = temp_conn.cursor()
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config.database.name,))
            exists = cur.fetchone() is not None
            cur.close()
            return exists
        except Exception as e:
            logger.error(f"DB Check error: {e}")
            return False
        finally:
            if temp_conn: temp_conn.close()

    def ensure_ready(self, password):
        """Creates DB if missing and initializes schema."""
        global runtime_password
        runtime_password = password
        
        if self._db_mode == 'sqlite':
            self.init_db()
            return True

        temp_conn = None
        try:
            temp_conn = psycopg2.connect(
                host=config.database.host,
                user=config.database.user,
                password=password,
                dbname='postgres'
            )
            temp_conn.autocommit = True
            cur = temp_conn.cursor()
            if not self.check_database_exists(password):
                cur.execute(f'CREATE DATABASE "{config.database.name}"')
            cur.close()
            self.init_db()
            return True
        except Exception as e:
            logger.error(f"Ensure Ready error: {e}")
            return False
        finally:
            if temp_conn: temp_conn.close()

    def init_db(self):
        conn = self.get_conn()
        try:
            cur = conn.cursor()
            dim = config.clip.get('available_models', {}).get(config.clip.get('current_model_label'), {}).get('dimension', 768)
            
            if self._db_mode == 'sqlite':
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS images (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT,
                        file_path TEXT UNIQUE,
                        embedding BLOB,
                        min_distance REAL,
                        density REAL,
                        score INTEGER,
                        tags TEXT,
                        affected INTEGER DEFAULT 0,
                        nearest_path_1 TEXT, nearest_path_2 TEXT, nearest_path_3 TEXT,
                        nearest_path_4 TEXT, nearest_path_5 TEXT, nearest_path_6 TEXT,
                        nearest_path_7 TEXT, nearest_path_8 TEXT, nearest_path_9 TEXT,
                        nearest_path_10 TEXT
                    )
                """)
            else:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS images (
                        id SERIAL PRIMARY KEY,
                        file_name TEXT,
                        file_path TEXT UNIQUE,
                        embedding vector({dim}),
                        min_distance FLOAT,
                        density FLOAT,
                        score INTEGER,
                        tags TEXT,
                        affected INTEGER DEFAULT 0,
                        nearest_path_1 TEXT, nearest_path_2 TEXT, nearest_path_3 TEXT,
                        nearest_path_4 TEXT, nearest_path_5 TEXT, nearest_path_6 TEXT,
                        nearest_path_7 TEXT, nearest_path_8 TEXT, nearest_path_9 TEXT,
                        nearest_path_10 TEXT
                    )
                """)
            conn.commit()
        finally:
            self.put_conn(conn)

    def initialize_schema(self, dimension):
        """Legacy support for database_sync.py"""
        self.init_db()
        return True

db_manager = DatabaseManager()
