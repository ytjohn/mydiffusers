"""SQLite database for run metadata indexing."""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, UTC
from contextlib import contextmanager

DB_PATH = Path("outputs/runs.db")


def init_database():
    """Initialize SQLite database with schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                prompt TEXT NOT NULL,
                source_run_id TEXT,
                tags TEXT,
                backend TEXT,
                seconds_elapsed REAL,
                indexed_at TEXT NOT NULL
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_type ON runs(type)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON runs(timestamp DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tags ON runs(tags)')


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def index_run(run_id: str, meta: dict):
    """Index a run's metadata in SQLite."""
    with get_db() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO runs
            (id, type, timestamp, prompt, source_run_id, tags, backend, seconds_elapsed, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            run_id,
            meta.get('type'),
            meta.get('timestamp'),
            meta.get('prompt', ''),
            meta.get('source_run_id'),
            json.dumps(meta.get('tags', [])),
            meta.get('backend'),
            meta.get('seconds_elapsed'),
            datetime.now(UTC).isoformat()
        ))


def get_runs(run_type: str = 'all', include_tags: list[str] = None,
             show_nsfw: bool = False, page: int = 1, limit: int = 24) -> tuple[list[dict], int]:
    """Query runs from SQLite with filtering and pagination.

    Args:
        run_type: Filter by type (all, image, video)
        include_tags: Tags to include (OR logic) - show ONLY runs with these tags
        show_nsfw: If True, include nsfw content; if False, exclude nsfw content
        page: Page number (1-indexed)
        limit: Results per page

    Returns:
        Tuple of (runs_list, total_count)
    """
    with get_db() as conn:
        where_clauses = []
        params = []

        # Type filter
        if run_type != 'all':
            where_clauses.append('type = ?')
            params.append(run_type)

        # Tag filtering (if any tags selected)
        if include_tags:
            # OR logic for multiple tags
            tag_conditions = ' OR '.join(['tags LIKE ?' for _ in include_tags])
            where_clauses.append(f'({tag_conditions})')
            params.extend([f'%"{tag}"%' for tag in include_tags])

        # NSFW filtering (exclude nsfw unless show_nsfw is True)
        if not show_nsfw:
            where_clauses.append('(tags IS NULL OR tags NOT LIKE ?)')
            params.append('%"nsfw"%')

        where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'

        # Get total count
        count_sql = f'SELECT COUNT(*) FROM runs WHERE {where_sql}'
        total = conn.execute(count_sql, params).fetchone()[0]

        # Get paginated results
        offset = (page - 1) * limit
        query_sql = f'''
            SELECT * FROM runs
            WHERE {where_sql}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        '''
        rows = conn.execute(query_sql, params + [limit, offset]).fetchall()

        runs = []
        for row in rows:
            runs.append({
                'id': row['id'],
                'type': row['type'],
                'timestamp': row['timestamp'],
                'prompt': row['prompt'],
                'source_run_id': row['source_run_id'],
                'tags': json.loads(row['tags']) if row['tags'] else [],
                'backend': row['backend'],
                'seconds_elapsed': row['seconds_elapsed']
            })

        return runs, total


def get_all_tags() -> list[str]:
    """Get all unique tags from all runs."""
    with get_db() as conn:
        rows = conn.execute('SELECT DISTINCT tags FROM runs WHERE tags IS NOT NULL').fetchall()
        all_tags = set()
        for row in rows:
            if row['tags']:
                tags = json.loads(row['tags'])
                all_tags.update(tags)
        return sorted(all_tags)


def delete_run(run_id: str):
    """Delete a run from the database."""
    with get_db() as conn:
        conn.execute('DELETE FROM runs WHERE id = ?', (run_id,))
