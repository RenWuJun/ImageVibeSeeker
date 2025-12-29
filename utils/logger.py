import logging
import os
import sys

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging():
    # Reconfigure sys.stdout to use utf-8 for console output
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    
    logging.basicConfig(
        level=logging.INFO,  # Default logging level
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),  # Log to file
            logging.StreamHandler(sys.stdout)          # Log to console
        ]
    )

def get_logger(name):
    return logging.getLogger(name)

# Setup logging when this module is imported
setup_logging()
