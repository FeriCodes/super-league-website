import httpx

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_manager_gw_score(manager_id: int, gameweek: int) -> dict:
    """Fetch net gameweek score for a given FPL manager ID."""
    url = f"https://fantasy.premierleague.com/api/entry/{manager_id}/event/{gameweek}/picks/"

    response = httpx.get(url, headers=HEADERS)

    if response.status_code == 200:
        data = response.json()
        history = data["entry_history"]

        gross_points = history["points"]
        hits = history["event_transfers_cost"]
        net_points = gross_points - hits

        return {
            "manager_id": manager_id,
            "gameweek": gameweek,
            "gross_points": gross_points,
            "hits": hits,
            "net_points": net_points,
            "status": "success",
        }

    return {
        "manager_id": manager_id,
        "gameweek": gameweek,
        "status": "error",
        "message": f"Failed with status code {response.status_code}",
    }


if __name__ == "__main__":
    result = get_manager_gw_score(1970094, 5)
    print(result)
