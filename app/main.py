import asyncio
import uvicorn
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.fpl.client import close_fpl_client
from app.fpl.managers import get_players_dict, get_team_summary
from app.fpl.live import get_live_scores_and_status
from app.fpl.gameweek import (
    get_gameweek_status,
    get_current_gameweek,
    get_team_fixtures_map,
)
from app.services.compare import build_head_to_head_comparison
from app.services.standings import compute_standings, get_team_total_points_fast
from app.services.storage import (
    init_db,
    close_db,
    load_teams,
    get_team_roster,
    load_fixtures,
    get_all_results_cache,
    get_cached_gameweek,
    save_cached_gameweek,
)

PLAYERS_CACHE = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()
    await close_fpl_client()


app = FastAPI(title="Super League H2H", lifespan=lifespan)

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render home page with dynamic current gameweek."""
    teams = load_teams()
    team_names = sorted(list(teams.keys()))
    current_gw = await get_current_gameweek()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "team_names": team_names,
            "results": None,
            "error_message": None,
            "selected_team_a": "",
            "selected_team_b": "",
            "gw": current_gw,
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
    """Compare two teams head-to-head with live updating scores."""
    if gameweek is None:
        gameweek = await get_current_gameweek()

    if not team_a_name or not team_b_name:
        return RedirectResponse(url="/", status_code=303)

    teams = load_teams()

    # Prevent comparing a team with itself
    if team_a_name == team_b_name:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "team_names": sorted(list(teams.keys())),
                "results": None,
                "error_message": "Cannot compare a team with itself. Please select two different teams.",
                "selected_team_a": team_a_name,
                "selected_team_b": team_b_name,
                "gw": gameweek,
                "active_page": "compare",
            },
        )

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

    live_data = await get_live_scores_and_status(gameweek)
    fixtures_map = await get_team_fixtures_map(gameweek)

    summary_a = await get_team_summary(team_a_ids, gameweek, PLAYERS_CACHE, live_data)
    summary_b = await get_team_summary(team_b_ids, gameweek, PLAYERS_CACHE, live_data)

    grouped_comparison = build_head_to_head_comparison(summary_a, summary_b, live_data, PLAYERS_CACHE, fixtures_map)

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
            "error_message": None,
            "selected_team_a": team_a_name,
            "selected_team_b": team_b_name,
            "gw": gameweek,
            "active_page": "compare",
        },
    )


@app.get("/fixtures", response_class=HTMLResponse)
async def fixtures_page(request: Request, gw: Optional[int] = Query(None)):
    """Render gameweek fixtures and store final results once the gameweek concludes."""
    teams = load_teams()
    fixtures = load_fixtures()

    # Default to current active gameweek directly if no gameweek is requested
    if gw is None:
        gw = await get_current_gameweek()

    gw_str = str(gw)
    raw_matches = fixtures.get(gw_str, [])

    gw_scores = await get_cached_gameweek(gw)

    gw_status = await get_gameweek_status(gw)
    is_gw_finished = gw_status.get("finished", False)

    if is_gw_finished and gw_scores is None:
        ordered_teams = []
        for t1, t2 in raw_matches:
            if t1 not in ordered_teams:
                ordered_teams.append(t1)
            if t2 not in ordered_teams:
                ordered_teams.append(t2)

        tasks = [get_team_total_points_fast(get_team_roster(teams, t_name, gw), gw) for t_name in ordered_teams]
        calculated_points = await asyncio.gather(*tasks)

        gw_scores = {}
        for t_name, score in zip(ordered_teams, calculated_points):
            gw_scores[t_name] = score

        await save_cached_gameweek(gw, gw_scores)

    if gw_scores is None:
        gw_scores = {}

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


@app.get("/standings", response_class=HTMLResponse)
async def standings_page(request: Request):
    """Render overall standings page."""
    teams = load_teams()
    fixtures = load_fixtures()
    results_cache = await get_all_results_cache()

    standings = compute_standings(fixtures, results_cache, teams)

    return templates.TemplateResponse(
        request=request,
        name="standings.html",
        context={
            "standings": standings,
            "active_page": "standings",
            "page_title": "Standings",
        },
    )


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
