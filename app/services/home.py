import httpx
from app.services.storage import load_teams, get_team_roster
from app.services.compare import build_head_to_head_comparison
from app.fpl.managers import get_players_dict, get_team_summary
from app.fpl.live import get_live_scores_and_status
from app.fpl.gameweek import get_team_fixtures_map

# In-memory cache mapping current season FPL team_id -> official club team_code
_TEAM_CODE_CACHE: dict[int, int] = {}


async def get_dynamic_team_codes() -> dict[int, int]:
    """Fetch and cache the exact {team_id: team_code} map from FPL bootstrap-static."""
    global _TEAM_CODE_CACHE
    if _TEAM_CODE_CACHE:
        return _TEAM_CODE_CACHE

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://fantasy.premierleague.com/api/bootstrap-static/")
            if resp.status_code == 200:
                data = resp.json()
                _TEAM_CODE_CACHE = {
                    int(t["id"]): int(t["code"]) for t in data.get("teams", []) if "id" in t and "code" in t
                }
    except Exception as e:
        print(f"Error fetching dynamic team codes: {e}")

    return _TEAM_CODE_CACHE


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


async def get_manager_pitch_data(fpl_id: int, current_gw: int):
    """Fetch and structure live squad and pitch lineup details for a specific FPL manager ID."""
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
        for pick in manager_info.get("picks", []):
            if not isinstance(pick, dict):
                continue
            p_id = pick.get("element_id") or pick.get("element") or pick.get("id")
            if p_id is not None:
                pid_int = int(p_id)
                pick_multipliers[pid_int] = int(pick.get("multiplier", 1))
                pick_positions[pid_int] = int(pick.get("position", 99))

        empty_summary = {
            k: ([] if isinstance(v, list) else ({} if isinstance(v, dict) else 0)) for k, v in summary.items()
        }
        grouped = build_head_to_head_comparison(summary, empty_summary, live_data, players, fixtures_map)

        captain_raw = manager_info.get("captain_name") or ""
        captain_clean = captain_raw.replace("(TC)", "").replace("(C)", "").strip()
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
                    team_id = p_cached.get("team_id") or p_cached.get("team")
                    team_code = p_cached.get("team_code") or (
                        team_codes_map.get(int(team_id)) if team_id is not None else None
                    )

                    raw_pts = row.get("player_points", 0)
                    mult = pick_multipliers.get(pid, 1)

                    is_cap = (pos_key != "BENCH") and (mult >= 2 or (captain_clean and pname == captain_clean))
                    is_tc = is_cap and (
                        mult >= 3 or active_chip in ("3xc", "TC", "Triple Captain") or "(TC)" in captain_raw
                    )

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
            "captain_name": captain_raw or "—",
            "left_to_play": summary.get("left_to_play", summary.get("players_left", 0)),
            "lineup": lineup,
        }
    except Exception as e:
        print(f"Error fetching pitch data for FPL ID {fpl_id}: {e}")
        return None
