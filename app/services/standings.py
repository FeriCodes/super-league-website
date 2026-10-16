import asyncio
from app.fpl.managers import get_manager_gw_data


async def get_team_total_points_fast(team_ids: list, gw: int) -> int:
    """Fetch cumulative team score asynchronously for final fixtures calculation."""
    if not team_ids:
        return 0
    tasks = [get_manager_gw_data(m_id, gw) for m_id in team_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total = 0
    for r in results:
        if isinstance(r, dict) and r.get("status") == "success":
            total += r.get("gw_points", 0)
    return total


def compute_standings(fixtures: dict, results_cache: dict, teams: dict) -> list:
    """Calculate overall league table standings based on cached finished results."""
    table = {}
    for team_name in teams.keys():
        table[team_name] = {
            "team": team_name,
            "played": 0,
            "won": 0,
            "drawn": 0,
            "lost": 0,
            "points": 0,
            "gd": 0,
        }

    for gw_str, matches in fixtures.items():
        if gw_str not in results_cache:
            continue
        gw_scores = results_cache[gw_str]

        for team_a, team_b in matches:
            if team_a in gw_scores and team_b in gw_scores:
                score_a = gw_scores[team_a]
                score_b = gw_scores[team_b]

                table[team_a]["played"] += 1
                table[team_b]["played"] += 1

                match_diff = score_a - score_b
                table[team_a]["gd"] += match_diff
                table[team_b]["gd"] -= match_diff

                if score_a > score_b:
                    table[team_a]["won"] += 1
                    table[team_a]["points"] += 3
                    table[team_b]["lost"] += 1
                elif score_b > score_a:
                    table[team_b]["won"] += 1
                    table[team_b]["points"] += 3
                    table[team_a]["lost"] += 1
                else:
                    table[team_a]["drawn"] += 1
                    table[team_a]["points"] += 1
                    table[team_b]["drawn"] += 1
                    table[team_b]["points"] += 1

    standings_list = sorted(
        table.values(),
        key=lambda x: (x["points"], x["gd"]),
        reverse=True,
    )

    for idx, row in enumerate(standings_list, start=1):
        row["pos"] = idx

    return standings_list
