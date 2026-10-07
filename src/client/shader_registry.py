import logging
from pathlib import Path

# Absolute path to the directory containing this file
ROOT = Path(__file__).parent
logger = logging.getLogger(__name__)


class ShaderRegistry:
    """Centralized paths for all GLSL source files."""

    # Paths relative to the client folder
    POLITICAL_V = ROOT / "renderers" / "shaders" / "political_map.vert"
    POLITICAL_F = ROOT / "renderers" / "shaders" / "political_map.frag"
    GLOBE_V = ROOT / "renderers" / "shaders" / "globe.vert"
    GLOBE_F = ROOT / "renderers" / "shaders" / "globe.frag"

    @classmethod
    def load_bundle(cls, vert_path: Path, frag_path: Path) -> dict:
        """Read an explicit vertex/fragment pair and identify missing sources clearly."""
        sources = {}
        for shader_type, path in (
            ("vertex", Path(vert_path)),
            ("fragment", Path(frag_path)),
        ):
            try:
                sources[f"{shader_type}_shader"] = path.read_text(encoding="utf-8")
            except FileNotFoundError as exc:
                logger.error("Missing %s shader source: %s", shader_type, path.resolve())
                raise FileNotFoundError(
                    f"Missing {shader_type} shader source: {path.resolve()}"
                ) from exc
        return sources
