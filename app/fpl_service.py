from collections import Counter
from datetime import datetime, timezone
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
    live_data: Dict[int, Dict[str, Any]],
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
            hits = data.get("hits", 0)
            chip = data.get("active_chip")
            if chip:
                readable_chip = chip_name_map.get(chip, chip.title())
                active_chips.append(readable_chip)

            is_bench_boost = chip == "bboost"
            manager_live_points = 0

            for item in data.get("picks", []):
                p_id = item["element_id"]
                pos = item.get("position", 0)
                mult = item.get("multiplier", 0)

                player_live = live_data.get(p_id, {})
                status = player_live.get("status", "Not Played Yet")

                # Count live points for players whose matches are underway or finished
                p_score = player_live.get("points", 0) if status in ("FT", "LIVE") else 0

                # Track captain selection (multiplier >= 2)
                if mult >= 2:
                    captain_counts[p_id] += 1

                # Bench Boost counts all 15 players
                if is_bench_boost:
                    player_counts[p_id] += 1
                    effective_mult = mult if mult > 0 else 1
                    manager_live_points += p_score * effective_mult
                else:
                    # Starting XI: multiplier > 0 OR lineup positions 1 to 11
                    if mult > 0:
                        player_counts[p_id] += 1
                        manager_live_points += p_score * mult
                    elif 1 <= pos <= 11 and mult == 0:
                        player_counts[p_id] += 1
                        manager_live_points += p_score

            # Deduct transfer hits from the manager's live points
            net_manager_points = manager_live_points - hits
            data["gw_points"] = net_manager_points

            managers_data.append(data)
            total_team_points += net_manager_points
            total_hits_cost += hits

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
    static_data = await fetch_fpl_api("bootstrap-static")
    player_to_team: Dict[int, int] = {}
    if static_data:
        for el in static_data.get("elements", []):
            player_to_team[el["id"]] = el.get("team")

    fixtures_data = await fetch_fpl_api("fixtures")
    finished_teams = set()
    started_teams = set()

    if fixtures_data and isinstance(fixtures_data, list):
        for fix in fixtures_data:
            if fix.get("event") == gw:
                home_team = fix.get("team_h")
                away_team = fix.get("team_a")
                is_finished = fix.get("finished") is True or fix.get("finished_provisional") is True
                is_started = fix.get("started") is True

                if is_finished:
                    finished_teams.add(home_team)
                    finished_teams.add(away_team)
                elif is_started:
                    started_teams.add(home_team)
                    started_teams.add(away_team)

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

        team_id = player_to_team.get(player_id)
        if team_id in finished_teams:
            status = "FT"
        elif team_id in started_teams:
            status = "LIVE"
        else:
            status = "Not Played Yet"

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

    # 1. Official is_current marker
    for event in events:
        if event.get("is_current") is True:
            return event.get("id", 1)

    # 2. Check by deadline time: find the latest gameweek that has actually started
    now = datetime.now(timezone.utc)
    started_gws = []
    for event in events:
        deadline_str = event.get("deadline_time")
        if deadline_str:
            try:
                # Format: 2026-08-15T10:00:00Z
                deadline_dt = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
                if deadline_dt <= now:
                    started_gws.append(event.get("id"))
            except Exception:
                pass

    if started_gws:
        return max(started_gws)

    # 3. Fallback: check finished flag
    finished_gws = [e.get("id") for e in events if e.get("finished") is True]
    if finished_gws:
        return max(finished_gws)

    # 4. Fallback: next upcoming gameweek
    for event in events:
        if event.get("is_next") is True:
            return event.get("id", 1)

    return 1
