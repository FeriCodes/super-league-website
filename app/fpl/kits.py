import httpx

_TEAM_CODE_CACHE: dict[int, int] = {}


async def get_dynamic_team_codes() -> dict[int, int]:
    """Fetch and cache the {team_id: team_code} mapping from FPL bootstrap-static."""
    global _TEAM_CODE_CACHE
    if _TEAM_CODE_CACHE:
        return _TEAM_CODE_CACHE

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://fantasy.premierleague.com/api/bootstrap-static/")
            if resp.status_code == 200:
                data = resp.json()
                _TEAM_CODE_CACHE = {
                    int(t["id"]): int(t["code"]) for t in data.get("teams", []) if "id" in t and "code" in t
                }
    except Exception as e:
        print(f"Error fetching dynamic team codes: {e}")

    return _TEAM_CODE_CACHE


def resolve_player_team_code(player_info: dict, team_codes_map: dict[int, int]) -> int | None:
    """Resolve team_code from cached player dict or fallback to team_id mapping."""
    if not isinstance(player_info, dict):
        return None

    raw_code = player_info.get("team_code")
    if raw_code:
        try:
            return int(raw_code)
        except (ValueError, TypeError):
            pass

    team_id = player_info.get("team_id") or player_info.get("team")
    if team_id:
        try:
            return team_codes_map.get(int(team_id))
        except (ValueError, TypeError):
            pass

    return None
