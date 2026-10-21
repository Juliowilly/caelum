"""Kivy app entry point.

Desktop preview:  python -m caelum.kivy_ui [--time 2026-10-21T19:30] [--size 1600x900]
                                           [--screenshot sky.png]
"""

import argparse
import datetime
import os

os.environ.setdefault('KIVY_NO_ARGS', '1')   # we parse our own arguments


def _parse_args(argv=None):
    p = argparse.ArgumentParser(prog='caelum-mobile')
    p.add_argument('--time', help='fixed UTC time, ISO format (preview the sky at that moment)')
    p.add_argument('--facing', type=float, help='initial facing azimuth in degrees')
    p.add_argument('--size', default='1600x900', help='desktop window size WxH')
    p.add_argument('--screenshot', help='render once, save PNG to this path, then quit')
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    from kivy.config import Config
    from kivy.utils import platform
    if platform not in ('android', 'ios'):
        w, h = args.size.lower().split('x')
        Config.set('graphics', 'width', w)
        Config.set('graphics', 'height', h)

    from kivy.app import App
    from kivy.clock import Clock, mainthread
    from kivy.core.window import Window

    from ..core import config as core_config
    from .sensors import Compass, request_location
    from .sky_view import SkyView

    class CaelumApp(App):
        title = 'Caelum'

        def build(self):
            if platform in ('android', 'ios'):
                core_config.set_config_dir(self.user_data_dir)
            self.cfg = core_config.load_config()
            if args.facing is not None:
                self.cfg['facing'] = args.facing
            Window.clearcolor = (0, 0, 0, 1)
            when = datetime.datetime.fromisoformat(args.time) if args.time else None
            self.compass = Compass()
            self.view = SkyView(self.cfg, compass=self.compass, time_override=when)
            request_location(self._on_location)
            if args.screenshot:
                Clock.schedule_once(self._screenshot, 1.5)
            return self.view

        @mainthread
        def _on_location(self, lat, lon):
            self.cfg['latitude'], self.cfg['longitude'] = round(lat, 4), round(lon, 4)
            core_config.save_config(self.cfg)
            self.view.redraw()

        def _screenshot(self, _dt):
            self.view.redraw()
            self.view.export_to_png(args.screenshot)
            self.stop()

        def on_pause(self):
            self.compass.stop()
            return True

        def on_resume(self):
            self.view.compass = self.compass = Compass()
            self.view.redraw()

        def on_stop(self):
            self.compass.stop()

    CaelumApp().run()
