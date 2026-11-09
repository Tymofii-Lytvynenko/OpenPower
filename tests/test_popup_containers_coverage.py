from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.ui.core import popup_containers as popup_module
from src.client.ui.core.popup_containers import PopupManager


def install_imgui(monkeypatch, *, popup_open: bool, modal_open: bool):
    imgui = SimpleNamespace(
        WindowFlags_=SimpleNamespace(no_title_bar=2, no_move=8),
        begin_popup=Mock(return_value=popup_open),
        end_popup=Mock(),
        set_next_window_pos=Mock(),
        set_next_window_size=Mock(),
        begin=Mock(return_value=modal_open),
        end=Mock(),
    )
    monkeypatch.setattr(popup_module, "imgui", imgui)
    return imgui


@pytest.mark.parametrize("is_open", [True, False], ids=["open", "closed"])
def test_popup_yields_open_state_and_closes_only_when_open(monkeypatch, is_open: bool) -> None:
    imgui = install_imgui(monkeypatch, popup_open=is_open, modal_open=False)
    yielded = []

    with PopupManager.popup("Save") as opened:
        yielded.append(opened)

    assert yielded == [is_open]
    imgui.begin_popup.assert_called_once_with("Save")
    if is_open:
        imgui.end_popup.assert_called_once_with()
    else:
        imgui.end_popup.assert_not_called()


def test_popup_closes_when_body_raises(monkeypatch) -> None:
    imgui = install_imgui(monkeypatch, popup_open=True, modal_open=False)

    with pytest.raises(ValueError, match="body failed"):
        with PopupManager.popup("Save") as opened:
            assert opened is True
            raise ValueError("body failed")

    imgui.end_popup.assert_called_once_with()


@pytest.mark.parametrize(
    ("dimensions", "expected_position"),
    [
        ((), (250.0, 100.0)),
        ((500, 250), (150.0, 175.0)),
    ],
    ids=["default-size", "custom-size"],
)
def test_centered_modal_positions_sizes_and_yields_open_state(
    monkeypatch,
    dimensions: tuple[int, ...],
    expected_position: tuple[float, float],
) -> None:
    imgui = install_imgui(monkeypatch, popup_open=False, modal_open=True)
    yielded = []

    with PopupManager.centered_modal("Confirm", 800, 600, *dimensions) as opened:
        yielded.append(opened)

    expected_size = dimensions or (300, 400)
    imgui.set_next_window_pos.assert_called_once_with(expected_position)
    imgui.set_next_window_size.assert_called_once_with(expected_size)
    imgui.begin.assert_called_once_with("Confirm", None, 10)
    imgui.end.assert_called_once_with()
    assert yielded == [True]


def test_centered_modal_yields_false_without_ending_closed_modal(monkeypatch) -> None:
    imgui = install_imgui(monkeypatch, popup_open=False, modal_open=False)
    yielded = []

    with PopupManager.centered_modal("Confirm", 800, 600) as opened:
        yielded.append(opened)

    assert yielded == [False]
    imgui.end.assert_not_called()


def test_centered_modal_closes_when_body_raises(monkeypatch) -> None:
    imgui = install_imgui(monkeypatch, popup_open=False, modal_open=True)

    with pytest.raises(ValueError, match="body failed"):
        with PopupManager.centered_modal("Confirm", 800, 600) as opened:
            assert opened is True
            raise ValueError("body failed")

    imgui.end.assert_called_once_with()
