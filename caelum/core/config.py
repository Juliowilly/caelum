"""Configuration: defaults, load/save (XDG config dir)."""

import json
import os
import shutil

from .i18n import _set_lang

_CONFIG_DIR = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'),
                           'caelum')
CONFIG_PATH = os.path.join(_CONFIG_DIR, 'config.json')
# Before packaging, config.json lived next to desktop_tracker.py in the source checkout
_LEGACY_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'config.json')

def set_config_dir(path):
    """Store config.json in `path` instead of the XDG dir (mobile apps have their own data dir)."""
    global _CONFIG_DIR, CONFIG_PATH
    _CONFIG_DIR = path
    CONFIG_PATH = os.path.join(path, 'config.json')

DEFAULT_CONFIG = {
    # Until the user sets their own: Lomé's public city-centre point, at the same ~1 km precision
    # Caelum uses for every online lookup (never a precise address)
    "latitude": 6.14,
    "longitude": 1.22,
    "timezone_offset": 0,
    "aster_scale": 1.0,
    "cards": {
        "clock": True,
        "location": True,
        "sunrise_sunset": True,
        "solar_noon": True,
        "moon_phase": True,
        "moon_rise_set": True,
        "daylight_remaining": True,
        "cloud_cover": True
    },
    "clean_mode": False,
    "click_through": True,
    "opaque_sky": True,
    "keep_above": False,
    "sticky": True,
    "show_constellations": True,
    "landscape": "plain",          # plain | mountains | sea | hills (drawn) | none
    "show_compass": True,
    "show_horizon_labels": True,
    "show_rainbow": True,
    "show_info_cards": False,
    "show_weekly_forecast": True,
    "language": "auto",
    "lockscreen_export": "off",
    "facing": 180.0,
    "compass_port": "",
    "app_enabled": True
}

# ─── Config ──────────────────────────────────────────────────────────────────

def _migrate_legacy_config():
    """Copy a pre-packaging config.json into the XDG config dir on first run."""
    if os.path.exists(CONFIG_PATH) or not os.path.exists(_LEGACY_CONFIG_PATH):
        return
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        shutil.copy2(_LEGACY_CONFIG_PATH, CONFIG_PATH)
    except OSError:
        pass

def _upgrade(cfg):
    """Settings saved by older versions, in today's terms."""
    # 1.3 → 1.4: the silhouette switch became a landscape choice
    if 'landscape' not in cfg and cfg.get('show_silhouette') is False:
        cfg['landscape'] = 'none'
    # 1.5.1 → 1.6: GNOME's lock screen shows the desktop wallpaper (blurred) and ignores its own
    # picture, so the wallpaper export is on ('both') or off. "Lock screen only" never showed
    # anything: it stays off rather than replacing the user's desktop wallpaper.
    if cfg.get('lockscreen_export') not in (None, 'off'):
        cfg['lockscreen_export'] = 'both' if cfg['lockscreen_export'] in ('background', 'both') else 'off'


def load_config():
    _migrate_legacy_config()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            _upgrade(cfg)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            for k, v in DEFAULT_CONFIG['cards'].items():
                if k not in cfg.get('cards', {}):
                    cfg.setdefault('cards', {})[k] = v
            for k in [k for k in list(cfg) if k not in DEFAULT_CONFIG]:
                del cfg[k]
            _set_lang(cfg.get('language', 'auto'))
            return cfg
        except Exception:
            pass
    cfg = dict(DEFAULT_CONFIG)
    cfg['cards'] = dict(DEFAULT_CONFIG['cards'])
    _set_lang('auto')
    return cfg

def save_config(cfg):
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)
