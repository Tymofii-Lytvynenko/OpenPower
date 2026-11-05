"""Pure proposal checks shared by authoritative processing and UI previews."""
from __future__ import annotations


def country_diplomacy_restriction(governments, country_tag: str) -> str:
    if governments is None:
        return ""
    for row in governments.iter_rows(named=True):
        if str(row.get("country_id") or "").upper() == country_tag.upper():
            forms = (row.get("government_type"), row.get("government_form_id"))
            if any(str(value or "").strip().casefold() == "anarchy" for value in forms):
                return "A country in anarchy cannot sponsor a treaty."
    return ""


def treaty_title_restriction(title: str, treaties, pending) -> str:
    # Reserve names in both tables so concurrent proposals cannot become active
    # with the same name after passing a client-side snapshot check.
    name = title.strip()
    for table, field in ((treaties, "name"), (pending, "title")):
        if table is not None and field in table.columns:
            if any(str(value or "").strip() == name for value in table[field].to_list()):
                return "A treaty with this name already exists. Choose another name."
    return ""
