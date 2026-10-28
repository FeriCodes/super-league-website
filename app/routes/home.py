from typing import Optional
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.fpl.gameweek import get_current_gameweek
from app.services.home import get_home_highlights, get_manager_pitch_data

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home_page(
    request: Request,
    gameweek: Optional[int] = Query(None),
    fpl_id: Optional[int] = Query(None),
):
    """Render the main Home dashboard with highlights and squad pitch viewer."""
    current_gw = await get_current_gameweek()
    target_gw = gameweek if gameweek is not None else current_gw
    highlights = await get_home_highlights(target_gw)

    manager_pitch = None
    if fpl_id:
        manager_pitch = await get_manager_pitch_data(fpl_id, target_gw)

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "gw": target_gw,
            "current_gw": current_gw,
            "active_page": "home",
            "mvp_manager": highlights["mvp_manager"],
            "top_team": highlights["top_team"],
            "top_captains": highlights["top_captains"],
            "live_data": highlights["live_data"],
            "manager_pitch": manager_pitch,
            "searched_fpl_id": fpl_id or "",
        },
    )
