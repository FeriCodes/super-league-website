import json
from pathlib import Path
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from .fpl_service import get_players_dict, get_team_summary

app = FastAPI(title="Super League H2H")

templates = Jinja2Templates(directory="app/templates")

TEAMS_FILE = Path(__file__).resolve().parent / "fpl_teams.json"

# In-memory cache for player info (ID -> name, position)
PLAYERS_CACHE = {}


def load_teams() -> dict:
    """Read and parse the local fpl_teams.json file into a Python dictionary."""
    if not TEAMS_FILE.exists():
        return {}
    with open(TEAMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
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


def build_head_to_head_comparison(summary_a: dict, summary_b: dict) -> dict:
    """Group players by position and calculate head-to-head differentials."""
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

        row = {
            "name": name,
            "pos": pos,
            "count_a": count_a,
            "count_b": count_b,
            "diff": diff,
        }

        if pos in grouped:
            grouped[pos].append(row)

    for pos in grouped:
        grouped[pos].sort(key=lambda item: abs(item["diff"]), reverse=True)

    return grouped


@app.post("/compare", response_class=HTMLResponse)
def compare_teams(
    request: Request,
    team_a_name: str = Form(...),
    team_b_name: str = Form(...),
    gameweek: int = Form(...),
):
    """Process team comparison form submitted by user."""
    global PLAYERS_CACHE

    # 1. Fetch player details once and store in cache
    if not PLAYERS_CACHE:
        PLAYERS_CACHE = get_players_dict()

    # 2. Load teams and lookup manager IDs by team name
    teams = load_teams()
    team_a_ids = teams.get(team_a_name, [])
    team_b_ids = teams.get(team_b_name, [])

    # 3. Fetch summary metrics for both teams from FPL API
    summary_a = get_team_summary(team_a_ids, gameweek, PLAYERS_CACHE)
    summary_b = get_team_summary(team_b_ids, gameweek, PLAYERS_CACHE)

    # 4. Compute head-to-head player differentials
    grouped_comparison = build_head_to_head_comparison(summary_a, summary_b)

    results = {
        "team_a_name": team_a_name,
        "team_b_name": team_b_name,
        "summary_a": summary_a,
        "summary_b": summary_b,
        "grouped": grouped_comparison,
        "gameweek": gameweek,
    }

    # 5. Return updated page with results and maintain form state
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
