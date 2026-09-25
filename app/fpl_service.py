from collections import Counter
import re
import time
from typing import Any, Dict, List, Optional
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
BASE_URL = "https://fantasy.premierleague.com/api"


def parse_manager_ids(raw_text: str) -> List[int]:
    """Extract integer manager IDs from messy text."""
    numbers = re.findall(r"\b\d+\b", raw_text)
    return [int(n) for n in numbers]


def get_players_dict() -> Dict[int, Dict[str, str]]:
    """Fetch all Premier League players and map ID to name and position."""
    url = f"{BASE_URL}/bootstrap-static/"
    try:
        with httpx.Client(headers=HEADERS, timeout=20.0, verify=False, follow_redirects=True) as client:
            response = client.get(url)
            if response.status_code != 200:
                return {}
            data = response.json()
    except Exception as e:
        print(f"Warning: could not fetch player cache: {e}")
        return {}

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


def get_manager_gw_data(
    manager_id: int,
    gameweek: int,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Fetch manager's gameweek score, transfer hits, and squad picks."""
    picks_url = f"{BASE_URL}/entry/{manager_id}/event/{gameweek}/picks/"

    def _fetch(http_client: httpx.Client) -> Dict[str, Any]:
        response = http_client.get(picks_url)
        if response.status_code != 200:
            print(f"Manager {manager_id} GW {gameweek} failed with status {response.status_code}")
            return {"status": "error", "manager_id": manager_id}

        data = response.json()
        entry_history = data.get("entry_history") or {}

        # Pure gameweek points (excluding hits)
        raw_points = entry_history.get("points", 0)
        hits = entry_history.get("event_transfers_cost", 0)
        net_gw_points = raw_points - hits
        active_chip = data.get("active_chip")

        picks_summary = [
            {
                "element_id": pick["element"],
                "position": pick.get("position", idx + 1),
                "multiplier": pick.get("multiplier", 0),
            }
            for idx, pick in enumerate(data.get("picks", []))
        ]

        return {
            "manager_id": manager_id,
            "gameweek": gameweek,
            "gw_points": net_gw_points,
            "hits": hits,
            "active_chip": active_chip,
            "picks": picks_summary,
            "status": "success",
        }

    try:
        if client is not None:
            return _fetch(client)
        with httpx.Client(headers=HEADERS, timeout=20.0, verify=False, follow_redirects=True) as local_client:
            return _fetch(local_client)
    except Exception as exc:
        print(f"Error fetching manager {manager_id} GW {gameweek}: {exc}")
        return {"status": "error", "manager_id": manager_id}


def get_team_summary(
    manager_ids: List[int],
    gameweek: int,
    players_dict: Dict[int, Dict[str, str]],
) -> Dict[str, Any]:
    """Aggregate total points, hit costs, and count effective player ownership."""
    managers_data = []
    player_counts = Counter()
    total_team_points = 0
    total_hits_cost = 0

    with httpx.Client(headers=HEADERS, timeout=25.0, verify=False, follow_redirects=True) as client:
        for m_id in manager_ids:
            data = get_manager_gw_data(m_id, gameweek, client=client)
            if data.get("status") == "success":
                managers_data.append(data)
                total_team_points += data["gw_points"]
                total_hits_cost += data["hits"]

                is_bench_boost = data.get("active_chip") == "bboost"

                for item in data.get("picks", []):
                    pos = item.get("position", 0)
                    mult = item.get("multiplier", 0)

                    # Bench Boost counts all 15 players
                    if is_bench_boost:
                        player_counts[item["element_id"]] += 1
                    else:
                        # Only starting XI counts: multiplier > 0 (standard active) OR position 1 to 11
                        if mult > 0 or (1 <= pos <= 11 and mult != 0):
                            player_counts[item["element_id"]] += 1
                        elif mult > 0:
                            player_counts[item["element_id"]] += 1

            # Small delay to prevent FPL rate limiting (429)
            time.sleep(0.05)

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
        "total_hits_cost": total_hits_cost,
        "managers_count": len(managers_data),
        "managers": managers_data,
        "ownership": ownership_list,
    }
