import unittest

from src.client.ui.components.shared.gml_slide_transition import GMLSlideTransition


class GMLSlideTransitionTests(unittest.TestCase):
    def test_source_delay_and_linear_motion(self):
        slide = GMLSlideTransition(577.0, 577.0, 577.0)
        slide.begin(36.0, 10.0)

        self.assertEqual(slide.advance(10.25), 577.0)
        self.assertEqual(slide.advance(10.26), 577.0)
        self.assertEqual(slide.advance(10.51), 306.5)
        self.assertEqual(slide.advance(10.76), 36.0)
        self.assertFalse(slide.active)

    def test_reversing_mid_transition_starts_from_current_position(self):
        slide = GMLSlideTransition(577.0, 577.0, 577.0)
        slide.begin(36.0, 10.0)
        middle = slide.advance(10.51)
        self.assertEqual(middle, 306.5)

        slide.begin(577.0, 10.51)
        self.assertEqual(slide.advance(10.76), middle)
        self.assertEqual(slide.advance(11.02), 441.75)
        self.assertEqual(slide.advance(11.27), 577.0)
        self.assertFalse(slide.active)


if __name__ == "__main__":
    unittest.main()
