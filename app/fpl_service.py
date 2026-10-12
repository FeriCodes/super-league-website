from collections import Counter
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from app.fpl_client import fetch_fpl_api


def parse_manager_ids(raw_text: str) -> List[int]:
    """Extract integer manager IDs from raw text."""
    numbers = re.findall(r"\b\d+\b", raw_text)
    return [int(n) for n in numbers]


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


def apply_manager_auto_subs(
    picks: List[Dict[str, Any]],
    live_data: Dict[int, Dict[str, Any]],
    players_dict: Dict[int, Dict[str, Any]],
    manager_id: int,
) -> Tuple[List[Dict[str, Any]], List[int], List[int]]:
    """
    Apply live auto-substitution rules for a manager's 15-player squad.
    Returns:
      1. Updated picks list
      2. List of subbed-in player element IDs
      3. List of subbed-out player element IDs
    """
    updated_picks = [{k: v for k, v in p.items()} for p in picks]
    subbed_in_player_ids: List[int] = []
    subbed_out_player_ids: List[int] = []

    picks_by_pos: Dict[int, Dict[str, Any]] = {}
    for p in updated_picks:
        pos_key = int(p.get("position", 0))
        picks_by_pos[pos_key] = p

    starters = [picks_by_pos[i] for i in range(1, 12) if i in picks_by_pos]
    bench_gkp = picks_by_pos.get(12)
    bench_outfield = [picks_by_pos[i] for i in [13, 14, 15] if i in picks_by_pos]

    def player_did_not_play(element_id: int) -> bool:
        p_live = live_data.get(element_id, {})
        mins = p_live.get("minutes", 0) or 0
        match_status = p_live.get("status", "")

        # Finished match with 0 minutes played
        if match_status == "FT" and mins == 0:
            return True

        # Confirmed 100% absence before kickoff
        p_info = players_dict.get(element_id, {})
        chance = p_info.get("chance_of_playing")
        fpl_status = p_info.get("status")

        if match_status != "FT" and mins == 0:
            if chance == 0 or (fpl_status in ["i", "s", "u"] and chance == 0):
                return True

        return False

    def player_can_sub_in(element_id: int) -> bool:
        p_live = live_data.get(element_id, {})
        mins = p_live.get("minutes", 0) or 0
        match_status = p_live.get("status", "")
        return mins > 0 or match_status != "FT" or (match_status == "FT" and mins == 0)

    current_pos_counts: Dict[str, int] = {"GKP": 0, "DEF": 0, "MID": 0, "FWD": 0}
    for s in starters:
        pos_name = players_dict.get(s["element_id"], {}).get("position", "")
        if pos_name in current_pos_counts:
            current_pos_counts[pos_name] += 1

    # 1. Evaluate starting goalkeeper substitution
    starting_gkp = picks_by_pos.get(1)
    if starting_gkp and player_did_not_play(starting_gkp["element_id"]):
        if bench_gkp and player_can_sub_in(bench_gkp["element_id"]):
            orig_mult = starting_gkp.get("multiplier", 1) or 1
            bench_gkp["multiplier"] = orig_mult
            starting_gkp["multiplier"] = 0
            subbed_in_player_ids.append(bench_gkp["element_id"])
            subbed_out_player_ids.append(starting_gkp["element_id"])
            g_in = players_dict.get(bench_gkp["element_id"], {}).get("name", "Unknown")
            g_out = players_dict.get(starting_gkp["element_id"], {}).get("name", "Unknown")
            print(f"[AUTO-SUB][Manager {manager_id}] GKP: {g_out} OUT -> {g_in} IN")

    # 2. Evaluate outfield substitutions (slots 2 to 11)
    available_bench = list(bench_outfield)

    for starter in starters:
        p_id = starter["element_id"]
        pos_name = players_dict.get(p_id, {}).get("position", "")

        if pos_name not in ["DEF", "MID", "FWD"] or not player_did_not_play(p_id):
            continue

        p_out_name = players_dict.get(p_id, {}).get("name", f"Player {p_id}")
        candidate_found = None

        for candidate in available_bench:
            cand_id = candidate["element_id"]
            if not player_can_sub_in(cand_id):
                continue

            candidate_pos = players_dict.get(cand_id, {}).get("position", "")
            if candidate_pos not in ["DEF", "MID", "FWD"]:
                continue

            temp_counts = dict(current_pos_counts)
            temp_counts[pos_name] = max(0, temp_counts.get(pos_name, 0) - 1)
            temp_counts[candidate_pos] = temp_counts.get(candidate_pos, 0) + 1

            # Official FPL formation rules: at least 3 DEF, 2 MID, 1 FWD
            if temp_counts.get("DEF", 0) >= 3 and temp_counts.get("MID", 0) >= 2 and temp_counts.get("FWD", 0) >= 1:
                candidate_found = candidate
                current_pos_counts = temp_counts
                break

        if candidate_found:
            available_bench.remove(candidate_found)
            orig_mult = starter.get("multiplier", 1) or 1
            candidate_found["multiplier"] = orig_mult
            starter["multiplier"] = 0
            subbed_in_player_ids.append(candidate_found["element_id"])
            subbed_out_player_ids.append(starter["element_id"])

            p_in_name = players_dict.get(candidate_found["element_id"], {}).get(
                "name", f"Player {candidate_found['element_id']}"
            )
            print(
                f"[AUTO-SUB SUCCESS][Manager {manager_id}] Field: {p_out_name} ({pos_name}) OUT -> {p_in_name} ({candidate_pos}) IN"
            )

    return updated_picks, subbed_in_player_ids, subbed_out_player_ids


async def get_team_summary(
    manager_ids: List[int],
    gameweek: int,
    players_dict: Dict[int, Dict[str, Any]],
    live_data: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate total points, hit costs, active chips, captains, and count effective player ownership with live auto-sub."""
    managers_data = []
    active_player_counts: Dict[int, int] = Counter()
    bench_player_counts: Dict[int, int] = Counter()
    captain_counts: Dict[int, int] = Counter()
    total_team_points = 0
    total_hits_cost = 0
    active_chips: List[str] = []
    all_subbed_in_ids: Set[int] = set()
    all_subbed_out_ids: Set[int] = set()
    has_bench_boost = False

    left_to_play_count = 0
    total_slots_count = 0

    for m_id in manager_ids:
        data = await get_manager_gw_data(m_id, gameweek)
        if data.get("status") == "success":
            hits = data.get("hits", 0)
            chip = data.get("active_chip")
            if chip:
                active_chips.append(chip)

            is_bench_boost = chip == "Bench Boost"
            if is_bench_boost:
                has_bench_boost = True

            manager_live_points = 0
            picks = data.get("picks", [])

            if not is_bench_boost:
                picks, sub_in_ids, sub_out_ids = apply_manager_auto_subs(picks, live_data, players_dict, m_id)
                all_subbed_in_ids.update(sub_in_ids)
                all_subbed_out_ids.update(sub_out_ids)
                data["picks"] = picks

            for item in picks:
                p_id = int(item["element_id"])
                mult = int(item.get("multiplier", 0))

                player_live = live_data.get(p_id, {})
                status = player_live.get("status", "Not Played Yet")
                p_score = player_live.get("points", 0)

                if mult >= 2:
                    captain_counts[p_id] += 1

                if is_bench_boost:
                    effective_weight = mult if mult > 0 else 1
                    active_player_counts[p_id] += effective_weight
                    manager_live_points += p_score * effective_weight
                    total_slots_count += 1
                    if status != "FT":
                        left_to_play_count += 1
                else:
                    if mult > 0:
                        active_player_counts[p_id] += mult
                        manager_live_points += p_score * mult
                        total_slots_count += 1
                        if status != "FT":
                            left_to_play_count += 1
                    else:
                        bench_player_counts[p_id] += 1

            net_manager_points = manager_live_points - hits
            data["gw_points"] = net_manager_points

            managers_data.append(data)
            total_team_points += net_manager_points
            total_hits_cost += hits

    ownership_list = []
    for p_id, count in Counter(active_player_counts).most_common():
        player_info = players_dict.get(p_id, {"name": "Unknown", "position": "Unknown"})
        ownership_list.append(
            {
                "id": p_id,
                "name": player_info["name"],
                "position": player_info["position"],
                "count": count,
                "is_sub_in": p_id in all_subbed_in_ids,
                "is_sub_out": False,
            }
        )

    bench_ownership_list = []
    for p_id, count in Counter(bench_player_counts).most_common():
        player_info = players_dict.get(p_id, {"name": "Unknown", "position": "Unknown"})
        bench_ownership_list.append(
            {
                "id": p_id,
                "name": player_info["name"],
                "position": player_info["position"],
                "count": count,
                "is_sub_in": False,
                "is_sub_out": p_id in all_subbed_out_ids,
            }
        )

    chips_list = []
    if active_chips:
        chip_counts = Counter(active_chips)
        for name, count in chip_counts.items():
            chips_list.append({"name": name, "count": count})
        chips_display = ", ".join(f"{c['count']}x {c['name']}" for c in chips_list)
    else:
        chips_display = "None"

    captains_list = []
    for p_id, count in Counter(captain_counts).most_common():
        player_name = players_dict.get(p_id, {}).get("name", "Unknown")
        captains_list.append({"name": player_name, "count": count})

    captains_display = ", ".join(f"{c['name']} ({c['count']}x)" for c in captains_list) if captains_list else "None"

    return {
        "gameweek": gameweek,
        "total_team_points": total_team_points,
        "total_hits_cost": total_hits_cost,
        "active_chips": chips_display,
        "chips_list": chips_list,
        "has_bench_boost": has_bench_boost,
        "captains": captains_display,
        "captains_list": captains_list,
        "managers_count": len(managers_data),
        "managers": managers_data,
        "ownership": ownership_list,
        "bench_ownership": bench_ownership_list,
        "status_counts": {
            "left_to_play": left_to_play_count,
            "total_slots": total_slots_count,
        },
    }


async def fetch_raw_live_data(gw: int) -> Dict[str, Any]:
    """Fetch live gameweek events directly from the official FPL endpoint."""
    endpoint = f"event/{gw}/live"
    data = await fetch_fpl_api(endpoint)
    return data if data else {}


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
