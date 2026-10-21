"""Entry point for the GTK desktop overlay."""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from .window import SkyTracker  # noqa: E402


def main():
    win = SkyTracker()
    win.connect('destroy', Gtk.main_quit)
    Gtk.main()
