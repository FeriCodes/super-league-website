from typing import Any, Dict, Dict, List, Optional, Set, Tuple
from app.fpl.client import fetch_fpl_api


async def fetch_raw_live_data(gw: int) -> Dict[str, Any]:
    """Fetch live gameweek events directly from the official FPL endpoint."""
    endpoint = f"event/{gw}/live"
    data = await fetch_fpl_api(endpoint)
    return data if data else {}


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

        team_id = player_to_team.get(player_id)

        # -------------------------------------------------------------
        # Scoring Accuracy Logic:
        # 1. Finished matches (FT): Use final official raw_points (includes confirmed bonuses).
        #    Never add provisional bonus to FT matches.
        # 2. Live matches (LIVE): Add provisional bonus only if official bonus is not yet confirmed.
        # 3. Unplayed matches: Use raw_points directly.
        # -------------------------------------------------------------
        if team_id in finished_teams:
            status = "FT"
            live_total = raw_points
        elif team_id in started_teams:
            status = "LIVE"
            bonus_to_add = provisional_bonuses.get(player_id, 0) if official_bonus == 0 else 0
            live_total = raw_points + bonus_to_add
        else:
            status = "Not Played Yet"
            live_total = raw_points

        live_summary[player_id] = {
            "points": live_total,
            "raw_points": raw_points,
            "status": status,
            "minutes": minutes_played,
        }

    return live_summary


def calculate_provisional_bps(elements: List[Dict[str, Any]]) -> Dict[int, int]:
    """Group players by match fixture and calculate provisional 3-2-1 bonus points based on BPS."""
    match_bps_map: Dict[int, List[Tuple[int, int]]] = {}
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
