import json
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.fpl_client import close_fpl_client
from .fpl_service import get_players_dict, get_team_summary, get_live_scores_and_status, get_gameweek_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_fpl_client()


app = FastAPI(title="Super League H2H", lifespan=lifespan)

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

TEAMS_FILE = Path(__file__).resolve().parent / "sl_teams.json"

# In-memory cache for player info (ID -> name, position)
PLAYERS_CACHE = {}


def load_teams() -> dict:
    """Read and parse the local sl_teams.json file into a Python dictionary."""
    if not TEAMS_FILE.exists():
        return {}
    with open(TEAMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


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
        },
    )


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
            },
        )

    global PLAYERS_CACHE

    if not PLAYERS_CACHE:
        PLAYERS_CACHE = await get_players_dict()

    team_a_ids = teams.get(team_a_name, [])
    team_b_ids = teams.get(team_b_name, [])

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
        },
    )
