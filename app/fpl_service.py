from collections import Counter
import re
from typing import Any, Dict, List, Optional
from app.fpl_client import fetch_fpl_api


def parse_manager_ids(raw_text: str) -> List[int]:
    """Extract integer manager IDs from messy text."""
    numbers = re.findall(r"\b\d+\b", raw_text)
    return [int(n) for n in numbers]


async def get_players_dict() -> Dict[int, Dict[str, str]]:
    """Fetch all Premier League players and map ID to name and position."""
    data = await fetch_fpl_api("bootstrap-static")
    if not data:
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


async def get_manager_gw_data(manager_id: int, gameweek: int) -> Dict[str, Any]:
    """Fetch manager's gameweek score, transfer hits, and squad picks."""
    endpoint = f"entry/{manager_id}/event/{gameweek}/picks"
    data = await fetch_fpl_api(endpoint)

    if not data:
        print(f"Manager {manager_id} GW {gameweek} failed to fetch.")
        return {"status": "error", "manager_id": manager_id}

    entry_history = data.get("entry_history") or {}

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


async def get_team_summary(
    manager_ids: List[int],
    gameweek: int,
    players_dict: Dict[int, Dict[str, str]],
) -> Dict[str, Any]:
    """Aggregate total points, hit costs, active chips, captains, and count effective player ownership."""
    managers_data = []
    player_counts = Counter()
    captain_counts = Counter()
    total_team_points = 0
    total_hits_cost = 0
    active_chips = []

    chip_name_map = {
        "bboost": "Bench Boost",
        "3xc": "Triple Captain",
        "freehit": "Free Hit",
        "wildcard": "Wildcard",
    }

    for m_id in manager_ids:
        data = await get_manager_gw_data(m_id, gameweek)
        if data.get("status") == "success":
            managers_data.append(data)
            total_team_points += data["gw_points"]
            total_hits_cost += data["hits"]

            chip = data.get("active_chip")
            if chip:
                readable_chip = chip_name_map.get(chip, chip.title())
                active_chips.append(readable_chip)

            is_bench_boost = chip == "bboost"

            for item in data.get("picks", []):
                pos = item.get("position", 0)
                mult = item.get("multiplier", 0)

                # Track captain selection (multiplier >= 2)
                if mult >= 2:
                    captain_counts[item["element_id"]] += 1

                # Bench Boost counts all 15 players
                if is_bench_boost:
                    player_counts[item["element_id"]] += 1
                else:
                    # Only starting XI counts: multiplier > 0 OR position 1 to 11
                    if mult > 0 or (1 <= pos <= 11 and mult != 0):
                        player_counts[item["element_id"]] += 1

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

    # Format chips display text
    if active_chips:
        chip_counts = Counter(active_chips)
        chips_display = ", ".join(f"{count}x {name}" for name, count in chip_counts.items())
    else:
        chips_display = "None"

    # Format captains display text
    captains_formatted = []
    for p_id, count in captain_counts.most_common():
        player_name = players_dict.get(p_id, {}).get("name", "Unknown")
        captains_formatted.append(f"{player_name} ({count}x)")
    captains_display = ", ".join(captains_formatted) if captains_formatted else "None"

    return {
        "gameweek": gameweek,
        "total_team_points": total_team_points,
        "total_hits_cost": total_hits_cost,
        "active_chips": chips_display,
        "captains": captains_display,
        "managers_count": len(managers_data),
        "managers": managers_data,
        "ownership": ownership_list,
    }


async def fetch_raw_live_data(gw: int) -> Dict[str, Any]:
    """Fetch live gameweek events directly from the official FPL endpoint."""
    endpoint = f"event/{gw}/live"
    data = await fetch_fpl_api(endpoint)
    return data if data else {}


def calculate_provisional_bps(elements: List[Dict[str, Any]]) -> Dict[int, int]:
    """Group players by match fixture and calculate provisional 3-2-1 bonus points based on BPS."""
    match_bps_map: Dict[int, List[tuple]] = {}
    provisional_bonuses: Dict[int, int] = {}

    for el in elements:
        player_id = el.get("id")
        stats = el.get("stats", {})
        bps_score = stats.get("bps", 0)

        explain_list = el.get("explain", [])
        if not explain_list:
            continue

        fixture_id = explain_list[0].get("fixture")
        if fixture_id is not None:
            match_bps_map.setdefault(fixture_id, []).append((player_id, bps_score))

    for fix_id, players in match_bps_map.items():
        sorted_by_bps = sorted(players, key=lambda item: item[1], reverse=True)
        if not sorted_by_bps:
            continue

        unique_scores = sorted(list(set(p[1] for p in sorted_by_bps if p[1] > 0)), reverse=True)

        for p_id, score in sorted_by_bps:
            if score <= 0:
                provisional_bonuses[p_id] = 0
            elif len(unique_scores) > 0 and score == unique_scores[0]:
                provisional_bonuses[p_id] = 3
            elif len(unique_scores) > 1 and score == unique_scores[1]:
                provisional_bonuses[p_id] = 2
            elif len(unique_scores) > 2 and score == unique_scores[2]:
                provisional_bonuses[p_id] = 1
            else:
                provisional_bonuses[p_id] = 0

    return provisional_bonuses


async def get_live_scores_and_status(gw: int) -> Dict[int, Dict[str, Any]]:
    """Generate live points, provisional bonuses, and match status keyed by player ID."""
    raw_data = await fetch_raw_live_data(gw)
    elements = raw_data.get("elements", [])
    provisional_bonuses = calculate_provisional_bps(elements)

    live_summary: Dict[int, Dict[str, Any]] = {}

    for el in elements:
        player_id = el.get("id")
        stats = el.get("stats", {})

        raw_points = stats.get("total_points", 0)
        official_bonus = stats.get("bonus", 0)
        minutes_played = stats.get("minutes", 0)

        bonus_to_add = provisional_bonuses.get(player_id, 0) if official_bonus == 0 else 0
        live_total = raw_points + bonus_to_add

        explain_list = el.get("explain", [])
        if not explain_list or minutes_played == 0:
            status = "Not Played Yet"
        elif minutes_played >= 90:
            status = "FT"
        else:
            status = "LIVE"

        live_summary[player_id] = {
            "points": live_total,
            "raw_points": raw_points,
            "status": status,
            "minutes": minutes_played,
        }

    return live_summary


async def get_gameweek_status(gameweek: int) -> dict:
    """Check if the requested gameweek has kicked off or is in the future."""
    data = await fetch_fpl_api("bootstrap-static")
    if not data or "events" not in data:
        return {"valid": True, "message": ""}

    for event in data["events"]:
        if event.get("id") == gameweek:
            # Check if gameweek deadline has passed and matches have started
            is_current = event.get("is_current", False)
            is_finished = event.get("finished", False)
            data_checked = event.get("data_checked", False)

            if not is_current and not is_finished and not data_checked:
                return {
                    "valid": False,
                    "message": f"Gameweek {gameweek} has not started yet. Team lineups and points will be available after the deadline.",
                }
            return {"valid": True, "message": ""}

    return {"valid": False, "message": f"Gameweek {gameweek} not found."}
