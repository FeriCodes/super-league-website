from collections import Counter
from typing import Any, Dict, List
import httpx

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://fantasy.premierleague.com/api"


def get_players_dict() -> Dict[int, Dict[str, str]]:
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


def get_manager_gw_data(manager_id: int, gameweek: int) -> dict:
    url = f"https://fantasy.premierleague.com/api/entry/{manager_id}/event/{gameweek}/picks/"
    response = httpx.get(url, headers=HEADERS)

    if response.status_code == 200:
        data = response.json()

        # ۱. حساب کردن امتیازها (تیکه اول)
        history = data["entry_history"]
        gross_points = history["points"]
        hits = history["event_transfers_cost"]
        net_points = gross_points - hits

        # ۲. بیرون کشیدن آیدی بازیکن‌ها (تیکه دوم)
        player_ids = []
        for pick in data["picks"]:
            player_ids.append(pick["element"])

        # ۳. تحویل همه‌چیز با هم
        return {
            "manager_id": manager_id,
            "gameweek": gameweek,
            "gw_points": net_points,
            "hits": hits,
            "player_ids": player_ids,
            "status": "success",
        }

    return {
        "manager_id": manager_id,
        "gameweek": gameweek,
        "status": "error",
        "message": f"Failed with status code {response.status_code}",
    }


def get_team_summary(manager_ids: List[int], gameweek: int, players_dict: Dict[int, Dict[str, str]]) -> Dict[str, Any]:
    """Aggregate total points and count player ownership across a list of managers."""
    managers_data = []
    all_player_ids = []
    total_team_points = 0

    for m_id in manager_ids:
        data = get_manager_gw_data(m_id, gameweek)
        if data.get("status") == "success":
            managers_data.append(data)
            total_team_points += data["gw_points"]
            all_player_ids.extend(data["player_ids"])

    # Count player occurrences
    player_counts = Counter(all_player_ids)
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
