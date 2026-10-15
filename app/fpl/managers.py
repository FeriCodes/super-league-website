from typing import Any, Dict
from app.fpl_client import fetch_fpl_api


async def get_players_dict() -> Dict[int, Dict[str, Any]]:
    """Fetch all Premier League players and map ID to name, position, team ID, and availability status."""
    data = await fetch_fpl_api("bootstrap-static")
    if not data:
        return {}

    position_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    players_dict = {}
    for element in data.get("elements", []):
        player_id = element["id"]
        pos_id = element["element_type"]
        chance = element.get("chance_of_playing_this_round")
        news = element.get("news", "")
        status = element.get("status", "a")

        players_dict[player_id] = {
            "name": element["web_name"],
            "position": position_map.get(pos_id, "Unknown"),
            "team_id": element.get("team"),
            "chance_of_playing": chance,
            "news": news,
            "status": status,
        }

    return players_dict


async def get_manager_gw_data(manager_id: int, gameweek: int) -> Dict[str, Any]:
    """Fetch manager gameweek score, transfer hits, active chip, and manager/team profile info."""
    endpoint = f"entry/{manager_id}/event/{gameweek}/picks"
    data = await fetch_fpl_api(endpoint)

    if not data:
        print(f"Manager {manager_id} GW {gameweek} failed to fetch.")
        return {"status": "error", "manager_id": manager_id}

    # Retrieve manager and squad names from public profile
    profile_data = await fetch_fpl_api(f"entry/{manager_id}/") or {}
    player_first = profile_data.get("player_first_name", "")
    player_last = profile_data.get("player_last_name", "")
    manager_name = f"{player_first} {player_last}".strip() or f"Manager #{manager_id}"
    team_name = profile_data.get("name", "FPL Squad")

    entry_history = data.get("entry_history") or {}
    raw_points = entry_history.get("points", 0)
    hits = entry_history.get("event_transfers_cost", 0)
    net_gw_points = raw_points - hits
    active_chip = data.get("active_chip")

    chip_map = {
        "bboost": "Bench Boost",
        "3xc": "Triple Captain",
        "freehit": "Free Hit",
        "wildcard": "Wildcard",
    }
    readable_chip = chip_map.get(active_chip, active_chip.title()) if active_chip else None

    picks_summary = [
        {
            "element_id": int(pick["element"]),
            "position": int(pick.get("position", idx + 1)),
            "multiplier": int(pick.get("multiplier", 0)),
        }
        for idx, pick in enumerate(data.get("picks", []))
    ]

    return {
        "manager_id": manager_id,
        "manager_name": manager_name,
        "team_name": team_name,
        "gameweek": gameweek,
        "gw_points": net_gw_points,
        "hits": hits,
        "active_chip": readable_chip,
        "picks": picks_summary,
        "status": "success",
    }
