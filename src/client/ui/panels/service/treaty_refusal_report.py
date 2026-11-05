"""Format the recorded refusal without guessing from surviving treaty rows."""
from src.client.ui.panels.shared.panel_data import resolve_country_name


def treaty_refusal_report(state, payload) -> str:
    accepted = sorted(set(payload.get("accepted_country_tags") or []))
    accepting_names = [resolve_country_name(state, tag) for tag in accepted]
    responder = payload.get("responder_country_tag") or ""
    refusing_name = resolve_country_name(state, responder) if responder else "Not recorded"
    reason = str(payload.get("reason") or "Reason not recorded")
    return (f"{payload.get('title') or payload.get('treaty_id') or 'Treaty'}\n\n"
            + "ACCEPTED\n" + ("\n".join(accepting_names) or "None recorded")
            + f"\n\nREFUSED\n{refusing_name} ({reason})")
