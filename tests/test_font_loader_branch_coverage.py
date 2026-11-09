from pathlib import Path
from types import SimpleNamespace

import pytest

from src.client.ui.core import font_loader
from src.client.ui.core.font_loader import FontLoader


class FakeFontConfig:
    __slots__ = ("oversample_h", "oversample_v", "pixel_snap_h", "merge_mode", "glyph_offset")


class FakeFonts:
    def __init__(self, *, fail_four_args=False, fail_all=False):
        self.calls = []
        self.cleared = False
        self.fail_four_args = fail_four_args
        self.fail_all = fail_all

    def clear(self):
        self.cleared = True

    def add_font_from_file_ttf(self, *args):
        self.calls.append(args)
        if self.fail_all or (self.fail_four_args and len(args) == 4):
            raise TypeError("unsupported binding signature")


@pytest.fixture(autouse=True)
def preserve_keep_alive_storage():
    original = FontLoader._keep_alive_storage[:]
    yield
    FontLoader._keep_alive_storage[:] = original


def install_fake_imgui(monkeypatch):
    monkeypatch.setattr(font_loader.imgui, "ImFontConfig", FakeFontConfig, raising=False)
    monkeypatch.setattr(font_loader.imgui, "ImVec2", lambda x, y: (x, y), raising=False)


def test_configure_ui_uses_the_shared_size_and_enables_icon_merge(monkeypatch, tmp_path):
    calls = []
    style = SimpleNamespace(font_scale_main=0)
    monkeypatch.setattr(
        FontLoader,
        "load_primary_font",
        staticmethod(lambda io, path, **kwargs: calls.append((io, path, kwargs))),
    )
    monkeypatch.setattr(font_loader.imgui, "get_style", lambda: style, raising=False)
    io = object()

    FontLoader.configure_ui(io, tmp_path / "font.ttf")

    assert calls == [(io, tmp_path / "font.ttf", {"size_pixels": 14.0, "load_cjk": False, "load_icons": True})]
    assert style.font_scale_main == 1.0


def test_assets_path_is_returned_and_missing_assets_are_reported(monkeypatch, tmp_path, capsys):
    package_dir = tmp_path / "imgui_bundle"
    package_dir.mkdir()
    (package_dir / "assets").mkdir()
    monkeypatch.setattr(font_loader.imgui_bundle, "__file__", str(package_dir / "__init__.py"))

    assert FontLoader.get_imgui_bundle_assets_path() == str(package_dir / "assets")
    (package_dir / "assets").rmdir()
    assert FontLoader.get_imgui_bundle_assets_path() == str(package_dir / "assets")
    assert "CRITICAL" in capsys.readouterr().out


def test_missing_base_font_returns_before_touching_imgui(capsys):
    fonts = FakeFonts()
    io = SimpleNamespace(fonts=fonts)

    FontLoader.load_primary_font(io, Path("missing-font.ttf"))

    assert fonts.calls == []
    assert not fonts.cleared
    assert "Font not found" in capsys.readouterr().out


def test_primary_font_loads_latin_and_cyrillic_ranges_with_four_arguments(monkeypatch, tmp_path):
    install_fake_imgui(monkeypatch)
    font = tmp_path / "main.ttf"
    font.write_bytes(b"font")
    fonts = FakeFonts()
    io = SimpleNamespace(fonts=fonts)

    FontLoader.load_primary_font(io, font, 18.0, load_cjk=False, load_icons=False)

    assert fonts.cleared
    assert len(fonts.calls) == 1
    assert fonts.calls[0][:2] == (str(font), 18.0)
    assert fonts.calls[0][2].oversample_h == 2
    assert fonts.calls[0][2].oversample_v == 1
    assert fonts.calls[0][2].pixel_snap_h is True
    assert fonts.calls[0][3] > 0
    assert len(FontLoader._keep_alive_storage[-1]) == 5


def test_primary_font_falls_back_to_three_argument_binding(monkeypatch, tmp_path, capsys):
    install_fake_imgui(monkeypatch)
    font = tmp_path / "main.ttf"
    font.touch()
    fonts = FakeFonts(fail_four_args=True)

    FontLoader.load_primary_font(SimpleNamespace(fonts=fonts), font, load_cjk=False, load_icons=False)

    assert [len(call) for call in fonts.calls] == [4, 3]
    assert "4-arg AddFont signature failed" in capsys.readouterr().out


def test_primary_font_invokes_each_requested_optional_merge(monkeypatch, tmp_path):
    install_fake_imgui(monkeypatch)
    font = tmp_path / "main.ttf"
    font.touch()
    fonts = FakeFonts()
    merges = []
    monkeypatch.setattr(FontLoader, "_merge_cjk", staticmethod(lambda *args: merges.append(("cjk", args[1:]))))
    monkeypatch.setattr(FontLoader, "_merge_icons", staticmethod(lambda *args: merges.append(("icons", args[1:]))))

    FontLoader.load_primary_font(SimpleNamespace(fonts=fonts), font, 18.0, load_cjk=True, load_icons=True)

    assert merges == [("cjk", (str(font), 18.0)), ("icons", (18.0,))]


def test_cjk_merge_uses_available_ranges_and_three_argument_fallback(monkeypatch, capsys):
    install_fake_imgui(monkeypatch)
    fonts = FakeFonts(fail_four_args=True)
    fonts.get_glyph_ranges_chinese_full = lambda: 123

    FontLoader._merge_cjk(SimpleNamespace(fonts=fonts), "main.ttf", 16.0)

    assert [len(call) for call in fonts.calls] == [4, 3]
    assert fonts.calls[0][3] == 123
    assert capsys.readouterr().out == ""


def test_cjk_merge_reports_success_for_four_argument_binding(monkeypatch, capsys):
    install_fake_imgui(monkeypatch)
    fonts = FakeFonts()

    FontLoader._merge_cjk(SimpleNamespace(fonts=fonts), "main.ttf", 16.0)

    assert len(fonts.calls) == 1
    assert "CJK Glyphs merged" in capsys.readouterr().out


def test_cjk_merge_uses_zero_ranges_when_binding_has_no_range_provider(monkeypatch, capsys):
    install_fake_imgui(monkeypatch)
    fonts = FakeFonts()

    FontLoader._merge_cjk(SimpleNamespace(fonts=fonts), "main.ttf", 16.0)

    assert fonts.calls[0][3] == 0
    assert "CJK Glyphs merged" in capsys.readouterr().out


def test_cjk_merge_reports_configuration_errors_without_raising(monkeypatch, capsys):
    monkeypatch.setattr(
        font_loader.imgui,
        "ImFontConfig",
        lambda: (_ for _ in ()).throw(RuntimeError("config failure")),
        raising=False,
    )

    FontLoader._merge_cjk(SimpleNamespace(fonts=FakeFonts()), "main.ttf", 16.0)

    assert "Skipped CJK merge: config failure" in capsys.readouterr().out


def test_icon_merge_loads_existing_font_and_scales_its_size(monkeypatch, tmp_path, capsys):
    install_fake_imgui(monkeypatch)
    assets = tmp_path / "assets"
    icon = assets / "fonts" / "Font_Awesome_6_Free-Solid-900.otf"
    icon.parent.mkdir(parents=True)
    icon.touch()
    monkeypatch.setattr(FontLoader, "get_imgui_bundle_assets_path", staticmethod(lambda: str(assets)))
    fonts = FakeFonts()

    FontLoader._merge_icons(SimpleNamespace(fonts=fonts), 14.0)

    assert fonts.calls[0][:2] == (str(icon), 21.0)
    assert fonts.calls[0][2].merge_mode is True
    assert fonts.calls[0][2].pixel_snap_h is True
    assert fonts.calls[0][2].glyph_offset == (0, 2)
    assert fonts.calls[0][3] > 0
    assert "Icons merged from" in capsys.readouterr().out


def test_icon_merge_falls_back_and_reports_a_missing_font(monkeypatch, tmp_path, capsys):
    install_fake_imgui(monkeypatch)
    assets = tmp_path / "assets"
    icon = assets / "fonts" / "Font_Awesome_6_Free-Solid-900.otf"
    icon.parent.mkdir(parents=True)
    icon.touch()
    monkeypatch.setattr(FontLoader, "get_imgui_bundle_assets_path", staticmethod(lambda: str(assets)))
    fonts = FakeFonts(fail_four_args=True)

    FontLoader._merge_icons(SimpleNamespace(fonts=fonts), 12.0)
    assert [len(call) for call in fonts.calls] == [4, 3]
    assert "Fallback Mode" in capsys.readouterr().out

    fonts.calls.clear()
    icon.unlink()
    FontLoader._merge_icons(SimpleNamespace(fonts=fonts), 12.0)
    assert fonts.calls == []
    assert "font file missing" in capsys.readouterr().out


def test_icon_merge_reports_configuration_errors_without_raising(monkeypatch, capsys):
    monkeypatch.setattr(
        font_loader.imgui,
        "ImFontConfig",
        lambda: (_ for _ in ()).throw(RuntimeError("icon config failure")),
        raising=False,
    )

    FontLoader._merge_icons(SimpleNamespace(fonts=FakeFonts()), 16.0)

    assert "Failed to load Icons: icon config failure" in capsys.readouterr().out
