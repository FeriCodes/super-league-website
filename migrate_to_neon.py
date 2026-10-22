import asyncio
import json
import os
from pathlib import Path
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "app" / "data"


async def run_migration():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not found in environment or .env file.")
        return

    print("Connecting to Neon PostgreSQL...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # 1. Migrate league teams
        teams_file = DATA_DIR / "sl_teams.json"
        with open(teams_file, "r", encoding="utf-8") as f:
            teams_data = json.load(f)

        await conn.execute("TRUNCATE TABLE league_teams;")
        for team, roster in teams_data.items():
            if isinstance(roster, list) and len(roster) > 0 and isinstance(roster[0], int):
                await conn.execute(
                    """
                    INSERT INTO league_teams (team_name, from_gw, to_gw, player_ids)
                    VALUES ($1, $2, $3, $4::jsonb)
                    """,
                    team,
                    1,
                    38,
                    json.dumps(roster),
                )
            elif isinstance(roster, list) and len(roster) > 0 and isinstance(roster[0], dict):
                for entry in roster:
                    await conn.execute(
                        """
                        INSERT INTO league_teams (team_name, from_gw, to_gw, player_ids)
                        VALUES ($1, $2, $3, $4::jsonb)
                        """,
                        team,
                        entry["from_gw"],
                        entry["to_gw"],
                        json.dumps(entry["ids"]),
                    )
        print("Successfully migrated league_teams to Neon.")

        # 2. Migrate league fixtures
        fixtures_file = DATA_DIR / "fixtures.json"
        with open(fixtures_file, "r", encoding="utf-8") as f:
            fixtures_data = json.load(f)

        await conn.execute("TRUNCATE TABLE league_fixtures;")
        for gw, matches in fixtures_data.items():
            await conn.execute(
                """
                INSERT INTO league_fixtures (gameweek, matches) VALUES ($1, $2::jsonb)
                """,
                int(gw),
                json.dumps(matches),
            )
        print("Successfully migrated league_fixtures to Neon.")

    except Exception as e:
        print(f"Migration error: {e}")
    finally:
        await conn.close()
        print("Database connection closed.")


if __name__ == "__main__":
    asyncio.run(run_migration())
