def build_head_to_head_comparison(
    summary_a: dict,
    summary_b: dict,
    live_data: dict,
    players_cache: dict,
    fixtures_map: dict,
) -> dict:
    """Build positional player breakdown and point diffs for head-to-head matchup, including bench."""
    grouped = {
        "GKP": [],
        "DEF": [],
        "MID": [],
        "FWD": [],
        "BENCH": [],
    }

    # 1. Process Active Starting XI
    a_dict = {int(p["id"]): p for p in summary_a.get("ownership", [])}
    b_dict = {int(p["id"]): p for p in summary_b.get("ownership", [])}
    all_player_ids = set(a_dict.keys()) | set(b_dict.keys())

    for pid in all_player_ids:
        info = a_dict.get(pid) or b_dict.get(pid)
        name = info.get("name", "Unknown")
        pos = info.get("position", "Unknown")

        count_a = a_dict[pid]["count"] if pid in a_dict else 0
        count_b = b_dict[pid]["count"] if pid in b_dict else 0
        diff = count_a - count_b

        live_info = live_data.get(pid, {})
        player_points = live_info.get("points", 0)
        match_status = live_info.get("status", "Not Played Yet")

        p_cached = players_cache.get(pid, {})
        team_id = p_cached.get("team_id")
        opp_short = fixtures_map.get(team_id, "")
        chance = p_cached.get("chance_of_playing")
        news = p_cached.get("news", "")

        is_sub_a = a_dict[pid].get("is_sub_in", False) if pid in a_dict else False
        is_sub_b = b_dict[pid].get("is_sub_in", False) if pid in b_dict else False

        row = {
            "id": pid,
            "name": name,
            "pos": pos,
            "count_a": count_a,
            "count_b": count_b,
            "diff": diff,
            "player_points": player_points,
            "status": match_status,
            "opponent": opp_short,
            "is_sub_in": is_sub_a or is_sub_b,
            "is_sub_out": False,
            "chance": chance,
            "news": news,
        }

        if pos in grouped:
            grouped[pos].append(row)

    # 2. Process Bench / Subs
    a_bench_dict = {int(p["id"]): p for p in summary_a.get("bench_ownership", [])}
    b_bench_dict = {int(p["id"]): p for p in summary_b.get("bench_ownership", [])}
    all_bench_ids = set(a_bench_dict.keys()) | set(b_bench_dict.keys())

    for pid in all_bench_ids:
        info = a_bench_dict.get(pid) or b_bench_dict.get(pid)
        name = info.get("name", "Unknown")
        pos = info.get("position", "Unknown")

        count_a = a_bench_dict[pid]["count"] if pid in a_bench_dict else 0
        count_b = b_bench_dict[pid]["count"] if pid in b_bench_dict else 0
        diff = count_a - count_b

        live_info = live_data.get(pid, {})
        player_points = live_info.get("points", 0)
        match_status = live_info.get("status", "Not Played Yet")

        p_cached = players_cache.get(pid, {})
        team_id = p_cached.get("team_id")
        opp_short = fixtures_map.get(team_id, "")
        chance = p_cached.get("chance_of_playing")
        news = p_cached.get("news", "")

        is_out_a = a_bench_dict[pid].get("is_sub_out", False) if pid in a_bench_dict else False
        is_out_b = b_bench_dict[pid].get("is_sub_out", False) if pid in b_bench_dict else False
        is_out = is_out_a or is_out_b

        row = {
            "id": pid,
            "name": name,
            "pos": pos,
            "count_a": count_a,
            "count_b": count_b,
            "diff": diff,
            "player_points": player_points,
            "status": match_status,
            "opponent": opp_short,
            "is_sub_in": False,
            "is_sub_out": is_out,
            "chance": chance,
            "news": news,
        }
        grouped["BENCH"].append(row)

    # Sort starters by Diff
    def starters_sort_key(item):
        diff = item.get("diff", 0)
        total_owners = item.get("count_a", 0) + item.get("count_b", 0)
        if diff > 0:
            return (1, diff, total_owners)
        elif diff == 0:
            return (0, 0, total_owners)
        else:
            return (-1, diff, total_owners)

    for pos in ["GKP", "DEF", "MID", "FWD"]:
        grouped[pos].sort(key=starters_sort_key, reverse=True)

    # Sort Bench by Football Position (GKP -> DEF -> MID -> FWD) then Diff
    pos_order = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}

    def bench_sort_key(item):
        pos_weight = pos_order.get(item.get("pos"), 5)
        diff = item.get("diff", 0)
        total_owners = item.get("count_a", 0) + item.get("count_b", 0)
        return (pos_weight, -abs(diff), -total_owners)

    grouped["BENCH"].sort(key=bench_sort_key)

    return grouped
