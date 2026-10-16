import asyncio
from collections import Counter
from typing import Any, Dict, List, Set

from app.fpl.client import fetch_fpl_api
from app.fpl.auto_sub import apply_manager_auto_subs


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

    # Fetch all managers' gameweek data concurrently to minimize network latency
    tasks = [get_manager_gw_data(m_id, gameweek) for m_id in manager_ids]
    managers_raw_data = await asyncio.gather(*tasks)

    for data in managers_raw_data:
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
                picks, sub_in_ids, sub_out_ids = apply_manager_auto_subs(
                    picks, live_data, players_dict, data.get("manager_id")
                )
                all_subbed_in_ids.update(sub_in_ids)
                all_subbed_out_ids.update(sub_out_ids)
                data["picks"] = picks

            # Extract individual manager's captain
            manager_captain_name = "-"
            for item in picks:
                p_id = int(item["element_id"])
                mult = int(item.get("multiplier", 0))

                player_live = live_data.get(p_id, {})
                status = player_live.get("status", "Not Played Yet")
                p_score = player_live.get("points", 0)

                if mult >= 2:
                    captain_counts[p_id] += 1
                    manager_captain_name = players_dict.get(p_id, {}).get("name", "Unknown")

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

            data["captain_name"] = manager_captain_name
            net_manager_points = manager_live_points - hits
            data["gw_points"] = net_manager_points

            managers_data.append(data)
            total_team_points += net_manager_points
            total_hits_cost += hits

    # sort managers by their gameweek points in descending order
    managers_data.sort(key=lambda m: m["gw_points"], reverse=True)

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
