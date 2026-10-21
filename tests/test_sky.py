import unittest

from caelum.core.astronomy import phase_index
from caelum.core.sky import set_facing, sky_to_screen

W, H = 1000, 500


class ProjectionTest(unittest.TestCase):
    def setUp(self):
        set_facing(180.0)

    def test_centre_and_edges(self):
        self.assertAlmostEqual(sky_to_screen(10, 180, W, H)[0], W * 0.5)
        self.assertAlmostEqual(sky_to_screen(10, 60, W, H)[0], W * 0.06)    # 120° left
        self.assertAlmostEqual(sky_to_screen(10, 300, W, H)[0], W * 0.94)   # 120° right

    def test_outside_field_of_view_is_hidden(self):
        self.assertIsNone(sky_to_screen(10, 0, W, H))      # directly behind
        self.assertIsNone(sky_to_screen(10, 59, W, H))
        self.assertIsNone(sky_to_screen(10, 301, W, H))

    def test_below_horizon_is_hidden(self):
        self.assertIsNone(sky_to_screen(-1, 180, W, H))


class PhaseNameTest(unittest.TestCase):
    def test_nearest_named_phase(self):
        cases = {0.0: 0, 0.06: 0, 0.07: 1, 0.25: 2, 0.36: 3, 0.5: 4, 0.75: 6, 0.95: 0}
        for phase, idx in cases.items():
            self.assertEqual(phase_index(phase), idx, msg=f'phase {phase}')


if __name__ == '__main__':
    unittest.main()
