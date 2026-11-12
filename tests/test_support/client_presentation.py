"""Helpers for exercising presentation code against the registered mod API."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Mapping

from modules.base.client_presentation import contribute_client_presentation


def client_state(*, client_presentation: Mapping[str, Any] | None = None, **attributes):
    contribution = contribute_client_presentation()
    values = contribution.values if client_presentation is None else client_presentation
    return SimpleNamespace(
        client_presentation=dict(values),
        **attributes,
    )


def attach_client_presentation(state, values: Mapping[str, Any] | None = None):
    contribution = contribute_client_presentation()
    state.client_presentation = dict(contribution.values if values is None else values)
    return state


def presentation_values() -> dict[str, object]:
    return dict(contribute_client_presentation().values)
