"""GNOME session autostart entry."""

import os
import shutil
import sys

from . import sandbox

# ─── Autostart ───────────────────────────────────────────────────────────────

_AUTOSTART_PATH = os.path.expanduser('~/.config/autostart/caelum.desktop')
# Directory containing the caelum package (the checkout root when run from source)
_PKG_PARENT     = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _launch_lines():
    """Exec (and Path, when running from source) lines for the .desktop entry."""
    if sandbox.kind() == 'snap':
        # snapd swaps the command for the snap's own launcher (snapcraft.yaml `autostart:`)
        return 'Exec=caelum\n'
    exe = shutil.which('caelum')
    if exe:
        return f'Exec={exe}\n'
    return f'Exec={sys.executable} -m caelum\nPath={_PKG_PARENT}\n'

# Inside a snap HOME is ~/snap/caelum/<rev>, which is where snapd looks for autostart entries
def set_autostart(enabled):
    if sandbox.kind() == 'flatpak':
        sandbox.flatpak_set_autostart(enabled)
        return
    if enabled:
        os.makedirs(os.path.dirname(_AUTOSTART_PATH), exist_ok=True)
        with open(_AUTOSTART_PATH, 'w') as f:
            f.write(
                '[Desktop Entry]\nType=Application\nName=Caelum\n'
                f'{_launch_lines()}Icon=io.github.juliowilly.Caelum\nHidden=false\n'
                'NoDisplay=false\nX-GNOME-Autostart-enabled=true\n'
            )
    elif os.path.exists(_AUTOSTART_PATH):
        os.remove(_AUTOSTART_PATH)

def autostart_enabled():
    if sandbox.kind() == 'flatpak':
        return sandbox.flatpak_autostart_enabled()
    return os.path.exists(_AUTOSTART_PATH)
