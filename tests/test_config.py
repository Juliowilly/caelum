import unittest

from caelum.core.config import _upgrade


class UpgradeTest(unittest.TestCase):
    def export(self, old):
        cfg = {'lockscreen_export': old}
        _upgrade(cfg)
        return cfg['lockscreen_export']

    def test_wallpaper_export_is_on_or_off(self):
        self.assertEqual(self.export('background'), 'both')
        self.assertEqual(self.export('both'), 'both')
        self.assertEqual(self.export('off'), 'off')
        # "Lock screen only" never showed anything on GNOME: don't take over the desktop wallpaper
        self.assertEqual(self.export('lockscreen'), 'off')
        self.assertEqual(self.export('nonsense'), 'off')

    def test_silhouette_switch_became_a_landscape(self):
        cfg = {'show_silhouette': False}
        _upgrade(cfg)
        self.assertEqual(cfg['landscape'], 'none')


if __name__ == '__main__':
    unittest.main()
