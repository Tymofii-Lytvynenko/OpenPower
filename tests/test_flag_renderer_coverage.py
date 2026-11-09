from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from PIL import Image

import src.client.renderers.flag_renderer as flag_module
from src.client.renderers.flag_renderer import FlagRenderer, FlagTexture


@pytest.fixture(autouse=True)
def reset_flag_renderer_singleton():
    previous = FlagRenderer._instance
    FlagRenderer._instance = None
    yield
    FlagRenderer._instance = previous


def _renderer(texture_uploader=None):
    return FlagRenderer(texture_uploader)


def test_flag_texture_wraps_gpu_object_and_renderer_reuses_singleton():
    gl_object = object()
    texture = FlagTexture(gl_object, 7, 16, 8)
    renderer = _renderer()

    assert (texture.gl_obj, texture.gl_id, texture.width, texture.height) == (gl_object, 7, 16, 8)
    assert _renderer() is renderer

    renderer._cache["old"] = texture
    renderer._emergency_texture = texture
    uploader = Mock(return_value=texture)
    assert _renderer(uploader) is renderer
    assert renderer._texture_uploader is uploader
    assert renderer._cache == {}
    assert renderer._emergency_texture is None


@pytest.mark.parametrize(
    "texture",
    [None, FlagTexture(None, 0, 1, 1)],
)
def test_draw_flag_uses_dummy_when_no_valid_texture(monkeypatch, texture):
    imgui = SimpleNamespace(ImVec2=lambda width, height: (width, height), dummy=Mock())
    monkeypatch.setattr(flag_module, "imgui", imgui)
    renderer = _renderer()
    renderer.get_texture = Mock(return_value=texture)

    renderer.draw_flag("USA", 24, 12)

    imgui.dummy.assert_called_once_with((24, 12))


def test_draw_flag_renders_a_valid_texture(monkeypatch):
    monkeypatch.setattr(flag_module, "imgui", SimpleNamespace())
    renderer = _renderer()
    texture = FlagTexture(object(), 5, 2, 1)
    renderer.get_texture = Mock(return_value=texture)
    renderer._render_imgui_image = Mock()

    renderer.draw_flag("USA", 24, 12)

    renderer._render_imgui_image.assert_called_once_with(5, 24, 12)


def test_render_imgui_image_uses_texture_ref_then_legacy_id(monkeypatch):
    image = Mock()
    monkeypatch.setattr(
        flag_module,
        "imgui",
        SimpleNamespace(
            ImVec2=lambda width, height: (width, height),
            ImTextureRef=lambda value: ("ref", value),
            ImTextureID=lambda value: ("id", value),
            image=image,
        ),
    )
    renderer = _renderer()
    renderer._render_imgui_image(9, 10, 20)
    image.assert_called_once_with(("ref", 9), (10, 20))

    image = Mock()

    def unsupported_reference(_value):
        raise ValueError("reference wrapper is unavailable")

    monkeypatch.setattr(
        flag_module,
        "imgui",
        SimpleNamespace(
            ImVec2=lambda width, height: (width, height),
            ImTextureRef=unsupported_reference,
            ImTextureID=lambda value: ("id", value),
            image=image,
        ),
    )
    renderer._render_imgui_image(9, 10, 20)
    image.assert_called_once_with(("id", 9), (10, 20))


def test_render_imgui_image_falls_back_to_integer_and_void_pointer(monkeypatch):
    image = Mock()
    monkeypatch.setattr(
        flag_module,
        "imgui",
        SimpleNamespace(ImVec2=lambda width, height: (width, height), image=image),
    )
    renderer = _renderer()
    renderer._render_imgui_image(13, 10, 20)
    image.assert_called_once_with(13, (10, 20))

    image = Mock(side_effect=[TypeError("int rejected"), None])
    monkeypatch.setattr(
        flag_module,
        "imgui",
        SimpleNamespace(ImVec2=lambda width, height: (width, height), image=image),
    )
    renderer._render_imgui_image(13, 10, 20)
    assert image.call_args_list[0].args == (13, (10, 20))
    assert image.call_args_list[1].args[0].value == 13

    image = Mock()

    def unsupported_id(_value):
        raise ValueError("legacy ID wrapper is unavailable")

    monkeypatch.setattr(
        flag_module,
        "imgui",
        SimpleNamespace(
            ImVec2=lambda width, height: (width, height),
            ImTextureRef=None,
            ImTextureID=unsupported_id,
            image=image,
        ),
    )
    renderer._render_imgui_image(13, 10, 20)
    image.assert_called_once_with(13, (10, 20))


def test_render_imgui_image_reports_final_failure_only_once(monkeypatch, capsys):
    image = Mock(side_effect=[TypeError("int rejected")] * 4)
    imgui = SimpleNamespace(
        ImVec2=lambda width, height: (width, height), image=image, text=Mock(),
    )
    monkeypatch.setattr(flag_module, "imgui", imgui)
    renderer = _renderer()

    renderer._render_imgui_image(17, 10, 20)
    renderer._render_imgui_image(17, 10, 20)

    assert imgui.text.call_args_list == [call("IMG_ERR"), call("IMG_ERR")]
    assert capsys.readouterr().out.count("FAILED all cast attempts") == 1
    assert renderer._error_printed is True


def test_emergency_texture_is_magenta_and_handles_image_creation_failure(monkeypatch):
    uploader = Mock(return_value=FlagTexture(object(), 2, 32, 32))
    renderer = _renderer(uploader)

    texture = renderer._create_emergency_texture()

    assert texture.gl_id == 2
    image, label = uploader.call_args.args
    assert image.size == (32, 32)
    assert image.getpixel((0, 0)) == (255, 0, 255, 255)
    assert label == "EMERGENCY"

    monkeypatch.setattr(flag_module, "Image", SimpleNamespace(new=Mock(side_effect=RuntimeError("no image"))))
    assert renderer._create_emergency_texture() is None


@pytest.mark.parametrize(
    "raw_id,expected_id",
    [
        (SimpleNamespace(glo_id=31), 31),
        (SimpleNamespace(value=32), 32),
        (33, 33),
        (None, 0),
    ],
)
def test_upload_to_arcade_context_extracts_supported_ids(monkeypatch, raw_id, expected_id):
    gl_texture = SimpleNamespace(glo=raw_id)
    context = SimpleNamespace(LINEAR=4, texture=Mock(return_value=gl_texture))
    monkeypatch.setattr(
        flag_module,
        "arcade",
        SimpleNamespace(get_window=lambda: SimpleNamespace(ctx=context)),
    )
    renderer = _renderer()
    image = Image.new("RGBA", (3, 2), (1, 2, 3, 4))

    texture = renderer._upload_to_gpu(image, "UKR")

    assert context.texture.call_args.args[0] == (3, 2)
    assert context.texture.call_args.kwargs["data"] == image.tobytes()
    assert gl_texture.filter == (4, 4)
    if expected_id:
        assert texture.gl_obj is gl_texture
        assert (texture.gl_id, texture.width, texture.height) == (expected_id, 3, 2)
    else:
        assert texture is None


def test_upload_to_gpu_uses_injected_uploader_and_logs_failures(monkeypatch, capsys):
    image = Image.new("RGBA", (1, 1))
    expected = FlagTexture(object(), 6, 1, 1)
    uploader = Mock(return_value=expected)
    assert _renderer(uploader)._upload_to_gpu(image, "AAA") is expected
    uploader.assert_called_once_with(image, "AAA")

    failing = _renderer(Mock(side_effect=RuntimeError("device lost")))
    assert failing._upload_to_gpu(image, "BBB") is None
    assert "GPU Upload Error (BBB): device lost" in capsys.readouterr().out

    monkeypatch.setattr(
        flag_module,
        "arcade",
        SimpleNamespace(get_window=Mock(side_effect=RuntimeError("no window"))),
    )
    FlagRenderer._instance = None
    assert _renderer()._upload_to_gpu(image, "CCC") is None
    assert "GPU Upload Error (CCC): no window" in capsys.readouterr().out


def _write_flag(directory: Path, filename: str) -> None:
    Image.new("RGBA", (2, 1), (20, 30, 40, 255)).save(directory / filename)


@pytest.mark.parametrize(
    "files,tag,expected_label,expect_emergency",
    [
        (("USA.png",), "USA", "USA", False),
        (("usa.png",), "UsA", "UsA", False),
        (("XXX.png",), "missing", "missing", False),
        ((), "missing", None, True),
    ],
)
def test_get_texture_resolves_exact_lowercase_fallback_and_missing(
    monkeypatch, tmp_path, files, tag, expected_label, expect_emergency,
):
    for filename in files:
        _write_flag(tmp_path, filename)
    renderer = _renderer()
    renderer.flags_dir = tmp_path
    if files == ("usa.png",):
        original_exists = Path.exists

        def case_sensitive_exists(path):
            if path.parent == tmp_path:
                return path.name == "usa.png"
            return original_exists(path)

        monkeypatch.setattr(Path, "exists", case_sensitive_exists)
    emergency = FlagTexture(object(), 1, 32, 32)
    renderer._create_emergency_texture = Mock(return_value=emergency)
    loaded = FlagTexture(object(), 8, 2, 1)
    renderer._upload_to_gpu = Mock(return_value=loaded)

    texture = renderer.get_texture(tag)

    if expect_emergency:
        assert texture is emergency
        renderer._upload_to_gpu.assert_not_called()
    else:
        assert texture is loaded
        assert renderer._upload_to_gpu.call_args.args[1] == expected_label
        assert renderer.get_texture(tag) is loaded
        renderer._upload_to_gpu.assert_called_once()
    renderer._create_emergency_texture.assert_called_once_with()


def test_get_texture_uses_emergency_after_upload_or_file_errors(monkeypatch, tmp_path, capsys):
    _write_flag(tmp_path, "USA.png")
    renderer = _renderer()
    renderer.flags_dir = tmp_path
    emergency = FlagTexture(object(), 1, 32, 32)
    renderer._create_emergency_texture = Mock(return_value=emergency)
    renderer._upload_to_gpu = Mock(return_value=None)
    assert renderer.get_texture("USA") is emergency
    renderer._upload_to_gpu.assert_called_once()

    (tmp_path / "other.png").write_text("invalid image", encoding="utf-8")
    assert renderer.get_texture("other") is emergency
    assert "Load Error other" in capsys.readouterr().out

    renderer._cache["broken"] = None
    assert renderer.get_texture("broken") is None


def test_clear_cache_forgets_loaded_and_emergency_textures():
    renderer = _renderer()
    renderer._cache["USA"] = FlagTexture(object(), 1, 1, 1)
    renderer._emergency_texture = FlagTexture(object(), 2, 1, 1)

    renderer.clear_cache()

    assert renderer._cache == {}
    assert renderer._emergency_texture is None
