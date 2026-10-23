from typing import Optional
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.fpl.gameweek import get_current_gameweek, get_gameweek_status
from app.services.standings import (
    get_live_league_scores_if_active,
    get_team_total_points_fast,
)
from app.services.storage import (
    get_cached_gameweek,
    get_team_roster,
    load_fixtures,
    load_teams,
    save_cached_gameweek,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/fixtures", response_class=HTMLResponse, include_in_schema=False)
async def fixtures_page(request: Request, gw: Optional[int] = Query(None)):
    """Render gameweek fixtures with live score support and final result caching."""
    teams = load_teams()
    fixtures = load_fixtures()

    if gw is None:
        gw = await get_current_gameweek()

    gw_str = str(gw)
    raw_matches = fixtures.get(gw_str, [])

    gw_scores = await get_cached_gameweek(gw)

    gw_status = await get_gameweek_status(gw)
    is_gw_finished = gw_status.get("finished", False)
    is_data_checked = gw_status.get("data_checked", False)
    is_live = gw_status.get("is_live", False)

    # 1. Permanently cache final scores once the gameweek is officially finished and checked
    if is_gw_finished and is_data_checked and gw_scores is None:
        ordered_teams = []
        for t1, t2 in raw_matches:
            if t1 not in ordered_teams:
                ordered_teams.append(t1)
            if t2 not in ordered_teams:
                ordered_teams.append(t2)

        calculated = []
        for t_name in ordered_teams:
            res = await get_team_total_points_fast(get_team_roster(teams, t_name, gw), gw)
            calculated.append(res)

        all_complete = all(complete for _, complete in calculated)
        computed_scores = {t_name: total for t_name, (total, _) in zip(ordered_teams, calculated)}

        if all_complete:
            await save_cached_gameweek(gw, computed_scores)
            gw_scores = computed_scores
        else:
            print(f"[FIXTURES] GW {gw} has incomplete data; results not cached")
            gw_scores = None

    # 2. Compute temporary live scores on the fly if the selected gameweek is currently live
    elif is_live and gw_scores is None:
        gw_scores = await get_live_league_scores_if_active(gw, teams)

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
            "is_live": is_live,
        },
    )
