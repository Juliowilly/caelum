import unittest

from caelum.core.astronomy import phase_index
from caelum.core.sky import (
    low_clouds, plane_to_sky,
    band_slots, cloud_layers, mid_sheet, naked_eye_visibility, opaque_cover, opaque_sky, overcast_deck, set_facing, sky_to_screen, veil_transmission,
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

    def test_deck_only_for_thick_closed_cloud(self):
        self.assertEqual(overcast_deck(_clouds(60, low=60)), 0.0)
        self.assertEqual(overcast_deck(_clouds(100, high=100)), 0.0)   # cirrus never closes
        self.assertEqual(overcast_deck(_clouds(100, low=100)), 1.0)
        self.assertTrue(0.0 < overcast_deck(_clouds(80, low=80)) < 1.0)

    def test_altostratus_sheet(self):
        self.assertEqual(mid_sheet(_clouds(50, mid=50)), 0.0)
        self.assertEqual(mid_sheet(_clouds(100, mid=100)), 1.0)

    def test_band_covers_the_body_as_often_as_the_sky(self):
        # Slots are ~one cloud wide, so the share of slots shown = share of time covered
        for cov in (0, 30, 60, 100):
            shown = len(band_slots('low', cov, 400.0, 0.1)) / 4000
            self.assertAlmostEqual(shown, cov / 100, delta=0.03, msg=f'{cov}%')

    def test_cover_change_keeps_existing_clouds_in_place(self):
        less = set(band_slots('low', 30, 4.0, 0.14))
        more = set(band_slots('low', 60, 4.0, 0.14))
        self.assertTrue(less <= more)


class LowCloudLayerTest(unittest.TestCase):
    def test_projection(self):
        el, az = plane_to_sky(0.0, 1.5, 1.5)          # 1.5 km north, 1.5 km up
        self.assertAlmostEqual(el, 45.0)
        self.assertAlmostEqual(az, 0.0)
        self.assertAlmostEqual(plane_to_sky(3.0, 0.0, 1.5)[1], 90.0)   # east

    def test_sight_lines_blocked_as_often_as_the_cover(self):
        import random
        rng = random.Random(7)
        for cov in (20, 50, 80):
            hits = n = 0
            for k in range(6):                         # several wind positions
                field = low_clouds(cov, (k * 7.3, k * -4.1), max_km=8.0)
                for _ in range(400):
                    px, py = rng.uniform(-5, 5), rng.uniform(-5, 5)
                    hits += any((x - px) ** 2 + (y - py) ** 2 < (s / 2) ** 2
                                for x, y, s, _t, _i in field)
                    n += 1
            self.assertAlmostEqual(hits / n, cov / 100, delta=0.06, msg=f'{cov}%')

    def test_more_cover_keeps_existing_clouds(self):
        less = {c[4] for c in low_clouds(30, (0.0, 0.0))}
        more = {c[4] for c in low_clouds(60, (0.0, 0.0))}
        self.assertTrue(less <= more)


class PlanetVisibilityTest(unittest.TestCase):
    def test_no_planets_in_daylight(self):
        for mag in (-4.0, -2.2, -1.0, 0.0, 0.7):          # Venus … Saturn
            self.assertEqual(naked_eye_visibility(mag, 30.0), 0.0)
            self.assertEqual(naked_eye_visibility(mag, 10.0), 0.0)

    def test_twilight_order(self):
        # Around sunset Venus is already showing; the fainter planets come later
        self.assertGreater(naked_eye_visibility(-4.0, 0.0), 0.0)
        self.assertEqual(naked_eye_visibility(0.7, 0.0), 0.0)
        self.assertEqual(naked_eye_visibility(-2.2, -3.5), 1.0)
        self.assertEqual(naked_eye_visibility(0.7, -8.0), 1.0)


class OpaqueSkyTest(unittest.TestCase):
    CLEAR = dict(total=0, low=0, mid=0, high=0)
    OVERCAST = dict(total=100, low=100, mid=0, high=0)

    @staticmethod
    def lum(c):
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def test_brightens_with_the_sun(self):
        prev = -1
        for el in (-18, -12, -6, -2, 2, 8, 20, 60):
            zen = opaque_sky(el, self.CLEAR, 0.0)[0]
            self.assertGreater(self.lum(zen), prev, el)
            prev = self.lum(zen)

    def test_clear_day_is_blue_with_paler_horizon(self):
        zen, hor, g_top, g_bot = opaque_sky(45, self.CLEAR, 0.0)
        self.assertGreater(zen[2], zen[0] * 2)
        self.assertGreater(self.lum(hor), self.lum(zen))
        self.assertLess(self.lum(g_top), self.lum(hor))
        self.assertLess(self.lum(g_bot), self.lum(g_top))

    def test_night_is_near_black(self):
        for c in opaque_sky(-30, self.CLEAR, 0.0):
            self.assertLess(max(c), 0.06)

    def test_overcast_day_is_grey(self):
        zen = opaque_sky(45, self.OVERCAST, 0.0)[0]
        self.assertLess(max(zen) - min(zen), 0.15)
        self.assertGreater(self.lum(zen), 0.4)

    def test_full_moon_lifts_the_night(self):
        dark = opaque_sky(-30, self.CLEAR, 0.0)[0]
        moon = opaque_sky(-30, self.CLEAR, 1.0)[0]
        self.assertGreater(self.lum(moon), self.lum(dark))
        self.assertLess(max(moon), 0.12)


if __name__ == '__main__':
    unittest.main()
