import math
import unittest

from caelum.core.orientation import heading_from_sensors

# Earth's field points north and (in the northern hemisphere) down; magnitude ~45 µT
DIP = math.radians(30)


def field(north, up):
    """Magnetic field vector in device axes, given the device-axis directions of north and up."""
    h, v = 45 * math.cos(DIP), -45 * math.sin(DIP)
    return tuple(h * n + v * u for n, u in zip(north, up))


class HeadingTest(unittest.TestCase):
    def check(self, north_dir, up_dir, expected):
        accel = tuple(9.81 * u for u in up_dir)
        got = heading_from_sensors(accel, field(north_dir, up_dir))
        self.assertIsNotNone(got)
        diff = (got - expected + 180) % 360 - 180
        self.assertAlmostEqual(diff, 0, places=6, msg=f'got {got}, want {expected}')

    def test_upright_portrait_camera_facing_each_direction(self):
        # Upright portrait: up = +y; the back camera (-z) looks at the horizon.
        for az in (0, 45, 90, 180, 270, 315):
            a = math.radians(az)
            # Camera points at azimuth `az`, so -z = that direction; north is rotated by -az
            # in the horizontal device plane spanned by -z (forward) and +x (right).
            north = (-math.sin(a), 0.0, -math.cos(a))
            self.check(north, (0, 1, 0), az)

    def test_upright_landscape(self):
        # Landscape (rotated left): up = +x; camera faces east.
        a = math.radians(90)
        north = (0.0, math.sin(a), -math.cos(a))
        self.check(north, (1, 0, 0), 90)

    def test_flat_on_table_uses_top_edge(self):
        # Flat, screen up: up = +z; top edge (+y) points west.
        self.check((1, 0, 0), (0, 0, 1), 270)

    def test_degenerate_readings(self):
        self.assertIsNone(heading_from_sensors((0, 0, 0), (10, 0, 0)))
        self.assertIsNone(heading_from_sensors((0, 9.8, 0), (0, 20, 0)))


if __name__ == '__main__':
    unittest.main()
