import unittest

from main import profiling_enabled


class MainProfilingTest(unittest.TestCase):
    def test_profiling_is_opt_in(self) -> None:
        self.assertFalse(profiling_enabled({}))
        self.assertTrue(profiling_enabled({"OPENPOWER_PROFILE": "1"}))
        self.assertTrue(profiling_enabled({"OPENPOWER_PROFILE": "true"}))
        self.assertFalse(profiling_enabled({"OPENPOWER_PROFILE": "0"}))


if __name__ == "__main__":
    unittest.main()
