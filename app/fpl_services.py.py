import httpx

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_manager_gw_data(manager_id: int, gameweek: int) -> dict:
    url = f"https://fantasy.premierleague.com/api/entry/{manager_id}/event/{gameweek}/picks/"
    response = httpx.get(url, headers=HEADERS)

    if response.status_code == 200:
        data = response.json()

        # ۱. حساب کردن امتیازها (تیکه اول)
        history = data["entry_history"]
        gross_points = history["points"]
        hits = history["event_transfers_cost"]
        net_points = gross_points - hits

        # ۲. بیرون کشیدن آیدی بازیکن‌ها (تیکه دوم)
        player_ids = []
        for pick in data["picks"]:
            player_ids.append(pick["element"])

        # ۳. تحویل همه‌چیز با هم
        return {
            "manager_id": manager_id,
            "gameweek": gameweek,
            "gw_points": net_points,
            "hits": hits,
            "player_ids": player_ids,
            "status": "success",
        }

    return {
        "manager_id": manager_id,
        "gameweek": gameweek,
        "status": "error",
        "message": f"Failed with status code {response.status_code}",
    }


if __name__ == "__main__":
    result = get_manager_gw_data(1970094, 5)
    print(result)
