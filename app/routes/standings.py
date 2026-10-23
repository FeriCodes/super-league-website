from typing import Optional
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.fpl.gameweek import get_current_gameweek, get_gameweek_status
from app.services.standings import compute_standings, get_live_league_scores_if_active
from app.services.storage import load_teams, load_fixtures, get_all_results_cache

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/standings", response_class=HTMLResponse, include_in_schema=False)
async def standings_page(request: Request, gw: Optional[int] = Query(None)):
    """Render overall standings page with optional live score injection."""
    teams = load_teams()
    fixtures = load_fixtures()
    results_cache = await get_all_results_cache()

    if gw is None:
        gw = await get_current_gameweek()

    # Inject live scores into results_cache if active
    live_gw_scores = await get_live_league_scores_if_active(gw, teams)
    if live_gw_scores:
        results_cache = dict(results_cache)
        results_cache[str(gw)] = live_gw_scores

    standings = compute_standings(fixtures, results_cache, teams)

    gw_status = await get_gameweek_status(gw)
    is_live = gw_status.get("is_live", False)

    return templates.TemplateResponse(
        request=request,
        name="standings.html",
        context={
            "standings": standings,
            "active_page": "standings",
            "page_title": "Standings",
            "is_live": is_live,
        },
    )
