from pathlib import Path

# Absolute path to the directory containing this file
ROOT = Path(__file__).parent

class ShaderRegistry:
    """Centralized paths for all GLSL source files."""
    
    # Paths relative to the client folder
    POLITICAL_V = ROOT / "renderers" / "shaders" / "political_map.vert"
    POLITICAL_F = ROOT / "renderers" / "shaders" / "political_map.frag"

    @classmethod
    def load_bundle(cls, vert_path: Path, frag_path: Path) -> dict:
        """Helper to read shader files into strings for Arcade."""
        return {
            "vertex_shader": vert_path.read_text(),
            "fragment_shader": frag_path.read_text()
        }