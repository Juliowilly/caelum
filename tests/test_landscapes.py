import json
import os
import unittest

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'caelum', 'data', 'landscapes')


class LandscapeDataTest(unittest.TestCase):
    """The shipped landscapes are complete and their geometry covers the screen."""

    def setUp(self):
        with open(os.path.join(DIR, 'landscapes.json')) as f:
            self.meta = json.load(f)

    def test_the_three_landscapes_are_listed(self):
        self.assertEqual(set(self.meta), {'plain', 'mountains', 'sea'})

    def test_files_exist(self):
        for name in self.meta:
            for suffix in ('.jpg', '-mask.png'):
                self.assertTrue(os.path.isfile(os.path.join(DIR, name + suffix)), name + suffix)

    def test_band_reaches_the_bottom_of_the_screen(self):
        # The screen bottom is 0.28 H below the horizon at 0.66 H per 90°: about 38°
        for name, m in self.meta.items():
            self.assertGreaterEqual(m['bottom'], 0.28 / 0.66 * 90, name)
            self.assertTrue(0 < m['top'] < 60, name)
            self.assertTrue(0 <= m['south'] < 1, name)
            self.assertEqual(m['license'], 'CC0-1.0', name)


if __name__ == '__main__':
    unittest.main()
