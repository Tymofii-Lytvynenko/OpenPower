import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import configure_multiprocessing, export_profile_html, profiling_enabled


class MainProfilingTest(unittest.TestCase):
    def test_profiling_is_opt_in(self) -> None:
        self.assertFalse(profiling_enabled({}))
        self.assertTrue(profiling_enabled({"OPENPOWER_PROFILE": "1"}))
        self.assertTrue(profiling_enabled({"OPENPOWER_PROFILE": "true"}))
        self.assertFalse(profiling_enabled({"OPENPOWER_PROFILE": "0"}))

    def test_launcher_configures_spawn_and_frozen_support(self) -> None:
        with (
            patch("main.mp.freeze_support") as freeze_support,
            patch("main.mp.set_start_method") as set_start_method,
        ):
            configure_multiprocessing()

        freeze_support.assert_called_once_with()
        set_start_method.assert_called_once_with("spawn", force=True)

    def test_profile_export_writes_only_when_the_profiler_has_a_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            output_path = tmp_path / "profile.html"
            profiler = MagicMock(last_session=object())
            profiler.output_html.return_value = "<html>profile</html>"

            saved_path = export_profile_html(profiler, output_path)

            self.assertEqual(saved_path, output_path)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "<html>profile</html>")
            profiler.output_html.assert_called_once_with()

            no_session_profiler = MagicMock(last_session=None)
            empty_path = tmp_path / "empty.html"
            self.assertIsNone(export_profile_html(no_session_profiler, empty_path))
            self.assertFalse(empty_path.exists())


if __name__ == "__main__":
    unittest.main()
