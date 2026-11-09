from types import SimpleNamespace
from unittest.mock import MagicMock, call

from src.client.renderers.base_renderer import BaseRenderer


class ConcreteRenderer(BaseRenderer):
    def draw(self) -> None:
        return None


class ProgramWithDeclaredUniforms:
    def __init__(self, uniforms: set[str]) -> None:
        self.uniforms = {name: None for name in uniforms}

    def __setitem__(self, name: str, value) -> None:
        if name not in self.uniforms:
            raise KeyError(name)
        self.uniforms[name] = value


def test_base_renderer_initializes_window_and_abstract_draw_body(monkeypatch) -> None:
    context = SimpleNamespace()
    window = SimpleNamespace(ctx=context)
    monkeypatch.setattr(
        "src.client.renderers.base_renderer.arcade.get_window",
        lambda: window,
    )

    renderer = ConcreteRenderer()

    assert renderer.window is window
    assert renderer.ctx is context
    assert BaseRenderer.draw(renderer) is None


def test_set_uniform_if_present_sets_known_uniform_and_ignores_missing_one() -> None:
    renderer = ConcreteRenderer.__new__(ConcreteRenderer)
    program = ProgramWithDeclaredUniforms({"u_color"})

    renderer._set_uniform_if_present(program, "u_color", (1.0, 0.5, 0.25))
    renderer._set_uniform_if_present(program, "u_missing", 7)

    assert program.uniforms == {"u_color": (1.0, 0.5, 0.25)}


def test_rendering_state_enables_depth_and_blend_and_disables_depth() -> None:
    renderer = ConcreteRenderer.__new__(ConcreteRenderer)
    context = SimpleNamespace(
        DEPTH_TEST="depth",
        BLEND="blend",
        BLEND_DEFAULT=("source", "destination"),
        enable=MagicMock(),
        disable=MagicMock(),
    )
    renderer.ctx = context

    renderer._enable_rendering_state()
    renderer._disable_rendering_state()

    assert context.enable.call_args_list == [call("depth"), call("blend")]
    assert context.blend_func == ("source", "destination")
    context.disable.assert_called_once_with("depth")
