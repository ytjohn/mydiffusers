"""SQLite database for run metadata indexing."""

import json
import logging
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from mydiffuser.utils.paths import list_all_runs, read_json

logger = logging.getLogger(__name__)

DB_PATH = Path("outputs/runs.db")


def get_video_dimensions(video_path: Path) -> tuple[int, int] | None:
    """Extract width and height from a video file using ffprobe.

    Args:
        video_path: Path to video file

    Returns:
        Tuple of (height, width) or None if extraction fails
    """
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'csv=p=0',
                str(video_path)
            ],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            width, height = result.stdout.strip().split(',')
            return int(height), int(width)
    except Exception as e:
        logger.debug(f"Failed to extract dimensions from {video_path}: {e}")
    return None


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get current database schema version."""
    try:
        result = conn.execute('SELECT version FROM schema_version ORDER BY version DESC LIMIT 1').fetchone()
        return result[0] if result else 0
    except sqlite3.OperationalError:
        # schema_version table doesn't exist yet
        return 0


def set_schema_version(conn: sqlite3.Connection, version: int):
    """Set database schema version."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    ''')
    conn.execute('INSERT INTO schema_version (version, applied_at) VALUES (?, ?)',
                 (version, datetime.now(UTC).isoformat()))


def migrate_v1_add_params_columns(conn: sqlite3.Connection):
    """Migration 1: Add generation parameter columns to runs table."""
    logger.info("Applying migration v1: Adding parameter columns")

    # Add generation parameters
    conn.execute('ALTER TABLE runs ADD COLUMN height INTEGER')
    conn.execute('ALTER TABLE runs ADD COLUMN width INTEGER')
    conn.execute('ALTER TABLE runs ADD COLUMN seed INTEGER')
    conn.execute('ALTER TABLE runs ADD COLUMN num_inference_steps INTEGER')
    conn.execute('ALTER TABLE runs ADD COLUMN guidance_scale REAL')

    # Add device/model info
    conn.execute('ALTER TABLE runs ADD COLUMN device TEXT')
    conn.execute('ALTER TABLE runs ADD COLUMN dtype TEXT')
    conn.execute('ALTER TABLE runs ADD COLUMN model_id TEXT')

    # Add video-specific fields
    conn.execute('ALTER TABLE runs ADD COLUMN num_frames INTEGER')
    conn.execute('ALTER TABLE runs ADD COLUMN fps INTEGER')
    conn.execute('ALTER TABLE runs ADD COLUMN duration_seconds INTEGER')
    conn.execute('ALTER TABLE runs ADD COLUMN resolution TEXT')

    # Add user metadata
    conn.execute('ALTER TABLE runs ADD COLUMN favorite INTEGER DEFAULT 0')
    conn.execute('ALTER TABLE runs ADD COLUMN notes TEXT')
    conn.execute('ALTER TABLE runs ADD COLUMN worker_name TEXT')
    conn.execute('ALTER TABLE runs ADD COLUMN negative_prompt TEXT')

    set_schema_version(conn, 1)
    logger.info("Migration v1 complete")


def migrate_v2_create_client_jobs(conn: sqlite3.Connection):
    """Migration 2: Create client_jobs table for persistent job tracking."""
    logger.info("Applying migration v2: Creating client_jobs table")

    conn.execute('''
        CREATE TABLE IF NOT EXISTS client_jobs (
            job_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            status TEXT NOT NULL,

            worker_name TEXT NOT NULL,
            worker_endpoint TEXT NOT NULL,
            worker_run_id TEXT,
            worker_progress REAL DEFAULT 0.0,
            worker_step INTEGER DEFAULT 0,
            worker_total_steps INTEGER DEFAULT 0,
            worker_message TEXT,

            prompt TEXT,
            preset TEXT DEFAULT 'draft',
            seed INTEGER DEFAULT 42,
            request_params TEXT,

            local_run_id TEXT,
            error TEXT,

            created_at TEXT NOT NULL,
            submitted_at TEXT,
            completed_at TEXT,
            fetched_at TEXT,

            FOREIGN KEY (local_run_id) REFERENCES runs(id)
        )
    ''')

    conn.execute('CREATE INDEX IF NOT EXISTS idx_client_jobs_status ON client_jobs(status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_client_jobs_worker ON client_jobs(worker_name)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_client_jobs_created ON client_jobs(created_at DESC)')

    set_schema_version(conn, 2)
    logger.info("Migration v2 complete")


def migrate_v3_create_assist_tables(conn: sqlite3.Connection):
    """Migration 3: Create prompt assistant session/turn tables."""
    logger.info("Applying migration v3: Creating assist tables")

    # Sessions table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS assist_sessions (
            session_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            goal TEXT,
            status TEXT DEFAULT 'active',
            final_prompt TEXT,
            final_run_id TEXT,
            turn_count INTEGER DEFAULT 0,

            FOREIGN KEY (final_run_id) REFERENCES runs(id)
        )
    ''')

    # Turns table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS assist_turns (
            turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            created_at TEXT NOT NULL,

            run_id TEXT,
            user_message TEXT,
            prompt_used TEXT,

            assistant_response TEXT,
            suggested_prompts TEXT,
            model_used TEXT,

            FOREIGN KEY (session_id) REFERENCES assist_sessions(session_id),
            FOREIGN KEY (run_id) REFERENCES runs(id)
        )
    ''')

    conn.execute('CREATE INDEX IF NOT EXISTS idx_assist_sessions_updated ON assist_sessions(updated_at DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_assist_turns_session ON assist_turns(session_id, turn_number)')

    set_schema_version(conn, 3)
    logger.info("Migration v3 complete")


def migrate_v4_create_fts(conn: sqlite3.Connection):
    """Migration 4: Create full-text search table and triggers."""
    logger.info("Applying migration v4: Creating FTS5 tables")

    # Create FTS5 virtual table
    conn.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS runs_fts USING fts5(
            id UNINDEXED,
            prompt,
            notes,
            tags,
            content=runs,
            content_rowid=rowid
        )
    ''')

    # Populate FTS from existing runs
    conn.execute('''
        INSERT INTO runs_fts(rowid, id, prompt, notes, tags)
        SELECT rowid, id, prompt, notes, tags FROM runs
    ''')

    # Create triggers to keep FTS in sync
    conn.execute('''
        CREATE TRIGGER IF NOT EXISTS runs_fts_insert AFTER INSERT ON runs BEGIN
            INSERT INTO runs_fts(rowid, id, prompt, notes, tags)
            VALUES (new.rowid, new.id, new.prompt, new.notes, new.tags);
        END
    ''')

    conn.execute('''
        CREATE TRIGGER IF NOT EXISTS runs_fts_delete AFTER DELETE ON runs BEGIN
            INSERT INTO runs_fts(runs_fts, rowid, id, prompt, notes, tags)
            VALUES('delete', old.rowid, old.id, old.prompt, old.notes, old.tags);
        END
    ''')

    conn.execute('''
        CREATE TRIGGER IF NOT EXISTS runs_fts_update AFTER UPDATE ON runs BEGIN
            INSERT INTO runs_fts(runs_fts, rowid, id, prompt, notes, tags)
            VALUES('delete', old.rowid, old.id, old.prompt, old.notes, old.tags);
            INSERT INTO runs_fts(rowid, id, prompt, notes, tags)
            VALUES (new.rowid, new.id, new.prompt, new.notes, new.tags);
        END
    ''')

    set_schema_version(conn, 4)
    logger.info("Migration v4 complete")


def init_database():
    """Initialize SQLite database with schema and apply migrations."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_db() as conn:
        # Create initial tables if they don't exist
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

        # Check current schema version and apply migrations
        current_version = get_schema_version(conn)
        logger.info(f"Current database schema version: {current_version}")

        migrations = [
            (1, migrate_v1_add_params_columns),
            (2, migrate_v2_create_client_jobs),
            (3, migrate_v3_create_assist_tables),
            (4, migrate_v4_create_fts),
        ]

        for version, migration_func in migrations:
            if current_version < version:
                try:
                    migration_func(conn)
                except Exception as e:
                    logger.error(f"Migration v{version} failed: {e}")
                    raise

        final_version = get_schema_version(conn)
        if final_version > current_version:
            logger.info(f"Database migrations complete: v{current_version} → v{final_version}")


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
    """Index a run's metadata in SQLite with full parameter extraction."""
    params = meta.get('params', {})
    tags = meta.get('tags', [])

    # Extract height/width - handle both image and video runs
    height = params.get('height')
    width = params.get('width')

    # For video runs, parse resolution string into height/width
    if meta.get('type') == 'video' and not height:
        resolution = params.get('resolution', '')
        if resolution == '480p':
            height, width = 480, 854
        elif resolution == '720p':
            height, width = 720, 1280
        elif resolution == '1080p':
            height, width = 1080, 1920
        elif not resolution:
            # No resolution metadata - try to extract from video file
            video_path = Path(f"outputs/run/{run_id}/output.mp4")
            if video_path.exists():
                dimensions = get_video_dimensions(video_path)
                if dimensions:
                    height, width = dimensions
                    logger.debug(f"[{run_id}] Extracted dimensions from video: {width}x{height}")

    with get_db() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO runs
            (id, type, timestamp, prompt, source_run_id, tags, backend, seconds_elapsed, indexed_at,
             height, width, seed, num_inference_steps, guidance_scale,
             device, dtype, model_id,
             num_frames, fps, duration_seconds, resolution,
             worker_name, negative_prompt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?)
        ''', (
            run_id,
            meta.get('type'),
            meta.get('timestamp'),
            meta.get('prompt', ''),
            meta.get('source_run_id'),
            json.dumps(tags),
            meta.get('backend'),
            meta.get('seconds_elapsed'),
            datetime.now(UTC).isoformat(),
            # Generation params
            height,
            width,
            params.get('seed'),
            params.get('num_inference_steps'),
            params.get('guidance_scale'),
            # Device/model
            params.get('device'),
            params.get('dtype'),
            params.get('model_id'),
            # Video params
            params.get('num_frames'),
            params.get('fps'),
            params.get('duration_seconds'),
            params.get('resolution'),
            # Worker/prompts
            params.get('worker_name'),
            params.get('negative_prompt'),
        ))


def get_runs(run_type: str = 'all', include_tags: list[str] | None = None,
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
        rows = conn.execute(query_sql, [*params, limit, offset]).fetchall()

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


def backfill_runs(force_refresh: bool = False, run_ids: list[str] | None = None) -> dict:
    """Backfill database with full parameters from meta.json files.

    Args:
        force_refresh: If True, update ALL runs even if they have params
        run_ids: If provided, only backfill these specific run IDs

    Returns:
        Dict with statistics: {total, processed, updated, errors, error_details}
    """
    logger.info("Starting database backfill from meta.json files...")

    stats = {
        "total": 0,
        "processed": 0,
        "updated": 0,
        "errors": 0,
        "error_details": []
    }

    # Get all run directories
    try:
        all_runs = list(list_all_runs())
        stats["total"] = len(all_runs)
        logger.info(f"Found {stats['total']} run directories")
    except Exception as e:
        logger.error(f"Failed to list runs: {e}")
        stats["error_details"].append(f"Failed to list runs: {e}")
        return stats

    for run_path in all_runs:
        run_id = run_path.name
        stats["processed"] += 1

        # Filter by run_ids if specified
        if run_ids and run_id not in run_ids:
            continue

        meta_path = run_path / "meta.json"
        if not meta_path.exists():
            logger.warning(f"[{run_id}] No meta.json found, skipping")
            stats["errors"] += 1
            stats["error_details"].append(f"{run_id}: No meta.json")
            continue

        try:
            # Check if we should skip this run
            if not force_refresh:
                with get_db() as conn:
                    result = conn.execute(
                        'SELECT height FROM runs WHERE id = ?',
                        (run_id,)
                    ).fetchone()
                    # If height is already set, params have been backfilled
                    if result and result[0] is not None:
                        logger.debug(f"[{run_id}] Already backfilled, skipping")
                        continue

            # Read meta.json and index
            meta = read_json(meta_path)
            index_run(run_id, meta)
            stats["updated"] += 1

            if stats["updated"] % 50 == 0:
                logger.info(f"Backfilled {stats['updated']}/{stats['total']} runs...")

        except Exception as e:
            logger.error(f"[{run_id}] Backfill failed: {e}")
            stats["errors"] += 1
            stats["error_details"].append(f"{run_id}: {e!s}")

    logger.info(f"Backfill complete: {stats['updated']} runs updated, {stats['errors']} errors")
    return stats


# ============================================================================
# Client Jobs CRUD Functions
# ============================================================================

def create_client_job(job_data: dict) -> None:
    """Insert a new client job into the database.

    Args:
        job_data: Dict with job fields matching ClientJob dataclass
    """
    with get_db() as conn:
        conn.execute('''
            INSERT INTO client_jobs (
                job_id, type, status,
                worker_name, worker_endpoint, worker_run_id,
                worker_progress, worker_step, worker_total_steps, worker_message,
                prompt, preset, seed, request_params,
                local_run_id, error,
                created_at, submitted_at, completed_at, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            job_data['job_id'],
            job_data['type'],
            job_data['status'],
            job_data['worker_name'],
            job_data['worker_endpoint'],
            job_data.get('worker_run_id'),
            job_data.get('worker_progress', 0.0),
            job_data.get('worker_step', 0),
            job_data.get('worker_total_steps', 0),
            job_data.get('worker_message'),
            job_data.get('prompt', ''),
            job_data.get('preset', 'draft'),
            job_data.get('seed', 42),
            job_data.get('request_params'),
            job_data.get('local_run_id'),
            job_data.get('error'),
            job_data['created_at'].isoformat() if job_data.get('created_at') else datetime.now(UTC).isoformat(),
            job_data['submitted_at'].isoformat() if job_data.get('submitted_at') else None,
            job_data['completed_at'].isoformat() if job_data.get('completed_at') else None,
            job_data['fetched_at'].isoformat() if job_data.get('fetched_at') else None,
        ))
    logger.debug(f"Created client job {job_data['job_id']} in database")


def get_client_job(job_id: str) -> dict | None:
    """Retrieve a client job by ID.

    Args:
        job_id: Job ID to fetch

    Returns:
        Job data dict or None if not found
    """
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM client_jobs WHERE job_id = ?',
            (job_id,)
        ).fetchone()

        if not row:
            return None

        return dict(row)


def list_client_jobs(limit: int = 50) -> list[dict]:
    """List all client jobs, newest first.

    Args:
        limit: Maximum number of jobs to return

    Returns:
        List of job data dicts
    """
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM client_jobs ORDER BY created_at DESC LIMIT ?',
            (limit,)
        ).fetchall()

        return [dict(row) for row in rows]


def update_client_job_status(job_id: str, updates: dict) -> None:
    """Update job status and progress fields.

    Args:
        job_id: Job ID to update
        updates: Dict with fields to update (status, worker_progress, worker_step, etc.)
    """
    with get_db() as conn:
        # Build dynamic UPDATE statement
        update_fields = []
        values = []

        for field in ['status', 'worker_run_id', 'worker_progress', 'worker_step',
                      'worker_total_steps', 'worker_message', 'local_run_id', 'error',
                      'completed_at', 'fetched_at']:
            if field in updates:
                update_fields.append(f'{field} = ?')
                value = updates[field]
                # Convert datetime to ISO string
                if field in ('completed_at', 'fetched_at') and value is not None:
                    value = value.isoformat() if hasattr(value, 'isoformat') else value
                values.append(value)

        if not update_fields:
            return

        values.append(job_id)
        sql = f"UPDATE client_jobs SET {', '.join(update_fields)} WHERE job_id = ?"
        conn.execute(sql, values)

    logger.debug(f"Updated client job {job_id}: {list(updates.keys())}")


# ============================================================================
# Assist Session Management
# ============================================================================

def create_assist_session(goal: str) -> str:
    """Create a new assist session.

    Args:
        goal: User's goal for this session (e.g., "improve character interaction")

    Returns:
        session_id: UUID for the new session
    """
    import uuid
    from datetime import datetime

    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    with get_db() as conn:
        conn.execute('''
            INSERT INTO assist_sessions (session_id, goal, status, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?)
        ''', (session_id, goal, now, now))

    logger.info(f"Created assist session {session_id}: {goal}")
    return session_id


def add_assist_turn(
    session_id: str,
    turn_number: int,
    run_id: str | None,
    current_prompt: str,
    user_message: str | None,
    assistant_response: str,
    suggested_prompts: list[dict],
    model_used: str = "Qwen2-VL-2B-Instruct"
) -> int:
    """Add a turn to an assist session.

    Args:
        session_id: Session UUID
        turn_number: Turn number (1-indexed)
        run_id: Optional run_id if analyzing existing image
        current_prompt: Prompt that generated the image
        user_message: Optional user feedback/issue description
        assistant_response: Full model response
        suggested_prompts: List of prompt suggestions with rationales
        model_used: Model identifier

    Returns:
        turn_id: Auto-increment ID for the turn
    """
    import json
    from datetime import datetime

    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO assist_turns
            (session_id, turn_number, run_id, prompt_used,
             user_message, assistant_response, suggested_prompts, model_used, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id, turn_number, run_id, current_prompt,
            user_message, assistant_response, json.dumps(suggested_prompts), model_used,
            datetime.now().isoformat()
        ))

        turn_id = cursor.lastrowid

        # Update session metadata
        conn.execute('''
            UPDATE assist_sessions
            SET turn_count = ?, updated_at = ?
            WHERE session_id = ?
        ''', (turn_number, datetime.now().isoformat(), session_id))

    logger.info(f"Added turn {turn_number} to session {session_id}")
    return turn_id


def get_assist_session(session_id: str) -> dict | None:
    """Get session with all turns.

    Args:
        session_id: Session UUID

    Returns:
        Dict with session info and list of turns, or None if not found
    """
    import json

    with get_db() as conn:
        # Get session
        session_row = conn.execute(
            'SELECT * FROM assist_sessions WHERE session_id = ?',
            (session_id,)
        ).fetchone()

        if not session_row:
            return None

        session = dict(session_row)

        # Get turns
        turn_rows = conn.execute('''
            SELECT * FROM assist_turns
            WHERE session_id = ?
            ORDER BY turn_number ASC
        ''', (session_id,)).fetchall()

        turns = []
        for row in turn_rows:
            turn = dict(row)
            # Parse JSON suggested_prompts
            if turn['suggested_prompts']:
                turn['suggested_prompts'] = json.loads(turn['suggested_prompts'])
            turns.append(turn)

        session['turns'] = turns
        return session


def list_assist_sessions(limit: int = 20, status: str | None = None) -> list[dict]:
    """List recent assist sessions.

    Args:
        limit: Maximum sessions to return
        status: Optional filter by status ('active', 'resolved', 'abandoned')

    Returns:
        List of session dicts (without turns)
    """
    with get_db() as conn:
        if status:
            rows = conn.execute('''
                SELECT * FROM assist_sessions
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ?
            ''', (status, limit)).fetchall()
        else:
            rows = conn.execute('''
                SELECT * FROM assist_sessions
                ORDER BY updated_at DESC
                LIMIT ?
            ''', (limit,)).fetchall()

        return [dict(row) for row in rows]


def resolve_assist_session(
    session_id: str,
    final_prompt: str,
    final_run_id: str | None = None
) -> None:
    """Mark session as resolved with final prompt.

    Args:
        session_id: Session UUID
        final_prompt: The final improved prompt
        final_run_id: Optional run_id of final generation
    """
    from datetime import datetime

    with get_db() as conn:
        conn.execute('''
            UPDATE assist_sessions
            SET status = 'resolved',
                final_prompt = ?,
                final_run_id = ?,
                updated_at = ?
            WHERE session_id = ?
        ''', (final_prompt, final_run_id, datetime.now().isoformat(), session_id))

    logger.info(f"Resolved assist session {session_id}")
