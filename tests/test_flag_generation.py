import io
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image

from src.core.paths import ProjectPaths
from utils.flags.flags_gen import CDN_URL_TEMPLATE, OUTPUT_DIR, TARGET_SIZE, FlagProcessor


def test_generator_defaults_to_runtime_path_and_maps_kosovo(tmp_path):
    assert OUTPUT_DIR == ProjectPaths.assets("base") / "flags"
    png = io.BytesIO()
    Image.new("RGB", (6, 4)).save(png, format="PNG")
    processor = FlagProcessor(tmp_path)
    processor.countries = []
    processor.session.get = Mock(return_value=SimpleNamespace(status_code=200, content=png.getvalue()))

    processor.run()

    processor.session.get.assert_called_once_with(CDN_URL_TEMPLATE.format(iso2="xk"), timeout=10)
    with Image.open(tmp_path / "KOS.png") as generated:
        assert generated.size == TARGET_SIZE
