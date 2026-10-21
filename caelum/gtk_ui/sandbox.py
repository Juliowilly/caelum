"""Sandbox awareness: plain install (.deb / pip / source) vs Snap vs Flatpak.

Inside Flatpak the host's dconf and ~/.config/autostart are out of reach, so wallpaper and
autostart go through the XDG desktop portals instead. Snap allows dconf writes through its
`gsettings` plug and handles autostart itself (snapcraft.yaml `autostart:`).
"""

import os

from gi.repository import Gio, GLib

APP_ID = 'io.github.juliowilly.Caelum'

_PORTAL_BUS  = 'org.freedesktop.portal.Desktop'
_PORTAL_PATH = '/org/freedesktop/portal/desktop'


def kind():
    """'flatpak', 'snap' or None."""
    if os.path.exists('/.flatpak-info'):
        return 'flatpak'
    if os.environ.get('SNAP_NAME'):
        return 'snap'
    return None


def cache_dir():
    if kind() == 'snap':
        # Revision-independent, so the wallpaper path survives snap refreshes
        return os.path.join(os.environ['SNAP_USER_COMMON'], '.cache')
    return os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache')


def _portal_call(interface, method, params, fd_list=None):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return bus.call_with_unix_fd_list_sync(
        _PORTAL_BUS, _PORTAL_PATH, interface, method, params,
        None, Gio.DBusCallFlags.NONE, -1, fd_list, None)


def set_wallpaper(path, mode):
    """Show the PNG at `path` as desktop background and/or lock screen.

    mode: 'background' | 'lockscreen' | 'both'. Call from the main thread.
    """
    if kind() == 'flatpak':
        with open(path, 'rb') as f:
            fds = Gio.UnixFDList.new_from_array([os.dup(f.fileno())])
            _portal_call('org.freedesktop.portal.Wallpaper', 'SetWallpaperFile',
                         GLib.Variant('(sha{sv})', ('', 0, {
                             'show-preview': GLib.Variant('b', False),
                             'set-on': GLib.Variant('s', mode),
                         })), fds)
        return
    uri = GLib.filename_to_uri(path, None)
    if mode in ('background', 'both'):
        _set_gnome_keys('org.gnome.desktop.background', ('picture-uri', 'picture-uri-dark'), uri)
    if mode in ('lockscreen', 'both'):
        _set_gnome_keys('org.gnome.desktop.screensaver', ('picture-uri',), uri)


def _set_gnome_keys(schema_id, keys, value):
    # Gio.Settings aborts the process on an unknown schema/key, so look them up first
    source = Gio.SettingsSchemaSource.get_default()
    schema = source.lookup(schema_id, True) if source else None
    if schema is None:
        return
    settings = Gio.Settings.new(schema_id)
    for key in keys:
        if schema.has_key(key):
            settings.set_string(key, value)
    Gio.Settings.sync()


# ─── Flatpak autostart via the Background portal ─────────────────────────────

def _flatpak_autostart_marker():
    # The host's ~/.config/autostart is invisible inside the sandbox; remember the choice ourselves
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'caelum', 'autostart-enabled')


def flatpak_set_autostart(enabled):
    _portal_call('org.freedesktop.portal.Background', 'RequestBackground',
                 GLib.Variant('(sa{sv})', ('', {
                     'reason': GLib.Variant('s', 'Show the live sky when you log in'),
                     'autostart': GLib.Variant('b', enabled),
                     'commandline': GLib.Variant('as', ['caelum']),
                 })))
    marker = _flatpak_autostart_marker()
    if enabled:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        open(marker, 'w').close()
    elif os.path.exists(marker):
        os.remove(marker)


def flatpak_autostart_enabled():
    return os.path.exists(_flatpak_autostart_marker())
