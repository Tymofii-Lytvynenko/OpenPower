import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from src.client.renderers import country_region_map as country_map
from src.client.renderers.country_region_map import (
    CountryMapTexture,
    CountryRegionMapRasterizer,
    CountryRegionMapTextureCache,
)


def map_data(packed_map):
    return SimpleNamespace(packed_map=packed_map, width=packed_map.shape[1], height=packed_map.shape[0])


def test_rasterizer_rejects_empty_ids_and_countries_absent_from_map():
    rasterizer = CountryRegionMapRasterizer()
    data = map_data(np.array([[1, 1], [0, 0]], dtype=np.int32))

    assert rasterizer.render(data, []) is None
    assert rasterizer.render(data, [0, -2]) is None
    assert rasterizer.render(data, [9]) is None


def test_rasterizer_clamps_padding_and_resizes_to_configured_bounds():
    rasterizer = CountryRegionMapRasterizer(max_size=(2, 1), padding_px=10)
    data = map_data(np.array([[1, 1, 0], [1, 2, 2], [0, 2, 2]], dtype=np.int32))

    raster = rasterizer.render(data, [2, 1, 1, 0, -1])

    assert raster.region_ids == (1, 2)
    assert raster.source_bbox == (0, 0, 3, 3)
    assert raster.image.size == (1, 1)


def test_rasterizer_keeps_same_size_images_and_accepts_zero_dimensions():
    rasterizer = CountryRegionMapRasterizer(max_size=(3, 2))
    image = Image.new("RGBA", (3, 2))
    zero_width = SimpleNamespace(width=0, height=2)

    assert rasterizer._resize_to_fit(image) is image
    assert rasterizer._resize_to_fit(zero_width) is zero_width


def test_region_borders_cover_outer_edges_and_disconnected_cells():
    rasterizer = CountryRegionMapRasterizer()
    ids = np.array([[1, 0, 2], [0, 2, 2]], dtype=np.int32)
    mask = ids > 0

    borders = rasterizer._region_borders(ids, mask)

    assert borders[0, 0]
    assert borders[0, 2]
    assert borders[1, 1]
    assert not borders[1, 2]


def test_texture_cache_reuses_entries_and_evicts_oldest_keys():
    image = Image.new("RGBA", (2, 2))

    class Rasterizer:
        def __init__(self):
            self.calls = []

        def render(self, data, ids):
            self.calls.append((data, ids))
            return SimpleNamespace(image=image)

    rasterizer = Rasterizer()
    cache = CountryRegionMapTextureCache(rasterizer=rasterizer, max_entries=2)
    uploaded = []
    cache._upload_to_gpu = lambda source: uploaded.append(source) or CountryMapTexture("gl", len(uploaded), 2, 2)
    first = map_data(np.array([[1]], dtype=np.int32))
    second = map_data(np.array([[2]], dtype=np.int32))
    third = map_data(np.array([[3]], dtype=np.int32))

    first_texture = cache.get_texture(first, [1, 1, 0])
    assert cache.get_texture(first, [1]) is first_texture
    cache.get_texture(second, [2])
    cache.get_texture(third, [3])
    cache.get_texture(first, [1])

    assert len(rasterizer.calls) == 4
    assert len(cache._cache) == 2


def test_texture_cache_handles_missing_inputs_and_caches_empty_rasters():
    class EmptyRasterizer:
        calls = 0

        def render(self, _data, _ids):
            self.calls += 1
            return None

    rasterizer = EmptyRasterizer()
    cache = CountryRegionMapTextureCache(rasterizer=rasterizer)
    data = map_data(np.array([[0]], dtype=np.int32))

    assert cache.get_texture(None, [1]) is None
    assert cache.get_texture(data, []) is None
    assert cache.get_texture(data, [1]) is None
    assert cache.get_texture(data, [1]) is None
    assert rasterizer.calls == 1


def test_draw_texture_forwards_texture_dimensions_and_test_id(monkeypatch):
    cache = CountryRegionMapTextureCache()
    calls = []
    monkeypatch.setattr(cache, "_render_imgui_image", lambda *args, **kwargs: calls.append((args, kwargs)))
    texture = CountryMapTexture("gl", 77, 80, 60)

    cache.draw_texture(texture, 120, 90, test_id="country.preview")

    assert calls == [((77, 120, 90), {"test_id": "country.preview"})]


def test_gpu_upload_uses_arcade_context_and_extracts_texture_id(monkeypatch):
    cache = CountryRegionMapTextureCache()
    gl_texture = SimpleNamespace(glo=SimpleNamespace(glo_id=93), filter=None)
    context = SimpleNamespace(NEAREST=7, texture=lambda *args, **kwargs: gl_texture)
    monkeypatch.setattr(country_map.arcade, "get_window", lambda: SimpleNamespace(ctx=context))

    texture = cache._upload_to_gpu(Image.new("RGBA", (4, 3)))

    assert texture == CountryMapTexture(gl_texture, 93, 4, 3)
    assert gl_texture.filter == (7, 7)


def test_gpu_upload_uses_current_context_when_arcade_window_is_missing(monkeypatch):
    cache = CountryRegionMapTextureCache()
    expected = CountryMapTexture(5, 5, 2, 3)
    monkeypatch.setattr(country_map.arcade, "get_window", lambda: None)
    monkeypatch.setattr(cache, "_upload_with_current_opengl_context", lambda image: expected)

    assert cache._upload_to_gpu(Image.new("RGBA", (2, 3))) == expected


def test_gpu_upload_falls_back_when_arcade_has_no_registered_window(monkeypatch):
    cache = CountryRegionMapTextureCache()
    expected = CountryMapTexture(6, 6, 1, 1)

    def no_window():
        raise RuntimeError("no Arcade window")

    monkeypatch.setattr(country_map.arcade, "get_window", no_window)
    monkeypatch.setattr(cache, "_upload_with_current_opengl_context", lambda _image: expected)

    assert cache._upload_to_gpu(Image.new("RGBA", (1, 1))) == expected


def test_gpu_upload_reports_failure_once_and_rejects_invalid_texture_id(monkeypatch, capsys):
    cache = CountryRegionMapTextureCache()
    monkeypatch.setattr(country_map.arcade, "get_window", lambda: SimpleNamespace(ctx=SimpleNamespace(
        texture=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("upload failed")),
        NEAREST=1,
    )))
    image = Image.new("RGBA", (1, 1))

    assert cache._upload_to_gpu(image) is None
    assert cache._upload_to_gpu(image) is None
    assert capsys.readouterr().out.count("GPU upload failed") == 1
    assert CountryRegionMapTextureCache()._extract_texture_id(SimpleNamespace(glo=0)) == 0


def test_gpu_upload_rejects_context_textures_without_ids(monkeypatch):
    cache = CountryRegionMapTextureCache()
    context = SimpleNamespace(NEAREST=1, texture=lambda *args, **kwargs: SimpleNamespace(glo=None))
    monkeypatch.setattr(country_map.arcade, "get_window", lambda: SimpleNamespace(ctx=context))

    assert cache._upload_to_gpu(Image.new("RGBA", (1, 1))) is None


def fake_gl(*, version=b"4.6", texture_id=55, fail_upload=False):
    gl = SimpleNamespace(
        GL_VERSION=1,
        GL_ACTIVE_TEXTURE=2,
        GL_TEXTURE0=10,
        GL_TEXTURE_BINDING_2D=3,
        GL_UNPACK_ALIGNMENT=4,
        GL_TEXTURE_2D=5,
        GL_TEXTURE_MIN_FILTER=6,
        GL_TEXTURE_MAG_FILTER=7,
        GL_NEAREST=8,
        GL_RGBA=9,
        GL_UNSIGNED_BYTE=10,
        calls=[],
    )
    values = {2: 13, 3: 14, 4: 4}
    gl.glGetString = lambda _name: version
    gl.glGenTextures = lambda _count: texture_id
    gl.glGetIntegerv = lambda name: values[name]
    gl.glActiveTexture = lambda value: gl.calls.append(("active", value))
    gl.glBindTexture = lambda *args: gl.calls.append(("bind", *args))
    gl.glPixelStorei = lambda *args: gl.calls.append(("pixel", *args))
    gl.glTexParameteri = lambda *args: gl.calls.append(("parameter", *args))

    def upload(*args):
        gl.calls.append(("upload", *args[:4]))
        if fail_upload:
            raise RuntimeError("upload failed")

    gl.glTexImage2D = upload
    gl.glDeleteTextures = lambda *args: gl.calls.append(("delete", *args))
    return gl


def install_fake_opengl(monkeypatch, gl):
    module = ModuleType("OpenGL")
    module.__path__ = []
    module.GL = gl
    monkeypatch.setitem(sys.modules, "OpenGL", module)


def test_current_context_upload_restores_texture_state(monkeypatch):
    gl = fake_gl()
    install_fake_opengl(monkeypatch, gl)
    cache = CountryRegionMapTextureCache()

    texture = cache._upload_with_current_opengl_context(Image.new("RGBA", (3, 2)))

    assert texture == CountryMapTexture(55, 55, 3, 2)
    assert ("bind", 5, 14) in gl.calls
    assert ("pixel", 4, 4) in gl.calls
    assert gl.calls[-1] == ("active", 13)


@pytest.mark.parametrize(
    "version, texture_id",
    [(None, 55), (b"4.6", 0)],
)
def test_current_context_upload_returns_none_without_context_or_texture(monkeypatch, version, texture_id):
    install_fake_opengl(monkeypatch, fake_gl(version=version, texture_id=texture_id))

    assert CountryRegionMapTextureCache()._upload_with_current_opengl_context(Image.new("RGBA", (1, 1))) is None


def test_current_context_upload_deletes_partial_texture_and_restores_state(monkeypatch):
    gl = fake_gl(fail_upload=True)
    install_fake_opengl(monkeypatch, gl)

    with pytest.raises(RuntimeError, match="upload failed"):
        CountryRegionMapTextureCache()._upload_with_current_opengl_context(Image.new("RGBA", (1, 1)))

    assert ("delete", 1, [55]) in gl.calls
    assert gl.calls[-1] == ("active", 13)


@pytest.mark.parametrize(
    "texture, expected",
    [
        (SimpleNamespace(glo=None), 0),
        (SimpleNamespace(glo=SimpleNamespace(glo_id="12")), 12),
        (SimpleNamespace(glo=SimpleNamespace(value="13")), 13),
        (SimpleNamespace(glo="14"), 14),
    ],
)
def test_texture_id_extraction_supports_binding_shapes(texture, expected):
    assert CountryRegionMapTextureCache()._extract_texture_id(texture) == expected


def test_imgui_image_uses_texture_ref_factory_when_available(monkeypatch):
    cache = CountryRegionMapTextureCache()
    calls = []
    monkeypatch.setattr(country_map.imgui, "ImVec2", lambda width, height: (width, height), raising=False)
    monkeypatch.setattr(country_map.imgui, "ImTextureRef", lambda gl_id: ("ref", gl_id), raising=False)
    monkeypatch.setattr(country_map.imgui, "ImTextureID", None, raising=False)
    monkeypatch.setattr(country_map.imgui, "image", lambda *args, **kwargs: calls.append((args, kwargs)), raising=False)

    cache._render_imgui_image(44, 30, 20, test_id="map")

    assert calls == [((("ref", 44), (30, 20)), {"test_id": "map"})]


def test_imgui_image_uses_integer_id_when_factory_is_unavailable(monkeypatch):
    cache = CountryRegionMapTextureCache()
    calls = []
    monkeypatch.setattr(country_map.imgui, "ImVec2", lambda width, height: (width, height), raising=False)
    monkeypatch.setattr(country_map.imgui, "ImTextureRef", None, raising=False)
    monkeypatch.setattr(country_map.imgui, "ImTextureID", None, raising=False)
    monkeypatch.setattr(country_map.imgui, "image", lambda *args, **kwargs: calls.append((args, kwargs)), raising=False)

    cache._render_imgui_image(44, 30, 20)

    assert calls == [((44, (30, 20)), {"test_id": None})]


def test_imgui_image_falls_back_from_factory_and_legacy_type_error(monkeypatch):
    cache = CountryRegionMapTextureCache()
    monkeypatch.setattr(country_map.imgui, "ImVec2", lambda width, height: (width, height), raising=False)
    monkeypatch.setattr(
        country_map.imgui,
        "ImTextureRef",
        lambda _gl_id: (_ for _ in ()).throw(RuntimeError("unsupported ref")),
        raising=False,
    )
    monkeypatch.setattr(country_map.imgui, "ImTextureID", None, raising=False)
    calls = []

    def image(texture, size, **kwargs):
        calls.append(texture)
        if isinstance(texture, int):
            raise TypeError("legacy binding requires pointer")

    monkeypatch.setattr(country_map.imgui, "image", image, raising=False)

    cache._render_imgui_image(44, 30, 20)

    assert calls[0] == 44
    assert calls[1].value == 44
