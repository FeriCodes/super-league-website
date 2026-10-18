from typing import Any, Dict, List, Tuple

# Outfield positions and the (min, max) player counts FPL allows on the pitch.
OUTFIELD_LIMITS = {
    "DEF": (3, 5),
    "MID": (2, 5),
    "FWD": (1, 3),
}


def apply_manager_auto_subs(
    picks: List[Dict[str, Any]],
    live_data: Dict[int, Dict[str, Any]],
    players_dict: Dict[int, Dict[str, Any]],
    manager_id: int,
) -> Tuple[List[Dict[str, Any]], List[int], List[int]]:
    """
    Apply FPL auto-substitution rules to one manager's 15-player squad.
    """
    updated = [dict(p) for p in picks]
    subbed_in: List[int] = []
    subbed_out: List[int] = []

    by_slot: Dict[int, Dict[str, Any]] = {int(p.get("position", 0)): p for p in updated}
    starters = [by_slot[i] for i in range(1, 12) if i in by_slot]
    bench_gk = by_slot.get(12)
    available_bench = [by_slot[i] for i in (13, 14, 15) if i in by_slot]

    def minutes(element_id: int) -> int:
        return live_data.get(element_id, {}).get("minutes") or 0

    def status_of(element_id: int) -> str:
        return live_data.get(element_id, {}).get("status", "Not Played Yet")

    def finished_without_playing(element_id: int) -> bool:
        return status_of(element_id) == "FT" and minutes(element_id) == 0

    def is_definitely_out(element_id: int) -> bool:
        """
        Return True ONLY if the player has 0% chance of playing (red flag)
        or is suspended ('s'), unavailable ('u'), or ineligible ('n').
        Players with 25%, 50%, or 75% chance are NOT definitely out.
        """
        p_info = players_dict.get(element_id, {})
        chance = p_info.get("chance_of_playing")
        fpl_status = p_info.get("status", "a")

        if chance is not None:
            return int(chance) == 0

        return fpl_status in ("s", "u", "n")

    def can_sub_in(element_id: int) -> bool:
        """
        A bench player can sub in if:
        1. They have already played (minutes > 0), OR
        2. Their match hasn't started yet ('Not Played Yet') AND they are not definitely ruled out (0%).
        """
        if minutes(element_id) > 0:
            return True
        if status_of(element_id) == "Not Played Yet" and not is_definitely_out(element_id):
            return True
        return False

    def position_of(element_id: int) -> str:
        return players_dict.get(element_id, {}).get("position", "")

    def name_of(element_id: int) -> str:
        return players_dict.get(element_id, {}).get("name", f"Player {element_id}")

    def outfield_counts(players: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {"DEF": 0, "MID": 0, "FWD": 0}
        for p in players:
            pos = position_of(p["element_id"])
            if pos in counts:
                counts[pos] += 1
        return counts

    def is_legal_formation(counts: Dict[str, int]) -> bool:
        return all(lo <= counts[pos] <= hi for pos, (lo, hi) in OUTFIELD_LIMITS.items())

    def swap(out_player: Dict[str, Any], in_player: Dict[str, Any], label: str) -> None:
        in_player["multiplier"] = 1
        out_player["multiplier"] = 0
        subbed_in.append(in_player["element_id"])
        subbed_out.append(out_player["element_id"])
        print(
            f"[AUTO-SUB][Manager {manager_id}] {label}: "
            f"{name_of(out_player['element_id'])} OUT -> {name_of(in_player['element_id'])} IN"
        )

    # 1. Captaincy: if the captain did not play, transfer armband multiplier to vice-captain first
    captain = next((p for p in starters if int(p.get("multiplier", 0)) >= 2), None)
    if captain and finished_without_playing(captain["element_id"]):
        cap_mult = int(captain["multiplier"])
        captain["multiplier"] = 1  # Reset to normal starter so bench sub gives 1x

        vice = next(
            (p for p in updated if p.get("is_vice_captain") and can_sub_in(p["element_id"])),
            None,
        )
        if vice:
            vice["multiplier"] = cap_mult
            print(
                f"[AUTO-SUB][Manager {manager_id}] CAPTAIN: "
                f"{name_of(captain['element_id'])} (0 mins) -> Armband to {name_of(vice['element_id'])}"
            )

    # 2. Goalkeeper: only the bench goalkeeper can replace the starting goalkeeper
    gk = by_slot.get(1)
    if gk and finished_without_playing(gk["element_id"]):
        if bench_gk and can_sub_in(bench_gk["element_id"]):
            swap(gk, bench_gk, "GKP")
        else:
            gk["multiplier"] = 0

    # 3. Outfield: replace in bench order, keeping a legal formation
    on_pitch = list(starters)
    for starter in list(starters):
        sid = starter["element_id"]
        if position_of(sid) not in OUTFIELD_LIMITS:
            continue
        if not finished_without_playing(sid):
            continue

        replaced = False
        for candidate in list(available_bench):
            cid = candidate["element_id"]
            if position_of(cid) not in OUTFIELD_LIMITS or not can_sub_in(cid):
                continue

            trial = [p for p in on_pitch if p is not starter] + [candidate]
            if is_legal_formation(outfield_counts(trial)):
                incoming_mult = candidate["multiplier"] if candidate["multiplier"] >= 2 else 1
                swap(starter, candidate, position_of(sid))
                candidate["multiplier"] = incoming_mult
                available_bench.remove(candidate)
                on_pitch = trial
                replaced = True
                break

        if not replaced:
            starter["multiplier"] = 0

    return updated, subbed_in, subbed_out
