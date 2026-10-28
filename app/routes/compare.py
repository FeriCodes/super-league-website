from typing import Optional
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.fpl.managers import get_players_dict, get_team_summary
from app.fpl.live import get_live_scores_and_status
from app.fpl.gameweek import (
    get_gameweek_status,
    get_current_gameweek,
    get_team_fixtures_map,
)
from app.services.compare import build_head_to_head_comparison
from app.services.storage import load_teams, get_team_roster

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/compare", response_class=HTMLResponse, include_in_schema=False)
async def compare_teams(
    request: Request,
    team_a_name: Optional[str] = Query(None),
    team_b_name: Optional[str] = Query(None),
    gameweek: Optional[int] = Query(None),
):
    """Compare two teams head-to-head with live updating scores."""
    if gameweek is None:
        gameweek = await get_current_gameweek()

    teams = load_teams()

    if not team_a_name or not team_b_name:
        return templates.TemplateResponse(
            request=request,
            name="compare.html",
            context={
                "team_names": sorted(list(teams.keys())),
                "results": None,
                "error_message": None,
                "selected_team_a": team_a_name or "",
                "selected_team_b": team_b_name or "",
                "gw": gameweek,
                "active_page": "compare",
            },
        )

    if team_a_name == team_b_name:
        return templates.TemplateResponse(
            request=request,
            name="compare.html",
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
            name="compare.html",
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

    players = await get_players_dict()

    team_a_ids = get_team_roster(teams, team_a_name, gameweek)
    team_b_ids = get_team_roster(teams, team_b_name, gameweek)

    live_data = await get_live_scores_and_status(gameweek)
    fixtures_map = await get_team_fixtures_map(gameweek)

    summary_a = await get_team_summary(team_a_ids, gameweek, players, live_data)
    summary_b = await get_team_summary(team_b_ids, gameweek, players, live_data)

    grouped_comparison = build_head_to_head_comparison(summary_a, summary_b, live_data, players, fixtures_map)

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
        name="compare.html",
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
