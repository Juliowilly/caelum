import unittest

from caelum.core.astronomy import phase_index
from caelum.core.sky import (
    body_occluders, cloud_layers, opaque_cover, set_facing, sky_to_screen, veil_transmission,
)

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


def _clouds(total, low=0, mid=0, high=0):
    return {'total': total, 'low': low, 'mid': mid, 'high': high}


class CloudOpticsTest(unittest.TestCase):
    def test_total_without_layers_counts_as_mid(self):
        self.assertEqual(cloud_layers(_clouds(40)), (0, 40, 0))

    def test_broken_cloud_does_not_veil_the_sun(self):
        # Scattered/broken low cloud hides the sun only where a cloud is drawn
        self.assertEqual(veil_transmission(_clouds(60, low=60)), 1.0)
        self.assertEqual(veil_transmission(_clouds(50, mid=50)), 1.0)

    def test_cirrus_is_a_thin_veil(self):
        self.assertGreater(veil_transmission(_clouds(100, high=100)), 0.8)
        self.assertLess(opaque_cover(_clouds(100, high=100)), 0.25)

    def test_overcast_low_deck_hides_the_sun(self):
        self.assertLess(veil_transmission(_clouds(100, low=100)), 0.2)
        self.assertEqual(opaque_cover(_clouds(100, low=100)), 1.0)

    def test_body_covered_as_often_as_the_sky(self):
        for cov in (0, 30, 60, 100):
            hits = sum('low' in body_occluders(_clouds(cov, low=cov), seed)
                       for seed in range(2000))
            self.assertAlmostEqual(hits / 2000, cov / 100, delta=0.04, msg=f'{cov}%')
        self.assertEqual(body_occluders(_clouds(80, high=80), 1), set())


if __name__ == '__main__':
    unittest.main()
