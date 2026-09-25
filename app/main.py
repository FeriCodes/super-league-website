import json
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Super League H2H")

# Set up templates directory
templates = Jinja2Templates(directory="app/templates")

# Path to the team database inside app directory
TEAMS_FILE = Path(__file__).resolve().parent / "fpl_teams.json"


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

    # Alphabetical list of team names for select menus
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
    # 1. Initialize buckets for positions
    grouped = {
        "GKP": [],
        "DEF": [],
        "MID": [],
        "FWD": [],
    }

    # 2. Fast lookup dictionaries by player ID
    a_dict = {p["id"]: p for p in summary_a.get("ownership", [])}
    b_dict = {p["id"]: p for p in summary_b.get("ownership", [])}

    # 3. All unique player IDs across both teams
    all_player_ids = set(a_dict.keys()) | set(b_dict.keys())

    # 4. Calculate differential for each player
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

    # 5. Sort each position group: highest differential first
    for pos in grouped:
        grouped[pos].sort(key=lambda item: abs(item["diff"]), reverse=True)

    return grouped
