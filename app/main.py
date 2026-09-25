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
