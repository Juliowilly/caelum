"""Entry point for the GTK desktop overlay."""

import argparse
import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib  # noqa: E402

from .. import __version__  # noqa: E402
from .window import SkyTracker  # noqa: E402

APP_ID = 'io.github.juliowilly.Caelum'
# Icon in the source checkout; installed packages get it from the icon theme instead
_SOURCE_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', f'{APP_ID}.svg')


def _set_app_identity():
    """Name and icon for every window; the prgname doubles as the Wayland app_id / X11 WM_CLASS,
    which GNOME matches against the installed .desktop file."""
    GLib.set_prgname(APP_ID)
    GLib.set_application_name('Caelum')
    if Gtk.IconTheme.get_default().has_icon(APP_ID):
        Gtk.Window.set_default_icon_name(APP_ID)
    elif os.path.exists(_SOURCE_ICON):
        try:
            Gtk.Window.set_default_icon_from_file(_SOURCE_ICON)
        except GLib.Error:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog='caelum', description='Live sky overlay for the desktop.')
    parser.add_argument('-V', '--version', action='version', version=f'Caelum {__version__}')
    parser.parse_args(argv)
    _set_app_identity()
    win = SkyTracker()
    win.connect('destroy', Gtk.main_quit)
    Gtk.main()
