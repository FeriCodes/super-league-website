import os
import json
from pathlib import Path
from typing import Optional
import asyncpg

APP_DIR = Path(__file__).resolve().parent.parent


TEAMS_FILE = APP_DIR / "data" / "sl_teams.json"
FIXTURES_FILE = APP_DIR / "data" / "fixtures.json"
RESULTS_CACHE_FILE = APP_DIR / "data" / "results_cache.json"

DATABASE_URL = os.getenv("DATABASE_URL")
db_pool: Optional[asyncpg.Pool] = None


async def init_db():
    """Initialize PostgreSQL connection pool and create cache table if needed."""
    global db_pool
    if DATABASE_URL:
        try:
            db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS results_cache (
                        gameweek INT PRIMARY KEY,
                        data JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
        except Exception as e:
            print(f"[DATABASE INIT ERROR] {e}")
            db_pool = None


async def close_db():
    """Close PostgreSQL connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()


def load_teams() -> dict:
    """Read and parse the local sl_teams.json file into a Python dictionary."""
    if not TEAMS_FILE.exists():
        return {}
    with open(TEAMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_team_roster(teams_data: dict, team_name: str, gw: int) -> list:
    """Fetch manager IDs dynamically for a team based on gameweek ranges."""
    data = teams_data.get(team_name, [])
    if not data:
        return []

    try:
        current_gw = int(gw)
    except (ValueError, TypeError):
        current_gw = 1

    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], int):
        return data

    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        for entry in data:
            from_gw = int(entry.get("from_gw", 1))
            to_gw = int(entry.get("to_gw", 38))
            if from_gw <= current_gw <= to_gw:
                return entry.get("ids", [])

    return []


def load_fixtures() -> dict:
    """Load league schedule mapping from fixtures.json."""
    if not FIXTURES_FILE.exists():
        return {}
    with open(FIXTURES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_local_results_cache() -> dict:
    """Load cached gameweek results from local json fallback."""
    if not RESULTS_CACHE_FILE.exists():
        return {}
    try:
        with open(RESULTS_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_local_results_cache(data: dict):
    """Write gameweek results to local json fallback."""
    try:
        with open(RESULTS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CACHE WRITE ERROR] {e}")


async def get_all_results_cache() -> dict:
    """Fetch all cached gameweeks from PostgreSQL with JSON file fallback."""
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("SELECT gameweek, data FROM results_cache")
                cache = {}
                for row in rows:
                    gw_str = str(row["gameweek"])
                    raw_data = row["data"]
                    cache[gw_str] = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
                return cache
        except Exception as e:
            print(f"[DB READ ALL ERROR] {e}")

    return _load_local_results_cache()


async def get_cached_gameweek(gw: int) -> Optional[dict]:
    """Fetch cached data for a specific gameweek."""
    gw_str = str(gw)
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow("SELECT data FROM results_cache WHERE gameweek = $1", gw)
                if row:
                    raw_data = row["data"]
                    return json.loads(raw_data) if isinstance(raw_data, str) else raw_data
                return None
        except Exception as e:
            print(f"[DB READ GW ERROR] {e}")

    cache = _load_local_results_cache()
    return cache.get(gw_str)


async def save_cached_gameweek(gw: int, data: dict):
    """Save gameweek scores persistently in PostgreSQL with JSON fallback."""
    if db_pool:
        try:
            json_payload = json.dumps(data)
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO results_cache (gameweek, data)
                    VALUES ($1, $2::jsonb)
                    ON CONFLICT (gameweek)
                    DO UPDATE SET data = EXCLUDED.data, created_at = CURRENT_TIMESTAMP
                    """,
                    gw,
                    json_payload,
                )
            return
        except Exception as e:
            print(f"[DB WRITE ERROR] {e}")

    cache = _load_local_results_cache()
    cache[str(gw)] = data
    _save_local_results_cache(cache)
