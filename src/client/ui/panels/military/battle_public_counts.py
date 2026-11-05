"""Read published aggregates, never reconstruct a foreign battle's roster."""


def observed_category_counts(state, battle, side):
    table = state.tables.get("battle_public_counts")
    if table is None:
        return None
    rows = [row for row in table.to_dicts() if row.get("battle_id") == battle.get("id")
            and row.get("side") == side]
    if (len(rows) != 4 or {row.get("category") for row in rows} != set("IGAN")
            or any(not row.get("complete") or row.get("unit_quantity") is None
                   or int(row["unit_quantity"]) < 0
                   or row.get("sampled_at_minute") != int(battle.get("updated_at_minute") or 0) for row in rows)):
        return None
    return {row["category"]: int(row["unit_quantity"]) for row in rows}
