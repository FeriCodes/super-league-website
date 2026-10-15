from typing import Any, Dict, List, Tuple


def apply_manager_auto_subs(
    picks: List[Dict[str, Any]],
    live_data: Dict[int, Dict[str, Any]],
    players_dict: Dict[int, Dict[str, Any]],
    manager_id: int,
) -> Tuple[List[Dict[str, Any]], List[int], List[int]]:
    """
    Apply live auto-substitution rules for a manager's 15-player squad.
    Returns:
      1. Updated picks list
      2. List of subbed-in player element IDs
      3. List of subbed-out player element IDs
    """
    updated_picks = [{k: v for k, v in p.items()} for p in picks]
    subbed_in_player_ids: List[int] = []
    subbed_out_player_ids: List[int] = []

    picks_by_pos: Dict[int, Dict[str, Any]] = {}
    for p in updated_picks:
        pos_key = int(p.get("position", 0))
        picks_by_pos[pos_key] = p

    starters = [picks_by_pos[i] for i in range(1, 12) if i in picks_by_pos]
    bench_gkp = picks_by_pos.get(12)
    bench_outfield = [picks_by_pos[i] for i in [13, 14, 15] if i in picks_by_pos]

    def player_did_not_play(element_id: int) -> bool:
        p_live = live_data.get(element_id, {})
        mins = p_live.get("minutes", 0) or 0
        match_status = p_live.get("status", "")

        # Finished match with 0 minutes played
        if match_status == "FT" and mins == 0:
            return True

        # Confirmed 100% absence before kickoff
        p_info = players_dict.get(element_id, {})
        chance = p_info.get("chance_of_playing")
        fpl_status = p_info.get("status")

        if match_status != "FT" and mins == 0:
            if chance == 0 or (fpl_status in ["i", "s", "u"] and chance == 0):
                return True

        return False

    def player_can_sub_in(element_id: int) -> bool:
        p_live = live_data.get(element_id, {})
        mins = p_live.get("minutes", 0) or 0
        match_status = p_live.get("status", "")
        return mins > 0 or match_status != "FT" or (match_status == "FT" and mins == 0)

    current_pos_counts: Dict[str, int] = {"GKP": 0, "DEF": 0, "MID": 0, "FWD": 0}
    for s in starters:
        pos_name = players_dict.get(s["element_id"], {}).get("position", "")
        if pos_name in current_pos_counts:
            current_pos_counts[pos_name] += 1

    # 1. Evaluate starting goalkeeper substitution
    starting_gkp = picks_by_pos.get(1)
    if starting_gkp and player_did_not_play(starting_gkp["element_id"]):
        if bench_gkp and player_can_sub_in(bench_gkp["element_id"]):
            orig_mult = starting_gkp.get("multiplier", 1) or 1
            bench_gkp["multiplier"] = orig_mult
            starting_gkp["multiplier"] = 0
            subbed_in_player_ids.append(bench_gkp["element_id"])
            subbed_out_player_ids.append(starting_gkp["element_id"])
            g_in = players_dict.get(bench_gkp["element_id"], {}).get("name", "Unknown")
            g_out = players_dict.get(starting_gkp["element_id"], {}).get("name", "Unknown")
            print(f"[AUTO-SUB][Manager {manager_id}] GKP: {g_out} OUT -> {g_in} IN")

    # 2. Evaluate outfield substitutions (slots 2 to 11)
    available_bench = list(bench_outfield)

    for starter in starters:
        p_id = starter["element_id"]
        pos_name = players_dict.get(p_id, {}).get("position", "")

        if pos_name not in ["DEF", "MID", "FWD"] or not player_did_not_play(p_id):
            continue

        p_out_name = players_dict.get(p_id, {}).get("name", f"Player {p_id}")
        candidate_found = None

        for candidate in available_bench:
            cand_id = candidate["element_id"]
            if not player_can_sub_in(cand_id):
                continue

            candidate_pos = players_dict.get(cand_id, {}).get("position", "")
            if candidate_pos not in ["DEF", "MID", "FWD"]:
                continue

            temp_counts = dict(current_pos_counts)
            temp_counts[pos_name] = max(0, temp_counts.get(pos_name, 0) - 1)
            temp_counts[candidate_pos] = temp_counts.get(candidate_pos, 0) + 1

            # Official FPL formation rules: at least 3 DEF, 2 MID, 1 FWD
            if temp_counts.get("DEF", 0) >= 3 and temp_counts.get("MID", 0) >= 2 and temp_counts.get("FWD", 0) >= 1:
                candidate_found = candidate
                current_pos_counts = temp_counts
                break

        if candidate_found:
            available_bench.remove(candidate_found)
            orig_mult = starter.get("multiplier", 1) or 1
            candidate_found["multiplier"] = orig_mult
            starter["multiplier"] = 0
            subbed_in_player_ids.append(candidate_found["element_id"])
            subbed_out_player_ids.append(starter["element_id"])

            p_in_name = players_dict.get(candidate_found["element_id"], {}).get(
                "name", f"Player {candidate_found['element_id']}"
            )
            print(
                f"[AUTO-SUB SUCCESS][Manager {manager_id}] Field: {p_out_name} ({pos_name}) OUT -> {p_in_name} ({candidate_pos}) IN"
            )

    return updated_picks, subbed_in_player_ids, subbed_out_player_ids
