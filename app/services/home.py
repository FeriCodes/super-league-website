from app.services.storage import load_teams, get_team_roster
from app.services.compare import build_head_to_head_comparison
from app.fpl.managers import get_players_dict, get_team_summary
from app.fpl.live import get_live_scores_and_status
from app.fpl.gameweek import get_team_fixtures_map

# Premier League team_id (1..20) to official FPL shirt team_code fallback map
PL_TEAM_CODES = {
    1: 3,  # Arsenal
    2: 7,  # Aston Villa
    3: 91,  # Bournemouth
    4: 94,  # Brentford
    5: 36,  # Brighton
    6: 8,  # Chelsea
    7: 31,  # Crystal Palace
    8: 11,  # Everton
    9: 54,  # Fulham
    10: 40,  # Ipswich / Promoted
    11: 13,  # Leicester / Promoted
    12: 14,  # Liverpool
    13: 43,  # Man City
    14: 1,  # Man Utd
    15: 4,  # Newcastle
    16: 17,  # Nott'm Forest
    17: 20,  # Southampton / Promoted
    18: 6,  # Spurs
    19: 21,  # West Ham
    20: 39,  # Wolves
}


async def get_home_highlights(current_gw: int):
    """Calculate both the MVP manager(s) and Top Scoring Team(s) in a single pass."""
    teams = load_teams()
    players = await get_players_dict()
    live_data = await get_live_scores_and_status(current_gw)

    max_mgr_pts = -1
    mvp_list = []

    max_team_pts = -1
    top_teams = []

    if teams:
        for team_name in teams.keys():
            team_ids = get_team_roster(teams, team_name, current_gw)
            if team_ids:
                summary = await get_team_summary(team_ids, current_gw, players, live_data)

                # Best team of the week calculation
                team_pts = summary.get("total_team_points", 0)
                if team_pts > max_team_pts:
                    max_team_pts = team_pts
                    top_teams = [team_name]
                elif team_pts == max_team_pts and max_team_pts > 0:
                    top_teams.append(team_name)

                # Best manager calculation
                for m in summary.get("managers", []):
                    pts = m.get("gw_points", 0)
                    mgr_id = m.get("manager_id") or m.get("id") or m.get("entry")
                    mgr_entry = {
                        "id": mgr_id,
                        "name": m.get("manager_name", "Unknown"),
                        "fpl_team": m.get("team_name", ""),
                        "club": team_name,
                        "display": f"{m.get('manager_name', 'Unknown')} ({team_name})",
                    }

                    if pts > max_mgr_pts:
                        max_mgr_pts = pts
                        mvp_list = [mgr_entry]
                    elif pts == max_mgr_pts and max_mgr_pts > 0:
                        mvp_list.append(mgr_entry)

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
        "live_data": live_data,
    }


def _extract_side_a_player(row: dict) -> dict:
    """Extract Team A player dictionary from a comparison row regardless of key naming."""
    if not isinstance(row, dict):
        return {}

    for key in ("player_a", "team_a", "side_a", "left", "a"):
        val = row.get(key)
        if isinstance(val, dict) and (val.get("name") or val.get("web_name") or val.get("player_name")):
            return val

    if row.get("name") or row.get("web_name") or row.get("player_name") or row.get("name_a"):
        return row

    for val in row.values():
        if isinstance(val, dict) and (val.get("name") or val.get("web_name") or val.get("player_name")):
            return val

    return {}


async def get_manager_pitch_data(fpl_id: int, current_gw: int):
    """Fetch and structure live squad and pitch lineup details for a specific FPL manager ID."""
    try:
        team_ids = [int(fpl_id)]
        players = await get_players_dict()
        live_data = await get_live_scores_and_status(current_gw)
        fixtures_map = await get_team_fixtures_map(current_gw)

        summary = await get_team_summary(team_ids, current_gw, players, live_data)
        if not summary or not summary.get("managers"):
            return None

        manager_info = summary["managers"][0]

        # Build an empty counterpart summary with identical keys to leverage build_head_to_head_comparison
        empty_summary = {
            k: ([] if isinstance(v, list) else ({} if isinstance(v, dict) else 0)) for k, v in summary.items()
        }
        grouped = build_head_to_head_comparison(summary, empty_summary, live_data, players, fixtures_map)

        # Build name -> player metadata lookup from players_dict
        player_lookup = {}
        if isinstance(players, dict):
            for pid, pinfo in players.items():
                if isinstance(pinfo, dict):
                    pname = pinfo.get("web_name") or pinfo.get("name")
                    if pname:
                        player_lookup[pname] = {**pinfo, "id": pid}

        captain_raw = manager_info.get("captain_name") or ""
        captain_clean = captain_raw.replace("(TC)", "").replace("(C)", "").strip()
        active_chip = manager_info.get("active_chip")

        lineup = {"GKP": [], "DEF": [], "MID": [], "FWD": [], "BENCH": []}

        if isinstance(grouped, dict):
            for pos_key in ("GKP", "DEF", "MID", "FWD", "BENCH"):
                rows = grouped.get(pos_key, [])
                for row in rows:
                    if isinstance(row, dict) and row.get("is_header"):
                        continue
                    raw_p = _extract_side_a_player(row)
                    if not raw_p:
                        continue

                    pname = (
                        raw_p.get("name") or raw_p.get("web_name") or raw_p.get("player_name") or raw_p.get("name_a")
                    )
                    if not pname:
                        continue

                    p_meta = player_lookup.get(pname, {})
                    team_id = raw_p.get("team_id") or raw_p.get("team") or p_meta.get("team_id") or p_meta.get("team")
                    team_code = raw_p.get("team_code") or p_meta.get("team_code") or PL_TEAM_CODES.get(team_id)

                    pos = (
                        raw_p.get("position")
                        or raw_p.get("pos")
                        or p_meta.get("position")
                        or (pos_key if pos_key != "BENCH" else "SUB")
                    )

                    pts = raw_p.get("points")
                    if pts is None:
                        pts = raw_p.get("pts", raw_p.get("gw_points", raw_p.get("pts_a", 0)))

                    is_cap = bool(
                        raw_p.get("is_captain") or (captain_clean and pname == captain_clean and pos_key != "BENCH")
                    )

                    lineup[pos_key].append(
                        {
                            "name": pname,
                            "points": pts,
                            "position": pos,
                            "opponent": raw_p.get("opponent") or raw_p.get("opp") or raw_p.get("opponent_a") or "",
                            "bench_slot": raw_p.get("bench_slot") or raw_p.get("slot") or "",
                            "is_captain": is_cap,
                            "is_tc": is_cap
                            and (active_chip in ("3xc", "TC", "Triple Captain") or "(TC)" in captain_raw),
                            "is_live": bool(raw_p.get("is_live") or raw_p.get("live")),
                            "is_ft": bool(raw_p.get("is_ft") or raw_p.get("finished") or raw_p.get("is_finished")),
                            "sub_in": bool(raw_p.get("sub_in") or raw_p.get("is_sub_in") or raw_p.get("subbed_in")),
                            "sub_out": bool(raw_p.get("sub_out") or raw_p.get("is_sub_out") or raw_p.get("subbed_out")),
                            "chance_of_playing": raw_p.get("chance_of_playing", p_meta.get("chance_of_playing")),
                            "news": raw_p.get("news") or p_meta.get("news") or "",
                            "team_code": team_code,
                        }
                    )

        return {
            "manager_id": fpl_id,
            "manager_name": manager_info.get("manager_name", "Unknown Manager"),
            "team_name": manager_info.get("team_name", f"FPL Squad #{fpl_id}"),
            "gw_points": manager_info.get("gw_points", summary.get("total_team_points", 0)),
            "hits": manager_info.get("hits", summary.get("total_hits_cost", 0)),
            "active_chip": active_chip,
            "captain_name": captain_raw or "—",
            "left_to_play": summary.get("left_to_play", summary.get("players_left", 0)),
            "lineup": lineup,
        }
    except Exception as e:
        print(f"Error fetching pitch data for FPL ID {fpl_id}: {e}")
        return None
