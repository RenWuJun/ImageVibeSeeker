import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from config_loader import config
from utils.logger import get_logger

logger = get_logger(__name__)

class FileScanner:
    def __init__(self):
        self.root_folder = config.paths['root_folder']

    def _walk_subdir(self, subdir):
        paths = set()
        for root, dirs, files in os.walk(subdir):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    full_path = os.path.normpath(os.path.join(root, file))
                    paths.add(full_path)
        return paths

    def collect_local_image_paths(self):
        local_paths = set()
        top_dirs = [os.path.join(self.root_folder, d) for d in os.listdir(self.root_folder) if os.path.isdir(os.path.join(self.root_folder, d))]
        top_dirs.append(self.root_folder) # Include the root folder itself

        logger.info(f"Scanning root folder: {self.root_folder}")
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_dir = {executor.submit(self._walk_subdir, dir): dir for dir in top_dirs}
            for future in as_completed(future_to_dir):
                try:
                    sub_paths = future.result()
                    local_paths.update(sub_paths)
                except Exception as e:
                    logger.error(f"Error walking {future_to_dir[future]}: {e}")
        logger.info(f"Found {len(local_paths)} image paths.")
        return local_paths

# Global instance for easy access
file_scanner = FileScanner()

# Example usage (for testing/demonstration)
if __name__ == "__main__":
    logger.info("Testing FileScanner...")
    paths = file_scanner.collect_local_image_paths()
    logger.info(f"Found {len(paths)} image paths.")
    # for p in list(paths)[:5]:
    #     logger.info(p)
