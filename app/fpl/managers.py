import asyncio
from collections import Counter
from typing import Any, Dict, List, Set

from app.fpl.client import fetch_fpl_api, fetch_many
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


async def get_manager_gw_data(
    manager_id: int,
    gameweek: int,
    include_profile: bool = True,
) -> Dict[str, Any]:
    """Fetch manager gameweek score, transfer hits, active chip, and optional manager/team profile info."""
    picks_endpoint = f"entry/{manager_id}/event/{gameweek}/picks"

    if include_profile:
        profile_endpoint = f"entry/{manager_id}"
        data, profile_data = await fetch_many([picks_endpoint, profile_endpoint], allow_stale=True)
    else:
        data = await fetch_fpl_api(picks_endpoint, allow_stale=True)
        profile_data = None

    if not data:
        print(f"Manager {manager_id} GW {gameweek} failed to fetch.")
        return {"status": "error", "manager_id": manager_id}

    profile_data = profile_data or {}
    player_first = profile_data.get("player_first_name", "")
    player_last = profile_data.get("player_last_name", "")
    manager_name = f"{player_first} {player_last}".strip() or f"Manager #{manager_id}"
    team_name = profile_data.get("name", "FPL Squad")

    entry_history = data.get("entry_history") or {}
    raw_points = entry_history.get("points", 0)
    hits = entry_history.get("event_transfers_cost", 0)
    net_gw_points = raw_points - hits
    active_chip = data.get("active_chip")

    overall_rank = profile_data.get("summary_overall_rank") or entry_history.get("overall_rank")
    overall_points = profile_data.get("summary_overall_points") or entry_history.get("total_points")

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
            "is_captain": bool(pick.get("is_captain", False)),
            "is_vice_captain": bool(pick.get("is_vice_captain", False)),
            "multiplier": int(pick.get("multiplier", 0)),
        }
        for idx, pick in enumerate(data.get("picks", []))
    ]

    raw_auto_subs = data.get("automatic_subs") or []
    api_sub_in_ids = [int(s["element_in"]) for s in raw_auto_subs if "element_in" in s]
    api_sub_out_ids = [int(s["element_out"]) for s in raw_auto_subs if "element_out" in s]

    return {
        "manager_id": manager_id,
        "manager_name": manager_name,
        "team_name": team_name,
        "gameweek": gameweek,
        "gw_points": net_gw_points,
        "overall_rank": overall_rank,
        "overall_points": overall_points,
        "hits": hits,
        "active_chip": readable_chip,
        "picks": picks_summary,
        "api_sub_in_ids": api_sub_in_ids,
        "api_sub_out_ids": api_sub_out_ids,
        "status": "success",
    }


async def get_team_summary(
    manager_ids: List[int],
    gameweek: int,
    players_dict: Dict[int, Dict[str, Any]],
    live_data: Dict[int, Dict[str, Any]],
    include_profile: bool = True,
) -> Dict[str, Any]:
    """Aggregate total points, hit costs, active chips, captains, vice-captains, and ownership with live auto-sub."""
    managers_data = []
    active_player_counts: Dict[int, int] = Counter()
    bench_player_counts: Dict[int, int] = Counter()
    captain_counts: Dict[int, int] = Counter()
    vice_captain_counts: Dict[int, int] = Counter()
    total_team_points = 0
    total_hits_cost = 0
    active_chips: List[str] = []
    all_subbed_in_ids: Set[int] = set()
    all_subbed_out_ids: Set[int] = set()
    has_bench_boost = False

    left_to_play_count = 0
    total_slots_count = 0

    tasks = [get_manager_gw_data(m_id, gameweek, include_profile=include_profile) for m_id in manager_ids]
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

            # Preserve original C / VC IDs before auto-sub runs so flags are never lost
            orig_cap_ids = {int(p["element_id"]) for p in picks if p.get("is_captain")}
            orig_vc_ids = {int(p["element_id"]) for p in picks if p.get("is_vice_captain")}

            if not is_bench_boost:
                api_in = data.get("api_sub_in_ids", [])
                api_out = data.get("api_sub_out_ids", [])

                if api_in or api_out:
                    all_subbed_in_ids.update(api_in)
                    all_subbed_out_ids.update(api_out)
                else:
                    picks, sub_in_ids, sub_out_ids = apply_manager_auto_subs(
                        picks, live_data, players_dict, data.get("manager_id")
                    )
                    all_subbed_in_ids.update(sub_in_ids)
                    all_subbed_out_ids.update(sub_out_ids)

            for item in picks:
                pid_check = int(item["element_id"])
                item["is_captain"] = bool(item.get("is_captain") or pid_check in orig_cap_ids)
                item["is_vice_captain"] = bool(item.get("is_vice_captain") or pid_check in orig_vc_ids)
            data["picks"] = picks

            manager_captain_name = "-"
            manager_vice_captain_name = "-"
            active_cap_pid = None

            for item in picks:
                p_id = int(item["element_id"])
                mult = int(item.get("multiplier", 0))
                is_vc = bool(item.get("is_vice_captain", False))

                player_live = live_data.get(p_id, {})
                status = player_live.get("status", "Not Played Yet")
                p_score = player_live.get("points", 0)

                if mult >= 2:
                    active_cap_pid = p_id
                    captain_counts[p_id] += 1
                    manager_captain_name = players_dict.get(p_id, {}).get("name", "Unknown")

                if is_vc:
                    vice_captain_counts[p_id] += 1
                    manager_vice_captain_name = players_dict.get(p_id, {}).get("name", "Unknown")

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

            # Fallback if both C and VC had 0 minutes (multiplier 0)
            if active_cap_pid is None and orig_cap_ids:
                fallback_cid = next(iter(orig_cap_ids))
                captain_counts[fallback_cid] += 1
                manager_captain_name = players_dict.get(fallback_cid, {}).get("name", "Unknown")

            data["captain_name"] = manager_captain_name
            data["vice_captain_name"] = manager_vice_captain_name
            net_manager_points = manager_live_points - hits
            data["gw_points"] = net_manager_points

            managers_data.append(data)
            total_team_points += net_manager_points
            total_hits_cost += hits

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

    vice_captains_list = []
    for p_id, count in Counter(vice_captain_counts).most_common():
        player_name = players_dict.get(p_id, {}).get("name", "Unknown")
        vice_captains_list.append({"name": player_name, "count": count})
    vice_captains_display = (
        ", ".join(f"{vc['name']} ({vc['count']}x)" for vc in vice_captains_list) if vice_captains_list else "None"
    )

    return {
        "gameweek": gameweek,
        "total_team_points": total_team_points,
        "total_hits_cost": total_hits_cost,
        "active_chips": chips_display,
        "chips_list": chips_list,
        "has_bench_boost": has_bench_boost,
        "captains": captains_display,
        "captains_list": captains_list,
        "vice_captains": vice_captains_display,
        "vice_captains_list": vice_captains_list,
        "managers_count": len(managers_data),
        "managers": managers_data,
        "ownership": ownership_list,
        "bench_ownership": bench_ownership_list,
        "status_counts": {
            "left_to_play": left_to_play_count,
            "total_slots": total_slots_count,
        },
    }
