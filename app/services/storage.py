import json
import os
from pathlib import Path
from typing import Optional
import asyncpg

APP_DIR = Path(__file__).resolve().parent.parent

TEAMS_FILE = APP_DIR / "data" / "sl_teams.json"
FIXTURES_FILE = APP_DIR / "data" / "fixtures.json"
RESULTS_CACHE_FILE = APP_DIR / "data" / "results_cache.json"

DATABASE_URL = os.getenv("DATABASE_URL")
db_pool: Optional[asyncpg.Pool] = None

# In-memory cache to prevent repetitive database roundtrips on every request
_memory_teams_cache: Optional[dict] = None
_memory_fixtures_cache: Optional[dict] = None


async def init_db():
    """Initialize PostgreSQL connection pool and preload Neon data."""
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
                    CREATE TABLE IF NOT EXISTS league_teams (
                        id SERIAL PRIMARY KEY,
                        team_name VARCHAR(100) NOT NULL,
                        from_gw INT NOT NULL DEFAULT 1,
                        to_gw INT NOT NULL DEFAULT 38,
                        player_ids JSONB NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS league_fixtures (
                        gameweek INT PRIMARY KEY,
                        matches JSONB NOT NULL
                    );
                """)
            # Preload database records into in-memory cache
            await preload_db_data()
        except Exception as e:
            print(f"[DATABASE INIT ERROR] {e}")
            db_pool = None


async def close_db():
    """Close PostgreSQL connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()


async def preload_db_data():
    """Preload teams and fixtures from Neon into in-memory cache on startup."""
    global _memory_teams_cache, _memory_fixtures_cache
    if not db_pool:
        return

    try:
        async with db_pool.acquire() as conn:
            # Load teams table from Neon
            team_rows = await conn.fetch("SELECT team_name, from_gw, to_gw, player_ids FROM league_teams")
            if team_rows:
                teams_dict = {}
                for row in team_rows:
                    t_name = row["team_name"]
                    raw_p = row["player_ids"]
                    p_ids = json.loads(raw_p) if isinstance(raw_p, str) else raw_p
                    entry = {"from_gw": row["from_gw"], "to_gw": row["to_gw"], "ids": p_ids}
                    teams_dict.setdefault(t_name, []).append(entry)
                _memory_teams_cache = teams_dict

            # Load fixtures table from Neon
            fix_rows = await conn.fetch("SELECT gameweek, matches FROM league_fixtures")
            if fix_rows:
                fix_dict = {}
                for row in fix_rows:
                    raw_m = row["matches"]
                    matches = json.loads(raw_m) if isinstance(raw_m, str) else raw_m
                    fix_dict[str(row["gameweek"])] = matches
                _memory_fixtures_cache = fix_dict
    except Exception as e:
        print(f"[PRELOAD ERROR] {e}")


def load_teams() -> dict:
    """Read teams from in-memory cache (Neon) with fallback to local sl_teams.json."""
    global _memory_teams_cache
    if _memory_teams_cache:
        return _memory_teams_cache

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
    """Load fixtures from in-memory cache (Neon) with fallback to local fixtures.json."""
    global _memory_fixtures_cache
    if _memory_fixtures_cache:
        return _memory_fixtures_cache

    if not FIXTURES_FILE.exists():
        return {}
    with open(FIXTURES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_local_results_cache() -> dict:
    """Read local results_cache.json file fallback."""
    if not RESULTS_CACHE_FILE.exists():
        return {}
    try:
        with open(RESULTS_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_local_results_cache(data: dict):
    """Write local results_cache.json file fallback."""
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
    """Persist gameweek scores in PostgreSQL with JSON fallback."""
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
