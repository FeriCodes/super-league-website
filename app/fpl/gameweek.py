from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.fpl.client import fetch_fpl_api

IRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def _build_deadline_info(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse an FPL event deadline_time (UTC) and format it for Iran time (UTC+3:30)."""
    deadline_str = event.get("deadline_time")
    if not deadline_str:
        return None

    try:
        deadline_utc = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
    except ValueError:
        return None

    deadline_iran = deadline_utc.astimezone(IRAN_TZ)
    return {
        "gw": event.get("id"),
        "deadline_iso": deadline_utc.isoformat(),
        "iran_date": deadline_iran.strftime("%a, %d %b %Y"),
        "iran_time": deadline_iran.strftime("%H:%M"),
        "iran_label": f"{deadline_iran.strftime('%a, %d %b - %H:%M')}",
    }


async def get_gw_deadline_info(target_gw: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Fetch upcoming gameweek deadline info converted to Iran time."""
    data = await fetch_fpl_api("bootstrap-static")
    if not data or "events" not in data:
        return None

    events = data.get("events", [])
    if target_gw is not None:
        event = next((e for e in events if e.get("id") == target_gw), None)
    else:
        event = next((e for e in events if e.get("is_next")), None)

    if not event:
        return None

    info = _build_deadline_info(event)
    if not info:
        return None

    deadline_utc = datetime.fromisoformat(info["deadline_iso"])
    if deadline_utc <= datetime.now(timezone.utc):
        return None

    return info


async def get_gameweek_status(gameweek: int) -> dict:
    """
    Report whether a gameweek has started, finished, and had its data checked.

    `data_checked` is FPL's signal that bonus points have been applied and the
    scores are final. Only that state is safe to persist as a permanent result.
    """
    data = await fetch_fpl_api("bootstrap-static")
    if not data or "events" not in data:
        return {
            "valid": True,
            "finished": False,
            "data_checked": False,
            "is_live": False,
            "message": "",
            "deadline": None,
        }

    for event in data.get("events", []):
        if event.get("id") == gameweek:
            is_current = bool(event.get("is_current", False))
            is_finished = bool(event.get("finished", False))
            data_checked = bool(event.get("data_checked", False))

            # A gameweek is live if it is the current active week and scores aren't finalized yet
            is_live = is_current and not data_checked

            if not is_current and not is_finished and not data_checked:
                return {
                    "valid": False,
                    "finished": False,
                    "data_checked": False,
                    "is_live": False,
                    "message": f"Gameweek {gameweek} has not started yet. Team lineups and points will be available after the deadline.",
                    "deadline": _build_deadline_info(event),
                }
            return {
                "valid": True,
                "finished": is_finished,
                "data_checked": data_checked,
                "is_live": is_live,
                "message": "",
                "deadline": None,
            }

    return {
        "valid": False,
        "finished": False,
        "data_checked": False,
        "is_live": False,
        "message": f"Gameweek {gameweek} not found.",
        "deadline": None,
    }


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
