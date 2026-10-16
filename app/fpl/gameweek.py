from typing import Any, Dict
from datetime import datetime, timezone
from app.fpl.client import fetch_fpl_api


async def get_gameweek_status(gameweek: int) -> dict:
    """Check if the requested gameweek has kicked off or is in the future."""
    data = await fetch_fpl_api("bootstrap-static")
    if not data or "events" not in data:
        return {"valid": True, "finished": False, "message": ""}

    for event in data.get("events", []):
        if event.get("id") == gameweek:
            is_current = bool(event.get("is_current", False))
            is_finished = bool(event.get("finished", False))
            data_checked = bool(event.get("data_checked", False))

            if not is_current and not is_finished and not data_checked:
                return {
                    "valid": False,
                    "finished": False,
                    "message": f"Gameweek {gameweek} has not started yet. Team lineups and points will be available after the deadline.",
                }
            return {
                "valid": True,
                "finished": is_finished,
                "message": "",
            }

    return {"valid": False, "finished": False, "message": f"Gameweek {gameweek} not found."}


async def get_current_gameweek() -> int:
    """Find the current active or most recently commenced gameweek based on deadlines."""
    data = await fetch_fpl_api("bootstrap-static")
    if not data or "events" not in data:
        return 1

    events = data.get("events", [])

    for event in events:
        if event.get("is_current") is True:
            return event.get("id", 1)

    now = datetime.now(timezone.utc)
    started_gws = []
    for event in events:
        deadline_str = event.get("deadline_time")
        if deadline_str:
            try:
                deadline_dt = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
                if deadline_dt <= now:
                    started_gws.append(event.get("id"))
            except Exception:
                pass

    if started_gws:
        return max(started_gws)

    finished_gws = [e.get("id") for e in events if e.get("finished") is True]
    if finished_gws:
        return max(finished_gws)

    for event in events:
        if event.get("is_next") is True:
            return event.get("id", 1)

    return 1


async def get_team_fixtures_map(gw: int) -> Dict[int, str]:
    """Map each Premier League team ID to their opponent's short name for the gameweek."""
    static_data = await fetch_fpl_api("bootstrap-static")
    if not static_data:
        return {}

    team_short_names = {t["id"]: t["short_name"] for t in static_data.get("teams", [])}

    fixtures_data = await fetch_fpl_api("fixtures")
    fixture_map: Dict[int, str] = {}

    if fixtures_data and isinstance(fixtures_data, list):
        for fix in fixtures_data:
            if fix.get("event") == gw:
                h_id = fix.get("team_h")
                a_id = fix.get("team_a")
                h_short = team_short_names.get(h_id, "OPP")
                a_short = team_short_names.get(a_id, "OPP")

                fixture_map[h_id] = a_short
                fixture_map[a_id] = h_short

    return fixture_map
