from collections import Counter


def build_head_to_head_comparison(
    summary_a: dict,
    summary_b: dict,
    live_data: dict,
    players_cache: dict,
    fixtures_map: dict,
) -> dict:
    """Build positional player breakdown and point diffs for head-to-head matchup, including bench and managers list."""
    grouped = {
        "GKP": [],
        "DEF": [],
        "MID": [],
        "FWD": [],
        "BENCH": [],
    }

    managers_a = summary_a.get("managers", [])
    managers_b = summary_b.get("managers", [])

    def get_managers_for_player(pid: int, managers_list: list, is_bench_section: bool = False) -> list:
        """
        Return list of formatted manager/team names owning `pid` in either active XI or bench.
        Includes (C) or (TC) indicator if the manager captained the player in active XI.
        """
        owning_managers = []
        if not managers_list:
            return owning_managers

        for m in managers_list:
            picks = m.get("picks", [])
            is_bb = m.get("active_chip") == "Bench Boost"
            team_label = m.get("team_name") or m.get("manager_name") or "Manager"

            for pick in picks:
                if not isinstance(pick, dict):
                    continue
                p_id = pick.get("element_id") or pick.get("element") or pick.get("id")
                if p_id is None or int(p_id) != pid:
                    continue

                mult = int(pick.get("multiplier", 0))

                if is_bench_section:
                    # In BENCH table: only include if player is actually on the bench (mult == 0 and no Bench Boost)
                    if not is_bb and mult == 0:
                        owning_managers.append(team_label)
                else:
                    # In Active Starting XI tables: include if mult > 0 or Bench Boost is active
                    if is_bb or mult > 0:
                        if mult == 2:
                            owning_managers.append(f"{team_label} (C)")
                        elif mult >= 3:
                            owning_managers.append(f"{team_label} (TC)")
                        else:
                            owning_managers.append(team_label)

        return owning_managers

    def get_player_bench_slot(pid: int, player_pos: str) -> int:
        """
        Determine the bench slot for a bench player:
        12 = Sub GKP
        13 = Bench 1
        14 = Bench 2
        15 = Bench 3
        """
        if player_pos == "GKP":
            return 12

        slots = []
        fallback_slots = []

        for m in managers_a + managers_b:
            if m.get("active_chip") == "Bench Boost":
                continue
            picks = m.get("picks", [])
            for pick in picks:
                if not isinstance(pick, dict):
                    continue
                p_id = pick.get("element_id") or pick.get("element") or pick.get("id")
                if p_id is not None and int(p_id) == pid:
                    mult = int(pick.get("multiplier", 0))
                    pos = int(pick.get("position", 0))
                    if mult == 0:
                        if pos in (13, 14, 15):
                            slots.append(pos)
                        elif pos < 12:
                            # Player started in XI and was auto-subbed out; find which bench slot replaced them
                            subbed_in_bench_slots = [
                                int(p.get("position", 15))
                                for p in picks
                                if int(p.get("position", 0)) in (13, 14, 15) and int(p.get("multiplier", 0)) > 0
                            ]
                            if subbed_in_bench_slots:
                                fallback_slots.append(min(subbed_in_bench_slots))
                            else:
                                fallback_slots.append(13)

        if slots:
            # Pick the most common bench slot across managers (tie-break by earliest slot)
            counts = Counter(slots)
            return sorted(counts.keys(), key=lambda s: (-counts[s], s))[0]

        if fallback_slots:
            return min(fallback_slots)

        return 15

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
        is_sub_in = is_sub_a or is_sub_b

        has_injury = chance is not None and chance <= 75 and match_status != "FT"
        if chance == 0:
            default_news = "Ruled Out (0%)"
        elif chance is not None:
            default_news = f"{chance}% chance of playing"
        else:
            default_news = ""

        managers_owning_a = get_managers_for_player(pid, managers_a, is_bench_section=False)
        managers_owning_b = get_managers_for_player(pid, managers_b, is_bench_section=False)

        row = {
            "id": pid,
            "name": name,
            "pos": pos,
            "bench_slot": 0,
            "bench_label": "",
            "bench_group_title": "",
            "count_a": count_a,
            "count_b": count_b,
            "diff": diff,
            "abs_diff": abs(diff),
            "player_points": player_points,
            "status": match_status,
            "is_live": match_status == "LIVE",
            "is_dimmed_ft": match_status == "FT",
            "opponent": opp_short,
            "is_sub_in": is_sub_in,
            "is_sub_in_a": is_sub_a,
            "is_sub_in_b": is_sub_b,
            "is_sub_out": False,
            "is_sub_out_a": False,
            "is_sub_out_b": False,
            "chance": chance,
            "news": news,
            "has_injury": has_injury,
            "injury_title": news or default_news,
            "is_pos_changed": False,
            "is_bench_changed": False,
            "managers_a": managers_owning_a,
            "managers_b": managers_owning_b,
        }

        if pos in grouped:
            grouped[pos].append(row)

    # 2. Process Bench / Subs
    a_bench_dict = {int(p["id"]): p for p in summary_a.get("bench_ownership", [])}
    b_bench_dict = {int(p["id"]): p for p in summary_b.get("bench_ownership", [])}
    all_bench_ids = set(a_bench_dict.keys()) | set(b_bench_dict.keys())

    slot_label_map = {
        12: ("Sub GKP", "SUB GOALKEEPER"),
        13: ("Bench 1", "BENCH 1 — FIRST SUB"),
        14: ("Bench 2", "BENCH 2 — SECOND SUB"),
        15: ("Bench 3", "BENCH 3 — THIRD SUB"),
    }

    for pid in all_bench_ids:
        info = a_bench_dict.get(pid) or b_bench_dict.get(pid)
        name = info.get("name", "Unknown")
        pos = info.get("position", "Unknown")

        bench_slot = get_player_bench_slot(pid, pos)
        bench_label, bench_group_title = slot_label_map.get(bench_slot, ("Bench 3", "BENCH 3 — THIRD SUB"))

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
        is_sub_out = is_out_a or is_out_b

        has_injury = chance is not None and chance <= 75 and match_status != "FT" and not is_sub_out
        if chance == 0:
            default_news = "Ruled Out (0%)"
        elif chance is not None:
            default_news = f"{chance}% chance of playing"
        else:
            default_news = ""

        managers_owning_a = get_managers_for_player(pid, managers_a, is_bench_section=True)
        managers_owning_b = get_managers_for_player(pid, managers_b, is_bench_section=True)

        row = {
            "id": pid,
            "name": name,
            "pos": pos,
            "bench_slot": bench_slot,
            "bench_label": bench_label,
            "bench_group_title": bench_group_title,
            "count_a": count_a,
            "count_b": count_b,
            "diff": diff,
            "abs_diff": abs(diff),
            "player_points": player_points,
            "status": match_status,
            "is_live": match_status == "LIVE" and not is_sub_out,
            "is_dimmed_ft": match_status == "FT",
            "opponent": opp_short,
            "is_sub_in": False,
            "is_sub_in_a": False,
            "is_sub_in_b": False,
            "is_sub_out": is_sub_out,
            "is_sub_out_a": is_out_a,
            "is_sub_out_b": is_out_b,
            "chance": chance,
            "news": news,
            "has_injury": has_injury,
            "injury_title": news or default_news,
            "is_pos_changed": False,
            "is_bench_changed": False,
            "managers_a": managers_owning_a,
            "managers_b": managers_owning_b,
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

    # Sort Bench strictly by bench_slot (12=Sub GKP, 13=Bench 1, 14=Bench 2, 15=Bench 3) then Team Differential
    def bench_sort_key(item):
        slot = item.get("bench_slot", 15)
        diff = item.get("diff", 0)
        total_owners = item.get("count_a", 0) + item.get("count_b", 0)
        if diff > 0:
            return (slot, -1, -diff, -total_owners)
        elif diff == 0:
            return (slot, 0, 0, -total_owners)
        else:
            return (slot, 1, -diff, -total_owners)

    grouped["BENCH"].sort(key=bench_sort_key)

    # Mark transitions between bench groups (Sub GKP -> Bench 1 -> Bench 2 -> Bench 3)
    for idx, item in enumerate(grouped["BENCH"]):
        if idx == 0:
            item["is_bench_changed"] = False
        else:
            prev_slot = grouped["BENCH"][idx - 1].get("bench_slot")
            item["is_bench_changed"] = item.get("bench_slot") != prev_slot

    return grouped
