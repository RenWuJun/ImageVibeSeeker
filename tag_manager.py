import os
import sqlite3
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
        """Update score in DB and corresponding MD file tags."""
        st = None
        if streamlit:
            try:
                import streamlit as st
            except ImportError:
                streamlit = False

        success = True
        conn = None
        try:
            conn = db_manager.get_conn()
            cur = conn.cursor()
            p = db_manager.p
            cur.execute(f"UPDATE images SET score = {p} WHERE id = {p}", (new_score, image_id))
            conn.commit()
            cur.close()
            logger.info(f"DB score updated to {new_score} for image ID {image_id}.")

            md_path = os.path.splitext(file_path)[0] + '.md'
            if os.path.exists(md_path):
                with open(md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                new_content = self.update_md_frontmatter(content, original_score, new_score)
                if new_content != content:
                    with open(md_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    if streamlit:
                        st.success(f"✅ Updated score to {new_score} for {os.path.basename(file_path)}")
            elif streamlit:
                st.warning(f"⚠️ No .md file found for {os.path.basename(file_path)} (DB updated)")

        except (psycopg2.Error, sqlite3.Error) as e:
            success = False
            error_msg = f"Database error: {e}"
            logger.error(error_msg)
            if streamlit: st.error(error_msg)
            if conn and db_manager._db_mode != 'sqlite': conn.rollback()
        except Exception as e:
            success = False
            error_msg = f"Update error: {e}"
            logger.error(error_msg)
            if streamlit: st.error(error_msg)
        finally:
            if conn: db_manager.put_conn(conn)

        return success

    def update_md_frontmatter(self, content, original_score, new_score):
        """Update frontmatter tags in MD content"""
        if not content.startswith('---\n'):
            new_keyword = self.get_keyword_for_score(new_score)
            if new_keyword:
                return f'---\ntags:\n  - {new_keyword}\n---\n\n{content}'
            return content

        end_idx = content.find('\n---\n', 4)
        if end_idx == -1:
            return content

        fm_str = content[4:end_idx]
        rest = content[end_idx + 5:]
        fm_lines = fm_str.splitlines()

        tags_start = None
        tags_end = None
        tags = []

        for i, line in enumerate(fm_lines):
            if line.strip() in ('tags:', 'tags :'):
                tags_start = i
                j = i + 1
                while j < len(fm_lines) and fm_lines[j].startswith((' ', '-', '  -')):
                    tag = fm_lines[j].strip().lstrip('- ').strip()
                    if tag: tags.append(tag)
                    j += 1
                tags_end = j
                break

        old_keyword = self.get_keyword_for_score(original_score)
        new_keyword = self.get_keyword_for_score(new_score)

        if old_keyword:
            tags = [t for t in tags if t != old_keyword]
        if new_keyword and new_keyword not in tags:
            tags.append(new_keyword)

        if tags_start is not None:
            new_tags_lines = [f"  - {tag}" for tag in tags]
            fm_lines = fm_lines[:tags_start + 1] + new_tags_lines + fm_lines[tags_end:]
        elif tags:
            fm_lines.extend(['', 'tags:'] + [f"  - {tag}" for tag in tags])

        fm_lines = [line for line in fm_lines if line.strip() or line == '']
        return '---\n' + '\n'.join(fm_lines) + '\n---\n' + rest

tag_manager = TagManager()
