from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.panels import migration_panel as migration_panel_module
from src.client.ui.panels.migration_panel import MigrationPanel


class _ImguiStub:
    def __init__(self):
        self.calls = []

    def text_wrapped(self, value):
        self.calls.append(("text_wrapped", value))

    def separator(self):
        self.calls.append(("separator",))

    def text(self, value):
        self.calls.append(("text", value))

    def text_disabled(self, value):
        self.calls.append(("text_disabled", value))


def _summary(*, top_routes=()):
    return SimpleNamespace(
        country_id="UKR",
        migration_policy="managed",
        border_policy="open",
        gross_inflow=1_200,
        gross_outflow=300,
        net_flow=900,
        recent_trend="rising",
        working_age_delta=125,
        service_pressure=0.25,
        political_pressure=0.10,
        law_pressure=0.05,
        entry_rate=0.5,
        exit_rate=0.25,
        asylum_rate=0.3,
        family_reunification_rate=0.4,
        skilled_worker_preference=0.6,
        enforcement_strength=0.7,
        top_routes=top_routes,
        status_counts=(("arrived", 4), ("pending", 0)),
    )


def _context(**changes):
    values = {
        "target_tag": "UKR",
        "selected_region_id": None,
        "is_own_country": False,
        "net_client": None,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _install_render_stubs(monkeypatch, *, window_open=True):
    imgui = _ImguiStub()
    monkeypatch.setattr(migration_panel_module, "imgui", imgui)
    monkeypatch.setattr(
        migration_panel_module.WindowManager,
        "window",
        lambda *_args, **_kwargs: nullcontext(window_open),
    )
    return imgui


def test_render_returns_false_when_window_is_closed(monkeypatch):
    presenter = SimpleNamespace(present_country=Mock())
    panel = MigrationPanel(presenter=presenter)
    _install_render_stubs(monkeypatch, window_open=False)

    assert not panel.render(SimpleNamespace(), _context())
    presenter.present_country.assert_not_called()


def test_render_shows_empty_state_when_country_summary_is_unavailable(monkeypatch):
    presenter = SimpleNamespace(present_country=Mock(return_value=None))
    panel = MigrationPanel(presenter=presenter)
    _install_render_stubs(monkeypatch)
    empty_state = Mock()
    monkeypatch.setattr(migration_panel_module, "draw_empty_state", empty_state)

    assert panel.render(SimpleNamespace(), _context())
    empty_state.assert_called_once_with("No migration profile is available for this country.")


def test_render_draws_country_and_region_summaries_and_skips_policy_for_observers(monkeypatch):
    route = SimpleNamespace(
        origin_region_id=1,
        destination_region_id=2,
        population_count=84,
        status="arrived",
        reason_label="Work opportunity",
    )
    summary = _summary(top_routes=(route,))
    region = SimpleNamespace(
        region_id=2,
        net_migration=84,
        incoming_population=100,
        pending_population=16,
        capacity_pressure=0.8,
        recent_reasons=("Employment", "Family reunification"),
    )
    presenter = SimpleNamespace(
        present_country=Mock(return_value=summary),
        present_region=Mock(return_value=region),
    )
    imgui = _install_render_stubs(monkeypatch)
    panel = MigrationPanel(presenter=presenter)
    state = SimpleNamespace()

    assert panel.render(state, _context(selected_region_id=2))

    presenter.present_country.assert_called_once()
    presenter.present_region.assert_called_once_with(state, 2)
    assert any("Top routes and latest reasons" in call for call in imgui.calls if call[0] == "text")
    assert any("1 → 2: 84" in call[1] for call in imgui.calls if call[0] == "text_wrapped")
    assert ("text_disabled", "Arrived: 4") in imgui.calls
    assert ("text_disabled", "Employment") in imgui.calls

    panel._render_country_summary(_summary())
    assert ("text_disabled", "No recorded routes in the current state.") in imgui.calls
    panel._render_region_summary(SimpleNamespace(), 99)
    presenter.present_region.return_value = None
    before = len(imgui.calls)
    panel._render_region_summary(SimpleNamespace(), 100)
    assert len(imgui.calls) == before


def test_policy_controls_ignore_observers_and_unknown_postures_use_default_index():
    panel = MigrationPanel()
    panel._render_policy_controls(
        SimpleNamespace(),
        _context(is_own_country=False, net_client=object()),
        _summary(),
    )

    assert panel._draft_country == ""
    assert MigrationPanel._index_or_default(("open", "managed"), "invalid") == 1
