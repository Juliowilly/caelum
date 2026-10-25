import json
import os
import tempfile
import unittest
from unittest import mock

from caelum.gtk_ui import landscape

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


class PersonalLandscapeTest(unittest.TestCase):
    """The user's own landscapes, from their data folder, join the shipped ones."""

    def catalog(self, meta):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'caelum', 'landscapes'))
            with open(os.path.join(d, 'caelum', 'landscapes', 'landscapes.json'), 'w') as f:
                json.dump(meta, f)
            with mock.patch.object(landscape.sandbox, 'data_dir', return_value=d):
                return landscape.available(), landscape.personal()

    def test_listed_after_the_shipped_ones(self):
        names, own = self.catalog({'yard': {'top': 28, 'bottom': 40, 'south': 0.25, 'label': 'My yard'}})
        self.assertEqual(names[-1], 'yard')
        self.assertIn('plain', names)
        self.assertEqual(own, [('yard', 'My yard')])

    def test_cannot_replace_a_shipped_or_reserved_name(self):
        names, own = self.catalog({'plain': {}, 'hills': {}, 'none': {}, '../x': {}, 'ok': 'not a dict'})
        self.assertEqual(own, [])
        self.assertNotIn('hills', names)

    def test_no_personal_folder(self):
        with mock.patch.object(landscape.sandbox, 'data_dir', return_value='/nonexistent'):
            self.assertEqual(landscape.personal(), [])
            self.assertEqual(set(landscape.available()), {'plain', 'mountains', 'sea'})


if __name__ == '__main__':
    unittest.main()
