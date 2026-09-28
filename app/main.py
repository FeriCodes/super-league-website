import json
import asyncio
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.fpl_client import close_fpl_client
from .fpl_service import (
    get_players_dict,
    get_team_summary,
    get_live_scores_and_status,
    get_gameweek_status,
    get_manager_gw_data,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_fpl_client()


app = FastAPI(title="Super League H2H", lifespan=lifespan)

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

TEAMS_FILE = Path(__file__).resolve().parent / "sl_teams.json"
FIXTURES_FILE = Path(__file__).resolve().parent / "fixtures.json"
RESULTS_CACHE_FILE = Path(__file__).resolve().parent / "results_cache.json"

# In-memory cache for player info (ID -> name, position)
PLAYERS_CACHE = {}


def load_teams() -> dict:
    """Read and parse the local sl_teams.json file into a Python dictionary."""
    if not TEAMS_FILE.exists():
        return {}
    with open(TEAMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_team_roster(teams_data: dict, team_name: str, gw: int) -> list:
    """Fetch manager IDs dynamically for a team based on gameweek ranges."""
    data = teams_data.get(team_name, [])
    if not data:
        return []

    # Ensure gameweek is an integer for accurate numeric comparison
    try:
        current_gw = int(gw)
    except (ValueError, TypeError):
        current_gw = 1

    # Simple flat list of manager IDs
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], int):
        return data

    # Historical ranges list of dicts
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        for entry in data:
            from_gw = int(entry.get("from_gw", 1))
            to_gw = int(entry.get("to_gw", 38))
            if from_gw <= current_gw <= to_gw:
                return entry.get("ids", [])

    return []


def load_fixtures() -> dict:
    if not FIXTURES_FILE.exists():
        return {}
    with open(FIXTURES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_results_cache() -> dict:
    if not RESULTS_CACHE_FILE.exists():
        return {}
    try:
        with open(RESULTS_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_results_cache(data: dict):
    try:
        with open(RESULTS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CACHE WRITE ERROR] {e}")


def calculate_team_match_status(summary: dict, live_data: dict) -> dict:
    """Calculate remaining players left to play out of total active squad slots."""
    ownership = summary.get("ownership", [])
    managers = summary.get("managers", [])

    total_slots = 0
    for m in managers:
        if m.get("active_chip") == "bboost":
            total_slots += 15
        else:
            total_slots += 11

    left_to_play = 0
    for item in ownership:
        p_id = item["id"]
        count = item["count"]
        status = live_data.get(p_id, {}).get("status", "Not Played Yet")

        if status == "Not Played Yet":
            left_to_play += count

    return {
        "left_to_play": left_to_play,
        "total_slots": total_slots,
    }


def build_head_to_head_comparison(summary_a: dict, summary_b: dict, live_data: dict) -> dict:
    grouped = {
        "GKP": [],
        "DEF": [],
        "MID": [],
        "FWD": [],
    }

    a_dict = {p["id"]: p for p in summary_a.get("ownership", [])}
    b_dict = {p["id"]: p for p in summary_b.get("ownership", [])}

    all_player_ids = set(a_dict.keys()) | set(b_dict.keys())

    for pid in all_player_ids:
        info = a_dict.get(pid) or b_dict.get(pid)
        name = info["name"]
        pos = info["position"]

        count_a = a_dict[pid]["count"] if pid in a_dict else 0
        count_b = b_dict[pid]["count"] if pid in b_dict else 0
        diff = count_a - count_b

        player_points = live_data.get(pid, {}).get("points", 0)

        row = {
            "id": pid,
            "name": name,
            "pos": pos,
            "count_a": count_a,
            "count_b": count_b,
            "diff": diff,
            "player_points": player_points,
        }

        if pos in grouped:
            grouped[pos].append(row)

    def sort_key(item):
        diff = item.get("diff", 0)
        total_owners = item.get("count_a", 0) + item.get("count_b", 0)

        if diff > 0:
            return (1, diff, total_owners)
        elif diff == 0:
            return (0, 0, total_owners)
        else:
            return (-1, diff, total_owners)

    for pos in grouped:
        grouped[pos].sort(key=sort_key, reverse=True)

    return grouped


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the main page with team options in two dropdown columns."""
    teams = load_teams()
    team_names = sorted(list(teams.keys()))

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "team_names": team_names,
            "results": None,
            "selected_team_a": "",
            "selected_team_b": "",
            "gw": 5,
            "active_page": "compare",
        },
    )


@app.get("/compare", response_class=HTMLResponse)
async def compare_teams(
    request: Request,
    team_a_name: Optional[str] = Query(None),
    team_b_name: Optional[str] = Query(None),
    gameweek: Optional[int] = Query(None),
):
    """Handle comparisons and fetch live stats with asynchronous cached endpoints."""
    if not team_a_name or not team_b_name or not gameweek:
        return RedirectResponse(url="/", status_code=303)

    teams = load_teams()
    gw_status = await get_gameweek_status(gameweek)
    if not gw_status["valid"]:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "team_names": sorted(list(teams.keys())),
                "results": None,
                "error_message": gw_status["message"],
                "selected_team_a": team_a_name,
                "selected_team_b": team_b_name,
                "gw": gameweek,
                "active_page": "compare",
            },
        )

    global PLAYERS_CACHE
    if not PLAYERS_CACHE:
        PLAYERS_CACHE = await get_players_dict()

    team_a_ids = get_team_roster(teams, team_a_name, gameweek)
    team_b_ids = get_team_roster(teams, team_b_name, gameweek)

    summary_a = await get_team_summary(team_a_ids, gameweek, PLAYERS_CACHE)
    summary_b = await get_team_summary(team_b_ids, gameweek, PLAYERS_CACHE)

    live_data = await get_live_scores_and_status(gameweek)

    summary_a["status_counts"] = calculate_team_match_status(summary_a, live_data)
    summary_b["status_counts"] = calculate_team_match_status(summary_b, live_data)

    grouped_comparison = build_head_to_head_comparison(summary_a, summary_b, live_data)

    results = {
        "team_a_name": team_a_name,
        "team_b_name": team_b_name,
        "summary_a": summary_a,
        "summary_b": summary_b,
        "grouped": grouped_comparison,
        "live_data": live_data,
        "gameweek": gameweek,
    }

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "team_names": sorted(list(teams.keys())),
            "results": results,
            "selected_team_a": team_a_name,
            "selected_team_b": team_b_name,
            "gw": gameweek,
            "active_page": "compare",
        },
    )


async def get_team_total_points_fast(team_ids: list, gw: int) -> int:
    """Fetch only the net points for a team without heavy differentials processing."""
    if not team_ids:
        return 0
    tasks = [get_manager_gw_data(m_id, gw) for m_id in team_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total = 0
    for r in results:
        if isinstance(r, dict) and r.get("status") == "success":
            total += r.get("gw_points", 0)
    return total


@app.get("/fixtures", response_class=HTMLResponse)
async def fixtures_page(request: Request, gw: int = Query(4)):
    teams = load_teams()
    fixtures = load_fixtures()
    results_cache = load_results_cache()

    gw_str = str(gw)
    raw_matches = fixtures.get(gw_str, [])

    gw_status = await get_gameweek_status(gw)
    is_gw_finished = gw_status.get("finished", False)

    # Only calculate and cache when official event has completed
    if is_gw_finished and gw_str not in results_cache:
        results_cache[gw_str] = {}
        ordered_teams = []
        for t1, t2 in raw_matches:
            if t1 not in ordered_teams:
                ordered_teams.append(t1)
            if t2 not in ordered_teams:
                ordered_teams.append(t2)

        tasks = [get_team_total_points_fast(get_team_roster(teams, t_name, gw), gw) for t_name in ordered_teams]
        calculated_points = await asyncio.gather(*tasks)

        for t_name, score in zip(ordered_teams, calculated_points):
            results_cache[gw_str][t_name] = score

        save_results_cache(results_cache)

    gw_scores = results_cache.get(gw_str, {})

    matches = []
    for team_a, team_b in raw_matches:
        has_scores = team_a in gw_scores and team_b in gw_scores
        score_a = gw_scores.get(team_a, 0)
        score_b = gw_scores.get(team_b, 0)

        winner = None
        if has_scores:
            if score_a > score_b:
                winner = "team_a"
            elif score_b > score_a:
                winner = "team_b"
            else:
                winner = "draw"

        matches.append(
            {
                "team_a": team_a,
                "team_b": team_b,
                "played": has_scores,
                "score_a": score_a,
                "score_b": score_b,
                "winner": winner,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="fixtures.html",
        context={
            "selected_gw": gw,
            "matches": matches,
            "active_page": "fixtures",
        },
    )
