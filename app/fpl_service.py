from collections import Counter
import re
from typing import Any, Dict, List
import httpx

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://fantasy.premierleague.com/api"


def parse_manager_ids(raw_text: str) -> List[int]:
    """Extract integer manager IDs from messy text."""
    numbers = re.findall(r"\b\d+\b", raw_text)
    return [int(n) for n in numbers]


def get_players_dict() -> Dict[int, Dict[str, str]]:
    """Fetch all Premier League players and map ID to name and position."""
    url = f"{BASE_URL}/bootstrap-static/"
    response = httpx.get(url, headers=HEADERS)

    if response.status_code != 200:
        return {}

    data = response.json()
    position_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

    players_dict = {}
    for element in data.get("elements", []):
        player_id = element["id"]
        pos_id = element["element_type"]
        players_dict[player_id] = {
            "name": element["web_name"],
            "position": position_map.get(pos_id, "Unknown"),
        }

    return players_dict


def get_manager_gw_data(manager_id: int, gameweek: int) -> Dict[str, Any]:
    """Fetch manager's score, hits, and squad picks with captain multipliers."""
    url = f"{BASE_URL}/entry/{manager_id}/event/{gameweek}/picks/"
    response = httpx.get(url, headers=HEADERS)

    if response.status_code != 200:
        return {"status": "error", "manager_id": manager_id}

    data = response.json()
    history = data["entry_history"]

    points = history["points"]
    hits = history["event_transfers_cost"]
    gw_points = points - hits

    picks_summary = [
        {"element_id": pick["element"], "multiplier": pick["multiplier"]} for pick in data.get("picks", [])
    ]

    return {
        "manager_id": manager_id,
        "gameweek": gameweek,
        "gw_points": gw_points,
        "hits": hits,
        "picks": picks_summary,
        "status": "success",
    }


def get_team_summary(manager_ids: List[int], gameweek: int, players_dict: Dict[int, Dict[str, str]]) -> Dict[str, Any]:
    """Aggregate total points and count effective player ownership (accounting for captains)."""
    managers_data = []
    player_counts = Counter()
    total_team_points = 0

    for m_id in manager_ids:
        data = get_manager_gw_data(m_id, gameweek)
        if data.get("status") == "success":
            managers_data.append(data)
            total_team_points += data["gw_points"]

            for item in data["picks"]:
                if item["multiplier"] > 0:
                    player_counts[item["element_id"]] += item["multiplier"]

    ownership_list = []
    for p_id, count in player_counts.most_common():
        player_info = players_dict.get(p_id, {"name": "Unknown", "position": "Unknown"})
        ownership_list.append(
            {
                "id": p_id,
                "name": player_info["name"],
                "position": player_info["position"],
                "count": count,
            }
        )

    return {
        "gameweek": gameweek,
        "total_team_points": total_team_points,
        "managers_count": len(managers_data),
        "managers": managers_data,
        "ownership": ownership_list,
    }
