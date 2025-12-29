import os
import psycopg2
import yaml

from config_loader import config
from db_manager import db_manager
from utils.logger import get_logger

logger = get_logger(__name__)

class TagManager:
    def __init__(self):
        self.score_rules = config.scores.rules

    def get_keyword_for_score(self, score):
        """Get normalized keyword for a score"""
        if score is None:
            return None
        return next((rule['keyword'].strip().lstrip(' -').strip() for rule in self.score_rules if rule['score'] == score), None)

    def update_score(self, image_id, new_score, file_path, original_score, streamlit=False):
        """
        Update score in DB and corresponding MD file tags.
        
        Args:
            image_id (int): Image ID in database
            new_score (int or None): New score (must match config.json rules or None)
            file_path (str): Path to image file
            original_score (int or None): Current score in DB
            streamlit (bool): If True, use st.success/warning for feedback
        
        Returns:
            bool: True if updated successfully, False if warnings issued
        """
        # FIXED: Import Streamlit ONLY if needed (avoids import errors in non-UI context)
        st = None
        if streamlit:
            try:
                import streamlit as st
            except ImportError:
                logger.warning("Streamlit not available for UI feedback.")
                streamlit = False
        
        success = True
        conn = None
        try:
            conn = db_manager.get_conn()
            cur = conn.cursor()
            cur.execute("UPDATE images SET score = %s WHERE id = %s", (new_score, image_id))
            conn.commit()
            cur.close()
            logger.info(f"DB score updated to {new_score} for image ID {image_id}.")
            
            # STEP 2: Update MD file
            md_path = os.path.splitext(file_path)[0] + '.md'
            
            if os.path.exists(md_path):
                with open(md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                new_content = self.update_md_frontmatter(content, original_score, new_score)
                
                if new_content != content:  # Only write if changed
                    with open(md_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    logger.info(f"MD file {os.path.basename(md_path)} updated for score {new_score}.")
                    if streamlit:
                        st.success(f"✅ Updated score to {new_score} for {os.path.basename(file_path)}")
                else:
                    logger.info(f"No changes needed for MD file {os.path.basename(md_path)}.")
                    if streamlit:
                        st.info(f"ℹ️ No changes needed for {os.path.basename(file_path)}")
            else:
                logger.warning(f"No .md file found for {os.path.basename(file_path)} (DB updated only).")
                if streamlit:
                    st.warning(f"⚠️ No .md file found for {os.path.basename(file_path)} (DB updated)")
            
        except psycopg2.Error as e:
            success = False
            error_msg = f"Database error updating score for {image_id}: {e}"
            logger.error(error_msg)
            if streamlit:
                st.error(error_msg)
            if conn: conn.rollback()
        except Exception as e:
            success = False
            error_msg = f"Update error for image {image_id}: {e}"
            logger.error(error_msg)
            if streamlit:
                st.error(error_msg)
        finally:
            if conn: db_manager.put_conn(conn)
        
        return success

    def update_md_frontmatter(self, content, original_score, new_score):
        """Update frontmatter tags in MD content"""
        if not content.startswith('---\n'):
            logger.debug("No frontmatter found, adding new.")
            # No frontmatter - add it
            new_keyword = self.get_keyword_for_score(new_score)
            if new_keyword:
                return f'---\ntags:\n  - {new_keyword}\n---\n\n{content}'
            return content
        
        # Parse existing frontmatter
        end_idx = content.find('\n---\n', 4)
        if end_idx == -1:
            logger.warning("Invalid frontmatter format.")
            return content  # Invalid frontmatter
        
        fm_str = content[4:end_idx]
        rest = content[end_idx + 5:]
        fm_lines = fm_str.splitlines()
        
        # Find or create tags section
        tags_start = None
        tags_end = None
        tags = []
        
        for i, line in enumerate(fm_lines):
            if line.strip() == 'tags:' or line.strip() == 'tags :':
                tags_start = i
                # Collect existing tags
                j = i + 1
                while j < len(fm_lines) and fm_lines[j].startswith((' ', '-', '  -')):
                    tag = fm_lines[j].strip().lstrip('- ').strip()
                    if tag:
                        tags.append(tag)
                    j += 1
                tags_end = j
                break
        
        # FIXED: Robust tag management
        old_keyword = self.get_keyword_for_score(original_score)
        new_keyword = self.get_keyword_for_score(new_score)
        
        # Remove old keyword
        if old_keyword:
            tags = [t for t in tags if t != old_keyword]
        
        # Add new keyword (if not None and not already present)
        if new_keyword and new_keyword not in tags:
            tags.append(new_keyword)
        
        # Rebuild frontmatter
        if tags_start is not None:
            # Replace tags section
            new_tags_lines = [f"  - {tag}" for tag in tags]
            fm_lines = fm_lines[:tags_start + 1] + new_tags_lines + fm_lines[tags_end:]
        elif tags:  # No tags section but need to add one
            fm_lines.extend(['', 'tags:'] + [f"  - {tag}" for tag in tags])
        
        # Clean up empty lines
        fm_lines = [line for line in fm_lines if line.strip() or line == '']
        
        new_fm_str = '\n'.join(fm_lines)
        return '---\n' + new_fm_str + '\n---\n' + rest

# Global instance for easy access
tag_manager = TagManager()

# Example usage (for testing/demonstration)
if __name__ == "__main__":
    logger.info("Testing TagManager...")
    # Example of how to use it (requires a running DB and images)
    # from db_manager import db_manager
    # conn = db_manager.get_conn()
    # cur = conn.cursor()
    # cur.execute("SELECT id, file_path, score FROM images LIMIT 1")
    # result = cur.fetchone()
    # cur.close()
    # conn.close()
    # if result:
    #     image_id, file_path, original_score = result
    #     logger.info(f"Testing ID {image_id}: {file_path}, score={original_score}")
    #     success = tag_manager.update_score(image_id, 10, file_path, original_score, streamlit=False)
    #     logger.info(f"Update {'PASSED' if success else 'FAILED'}")
