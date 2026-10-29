from app.fpl.kits import resolve_player_team_code


def build_head_to_head_comparison(
    summary_a: dict,
    summary_b: dict,
    live_data: dict,
    players_cache: dict,
    fixtures_map: dict,
    team_codes_map: dict | None = None,
) -> dict:
    """Build positional player breakdown and point diffs for head-to-head matchup, including bench and manager links."""
    grouped = {
        "GKP": [],
        "DEF": [],
        "MID": [],
        "FWD": [],
        "BENCH": [],
    }

    codes_lookup = team_codes_map or {}
    managers_a = summary_a.get("managers", [])
    managers_b = summary_b.get("managers", [])

    def get_managers_for_starter(pid: int, managers_list: list) -> list:
        """Return list of dicts with manager details owning `pid` in active Starting XI."""
        owning_managers = []
        if not managers_list:
            return owning_managers

        for m in managers_list:
            picks = m.get("picks", [])
            is_bb = m.get("active_chip") == "Bench Boost"
            team_label = m.get("team_name") or m.get("manager_name") or "Manager"
            mgr_id = m.get("manager_id") or m.get("id") or m.get("entry")

            for pick in picks:
                if not isinstance(pick, dict):
                    continue
                p_id = pick.get("element_id") or pick.get("element") or pick.get("id")
                if p_id is None or int(p_id) != pid:
                    continue

                mult = int(pick.get("multiplier", 0))
                is_vc = bool(pick.get("is_vice_captain", False))

                if is_bb or mult > 0:
                    suffix = ""
                    if mult == 2:
                        suffix = " (C)"
                    elif mult >= 3:
                        suffix = " (TC)"
                    elif is_vc:
                        suffix = " (V)"

                    owning_managers.append(
                        {
                            "name": f"{team_label}{suffix}",
                            "manager_id": mgr_id,
                        }
                    )

        return owning_managers

    # =============================================================
    # 1. Process Active Starting XI
    # =============================================================
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
        team_code = resolve_player_team_code(p_cached, codes_lookup)
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

        managers_owning_a = get_managers_for_starter(pid, managers_a)
        managers_owning_b = get_managers_for_starter(pid, managers_b)

        row = {
            "id": pid,
            "name": name,
            "pos": pos,
            "team_code": team_code,
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

    # =============================================================
    # 2. Process Bench / Subs Strictly Slot-by-Slot (12, 13, 14, 15)
    # =============================================================
    a_sub_out_ids = {int(p["id"]) for p in summary_a.get("bench_ownership", []) if p.get("is_sub_out", False)}
    b_sub_out_ids = {int(p["id"]) for p in summary_b.get("bench_ownership", []) if p.get("is_sub_out", False)}

    def get_manager_exact_bench_slots(manager: dict, team_sub_out_ids: set) -> dict:
        if manager.get("active_chip") == "Bench Boost":
            return {}

        picks = manager.get("picks", [])
        by_pos = {}
        for pick in picks:
            if not isinstance(pick, dict):
                continue
            pos = int(pick.get("position", 0))
            p_id = pick.get("element_id") or pick.get("element") or pick.get("id")
            if pos and p_id is not None:
                by_pos[pos] = {
                    "id": int(p_id),
                    "mult": int(pick.get("multiplier", 0)),
                }

        slot_assignment = {}
        if 12 in by_pos:
            if by_pos[12]["mult"] == 0:
                slot_assignment[12] = (by_pos[12]["id"], False)
            elif 1 in by_pos and by_pos[1]["mult"] == 0:
                slot_assignment[12] = (by_pos[1]["id"], True)

        subbed_in_bench_slots = []
        for s in (13, 14, 15):
            if s in by_pos:
                if by_pos[s]["mult"] == 0:
                    slot_assignment[s] = (by_pos[s]["id"], False)
                else:
                    subbed_in_bench_slots.append(s)

        if subbed_in_bench_slots:
            zero_mult_starters = [by_pos[p]["id"] for p in range(2, 12) if p in by_pos and by_pos[p]["mult"] == 0]
            confirmed_out = [pid for pid in zero_mult_starters if pid in team_sub_out_ids]
            other_zero = [pid for pid in zero_mult_starters if pid not in team_sub_out_ids]
            ordered_out_starters = confirmed_out + other_zero

            for s, out_pid in zip(subbed_in_bench_slots, ordered_out_starters):
                slot_assignment[s] = (out_pid, True)

        return slot_assignment

    def build_bench_manager_entries(managers_list: list, sub_out_ids: set) -> list:
        entries = []
        for m in managers_list:
            vc_ids = {
                int(pk.get("element_id") or pk.get("element") or pk.get("id"))
                for pk in m.get("picks", [])
                if isinstance(pk, dict)
                and pk.get("is_vice_captain")
                and (pk.get("element_id") or pk.get("element") or pk.get("id")) is not None
            }
            entries.append(
                {
                    "label": m.get("team_name") or m.get("manager_name") or "Manager",
                    "manager_id": m.get("manager_id") or m.get("id") or m.get("entry"),
                    "vc_ids": vc_ids,
                    "slots": get_manager_exact_bench_slots(m, sub_out_ids),
                }
            )
        return entries

    managers_a_slots = build_bench_manager_entries(managers_a, a_sub_out_ids)
    managers_b_slots = build_bench_manager_entries(managers_b, b_sub_out_ids)

    slot_configs = [
        (12, "Sub GKP", "SUB GOALKEEPER"),
        (13, "Bench 1", "BENCH 1 — FIRST SUB"),
        (14, "Bench 2", "BENCH 2 — SECOND SUB"),
        (15, "Bench 3", "BENCH 3 — THIRD SUB"),
    ]

    for bench_slot, bench_label, bench_group_title in slot_configs:
        slot_owners_a = {}
        slot_sub_out_a = set()
        for entry in managers_a_slots:
            s_map = entry["slots"]
            if bench_slot in s_map:
                pid, is_out = s_map[bench_slot]
                suffix = " (V)" if pid in entry["vc_ids"] else ""
                slot_owners_a.setdefault(pid, []).append(
                    {
                        "name": f"{entry['label']}{suffix}",
                        "manager_id": entry["manager_id"],
                    }
                )
                if is_out:
                    slot_sub_out_a.add(pid)

        slot_owners_b = {}
        slot_sub_out_b = set()
        for entry in managers_b_slots:
            s_map = entry["slots"]
            if bench_slot in s_map:
                pid, is_out = s_map[bench_slot]
                suffix = " (V)" if pid in entry["vc_ids"] else ""
                slot_owners_b.setdefault(pid, []).append(
                    {
                        "name": f"{entry['label']}{suffix}",
                        "manager_id": entry["manager_id"],
                    }
                )
                if is_out:
                    slot_sub_out_b.add(pid)

        slot_pids = set(slot_owners_a.keys()) | set(slot_owners_b.keys())
        slot_rows = []

        for pid in slot_pids:
            p_cached = players_cache.get(pid, {})
            name = p_cached.get("name", "Unknown")
            pos = p_cached.get("position", "GKP" if bench_slot == 12 else "Unknown")

            managers_owning_a = slot_owners_a.get(pid, [])
            managers_owning_b = slot_owners_b.get(pid, [])
            count_a = len(managers_owning_a)
            count_b = len(managers_owning_b)
            diff = count_a - count_b

            live_info = live_data.get(pid, {})
            player_points = live_info.get("points", 0)
            match_status = live_info.get("status", "Not Played Yet")

            team_id = p_cached.get("team_id")
            team_code = resolve_player_team_code(p_cached, codes_lookup)
            opp_short = fixtures_map.get(team_id, "")
            chance = p_cached.get("chance_of_playing")
            news = p_cached.get("news", "")

            is_out_a = pid in slot_sub_out_a
            is_out_b = pid in slot_sub_out_b
            is_sub_out = is_out_a or is_out_b

            has_injury = chance is not None and chance <= 75 and match_status != "FT" and not is_sub_out
            if chance == 0:
                default_news = "Ruled Out (0%)"
            elif chance is not None:
                default_news = f"{chance}% chance of playing"
            else:
                default_news = ""

            slot_rows.append(
                {
                    "id": pid,
                    "name": name,
                    "pos": pos,
                    "team_code": team_code,
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
            )

        slot_rows.sort(key=lambda r: (-(r["count_a"] + r["count_b"]), -r["count_a"], -r["count_b"], r["name"]))

        if slot_rows:
            slot_rows[0]["is_bench_changed"] = True
            grouped["BENCH"].extend(slot_rows)

    if grouped["BENCH"]:
        grouped["BENCH"][0]["is_bench_changed"] = False

    return grouped
