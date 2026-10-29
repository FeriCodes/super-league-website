from app.services.storage import load_teams, get_team_roster
from app.services.compare import build_head_to_head_comparison
from app.fpl.managers import get_players_dict, get_team_summary
from app.fpl.live import get_live_scores_and_status
from app.fpl.gameweek import get_team_fixtures_map
from app.fpl.kits import get_dynamic_team_codes, resolve_player_team_code


async def get_home_highlights(current_gw: int):
    teams = load_teams()
    players = await get_players_dict()
    live_data = await get_live_scores_and_status(current_gw)

    max_mgr_pts = -1
    mvp_list = []

    max_team_pts = -1
    top_teams = []

    captain_counts = {}
    total_managers_count = 0

    if teams:
        for team_name in teams.keys():
            team_ids = get_team_roster(teams, team_name, current_gw)
            if team_ids:
                summary = await get_team_summary(team_ids, current_gw, players, live_data)

                team_pts = summary.get("total_team_points", 0)

                if team_pts > max_team_pts and team_pts > 0:
                    max_team_pts = team_pts
                    top_teams = [team_name]
                elif team_pts == max_team_pts and max_team_pts > 0:
                    top_teams.append(team_name)

                for m in summary.get("managers", []):
                    total_managers_count += 1

                    cap_raw = m.get("captain_name") or ""
                    cap_clean = cap_raw.replace("(TC)", "").replace("(C)", "").strip()
                    if cap_clean and cap_clean not in ("—", "-"):
                        captain_counts[cap_clean] = captain_counts.get(cap_clean, 0) + 1

                    pts = m.get("gw_points", 0)
                    mgr_id = m.get("manager_id") or m.get("id") or m.get("entry")
                    mgr_entry = {
                        "id": mgr_id,
                        "name": m.get("manager_name", "Unknown"),
                        "fpl_team": m.get("team_name", ""),
                        "club": team_name,
                        "display": f"{m.get('manager_name', 'Unknown')} ({team_name})",
                    }

                    if pts > max_mgr_pts and pts > 0:
                        max_mgr_pts = pts
                        mvp_list = [mgr_entry]
                    elif pts == max_mgr_pts and max_mgr_pts > 0:
                        mvp_list.append(mgr_entry)

    # Top 3 Popular Captains Calculation
    top_captains_list = []
    if captain_counts and total_managers_count > 0:
        team_codes_map = await get_dynamic_team_codes()
        sorted_caps = sorted(captain_counts.items(), key=lambda x: x[1], reverse=True)[:3]

        for cap_name, count in sorted_caps:
            pct = round((count / total_managers_count) * 100)
            c_pts = 0
            c_team_code = None

            for pid, pinfo in players.items():
                if isinstance(pinfo, dict):
                    pname = pinfo.get("web_name") or pinfo.get("name")
                    if pname == cap_name:
                        live_info = live_data.get(int(pid), {})
                        c_pts = live_info.get("points", 0)
                        c_team_code = resolve_player_team_code(pinfo, team_codes_map)
                        break

            top_captains_list.append(
                {
                    "name": cap_name,
                    "pct": pct,
                    "pts": c_pts,
                    "team_code": c_team_code,
                }
            )

    return {
        "mvp_manager": {
            "name": " & ".join(item["display"] for item in mvp_list) if mvp_list else "—",
            "pts": max_mgr_pts if max_mgr_pts > 0 else 0,
            "managers": mvp_list,
        },
        "top_team": {
            "name": " & ".join(top_teams) if top_teams else "—",
            "pts": max_team_pts if max_team_pts > 0 else 0,
        },
        "top_captains": top_captains_list,
        "live_data": live_data,
    }


async def get_manager_pitch_data(fpl_id: int, current_gw: int):
    try:
        team_ids = [int(fpl_id)]
        players = await get_players_dict()
        live_data = await get_live_scores_and_status(current_gw)
        fixtures_map = await get_team_fixtures_map(current_gw)
        team_codes_map = await get_dynamic_team_codes()

        summary = await get_team_summary(team_ids, current_gw, players, live_data)
        if not summary or not summary.get("managers"):
            return None

        manager_info = summary["managers"][0]

        pick_multipliers = {}
        pick_positions = {}
        pick_captains = {}
        pick_vice_captains = {}

        for pick in manager_info.get("picks", []):
            if not isinstance(pick, dict):
                continue
            p_id = pick.get("element_id") or pick.get("element") or pick.get("id")
            if p_id is not None:
                pid_int = int(p_id)
                pick_multipliers[pid_int] = int(pick.get("multiplier", 1))
                pick_positions[pid_int] = int(pick.get("position", 99))
                pick_captains[pid_int] = bool(pick.get("is_captain", False))
                pick_vice_captains[pid_int] = bool(pick.get("is_vice_captain", False))

        has_active_mult_cap = any(m >= 2 for m in pick_multipliers.values())

        empty_summary = {
            k: ([] if isinstance(v, list) else ({} if isinstance(v, dict) else 0)) for k, v in summary.items()
        }
        grouped = build_head_to_head_comparison(
            summary,
            empty_summary,
            live_data,
            players,
            fixtures_map,
            team_codes_map=team_codes_map,
        )

        captain_raw = manager_info.get("captain_name") or "—"
        if captain_raw == "-":
            captain_raw = "—"

        vice_captain_raw = manager_info.get("vice_captain_name") or "—"
        if vice_captain_raw == "-":
            vice_captain_raw = "—"

        active_chip = manager_info.get("active_chip")

        lineup = {"GKP": [], "DEF": [], "MID": [], "FWD": [], "BENCH": []}

        if isinstance(grouped, dict):
            for pos_key in ("GKP", "DEF", "MID", "FWD", "BENCH"):
                rows = grouped.get(pos_key, [])
                for row in rows:
                    if not isinstance(row, dict):
                        continue

                    pid = int(row.get("id", 0))
                    pname = row.get("name", "Unknown")
                    pos = row.get("pos", pos_key if pos_key != "BENCH" else "SUB")

                    p_cached = players.get(pid, {}) if isinstance(players, dict) else {}
                    team_code = resolve_player_team_code(p_cached, team_codes_map)

                    raw_pts = row.get("player_points", 0)
                    mult = pick_multipliers.get(pid, 1)

                    is_cap = (mult >= 2) if has_active_mult_cap else pick_captains.get(pid, False)
                    is_tc = is_cap and (
                        mult >= 3 or active_chip in ("3xc", "TC", "Triple Captain") or "(TC)" in captain_raw
                    )
                    is_vc = pick_vice_captains.get(pid, False) and not is_cap

                    if pos_key != "BENCH" and mult > 1:
                        effective_pts = raw_pts * mult
                    else:
                        effective_pts = raw_pts

                    lineup[pos_key].append(
                        {
                            "id": pid,
                            "name": pname,
                            "points": effective_pts,
                            "raw_points": raw_pts,
                            "position": pos,
                            "opponent": row.get("opponent", ""),
                            "bench_slot": row.get("bench_label") or row.get("bench_slot") or "",
                            "is_captain": is_cap,
                            "is_vice_captain": is_vc,
                            "is_tc": is_tc,
                            "is_live": bool(row.get("is_live")),
                            "is_ft": bool(row.get("is_dimmed_ft")),
                            "sub_in": bool(row.get("is_sub_in")),
                            "sub_out": bool(row.get("is_sub_out")),
                            "chance_of_playing": row.get("chance"),
                            "has_injury": bool(row.get("has_injury")),
                            "news": row.get("injury_title") or row.get("news") or "",
                            "team_code": team_code,
                            "pick_order": pick_positions.get(pid, 99),
                        }
                    )

                if pos_key != "BENCH":
                    lineup[pos_key].sort(key=lambda x: x["pick_order"])

        overall_rank = manager_info.get("overall_rank") or summary.get("overall_rank")
        overall_points = (
            manager_info.get("total_points") or manager_info.get("overall_points") or summary.get("overall_points")
        )
        status_counts = summary.get("status_counts") or {}
        ltp_val = status_counts.get("left_to_play", 0)
        slots_val = status_counts.get("total_slots", 11)

        return {
            "manager_id": fpl_id,
            "manager_name": manager_info.get("manager_name", "Unknown Manager"),
            "team_name": manager_info.get("team_name", f"FPL Squad #{fpl_id}"),
            "gw_points": manager_info.get("gw_points", summary.get("total_team_points", 0)),
            "overall_rank": (
                f"{int(overall_rank):,}"
                if isinstance(overall_rank, (int, float)) and overall_rank > 0
                else (overall_rank or None)
            ),
            "overall_points": overall_points,
            "hits": manager_info.get("hits", summary.get("total_hits_cost", 0)),
            "active_chip": active_chip,
            "captain_name": captain_raw,
            "vice_captain_name": vice_captain_raw,
            "left_to_play": f"{ltp_val} / {slots_val}",
            "lineup": lineup,
        }
    except Exception as e:
        print(f"Error fetching pitch data for FPL ID {fpl_id}: {e}")
        return None
