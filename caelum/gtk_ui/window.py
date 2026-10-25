"""Main transparent sky overlay window."""

import datetime
import glob
import math
import os
import random
import sys
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import cairo

from ..core.astronomy import (
    phase_index,
    _PLANET_MAG, _bv_to_rgb, _find_event, _find_moon_event, _get_star_positions,
    _ra_dec_to_alt_az, _solar_noon, moon_phase_age, moon_position,
    planet_positions, solar_position,
)
from ..core.catalog import _CONSTELLATIONS
from ..core.config import DEFAULT_CONFIG, load_config, save_config
from ..core.i18n import _PHASE_NAMES, _day_name, _fmt_date, _t
from ..core.sky import (
    _clamp, _cloud_palette, _lerp, _seg_dist, cloud_layers, get_facing, landscape_light,
    mid_sheet, moon_brightness, naked_eye_visibility, opaque_sky, overcast_deck, precip_intensity,
    rain_slant, set_facing, sky_color_adaptive, sky_to_screen,
    veil_transmission,
)
from ..core.weather import (
    _NO_CLOUDS, _WX_ACCENT, _WX_LABEL, fetch_met_norway, fetch_open_meteo, merge_weather,
)
from ..core import observed, snapstore
from ..core.net import coord, get_json
from .clouds import (
    _soft_puff, draw_altocumulus, draw_cirrus, draw_cumulus, draw_deck, draw_mid_sheet,
)
from . import sandbox
from .landscape import Landscape
from . import precip as wx
from .settings import SettingsDialog

# ─── Window ───────────────────────────────────────────────────────────────────

# Cloud drift across the view: degrees per second per m/s of surface wind
_CLOUD_DRIFT = {'low': 0.020, 'mid': 0.012, 'high': 0.007}
# Wind at low-cloud base relative to the surface wind
_LOW_WIND_FACTOR = 1.5

# Weather refresh intervals (s). Kept on the wall clock: GLib timers use the monotonic clock,
# which stops during suspend/hibernate, so a 1 h timer would still wait ~1 h after resume.
# radar frames every 5–10 min, airports 30–60; Settings → About states these intervals
_REFRESH = {'om': 15 * 60, 'met': 60 * 60, 'obs': 10 * 60}
_RETRY   = (15, 30, 60, 120, 300)   # back-off after a failed fetch (s)
_SLEPT   = 60   # wall time the monotonic clock missed beyond this → the system was asleep
# Explore mode (click-through on): seconds without pointer motion before the sky lets clicks through again
_EXPLORE_IDLE = 20

class SkyTracker(Gtk.Window):

    def __init__(self):
        super().__init__()
        self.cfg      = load_config()
        self._sunrise = self._sunset = self._s_noon = None
        self._max_el  = 0.0
        self._last_date    = None
        self._settings_win = None
        self._clouds           = dict(_NO_CLOUDS)
        self._last_weather_ts  = ''   # last merged ts; changes when either source updates
        self._last_om          = None # last Open-Meteo raw result
        self._last_met         = None # last MET Norway raw result
        self._last_obs         = None # (time, observed.observe result): the weather observed now
        self._om_fetching      = False
        self._met_fetching     = False
        self._obs_fetching     = False
        self._due   = {'om': 0.0, 'met': 0.0, 'obs': 0.0}   # wall time each source is next fetched
        self._fails = {'om': 0, 'met': 0, 'obs': 0}         # consecutive failed fetches per source
        self._clock = (time.time(), time.monotonic())
        self._export_pending = False            # export the wallpaper once fresh weather lands
        self._hover_const  = None
        self._star_screen_cache = {}
        self._mouse_x = self._mouse_y = -1
        self._gear_cx = self._gear_cy = 0
        self._selected_day       = None   # date string 'YYYY-MM-DD' of clicked weekly card
        self._selected_day_slots = []     # hourly slots for selected day (cached in _on_click)
        self._weekly_card_rects  = []     # [(date_str, x, y, w, h), ...]
        self._input_rects        = ()     # input region last applied (see _update_input_region)
        self._explore_until      = 0.0    # monotonic deadline of explore mode (whole sky takes input)
        self._exporting          = False  # rendering the wallpaper/lock-screen image
        self._landscapes         = {}     # name → Landscape (None if its files are missing)
        self._land_cache         = None   # (key, surface, y) of the relit landscape
        self._city_name          = None   # reverse-geocoded city name
        self._moon_limb_angle    = 0.0    # stored each frame for use in info card icon
        self._today_str          = datetime.date.today().isoformat()
        self._astro_cache        = None   # (sun_el, sun_az, m_el, m_az, phase, age, m_bright)
        self._astro_cache_t      = 0.0    # time.monotonic() of last astro recalc
        self._cmp_cx  = 62
        self._cmp_cy  = 95
        self._cmp_r   = 46
        self._insets  = (0, 0, 0, 0)   # screen edges under the Windows taskbar: left, top, right, bottom
        self._moonrise = self._moonset = None
        self._meteors  = []
        self._storm    = wx.Storm()
        self._update   = None    # version of a newer snap revision installed while running
        self._waiting  = None    # version of a newer snap waiting in the store (installs on close)
        # Cloud layers' scroll offsets (screen widths); start where the wind left them
        self._drift   = {layer: time.time() / 600.0 * 0.618 % 4.0 for layer in _CLOUD_DRIFT}
        self._drift_t = time.monotonic()
        # Low cumulus layer position (km east, km north); start somewhere new each run
        self._low_offset = [time.time() * 0.0137 % 50.0, time.time() * 0.0091 % 50.0]
        self._cloud_surf = self._cloud_key = None   # cached cloud layer (see _draw_clouds)
        self._cloud_t    = 0.0
        self._hw_heading   = None   # live heading from hardware sensor (degrees)
        self._has_compass  = False
        self._compass_dev  = None   # IIO sysfs device path
        self._detect_compass()

        self._setup_window()
        self._refresh_day()
        self._fetch_weather_async()
        self._fetch_city_name()
        GLib.timeout_add(100,              self._tick)
        GLib.timeout_add_seconds(5,        self._watch_weather)
        GLib.timeout_add_seconds(60,       self._check_update)
        if sandbox.snap_identity():
            GLib.timeout_add_seconds(90, lambda: self._check_store() and False)
            GLib.timeout_add_seconds(6 * 3600, self._check_store)
        GLib.timeout_add_seconds(60,       self._export_lockscreen_bg)
        try:
            Gio.NetworkMonitor.get_default().connect('network-changed', self._on_network_changed)
        except Exception:
            pass
        if self._has_compass:
            GLib.timeout_add(500, self._poll_compass)

    # ── Hardware compass ─────────────────────────────────────────────────────

    def _detect_compass(self):
        """Probe for a magnetometer — IIO sysfs, D-Bus, or USB serial."""
        # Close any previous serial connection
        if hasattr(self, '_serial_compass') and self._serial_compass:
            try:
                self._serial_compass.close()
            except Exception:
                pass
            self._serial_compass = None

        self._has_compass  = False
        self._compass_dev  = None
        self._compass_src  = None   # 'iio' | 'dbus' | 'serial'
        self._compass_status = 'Not detected'

        # Method 1: IIO sysfs (works without any daemon)
        for dev in glob.glob('/sys/bus/iio/devices/iio:device*'):
            xf = os.path.join(dev, 'in_magn_x_raw')
            yf = os.path.join(dev, 'in_magn_y_raw')
            if os.path.exists(xf) and os.path.exists(yf):
                self._compass_dev    = dev
                self._has_compass    = True
                self._compass_src    = 'iio'
                self._compass_status = 'IIO sensor active'
                return

        # Method 2: iio-sensor-proxy via D-Bus
        try:
            import dbus
            bus  = dbus.SystemBus()
            prox = bus.get_object('net.hadess.SensorProxy', '/net/hadess/SensorProxy')
            dbus.Interface(prox, 'net.hadess.SensorProxy').ClaimCompass()
            self._dbus_sensor_proxy = prox
            self._has_compass    = True
            self._compass_src    = 'dbus'
            self._compass_status = 'iio-sensor-proxy active'
            return
        except Exception:
            pass

        # Method 3: external USB/serial compass (Arduino, USB dongle, etc.)
        port = self.cfg.get('compass_port', '').strip()
        if port:
            try:
                import serial as _serial
                ser = _serial.Serial(port, baudrate=9600, timeout=1)
                # Quick read to verify it responds with a float heading
                line = ser.readline().decode(errors='ignore').strip()
                float(line)   # raises if not a number
                self._serial_compass = ser
                self._has_compass    = True
                self._compass_src    = 'serial'
                self._compass_status = f'Serial: {port}'
            except ImportError:
                self._compass_status = 'pyserial not installed (pip3 install pyserial)'
            except Exception as e:
                self._compass_status = f'Serial error: {e}'

    def _poll_compass(self):
        """Read compass heading; called every 500 ms via GLib timer."""
        if not self._has_compass:
            return False
        def _work():
            hdg = None
            src = getattr(self, '_compass_src', None)
            if src == 'iio' and self._compass_dev:
                try:
                    x  = float(open(f'{self._compass_dev}/in_magn_x_raw').read())
                    y  = float(open(f'{self._compass_dev}/in_magn_y_raw').read())
                    sf = os.path.join(self._compass_dev, 'in_magn_x_scale')
                    sc = float(open(sf).read()) if os.path.exists(sf) else 1.0
                    hdg = (math.degrees(math.atan2(-y * sc, x * sc)) + 360) % 360
                except Exception:
                    pass
            elif src == 'dbus' and hasattr(self, '_dbus_sensor_proxy'):
                try:
                    import dbus
                    props = dbus.Interface(self._dbus_sensor_proxy,
                                          'org.freedesktop.DBus.Properties')
                    hdg = float(props.Get('net.hadess.SensorProxy.Compass',
                                         'CompassHeading'))
                except Exception:
                    pass
            elif src == 'serial' and hasattr(self, '_serial_compass'):
                try:
                    line = self._serial_compass.readline().decode(
                        errors='ignore').strip()
                    if line:
                        hdg = float(line) % 360
                except Exception:
                    pass
            if hdg is not None:
                GLib.idle_add(self._apply_heading, hdg)
        threading.Thread(target=_work, daemon=True).start()
        return True

    def _apply_heading(self, hdg):
        self._hw_heading = hdg
        return False

    # ── Window setup ─────────────────────────────────────────────────────────

    def _setup_window(self):
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        # Windows draws see-through GTK windows as layered windows, which show nothing once the
        # sky is a child of the desktop's icon layer
        if visual and sys.platform != 'win32':
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        if self.cfg.get('sticky', True):
            self.stick()
        if self.cfg.get('keep_above', False):
            self.set_keep_above(True)

        self.da = Gtk.DrawingArea()
        self.da.connect('draw', self._on_draw)
        self.da.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        self.da.connect('motion-notify-event', self._on_motion)
        self.add(self.da)

        self.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.set_can_focus(True)
        self.connect('key-press-event', self._on_key)
        self.connect('button-press-event', self._on_click)

        self._win32 = None
        if sys.platform == 'win32':
            self._setup_windows_desktop()
        self.show_all()
        GLib.idle_add(self._force_fullscreen)
        GLib.timeout_add(500, self._force_fullscreen)

    def _force_fullscreen(self):
        display = self.get_screen().get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor:
            geo = monitor.get_geometry()
            self.move(geo.x, geo.y)
            self.resize(geo.width, geo.height)
        if self._win32:
            self._place_on_desktop()
        return False

    # ── Windows desktop ──────────────────────────────────────────────────────

    def _setup_windows_desktop(self):
        """Windows has no desktop window type: the sky goes behind the icons (see win32.py),
        and a tray icon opens Settings, since the gear can't be clicked there."""
        import atexit
        from . import win32
        self._win32        = win32
        self._placed_for   = None    # click_through value the window was placed for
        self._behind_icons = False
        self._tray         = self._make_tray()
        GLib.timeout_add_seconds(5, self._update_insets)   # the taskbar can move or auto-hide
        # GTK paints at the size it asked for: ask for the whole screen before the first show
        self.set_default_size(*win32.primary_size())
        atexit.register(self._leave_desktop)

    def _place_on_desktop(self):
        want = self.cfg.get('click_through', True)
        self._placed_for = want
        try:
            behind = self._win32.place_sky(self._win32.hwnd_of(self.get_window()), want)
        except Exception as e:
            print(f'Caelum: could not place the sky on the desktop: {e}', file=sys.stderr)
            return
        if self._behind_icons and not behind:
            self._win32.restore_desktop()
        self._behind_icons = behind
        alloc = self.da.get_allocation()
        print(f'Caelum: GTK draws {alloc.width}x{alloc.height}', file=sys.stderr, flush=True)
        self._update_insets()

    def _update_insets(self):
        """Keep the gear, compass and forecast off the taskbar: the sky covers the whole screen."""
        try:
            edges, screen_w = self._win32.taskbar_edges()
        except Exception as e:
            print(f'Caelum: no taskbar edges: {e}', file=sys.stderr, flush=True)
            return True
        width = self.da.get_allocation().width
        k = width / screen_w if width > 1 and screen_w else 1.0   # Windows pixels → GTK pixels
        insets = tuple(int(round(e * k)) for e in edges)
        if insets != self._insets:
            print(f'Caelum: taskbar edges {edges} (screen {screen_w} px) → {insets} in GTK pixels',
                  file=sys.stderr, flush=True)
            self._insets = insets
            self.da.queue_draw()
        return True

    def _leave_desktop(self):
        """On exit: take the sky off the icon layer so the user's wallpaper shows again."""
        if self._behind_icons:
            self.hide()
            self._win32.restore_desktop()
            self._behind_icons = False

    def _make_tray(self):
        tray  = Gtk.StatusIcon()
        icons = Gtk.Window.get_default_icon_list()
        if icons:
            tray.set_from_pixbuf(icons[0])
        else:
            tray.set_from_icon_name('weather-clear')
        tray.set_tooltip_text('Caelum')
        tray.connect('activate', lambda _i: self._open_settings())
        tray.connect('popup-menu', self._on_tray_menu)
        return tray

    def _on_tray_menu(self, tray, button, when):
        menu = Gtk.Menu()
        for label, action in ((_t('Settings'), self._open_settings),
                              (_t('Clean Mode  (Ctrl+H)'), self._toggle_clean),
                              (_t('Quit Caelum'), Gtk.main_quit)):
            item = Gtk.MenuItem(label=label)
            item.connect('activate', lambda _m, a=action: a())
            menu.append(item)
        menu.show_all()
        self._tray_menu = menu    # keep it alive while it is open
        menu.popup(None, None, Gtk.StatusIcon.position_menu, tray, button, when)

    # ── Day data ─────────────────────────────────────────────────────────────

    def _refresh_day(self):
        self._last_date  = datetime.date.today()   # prevent re-entry from _tick
        self._today_str  = self._last_date.isoformat()
        cfg = self.cfg
        lat = cfg['latitude']; lon = cfg['longitude']; tz = cfg['timezone_offset']
        today = self._last_date
        def _work():
            sunrise  = _find_event(lat, lon, today, tz, 'rise')
            sunset   = _find_event(lat, lon, today, tz, 'set')
            s_noon, max_el = _solar_noon(lat, lon, today, tz)
            moonrise = _find_moon_event(lat, lon, today, tz, 'rise')
            moonset  = _find_moon_event(lat, lon, today, tz, 'set')
            def _apply():
                self._sunrise  = sunrise
                self._sunset   = sunset
                self._s_noon   = s_noon
                self._max_el   = max_el
                self._moonrise = moonrise
                self._moonset  = moonset
                self.da.queue_draw()
                return False
            GLib.idle_add(_apply)
        threading.Thread(target=_work, daemon=True).start()

    def _tick(self):
        if datetime.date.today() != self._last_date:
            self._refresh_day()
        self.da.queue_draw()
        return True

    # ── Weather ──────────────────────────────────────────────────────────────

    def _watch_weather(self):
        """Every 5 s: notice a resume from suspend/hibernate and fetch whatever is due."""
        wall, mono = time.time(), time.monotonic()
        slept = (wall - self._clock[0]) - (mono - self._clock[1]) > _SLEPT
        self._clock = (wall, mono)
        if slept:
            self._on_resume()
        if wall >= self._due['om']:
            self._fetch_om_async()
        if wall >= self._due['met']:
            self._fetch_met_async()
        if wall >= self._due['obs']:
            self._fetch_obs_async()
        return True

    def _check_update(self):
        """Every minute: has snapd installed a newer Caelum under us? Then ask for a restart."""
        update = sandbox.installed_update()
        if update != self._update:
            self._update = update
            self.da.queue_draw()
        return True

    def _check_store(self):
        """
        Every 6 h (snap only): is a newer Caelum waiting in the store? snapd won't install it while
        Caelum runs, and Caelum runs all session, so say so.
        """
        ident = sandbox.snap_identity()
        def work():
            version = snapstore.check(*ident)
            GLib.idle_add(self._set_waiting, version)
        threading.Thread(target=work, daemon=True).start()
        return True

    def _set_waiting(self, version):
        if version != self._waiting:
            self._waiting = version
            self.da.queue_draw()
        return False

    def _on_resume(self):
        """Back from sleep: refetch everything now and refresh the exported wallpaper."""
        self._due   = {'om': 0.0, 'met': 0.0, 'obs': 0.0}
        self._fails = {'om': 0, 'met': 0, 'obs': 0}
        self._astro_cache = None
        self._cloud_key   = None
        self._export_pending = True
        self._export_lockscreen_bg()   # sun/moon/stars right away; weather follows when fetched

    def _on_network_changed(self, monitor, available):
        """Network back (typical just after resume): retry failed sources without waiting."""
        if available:
            for src in ('om', 'met', 'obs'):
                if self._fails[src]:
                    self._due[src] = 0.0

    def _fetched(self, src, ok):
        """Schedule the next fetch of a source: normal interval, or back-off after a failure."""
        if ok:
            self._fails[src] = 0
            self._due[src] = time.time() + _REFRESH[src]
        else:
            self._due[src] = time.time() + _RETRY[min(self._fails[src], len(_RETRY) - 1)]
            self._fails[src] += 1

    def _weather_updated(self):
        # Observations go stale if the sources stop answering: the forecasts take over
        obs = self._last_obs[1] if self._last_obs and time.time() - self._last_obs[0] < 30 * 60 else None
        merged = merge_weather(self._last_om, self._last_met, obs)
        if merged is not None:
            self._apply_clouds(merged)
            if self._export_pending:
                self._export_pending = False
                self._export_lockscreen_bg()

    def _fetch_weather_async(self):
        """Fetch every source at once — used at startup and after location change."""
        self._fetch_om_async()
        self._fetch_met_async()
        self._fetch_obs_async()
        return True

    def _fetch_om_async(self):
        """Fetch Open-Meteo (current conditions); due every 15 min."""
        if self._om_fetching:
            return True
        self._om_fetching = True
        lat, lon = self.cfg['latitude'], self.cfg['longitude']
        def _work():
            result = fetch_open_meteo(lat, lon)
            GLib.idle_add(self._apply_om, result)
        threading.Thread(target=_work, daemon=True).start()
        return True

    def _apply_om(self, result):
        self._om_fetching = False
        self._fetched('om', result is not None)
        if result is not None:
            self._last_om = result
            self._weather_updated()
        return False

    def _fetch_met_async(self):
        """Fetch MET Norway (forecast + hourly); due every hour."""
        if self._met_fetching:
            return True
        self._met_fetching = True
        lat, lon = self.cfg['latitude'], self.cfg['longitude']
        def _work():
            result = fetch_met_norway(lat, lon)
            GLib.idle_add(self._apply_met, result)
        threading.Thread(target=_work, daemon=True).start()
        return True

    def _apply_met(self, result):
        self._met_fetching = False
        self._fetched('met', result is not None)
        if result is not None:
            self._last_met = result
            self._weather_updated()
        return False

    def _fetch_obs_async(self):
        """What is the weather actually doing? Ask the best observing sources; due every 10 min."""
        if self._obs_fetching:
            return True
        self._obs_fetching = True
        lat, lon = self.cfg['latitude'], self.cfg['longitude']
        def _work():
            GLib.idle_add(self._apply_obs, observed.observe(lat, lon))
        threading.Thread(target=_work, daemon=True).start()
        return True

    def _apply_obs(self, obs):
        # Parts nobody observes (or that failed) are None: the forecasts keep those
        self._obs_fetching = False
        self._fetched('obs', True)
        self._last_obs = (time.time(), obs)
        self._weather_updated()
        return False

    def _fetch_city_name(self):
        """Reverse-geocode current coordinates via Nominatim (once at startup)."""
        lat = self.cfg['latitude']
        lon = self.cfg['longitude']
        def _work():
            try:
                data = get_json(f"https://nominatim.openstreetmap.org/reverse"
                                f"?format=json&lat={coord(lat)}&lon={coord(lon)}&zoom=10",
                                timeout=8)
                addr = data.get('address', {})
                city = (addr.get('city') or addr.get('town') or
                        addr.get('village') or addr.get('municipality') or
                        addr.get('county') or '')
                country = addr.get('country', '')
                name = f"{city}, {country}" if city and country else city or country or ''
                GLib.idle_add(self._set_city_name, name)
            except Exception:
                pass
        threading.Thread(target=_work, daemon=True).start()

    def _set_city_name(self, name):
        self._city_name = name
        self.da.queue_draw()
        return False

    def _apply_clouds(self, value):
        ts = value.get('ts', '')
        if ts and ts == self._last_weather_ts:
            return False   # same 15-min slot — nothing changed, skip redraw
        self._last_weather_ts = ts
        self._clouds = value
        if self._selected_day:
            all_h = value.get('hourly_forecast', [])
            self._selected_day_slots = [
                s for s in all_h if s.get('ts', '')[:10] == self._selected_day
            ][:8]
        self.da.queue_draw()
        return False

    # ── Event handlers ───────────────────────────────────────────────────────

    def _on_key(self, _w, ev):
        ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
        k    = ev.keyval
        if ctrl and k in (ord('h'), ord('H')):
            self._toggle_clean()
            return True
        if ctrl and k in (ord('s'), ord('S')):
            self._open_settings()
            return True
        if ctrl and k in (ord('q'), ord('Q')):
            Gtk.main_quit()
            return True
        if k == Gdk.KEY_Escape and self._exploring():
            self._explore_until = 0.0
            self.da.queue_draw()
            return True
        return False

    def _toggle_clean(self):
        self.cfg['clean_mode'] = not self.cfg.get('clean_mode', False)
        save_config(self.cfg)
        self.da.queue_draw()

    def _on_click(self, _w, ev):
        if math.hypot(ev.x - self._gear_cx, ev.y - self._gear_cy) <= 20:
            self._open_settings()
            return True
        if (self.cfg.get('show_compass', True) and self._hw_heading is None
                and math.hypot(ev.x - self._cmp_cx, ev.y - self._cmp_cy) <= self._cmp_r):
            # Click inside compass rose → angle from centre = new facing direction
            dx = ev.x - self._cmp_cx
            dy = ev.y - self._cmp_cy
            # atan2 with y-down screen: angle 0=up=North, clockwise positive
            facing = (math.degrees(math.atan2(dx, -dy)) + 360) % 360
            self.cfg['facing'] = round(facing, 1)
            save_config(self.cfg)
            self._start_explore()
            return True
        # Click on a weekly forecast day card
        if self.cfg.get('show_weekly_forecast', True):
            for date_str, rx, ry, rw, rh in self._weekly_card_rects:
                if rx <= ev.x <= rx + rw and ry <= ev.y <= ry + rh:
                    if self._selected_day == date_str:
                        self._selected_day       = None
                        self._selected_day_slots = []
                    else:
                        self._selected_day = date_str
                        all_h = self._clouds.get('hourly_forecast', [])
                        self._selected_day_slots = [
                            s for s in all_h if s.get('ts', '')[:10] == date_str
                        ][:8]
                    self._start_explore()
                    return True
        if self._exploring() and ev.button == 1:
            # Click on empty sky ends explore mode; later clicks reach the desktop again
            self._explore_until = 0.0
            self._selected_day  = None
            self.da.queue_draw()
            return True
        if ev.button == 3:
            self._open_settings()
            return True
        # Left-click outside everything deselects the day
        if ev.button == 1 and self._selected_day is not None:
            self._selected_day = None
            self.da.queue_draw()
        return False

    def _start_explore(self):
        """After a click on the compass or a card the whole sky takes input for a while,
        so constellation names show on hover even with click-through on."""
        self._explore_until = time.monotonic() + _EXPLORE_IDLE
        self.da.queue_draw()

    def _exploring(self):
        return self.cfg.get('click_through', True) and time.monotonic() < self._explore_until

    def _on_motion(self, _w, ev):
        self._mouse_x, self._mouse_y = ev.x, ev.y
        if self._exploring():
            self._explore_until = time.monotonic() + _EXPLORE_IDLE
        if self.cfg.get('show_constellations', True) and self._star_screen_cache:
            new_hover = self._hit_test_constellation(ev.x, ev.y)
        else:
            new_hover = None
        if new_hover != self._hover_const:
            self._hover_const = new_hover
            self.da.queue_draw()
        # Compass hover — only when no hardware heading (manual mode)
        over_cmp = (self.cfg.get('show_compass', True)
                    and self._hw_heading is None
                    and math.hypot(ev.x - self._cmp_cx, ev.y - self._cmp_cy) <= self._cmp_r)
        if over_cmp != getattr(self, '_hover_compass', False):
            self._hover_compass = over_cmp
            win = self.get_window()
            if win:
                win.set_cursor(
                    Gdk.Cursor.new_from_name(self.get_display(),
                                             'crosshair' if over_cmp else 'default'))
            self.da.queue_draw()

    def _update_input_region(self, W, H):
        """Click-through: the window takes input only on its controls, so clicks on the sky
        reach the desktop icons and windows below. Without it the whole screen is hit-testable."""
        cfg = self.cfg
        if self._win32 and self._placed_for not in (None, cfg.get('click_through', True)):
            self._place_on_desktop()   # the switch moves the sky behind or in front of the icons
        if not cfg.get('click_through', True) or self._exploring():
            rects = None
        else:
            r = 22
            rects = [(self._gear_cx - r, self._gear_cy - r, 2 * r, 2 * r)]
            if cfg.get('app_enabled', True):   # switched off: only the gear is drawn
                if cfg.get('show_compass', True) and self._hw_heading is None:
                    c = self._cmp_r
                    rects.append((self._cmp_cx - c, self._cmp_cy - c, 2 * c, 2 * c))
                if not cfg.get('clean_mode', False) and cfg.get('show_weekly_forecast', True):
                    rects += [rect[1:] for rect in self._weekly_card_rects]
            rects = tuple(tuple(int(round(v)) for v in rect) for rect in rects)
        if rects == self._input_rects:
            return
        self._input_rects = rects
        if rects is None:
            self.input_shape_combine_region(None)
        else:
            self.input_shape_combine_region(
                cairo.Region([cairo.RectangleInt(x, y, w, h) for x, y, w, h in rects]))
        if self._hover_const and rects is not None:
            self._hover_const = None   # no motion events reach the sky any more

    def _hit_test_constellation(self, mx, my):
        threshold = 22.0
        for name, polylines in _CONSTELLATIONS:
            for polyline in polylines:
                pts = [self._star_screen_cache.get((round(r, 2), round(d, 1)))
                       for r, d in polyline]
                for i in range(len(pts) - 1):
                    a, b = pts[i], pts[i + 1]
                    if a is None or b is None:
                        continue
                    if _seg_dist(mx, my, a[0], a[1], b[0], b[1]) < threshold:
                        return name
        return None

    def _open_settings(self):
        if self._settings_win and self._settings_win.get_visible():
            self._settings_win.present()
            return
        self._settings_win = SettingsDialog(self)
        self._settings_win.show_all()

    # ── Draw dispatch ────────────────────────────────────────────────────────

    def _on_draw(self, _w, cr):
        cfg   = self.cfg
        alloc = self.da.get_allocation()
        W, H  = alloc.width, alloc.height

        set_facing(float(self._hw_heading)
                   if self._hw_heading is not None
                   else float(cfg.get('facing', 180.0)))

        utc    = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        now    = utc + datetime.timedelta(hours=cfg['timezone_offset'])
        lat, lon = cfg['latitude'], cfg['longitude']
        scale  = cfg.get('aster_scale', 1.0)
        clean  = cfg.get('clean_mode', False)

        t_now = time.monotonic()
        if self._astro_cache is None or t_now - self._astro_cache_t >= 1.0:
            sun_el, sun_az = solar_position(lat, lon, utc)
            m_el,   m_az   = moon_position(lat, lon, utc)
            phase,  age    = moon_phase_age(utc)
            m_bright       = moon_brightness(phase, m_el)
            self._astro_cache   = (sun_el, sun_az, m_el, m_az, phase, age, m_bright)
            self._astro_cache_t = t_now
        else:
            sun_el, sun_az, m_el, m_az, phase, age, m_bright = self._astro_cache

        # ── Cloud veil: uniform dimming only from layers that form a continuous sheet.
        # Broken cloud hides the bodies by being drawn in front of them (_draw_clouds).
        veil = veil_transmission(self._clouds)
        # Sun: always retains a faint diffuse glow through overcast
        sun_vis  = max(0.10, veil)
        # Moon: dims a bit faster than the sun
        moon_vis = max(0.04, veil ** 1.2)
        # Stars and planets are faint: a veil the sun shines through hides them
        sky_vis  = veil ** 2

        # ── Gear button is always drawn first (visible even when app is off)
        il, it, ir, ib = self._insets
        gx, gy = W - 28 - ir, H - 28 - ib
        self._cmp_cx, self._cmp_cy = 62 + il, 95 + it
        self._gear_cx, self._gear_cy = gx, gy
        app_on = cfg.get('app_enabled', True)

        if not app_on:
            # Clear to transparent, show only the gear button in red-tinted "off" state
            cr.set_operator(cairo.Operator.SOURCE)
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            cr.set_operator(cairo.Operator.OVER)
            self._draw_gear_btn(cr, gx, gy, 16, off=True)
            self._update_input_region(W, H)
            return

        # ── sky gradient + stars (clouds come after the bodies, so they can pass in front)
        self._draw_sky(cr, W, H, sun_el, sun_az, self._clouds, m_bright, sky_vis, lat, lon, utc)

        # ── sun (show once above ~-2° so horizon glow is visible)
        if sun_el > -2:
            pos = sky_to_screen(max(sun_el, 0.5), sun_az, W, H)
            if pos:
                use_group = sun_vis < 0.999
                if use_group:
                    cr.push_group()
                self._draw_crepuscular_rays(cr, W, H, sun_el, sun_az, scale)
                self._draw_sun(cr, pos[0], pos[1], sun_el, scale)
                if use_group:
                    cr.pop_group_to_source()
                    cr.paint_with_alpha(sun_vis)

        # ── moon pre-glow at horizon (scaled by cloud occlusion)
        if 0 <= m_el <= 15:
            illumination = (1 - math.cos(phase * 2 * math.pi)) / 2
            if illumination > 0.10:
                horiz_pos = sky_to_screen(0.1, m_az, W, H)
                if horiz_pos:
                    hx = horiz_pos[0]; hy = H * 0.72
                    pg_intens = _clamp(1.0 - m_el / 15.0, 0.0, 1.0) * illumination * moon_vis
                    pgr = W * 0.35
                    pg = cairo.RadialGradient(hx, hy, 0, hx, hy, pgr)
                    pg.add_color_stop_rgba(0.00, 0.90, 0.90, 0.82, pg_intens * 0.38)
                    pg.add_color_stop_rgba(0.28, 0.76, 0.76, 0.68, pg_intens * 0.16)
                    pg.add_color_stop_rgba(0.60, 0.55, 0.55, 0.48, pg_intens * 0.05)
                    pg.add_color_stop_rgba(1.00, 0.00, 0.00, 0.00, 0.00)
                    cr.arc(hx, hy, pgr, 0, 2 * math.pi)
                    cr.set_source(pg)
                    cr.fill()

        # ── moon (show only when above horizon)
        if m_el > 0:
            pos = sky_to_screen(m_el, m_az, W, H)
            if pos:
                sun_rel    = ((sun_az - get_facing() + 180.0) % 360.0) - 180.0
                sun_t      = _clamp((sun_rel + 120.0) / 240.0, 0.0, 1.0)
                sun_sx     = W * 0.06 + sun_t * (W * 0.88)
                sun_sy     = H * 0.72 - (H * 0.66) * (sun_el / 90.0)
                limb_angle = math.atan2(pos[1] - sun_sy, sun_sx - pos[0])
                self._moon_limb_angle = limb_angle
                use_group  = moon_vis < 0.999
                if use_group:
                    cr.push_group()
                self._draw_moon(cr, pos[0], pos[1], phase, scale, limb_angle)
                if use_group:
                    cr.pop_group_to_source()
                    cr.paint_with_alpha(moon_vis)

        # ── planets (fully hidden behind thick cloud)
        if sky_vis > 0.02:
            planets = planet_positions(lat, lon, utc)
            if sky_vis < 0.999:
                cr.push_group()
            self._draw_planets(cr, W, H, planets, scale, sun_el)
            if sky_vis < 0.999:
                cr.pop_group_to_source()
                cr.paint_with_alpha(sky_vis)

        # ── clouds, rain and silhouette in front of the sun, moon and planets
        self._draw_weather(cr, W, H, sun_el, sun_az, m_el, m_az, self._clouds, scale, m_bright)

        # Constellation names only meaningful at night
        if sun_el >= -5:
            self._hover_const = None
            self._star_screen_cache = {}

        # ── HUD cards (astronomical info — off by default, toggle in Settings)
        if not clean and cfg.get('show_info_cards', False):
            self._draw_cards(cr, W, H, now, sun_el, phase, age, m_el)

        # ── Weekly forecast column (accordion — hourly expands under clicked day)
        if not clean and cfg.get('show_weekly_forecast', True):
            self._draw_weekly_forecast(cr, W, H)

        # ── Horizon direction labels
        if cfg.get('show_horizon_labels', True):
            self._draw_horizon_labels(cr, W, H)

        # ── Compass rose (top-left, toggleable)
        if cfg.get('show_compass', True):
            self._draw_compass(cr, self._cmp_cx, self._cmp_cy, self._cmp_r)

        # ── Gear / settings button
        self._draw_gear_btn(cr, gx, gy, 16)
        if self._exploring():
            self._draw_explore_hint(cr, gx - 30, gy)
        elif self._update is not None and not self._exporting:
            self._draw_hint(cr, gx - 30, gy, _t('Caelum {v} is installed · restart Caelum to use it').format(
                v=self._update) if self._update else _t('Caelum was updated · restart it to use the new version'))
        elif self._waiting and not self._exporting:
            self._draw_hint(cr, gx - 30, gy, _t('Caelum {v} is ready · it installs when Caelum closes '
                                               '(Ctrl+Q, or when you log out)').format(v=self._waiting))
        self._update_input_region(W, H)

        # ── Constellation hover label
        if (self._hover_const
                and self.cfg.get('show_constellations', True)
                and 0 < self._mouse_x < W
                and 0 < self._mouse_y < H):
            self._draw_const_label(cr, self._mouse_x, self._mouse_y,
                                   self._hover_const, W, H)

    # ── Sky background ───────────────────────────────────────────────────────

    def _draw_sky(self, cr, W, H, sun_el, sun_az, clouds, m_bright, star_vis=1.0,
                  lat=DEFAULT_CONFIG['latitude'], lon=DEFAULT_CONFIG['longitude'], utc=None):
        if self.cfg.get('opaque_sky', True) or self._exporting:
            # Paint the whole sky so the wallpaper doesn't show (the exported image always does)
            zen, hor, g_top, g_bot = opaque_sky(sun_el, clouds, m_bright)
            base = cairo.LinearGradient(0, 0, 0, H)
            base.add_color_stop_rgb(0.0,  *zen)
            base.add_color_stop_rgb(0.40, *_lerp(zen, hor, 0.30))
            base.add_color_stop_rgb(0.72, *hor)
            base.add_color_stop_rgb(0.72, *g_top)
            base.add_color_stop_rgb(1.0,  *g_bot)
            cr.set_source(base)
            cr.paint()
        r, g, b, a = sky_color_adaptive(sun_el, clouds, m_bright)
        grad = cairo.LinearGradient(0, 0, 0, H)
        # At night keep the bottom dark too — prevents bright wallpaper bleeding through
        night = sun_el < -6
        a_mid = a * 0.88 if night else a * 0.75
        a_bot = a * 0.70 if night else a * 0.35
        grad.add_color_stop_rgba(0.0, min(1, r * 1.15), min(1, g * 1.15), min(1, b * 1.15), a)
        grad.add_color_stop_rgba(0.6, r,        g,        b,        a_mid)
        grad.add_color_stop_rgba(1.0, r * 0.70, g * 0.70, b * 0.70, a_bot)
        cr.set_source(grad)
        cr.paint()

        self._draw_horizon_effects(cr, W, H, sun_el, sun_az)

        if sun_el < -5:
            self._draw_stars(cr, W, H,
                             _clamp((-5 - sun_el) / 13, 0, 1) * star_vis,
                             lat, lon, utc, m_bright)
            self._maybe_spawn_meteor(W, H)
            self._draw_meteors(cr, W, H)

    def _draw_weather(self, cr, W, H, sun_el, sun_az, m_el, m_az, clouds, scale, m_bright=0.0):
        if clouds['total'] > 0:
            # Disc to keep clear (or cover): the sun's bright core, else the moon
            body = None
            if sun_el > -0.83:
                pos = sky_to_screen(max(sun_el, 0.5), sun_az, W, H)
                if pos:
                    body = (pos[0], pos[1], 40 * scale)
            if body is None and m_el > 0:
                pos = sky_to_screen(m_el, m_az, W, H)
                if pos:
                    body = (pos[0], pos[1], 36 * scale)
            self._draw_clouds(cr, W, H, clouds, sun_el, body)

        precip = clouds.get('precip', 0.0)
        if precip > 0:
            if self.cfg.get('show_rainbow', True):
                self._draw_rainbow(cr, W, H, sun_el, sun_az, precip)
            rain = self._precip_scene(sun_el, clouds, m_bright)
            self._draw_precip(cr, W, H, rain, wx.FAR)
            # Lightning lights the sky and clouds; the landscape stays a dark silhouette
            if 95 <= clouds.get('wmo', 0) <= 99 and not rain['snow']:
                self._storm.draw(cr, W, H, rain['t'], clouds.get('wmo', 0) >= 96)

        # Landscape last — always in front of sky, stars, and clouds
        land = self.cfg.get('landscape', 'plain')
        if land == 'hills':
            self._draw_horizon_silhouette(cr, W, H)
        elif land != 'none' and not self._draw_landscape(cr, W, H, land, sun_el, clouds, m_bright):
            self._draw_horizon_silhouette(cr, W, H)   # photo not installed

        if precip > 0:
            wx.draw_veil(cr, W, H, rain['inten'], rain['snow'], rain['haze'])
            self._draw_precip(cr, W, H, rain, wx.NEAR)

    def _precip_scene(self, sun_el, clouds, m_bright):
        """What the rain or snow looks like now: amount, wind slant, and colours lit by the scene."""
        light, _sat = landscape_light(sun_el, clouds, m_bright)
        lum  = _clamp(max(light) * 1.1, 0.0, 1.0)
        snow = clouds.get('snow', False)
        _zen, hor, _gt, _gb = opaque_sky(sun_el, clouds, m_bright)
        # Drops catch the light: a little paler than the sky, so they show against it and
        # (more) against the darker ground
        if snow:
            drop = _lerp(hor, (0.97, 0.98, 1.0), 0.45 + 0.4 * lum)
        else:
            drop = tuple(min(1.0, c * 1.25 + 0.07) for c in hor)
        haze = _lerp(hor, (0.92, 0.93, 0.95), 0.35 * lum) if snow else hor
        return dict(t=time.time(), snow=snow, inten=precip_intensity(clouds.get('precip', 0.0)),
                    slant=rain_slant(clouds.get('wind_speed', 0.0), clouds.get('wind_dir', 180.0)),
                    drop=drop, haze=haze, cover=overcast_deck(clouds),
                    shaft=_lerp(hor, (0.35, 0.38, 0.44), 0.5) if not snow else haze)

    def _draw_precip(self, cr, W, H, rain, layers):
        if layers == wx.FAR:
            wx.draw_shafts(cr, W, H, rain['inten'], rain['cover'], rain['slant'], rain['shaft'],
                           int(rain['t'] // 3600))
        draw = wx.draw_snow if rain['snow'] else wx.draw_rain
        draw(cr, W, H, rain['t'], layers, rain['inten'], rain['slant'], rain['drop'])

    def _draw_landscape(self, cr, W, H, name, sun_el, clouds, m_bright):
        """Photo landscape, relit to the sun; cached until the view or the light changes.
        Returns False when the photo isn't available."""
        if name not in self._landscapes:
            try:
                self._landscapes[name] = Landscape(name)
            except Exception:
                self._landscapes[name] = None
        land = self._landscapes[name]
        if land is None:
            return False
        light, sat = landscape_light(sun_el, clouds, m_bright)
        key = (name, W, H, round(get_facing(), 1),
               tuple(round(c * 64) for c in light), round(sat * 32))
        if self._land_cache is None or self._land_cache[0] != key:
            surf, y = land.render(W, H, get_facing(), tuple(round(c * 64) / 64 for c in light),
                                  round(sat * 32) / 32)
            self._land_cache = (key, surf, y)
        _key, surf, y = self._land_cache
        cr.set_source_surface(surf, 0, y)
        cr.paint()
        return True

    def _draw_horizon_effects(self, cr, W, H, sun_el, sun_az):
        """Layered horizon effects: Belt of Venus, pre-glow, golden-hour band, atmospheric haze."""
        y0 = H * 0.72

        # ── Belt of Venus: pink/mauve arch on the anti-solar horizon at twilight ──
        # Visible when sun is -1° to -10°, opposite the sunset/sunrise direction.
        if -10.0 < sun_el < -0.5:
            anti_az  = (sun_az + 180.0) % 360.0
            anti_rel = ((anti_az - get_facing() + 180.0) % 360.0) - 180.0
            if abs(anti_rel) < 120.0:
                anti_t  = _clamp((anti_rel + 120.0) / 240.0, 0.0, 1.0)
                ax      = W * 0.06 + anti_t * (W * 0.88)
                intens  = _clamp(1.0 - abs(sun_el + 5.0) / 5.0, 0.0, 1.0) ** 1.4
                bv_r    = W * 0.58
                bv = cairo.RadialGradient(ax, y0, 0, ax, y0, bv_r)
                bv.add_color_stop_rgba(0.00, 0.88, 0.52, 0.72, intens * 0.42)
                bv.add_color_stop_rgba(0.18, 0.72, 0.38, 0.62, intens * 0.28)
                bv.add_color_stop_rgba(0.45, 0.45, 0.20, 0.48, intens * 0.12)
                bv.add_color_stop_rgba(1.00, 0.00, 0.00, 0.00, 0.00)
                cr.arc(ax, y0, bv_r, 0, 2 * math.pi)
                cr.set_source(bv)
                cr.fill()

        # ── Pre-glow: sun just below horizon (-12° to 0°) ────────────────────
        # Deep orange-red radial bloom centred on the sun's horizon point.
        if -12.0 < sun_el < 0.0:
            sun_rel = ((sun_az - get_facing() + 180.0) % 360.0) - 180.0
            sun_t   = _clamp((sun_rel + 120.0) / 240.0, 0.0, 1.0)
            gx      = W * 0.06 + sun_t * (W * 0.88)
            intens  = _clamp(1.0 - abs(sun_el) / 12.0, 0.0, 1.0) ** 1.5
            gr      = W * 0.52
            grd = cairo.RadialGradient(gx, y0, 0, gx, y0, gr)
            grd.add_color_stop_rgba(0.00, 1.00, 0.45, 0.02, intens * 0.60)
            grd.add_color_stop_rgba(0.22, 1.00, 0.30, 0.01, intens * 0.32)
            grd.add_color_stop_rgba(0.55, 0.80, 0.15, 0.00, intens * 0.10)
            grd.add_color_stop_rgba(1.00, 0.00, 0.00, 0.00, 0.00)
            cr.arc(gx, y0, gr, 0, 2 * math.pi)
            cr.set_source(grd)
            cr.fill()

        # ── Golden-hour band: warm strip across the full horizon ──────────────
        # Peaks near sun_el ≈ 2°; fades out above 15° and below -6°.
        if -6.0 < sun_el < 15.0:
            intens = _clamp(1.0 - abs(sun_el - 2.0) / 8.0, 0.0, 1.0) ** 2.0
            if intens > 0.01:
                gh = H * 0.22
                grd = cairo.LinearGradient(0, y0 - gh, 0, y0)
                grd.add_color_stop_rgba(0.00, 0.00, 0.00, 0.00, 0.00)
                grd.add_color_stop_rgba(0.50, 1.00, 0.55, 0.06, intens * 0.10)
                grd.add_color_stop_rgba(0.78, 1.00, 0.38, 0.02, intens * 0.20)
                grd.add_color_stop_rgba(1.00, 1.00, 0.22, 0.01, intens * 0.16)
                cr.rectangle(0, y0 - gh, W, gh)
                cr.set_source(grd)
                cr.fill()

        # ── Atmospheric haze: subtle veil on the lower sky ────────────────────
        # Gives visual depth — daytime blue-white, nighttime dark haze.
        hz = H * 0.18
        if sun_el > 0:
            hr, hg, hb, ha = 0.82, 0.88, 1.00, 0.09
        else:
            hr, hg, hb, ha = 0.06, 0.07, 0.14, 0.06
        hrd = cairo.LinearGradient(0, y0 - hz, 0, y0)
        hrd.add_color_stop_rgba(0.0, hr, hg, hb, 0.00)
        hrd.add_color_stop_rgba(1.0, hr, hg, hb, ha)
        cr.rectangle(0, y0 - hz, W, hz)
        cr.set_source(hrd)
        cr.fill()

    def _draw_stars(self, cr, W, H, intensity, lat=DEFAULT_CONFIG['latitude'], lon=DEFAULT_CONFIG['longitude'],
                    utc=None, m_bright=0.0):
        if utc is None:
            utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        rng = random.Random(42)

        # ── Background faint star field — static texture of dim (mag 5-7) stars ──
        rng_bg = random.Random(0xC7D9)
        bg_limit = intensity * (1.0 - m_bright * 0.88)
        for _ in range(420):
            bsx = rng_bg.uniform(0, W)
            bsy = rng_bg.uniform(0, H * 0.72)
            ba  = bg_limit * rng_bg.uniform(0.03, 0.16)
            if ba < 0.015:
                rng_bg.random()   # keep rng state stable
                continue
            br = rng_bg.uniform(0.3, 0.65)
            cr.set_source_rgba(0.88, 0.90, 0.96, ba)
            cr.arc(bsx, bsy, br, 0, 2 * math.pi)
            cr.fill()

        # ── Airglow — faint green emission band near horizon on dark nights ──────
        if intensity > 0.4 and m_bright < 0.80:
            ag_a = (intensity - 0.4) / 0.6 * 0.036 * (1.0 - m_bright / 0.80)
            ag_grd = cairo.LinearGradient(0, H * 0.57, 0, H * 0.72)
            ag_grd.add_color_stop_rgba(0.0, 0.00, 0.00, 0.00, 0.00)
            ag_grd.add_color_stop_rgba(1.0, 0.28, 0.65, 0.30, ag_a)
            cr.rectangle(0, H * 0.57, W, H * 0.15)
            cr.set_source(ag_grd)
            cr.fill()

        # ── Milky Way — fades under moonlight (bright moon washes it out)
        if intensity > 0.5 and m_bright < 0.7:
            mw_alpha = (intensity - 0.5) * 2 * 0.07 * (1.0 - m_bright / 0.7)
            pdx, pdy = 1.2 * W, -0.45 * H
            plen = math.sqrt(pdx * pdx + pdy * pdy)
            nx, ny = -pdy / plen, pdx / plen
            for i in range(180):
                t      = i / 179.0
                cx     = W * (-0.1 + t * 1.2)
                cy     = H * (0.55 - t * 0.45)
                spread = rng.gauss(0, H * 0.09)
                bx     = cx + nx * spread + rng.uniform(-W * 0.01, W * 0.01)
                by     = cy + ny * spread + rng.uniform(-H * 0.01, H * 0.01)
                bw     = W * rng.uniform(0.05, 0.14)
                bh     = H * rng.uniform(0.05, 0.13)
                a      = mw_alpha * rng.uniform(0.3, 1.0)
                _soft_puff(cr, bx, by, bw, bh, 0.60, 0.65, 0.80, a)

        # ── Real star catalog — positions computed from RA/Dec for current time
        # Moon washes out dim stars: full moon → limiting mag ~3.0; no moon → ~6.5
        limiting_mag = 6.5 - m_bright * 3.5

        star_data = _get_star_positions(lat, lon, utc)

        # Build screen-position lookup keyed by rounded RA/Dec for constellation lines
        star_screen = {}
        for alt, az, mag, bv, ra_h, dec_deg in star_data:
            pos = sky_to_screen(alt, az, W, H)
            if pos is not None:
                star_screen[(round(ra_h, 2), round(dec_deg, 1))] = pos
        self._star_screen_cache = star_screen

        # Constellation lines drawn before stars so stars render on top
        if self.cfg.get('show_constellations', True):
            line_alpha = 0.28 * intensity * max(0.0, 1.0 - m_bright * 0.8)
            if line_alpha > 0.01:
                cr.set_line_width(0.8)
                for name, polylines in _CONSTELLATIONS:
                    hovered = (name == self._hover_const)
                    if hovered:
                        cr.set_source_rgba(0.75, 0.85, 1.00, min(1.0, line_alpha * 2.8))
                    else:
                        cr.set_source_rgba(0.55, 0.65, 0.95, line_alpha)
                    for polyline in polylines:
                        prev = None
                        for ra_h_pt, dec_deg_pt in polyline:
                            key = (round(ra_h_pt, 2), round(dec_deg_pt, 1))
                            pt = star_screen.get(key)
                            if pt is None:
                                prev = None
                                continue
                            if prev is not None:
                                cr.move_to(prev[0], prev[1])
                                cr.line_to(pt[0], pt[1])
                                cr.stroke()
                            prev = pt

        for alt, az, mag, bv, ra_h, dec_deg in star_data:
            pos = star_screen.get((round(ra_h, 2), round(dec_deg, 1)))
            if pos is None:
                continue
            sx, sy = pos
            sr, sg, sb = _bv_to_rgb(bv)

            moon_fade = _clamp((limiting_mag - mag) / 2.0, 0.0, 1.0)
            if moon_fade <= 0:
                continue

            elev_fade = _clamp((alt + 1.0) / 12.0, 0.0, 1.0)
            alpha     = intensity * elev_fade * moon_fade * _clamp((6.0 - mag) / 6.5, 0.05, 1.0)
            t_sec     = utc.hour * 3600 + utc.minute * 60 + utc.second
            phase_off = (ra_h * 7919.0 + abs(dec_deg) * 3571.0) % (2 * math.pi)
            alpha     = _clamp(alpha * (1.0 + 0.14 * math.sin(t_sec * 2.7 + phase_off)), 0.0, 1.0)
            radius    = max(0.4, (5.5 - mag) * 0.38)

            cr.set_source_rgba(sr, sg, sb, alpha)
            cr.arc(sx, sy, radius, 0, 2 * math.pi)
            cr.fill()

            if mag < 2.0:
                glow_r = radius * 3.5 + 1.5
                _soft_puff(cr, sx, sy, glow_r, glow_r,
                           sr, sg, sb, alpha * 0.35 * intensity)

        # ── Orion Nebula (M42) — faint pink-teal glow below Orion's belt ────────
        m42_alt, m42_az = _ra_dec_to_alt_az(5.5875, -5.391, lat, lon, utc)
        if m42_alt > 0:
            m42_pos = sky_to_screen(m42_alt, m42_az, W, H)
            if m42_pos:
                nf = intensity * _clamp((m42_alt + 1.0) / 18.0, 0.0, 1.0) * (1.0 - m_bright * 0.75)
                if nf > 0.01:
                    nx, ny = m42_pos
                    nw, nh = W * 0.013, H * 0.020
                    _soft_puff(cr, nx, ny, nw, nh, 0.85, 0.55, 0.72, nf * 0.38)
                    _soft_puff(cr, nx, ny, nw * 0.55, nh * 0.55, 0.50, 0.72, 0.80, nf * 0.28)

    # ── Crepuscular rays ─────────────────────────────────────────────────────

    def _draw_crepuscular_rays(self, cr, W, H, sun_el, sun_az, scale):
        if sun_el < -1 or sun_el > 28:
            return
        pos = sky_to_screen(max(sun_el, 0.5), sun_az, W, H)
        if pos is None:
            return
        sx, sy   = pos
        intens   = _clamp(1.0 - abs(sun_el - 6.0) / 18.0, 0.0, 1.0) ** 2.0
        if intens < 0.01:
            return
        n_rays   = 7
        ray_len  = W * 1.3
        half_w   = W * 0.006
        rng      = random.Random(datetime.date.today().toordinal())
        cr.save()
        cr.set_operator(cairo.Operator.SCREEN)
        for _ in range(n_rays):
            ang  = rng.uniform(0, 2 * math.pi)
            alph = rng.uniform(0.012, 0.040) * intens
            ex   = sx + ray_len * math.cos(ang)
            ey   = sy + ray_len * math.sin(ang)
            nx   = -math.sin(ang) * half_w
            ny   =  math.cos(ang) * half_w
            cr.new_path()
            cr.move_to(sx + nx, sy + ny)
            cr.line_to(sx - nx, sy - ny)
            cr.line_to(ex,      ey)
            cr.close_path()
            grd = cairo.LinearGradient(sx, sy, ex, ey)
            grd.add_color_stop_rgba(0.00, 1.0, 0.98, 0.82, alph * 2.0)
            grd.add_color_stop_rgba(0.25, 1.0, 0.95, 0.72, alph)
            grd.add_color_stop_rgba(1.00, 1.0, 0.90, 0.60, 0.00)
            cr.set_source(grd)
            cr.fill()
        cr.restore()

    # ── Lunar halo ───────────────────────────────────────────────────────────

    def _draw_lunar_halo(self, cr, x, y, moon_r, clouds, phase):
        if clouds.get('high', 0) < 20:
            return
        illumination = (1 - math.cos(phase * 2 * math.pi)) / 2
        if illumination < 0.20:
            return
        intens  = min(clouds['high'] / 100.0, 1.0) * illumination
        halo_r  = moon_r * 5.2   # 22° halo ≈ 5× moon radius on screen
        inner_r = halo_r * 0.88
        outer_r = halo_r * 1.12
        halo = cairo.RadialGradient(x, y, inner_r, x, y, outer_r)
        halo.add_color_stop_rgba(0.00, 0.00, 0.00, 0.00, 0.00)
        halo.add_color_stop_rgba(0.35, 0.90, 0.92, 0.95, intens * 0.20)
        halo.add_color_stop_rgba(0.50, 0.95, 0.96, 1.00, intens * 0.32)
        halo.add_color_stop_rgba(0.65, 0.90, 0.92, 0.95, intens * 0.20)
        halo.add_color_stop_rgba(1.00, 0.00, 0.00, 0.00, 0.00)
        cr.arc(x, y, outer_r, 0, 2 * math.pi)
        cr.set_source(halo)
        cr.fill()

    # ── Horizon direction labels ─────────────────────────────────────────────

    def _draw_horizon_labels(self, cr, W, H):
        y0 = H * 0.72
        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(10)
        for lbl, az in [('N', 0), ('NE', 45), ('E', 90), ('SE', 135),
                        ('S', 180), ('SW', 225), ('W', 270), ('NW', 315)]:
            rel = ((az - get_facing() + 180.0) % 360.0) - 180.0
            if abs(rel) > 117:
                continue
            t  = _clamp((rel + 120.0) / 240.0, 0.0, 1.0)
            lx = W * 0.06 + t * (W * 0.88)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.22)
            cr.set_line_width(1.0)
            cr.move_to(lx, y0 - 5)
            cr.line_to(lx, y0 + 5)
            cr.stroke()
            ext = cr.text_extents(lbl)
            col = (1.0, 0.30, 0.30, 0.72) if lbl == 'N' else (0.85, 0.90, 1.00, 0.42)
            cr.set_source_rgba(*col)
            cr.move_to(lx - ext.width / 2 - ext.x_bearing, y0 - 9)
            cr.show_text(lbl)

    # ── Rainbow ──────────────────────────────────────────────────────────────

    def _draw_rainbow(self, cr, W, H, sun_el, sun_az, precip):
        if precip < 0.1 or sun_el < 10 or sun_el > 45:
            return
        anti_az  = (sun_az + 180.0) % 360.0
        anti_rel = ((anti_az - get_facing() + 180.0) % 360.0) - 180.0
        if abs(anti_rel) > 118.0:
            return
        anti_t  = _clamp((anti_rel + 120.0) / 240.0, 0.0, 1.0)
        ax      = W * 0.06 + anti_t * (W * 0.88)
        y0      = H * 0.72
        top_el  = 42.0 - sun_el
        if top_el <= 0:
            return
        top_y   = H * 0.72 - (H * 0.66) * _clamp(top_el / 90.0, 0, 1)
        bow_r   = y0 - top_y
        if bow_r < 10:
            return
        intens  = min(precip / 5.0, 1.0) * _clamp((45.0 - sun_el) / 35.0, 0, 1)
        bow_w   = bow_r * 0.028
        cr.save()
        cr.set_line_width(bow_w)
        for i, (r, g, b) in enumerate([
                (1.00, 0.10, 0.00),   # red outer
                (1.00, 0.50, 0.00),   # orange
                (1.00, 0.95, 0.00),   # yellow
                (0.15, 0.85, 0.15),   # green
                (0.10, 0.30, 1.00),   # blue
                (0.38, 0.00, 0.90),   # violet inner
        ]):
            ri = bow_r * (1.0 + (2 - i) * 0.018)
            cr.arc(ax, y0, ri, math.pi, 0)
            cr.set_source_rgba(r, g, b, intens * 0.18)
            cr.stroke()
        cr.restore()

    # ── Lock-screen export ───────────────────────────────────────────────────

    def _render_frame_to_surface(self):
        """Render the current sky frame off-screen and return an ImageSurface."""
        alloc = self.da.get_allocation()
        W, H  = alloc.width, alloc.height
        if W < 10 or H < 10:
            return None
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        cr   = cairo.Context(surf)
        # Opaque sky: a wallpaper can't show another wallpaper through it
        self._exporting = True
        try:
            self._on_draw(self.da, cr)
        finally:
            self._exporting = False
        return surf

    def _export_lockscreen_bg(self):
        """Save current sky frame as PNG and push it to background/lock screen per config."""
        mode = self.cfg.get('lockscreen_export', 'off')
        if mode == 'off':
            return True   # keep timer alive
        # Render on the main thread (GTK/Cairo requirement), then hand PNG bytes to a thread
        surf = self._render_frame_to_surface()
        if surf is None:
            return True
        out_dir  = sandbox.cache_dir()
        out_path = os.path.join(out_dir, 'caelum-lockscreen.png')
        def _work(surface, path, export_mode):
            try:
                os.makedirs(out_dir, exist_ok=True)
                surface.write_to_png(path)
            except OSError:
                return
            GLib.idle_add(self._apply_wallpaper, path, export_mode)
        threading.Thread(target=_work, args=(surf, out_path, mode), daemon=True).start()
        return True   # keep timer alive

    def _apply_wallpaper(self, path, mode):
        try:
            sandbox.set_wallpaper(path, mode)
        except Exception:
            pass   # no portal / no GNOME schemas: export stays a no-op
        return False

    def _draw_gear_btn(self, cr, cx, cy, r, off=False):
        if off:
            bg   = (0.28, 0.04, 0.04, 0.72)
            ring = (1.0, 0.35, 0.35, 0.50)
            icon = (1.0, 0.55, 0.55, 0.95)
            hole = (0.28, 0.04, 0.04, 0.72)
        else:
            bg   = (0.04, 0.05, 0.12, 0.58)
            ring = (1.0,  1.0,  1.0,  0.22)
            icon = (1.0,  1.0,  1.0,  0.88)
            hole = (0.04, 0.05, 0.12, 0.58)

        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source_rgba(*bg)
        cr.fill()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source_rgba(*ring)
        cr.set_line_width(1)
        cr.stroke()

        cr.save()
        cr.translate(cx, cy)
        cr.set_source_rgba(*icon)
        n = 8
        ro, ri = r * 0.66, r * 0.44
        tooth = math.pi / n * 0.55
        cr.new_path()
        for i in range(n):
            mid = 2 * math.pi * i / n
            a0, a1 = mid - math.pi / n + tooth, mid - tooth
            a2, a3 = mid + tooth, mid + math.pi / n - tooth
            cr.arc(0, 0, ri, a0 - 0.01, a0)
            cr.arc(0, 0, ro, a1, a2)
            cr.arc(0, 0, ri, a3, a3 + 0.01)
        cr.close_path()
        cr.fill()
        cr.set_source_rgba(*hole)
        cr.arc(0, 0, r * 0.22, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

    def _draw_explore_hint(self, cr, right, cy):
        """Small pill left of the gear while explore mode holds the desktop's clicks."""
        self._draw_hint(cr, right, cy, _t('Exploring the sky · click empty sky or Esc to return to the desktop'))

    def _draw_hint(self, cr, right, cy, text):
        """Small pill ending at x = right, centred on cy."""
        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(12)
        ext = cr.text_extents(text)
        w, h = ext.x_advance + 20, 24
        self._rrect(cr, right - w, cy - h / 2, w, h, 12)
        cr.set_source_rgba(0.04, 0.05, 0.12, 0.58)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.85)
        cr.move_to(right - w + 10, cy + 4)
        cr.show_text(text)

    def _draw_const_label(self, cr, mx, my, name, W, H):
        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13)
        ext = cr.text_extents(name)
        pw, ph = ext.width + 20, 26
        px = _clamp(mx + 16, 4, W - pw - 4)
        py = _clamp(my - ph - 8, 4, H - ph - 4)
        self._rrect(cr, px, py, pw, ph, 6)
        cr.set_source_rgba(0.04, 0.05, 0.14, 0.72)
        cr.fill_preserve()
        cr.set_source_rgba(0.55, 0.65, 0.95, 0.45)
        cr.set_line_width(1)
        cr.stroke()
        cr.set_source_rgba(0.85, 0.90, 1.00, 0.95)
        cr.move_to(px + 10, py + ph - 7)
        cr.show_text(name)

    def _advance_cloud_drift(self, clouds):
        """
        Scroll each cloud layer with the wind. Angular speed falls with height (higher clouds
        are farther away); only the wind's sideways component, relative to the facing
        direction, moves clouds across the view.
        """
        now = time.monotonic()
        dt  = _clamp(now - self._drift_t, 0.0, 1.0)   # no jump after suspend
        self._drift_t = now
        wind_spd = max(clouds.get('wind_speed', 0.0), 1.5)   # winds aloft are rarely calm
        wind_to  = (clouds.get('wind_dir', 0.0) + 180.0) % 360.0
        side     = math.sin(math.radians(wind_to - get_facing()))
        # Wind straight toward/away from you still shows some sideways movement
        side     = math.copysign(max(abs(side), 0.25), side)
        for layer, deg_per_ms in _CLOUD_DRIFT.items():
            # degrees/s → screen widths/s (the panorama spans 240°)
            self._drift[layer] += side * wind_spd * deg_per_ms / 240.0 * dt
        # Low cumulus layer: carried bodily by the wind (km), stronger at cloud base than at
        # the ground; perspective then turns this into on-screen motion
        km = _LOW_WIND_FACTOR * wind_spd / 1000.0 * dt
        self._low_offset[0] += km * math.sin(math.radians(wind_to))
        self._low_offset[1] += km * math.cos(math.radians(wind_to))

    def _draw_clouds(self, cr, W, H, clouds, sun_el, body=None):
        """
        Clouds move a pixel or two a second, so the layer is rendered into a cached surface at
        half resolution (soft shapes: the upscale doesn't show, and it is 4× less to fill).
        It is redrawn at once when the scene changes (size, weather, view, sun/moon), and
        for drift at most once a second.
        """
        self._advance_cloud_drift(clouds)
        # Drift snapped to half-res pixels, so the cached image matches what would be drawn
        drift  = {k: round(v * W / 2) * 2 / W for k, v in self._drift.items()}
        # Low layer snapped to 8 m steps: about one half-res pixel for a cloud overhead
        offset = tuple(round(v / 0.008) * 0.008 for v in self._low_offset)
        scene  = (W, H, id(clouds), clouds.get('ts'), round(get_facing(), 1), round(sun_el * 4),
                  tuple(round(v) for v in body) if body else None)
        motion = (tuple(drift.values()), offset)
        now    = time.monotonic()
        if self._cloud_key is None or scene != self._cloud_key[0] or (
                motion != self._cloud_key[1] and now - self._cloud_t >= 1.0):
            surf = cr.get_target().create_similar(cairo.Content.COLOR_ALPHA, W // 2, H // 2)
            ctx  = cairo.Context(surf)
            ctx.scale(0.5, 0.5)
            self._render_clouds(ctx, W, H, clouds, sun_el, body, drift, offset)
            self._cloud_surf, self._cloud_key, self._cloud_t = surf, (scene, motion), now
        cr.save()
        cr.scale(2.0, 2.0)
        cr.set_source_surface(self._cloud_surf, 0, 0)
        cr.get_source().set_filter(cairo.Filter.BILINEAR)
        cr.paint()
        cr.restore()

    @staticmethod
    def _draw_faded(cr, alpha, draw, *args, **kwargs):
        """Run a cloud draw function at reduced overall opacity (skipped when invisible)."""
        if alpha < 0.02:
            return
        if alpha < 1.0:
            cr.push_group()
        draw(cr, *args, **kwargs)
        if alpha < 1.0:
            cr.pop_group_to_source()
            cr.paint_with_alpha(alpha)

    def _render_clouds(self, cr, W, H, clouds, sun_el, body, drift, offset):
        top_col, dark_col, cir_col = _cloud_palette(sun_el)
        # Rain clouds are thick: their bases go dark grey, their tops lose the glare
        rain = precip_intensity(clouds.get('precip', 0.0))
        if rain > 0:
            dark_col = tuple(c * (1.0 - 0.38 * rain) for c in dark_col)
            top_col  = tuple(c * (1.0 - 0.15 * rain) for c in top_col)

        low_cov, mid_cov, high_cov = cloud_layers(clouds)
        wmo = clouds.get('wmo', 0)

        # Back-to-front: cirrus → altocumulus → overcast deck → cumulus. Broken cloud doesn't
        # dim the whole sky: the sun/moon is hidden only while a cloud is in front of it — low
        # cumulus by perspective geometry, altocumulus by a band drifting past the body.
        pos  = body[:2] if body else None
        deck = overcast_deck(clouds)
        sheet = mid_sheet(clouds)
        above = 1.0 - deck   # layers above the deck vanish as it closes
        self._draw_faded(cr, above, draw_cirrus, W, H, high_cov, cir_col, drift=drift['high'])
        # As a layer closes into a sheet, its separate clouds merge into it
        self._draw_faded(cr, above * (1.0 - 0.85 * sheet), draw_altocumulus,
                         W, H, mid_cov, top_col, drift=drift['mid'], body=body)
        draw_mid_sheet(cr, W, H, sheet * max(above, 0.3), top_col, dark_col)
        # The deck hides what is above it; puffs (white, sunlit tops that can't be seen
        # from under a ceiling) fade into it as it closes
        draw_deck(cr, W, H, deck, top_col, dark_col, drift=drift['low'])
        self._draw_faded(cr, 1.0 - deck ** 2, draw_cumulus,
                         W, H, low_cov, top_col, dark_col, wmo=wmo, offset=offset)

        # Celestial body glow: illuminates clouds around sun/moon position
        if pos:
            self._draw_body_glow_on_clouds(cr, W, H, pos, sun_el)

    def _draw_body_glow_on_clouds(self, cr, W, H, pos, sun_el):
        """
        Radial light gradient from the sun or moon that brightens nearby clouds.
        At night this is cool silver-white (moonlight, no pollution).
        At sunrise/sunset it's warm gold.
        """
        bx, by = pos
        radius = W * 0.42   # glow spreads wide across the sky

        if sun_el < -0.83:  # moon is the source — natural silver
            col_inner = (0.92, 0.90, 0.82)
            col_mid   = (0.76, 0.74, 0.66)
            a_inner, a_mid = 0.55, 0.22
        elif sun_el < 8:    # golden hour / sunrise-sunset — warm gold
            col_inner = (1.00, 0.82, 0.45)
            col_mid   = (1.00, 0.65, 0.20)
            a_inner, a_mid = 0.42, 0.16
        else:               # daytime — bright white-blue
            col_inner = (1.00, 1.00, 1.00)
            col_mid   = (0.88, 0.92, 1.00)
            a_inner, a_mid = 0.28, 0.08

        grd = cairo.RadialGradient(bx, by, 0, bx, by, radius)
        grd.add_color_stop_rgba(0.00, col_inner[0], col_inner[1], col_inner[2], a_inner)
        grd.add_color_stop_rgba(0.35, col_mid[0],   col_mid[1],   col_mid[2],   a_mid)
        grd.add_color_stop_rgba(0.75, col_mid[0],   col_mid[1],   col_mid[2],   a_mid * 0.3)
        grd.add_color_stop_rgba(1.00, 0, 0, 0, 0)
        cr.rectangle(0, 0, W, H)
        cr.set_source(grd)
        cr.fill()

    # ── Planets ──────────────────────────────────────────────────────────────

    def _draw_planets(self, cr, W, H, planets, scale, sun_el):
        for name, el, az, col in planets:
            mag = _PLANET_MAG.get(name, 0.0)
            vis = naked_eye_visibility(mag, sun_el)   # hidden by daylight / bright twilight
            if el <= 0 or vis <= 0.01:
                continue
            pos = sky_to_screen(el, az, W, H)
            if pos is None:
                continue
            px, py = pos
            r, g, b = col
            radius = max(3.5, (5.5 - mag * 0.50)) * scale
            glow = cairo.RadialGradient(px, py, 0, px, py, radius * 3.5)
            glow.add_color_stop_rgba(0.0, r, g, b, 0.60 * vis)
            glow.add_color_stop_rgba(0.5, r, g, b, 0.22 * vis)
            glow.add_color_stop_rgba(1.0, r, g, b, 0.00)
            cr.arc(px, py, radius * 3.5, 0, 2 * math.pi)
            cr.set_source(glow)
            cr.fill()
            cr.set_source_rgba(r, g, b, 0.95 * vis)
            cr.arc(px, py, radius, 0, 2 * math.pi)
            cr.fill()
            if name == 'Saturn':
                cr.save()
                cr.translate(px, py)
                cr.scale(1.0, 0.32)
                cr.set_source_rgba(r, g, b, 0.50 * vis)
                cr.set_line_width(radius * 0.55)
                cr.arc(0, 0, radius * 2.1, 0, 2 * math.pi)
                cr.stroke()
                cr.restore()
            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(9 * scale)
            cr.set_source_rgba(r, g, b, 0.72 * vis)
            cr.move_to(px + radius + 3, py + 4)
            cr.show_text(name)

    # ── Compass rose ─────────────────────────────────────────────────────────

    def _draw_compass(self, cr, cx, cy, r):
        pi2      = 2 * math.pi
        # heading = real device heading when hw compass is active, else manual facing
        heading  = (float(self._hw_heading)
                    if self._hw_heading is not None
                    else float(self.cfg.get('facing', 180.0)))
        fac_ang  = math.radians(heading) - math.pi / 2   # screen angle, N=up=−pi/2
        half_fov = math.radians(120)                      # 240° total FOV

        # Background disc
        cr.arc(cx, cy, r, 0, pi2)
        cr.set_source_rgba(0.04, 0.06, 0.14, 0.62)
        cr.fill()
        cr.arc(cx, cy, r, 0, pi2)
        cr.set_source_rgba(1, 1, 1, 0.20)
        cr.set_line_width(1)
        cr.stroke()

        # Field-of-view wedge: 240° sector showing panorama coverage
        cr.move_to(cx, cy)
        cr.arc(cx, cy, r * 0.50, fac_ang - half_fov, fac_ang + half_fov)
        cr.close_path()
        cr.set_source_rgba(0.50, 0.72, 1.0, 0.13)
        cr.fill()
        # Facing direction arrow
        cr.move_to(cx, cy)
        cr.line_to(cx + r * 0.42 * math.cos(fac_ang),
                   cy + r * 0.42 * math.sin(fac_ang))
        cr.set_source_rgba(0.50, 0.72, 1.0, 0.55)
        cr.set_line_width(1.5)
        cr.stroke()

        # Tick marks — 8 directions (4 cardinal + 4 intercardinal)
        for i in range(8):
            ang   = pi2 * i / 8 - math.pi / 2   # 0 = North = up
            major = (i % 2 == 0)
            r_in  = r * (0.72 if major else 0.82)
            r_out = r * 0.94
            cr.move_to(cx + r_in  * math.cos(ang), cy + r_in  * math.sin(ang))
            cr.line_to(cx + r_out * math.cos(ang), cy + r_out * math.sin(ang))
            cr.set_source_rgba(1, 1, 1, 0.55 if major else 0.28)
            cr.set_line_width(1.2 if major else 0.7)
            cr.stroke()

        # N / E / S / W labels
        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(r * 0.30)
        for lbl, frac in [('N', 0), ('E', 0.25), ('S', 0.5), ('W', 0.75)]:
            ang  = pi2 * frac - math.pi / 2
            lx   = cx + r * 0.52 * math.cos(ang)
            ly   = cy + r * 0.52 * math.sin(ang)
            ext  = cr.text_extents(lbl)
            col  = (1.0, 0.30, 0.30, 0.95) if lbl == 'N' else (0.90, 0.92, 1.0, 0.80)
            cr.set_source_rgba(*col)
            cr.move_to(lx - ext.width / 2 - ext.x_bearing,
                       ly - ext.height / 2 - ext.y_bearing)
            cr.show_text(lbl)

        # Needle — diamond; rotate so red tip always points geographic North.
        # When heading=0 (facing N): no rotation, red tip at top.
        # When heading=90 (facing E): rotate -90 deg, red tip points left.
        nl = r * 0.52   # north arm length
        sl = r * 0.34   # south arm length
        nw = r * 0.12   # half-width at pivot

        cr.save()
        cr.translate(cx, cy)
        cr.rotate(-math.radians(heading))   # needle tracks geographic North

        # North half (red)
        cr.new_path()
        cr.move_to(0, -nl)
        cr.line_to(-nw, 0)
        cr.line_to( nw, 0)
        cr.close_path()
        cr.set_source_rgba(0.95, 0.22, 0.22, 0.92)
        cr.fill()

        # South half (white/silver)
        cr.new_path()
        cr.move_to(0,  sl)
        cr.line_to(-nw, 0)
        cr.line_to( nw, 0)
        cr.close_path()
        cr.set_source_rgba(0.88, 0.90, 0.95, 0.80)
        cr.fill()

        cr.restore()

        # Pivot dot (drawn after restore, no rotation needed)
        cr.arc(cx, cy, r * 0.09, 0, pi2)
        cr.set_source_rgba(0.10, 0.12, 0.18, 0.95)
        cr.fill()
        cr.arc(cx, cy, r * 0.09, 0, pi2)
        cr.set_source_rgba(1, 1, 1, 0.40)
        cr.set_line_width(0.8)
        cr.stroke()

        # Hover highlight ring — shown in manual mode when mouse is over compass
        if (self._hw_heading is None
                and getattr(self, '_hover_compass', False)):
            cr.arc(cx, cy, r + 2, 0, pi2)
            cr.set_source_rgba(0.50, 0.80, 1.0, 0.55)
            cr.set_line_width(2.0)
            cr.stroke()
            # Small "click to set facing" label below compass
            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(9)
            cr.set_source_rgba(0.70, 0.88, 1.0, 0.80)
            lbl = _t('click to set facing')
            ext = cr.text_extents(lbl)
            cr.move_to(cx - ext.width / 2, cy + r + 14)
            cr.show_text(lbl)

    # ── Horizon silhouette ───────────────────────────────────────────────────

    def _draw_horizon_silhouette(self, cr, W, H):
        rng  = random.Random(0xA5B2)
        y0   = H * 0.72
        # Build list of (x_peak, y_peak, seg_width) peaks
        peaks = []
        x = 0.0
        while x < W + W * 0.05:
            seg   = rng.uniform(W * 0.014, W * 0.048)
            shape = rng.random()
            if shape < 0.25:
                ht = rng.uniform(H * 0.06, H * 0.13)
            elif shape < 0.55:
                ht = rng.uniform(H * 0.02, H * 0.055)
            else:
                ht = rng.uniform(0.0, H * 0.018)
            peaks.append((x + seg * 0.5, y0 - ht, seg))
            x += seg

        cr.new_path()
        cr.move_to(0, H)
        cr.line_to(0, y0)

        for i, (px, py, sw) in enumerate(peaks):
            if i == 0:
                cr.curve_to(px - sw * 0.40, y0, px - sw * 0.15, py, px, py)
            else:
                ppx, ppy, psw = peaks[i - 1]
                mid_x = (ppx + px) / 2.0
                cr.curve_to(ppx + psw * 0.30, ppy, mid_x - sw * 0.12, y0, mid_x, y0)
                cr.curve_to(mid_x + sw * 0.12, y0, px - sw * 0.20,   py, px,     py)

        if peaks:
            lpx, _, lsw = peaks[-1]
            cr.curve_to(lpx + lsw * 0.30, y0, W, y0, W, y0)

        cr.line_to(W, H)
        cr.close_path()
        cr.set_source_rgba(0.04, 0.07, 0.04, 0.72)
        cr.fill()

    # ── Shooting stars ───────────────────────────────────────────────────────

    def _maybe_spawn_meteor(self, W, H):
        if random.random() > 0.006:
            return
        now = time.time()
        rng = random.Random(int(now * 1000))
        sx  = rng.uniform(0.05 * W, 0.92 * W)
        sy  = rng.uniform(0.03 * H, 0.42 * H)
        ang = rng.uniform(math.pi * 0.25, math.pi * 0.75)
        spd = rng.uniform(W * 0.20, W * 0.52)
        dur = rng.uniform(0.5, 1.4)
        lng = rng.uniform(W * 0.04, W * 0.11)
        self._meteors.append({
            'sx': sx, 'sy': sy, 'ang': ang, 'spd': spd,
            'start': now, 'dur': dur, 'lng': lng,
        })

    def _draw_meteors(self, cr, W, H):
        now   = time.time()
        still = []
        for m in self._meteors:
            t = (now - m['start']) / m['dur']
            if t >= 1.0:
                continue
            fade = math.sin(t * math.pi)
            dist = m['spd'] * m['dur'] * t
            ex   = m['sx'] + math.cos(m['ang']) * dist
            ey   = m['sy'] + math.sin(m['ang']) * dist
            bx   = ex - math.cos(m['ang']) * m['lng']
            by   = ey - math.sin(m['ang']) * m['lng']
            grad = cairo.LinearGradient(bx, by, ex, ey)
            grad.add_color_stop_rgba(0.00, 1.00, 0.50, 0.15, 0.00)          # orange tail fades
            grad.add_color_stop_rgba(0.35, 1.00, 0.78, 0.42, fade * 0.38)   # warm yellow
            grad.add_color_stop_rgba(0.70, 0.55, 0.95, 0.68, fade * 0.80)   # green-teal
            grad.add_color_stop_rgba(1.00, 0.88, 0.98, 0.92, fade * 1.00)   # white-green head
            cr.move_to(bx, by)
            cr.line_to(ex, ey)
            cr.set_source(grad)
            cr.set_line_width(1.5)
            cr.stroke()
            still.append(m)
        self._meteors = still

    # ── Sun ──────────────────────────────────────────────────────────────────

    def _draw_sun(self, cr, x, y, el, scale):
        # Real naked-eye sun: no visible disc, just a blinding bloom of light.
        # Three nested SCREEN-blended layers create the overexposed appearance.
        r = 16 * scale
        t = _clamp(el / 20.0, 0.0, 1.0)   # 0=horizon, 1=high sun

        cr.save()
        cr.set_operator(cairo.Operator.SCREEN)

        # Layer 1 — wide atmospheric diffusion (brightens a large sky area)
        wr = r * 16
        w = cairo.RadialGradient(x, y, 0, x, y, wr)
        w.add_color_stop_rgba(0.00, 1.0, 0.80 + 0.18*t, 0.30 + 0.55*t, 0.50)
        w.add_color_stop_rgba(0.18, 1.0, 0.65 + 0.15*t, 0.18 + 0.25*t, 0.18)
        w.add_color_stop_rgba(0.45, 1.0, 0.50,           0.10,           0.05)
        w.add_color_stop_rgba(1.00, 0.0, 0.0,            0.0,            0.00)
        cr.arc(x, y, wr, 0, 2 * math.pi)
        cr.set_source(w)
        cr.fill()

        # Layer 2 — bright bloom (main visible glare)
        br = r * 5
        b = cairo.RadialGradient(x, y, 0, x, y, br)
        b.add_color_stop_rgba(0.00, 1.0, 1.0,            0.88 + 0.12*t, 0.92)
        b.add_color_stop_rgba(0.25, 1.0, 0.90 + 0.10*t, 0.55 + 0.35*t, 0.75)
        b.add_color_stop_rgba(0.65, 1.0, 0.70,           0.28,           0.28)
        b.add_color_stop_rgba(1.00, 0.0, 0.0,            0.0,            0.00)
        cr.arc(x, y, br, 0, 2 * math.pi)
        cr.set_source(b)
        cr.fill()

        # Layer 3 — overexposed white-hot core (pure white, fully blown out)
        cr_r = r * 1.2
        c = cairo.RadialGradient(x, y, 0, x, y, cr_r)
        c.add_color_stop_rgba(0.00, 1.0, 1.0, 1.0, 1.00)
        c.add_color_stop_rgba(0.50, 1.0, 1.0, 0.95, 0.90)
        c.add_color_stop_rgba(1.00, 1.0, 0.90, 0.60, 0.00)
        cr.arc(x, y, cr_r, 0, 2 * math.pi)
        cr.set_source(c)
        cr.fill()

        cr.restore()

    # ── Moon ─────────────────────────────────────────────────────────────────

    def _draw_moon(self, cr, x, y, phase, scale, limb_angle=0.0):
        r = 32 * scale
        self._draw_lunar_halo(cr, x, y, r, self._clouds, phase)

        # Glow — unrotated, centered on screen pos
        glow = cairo.RadialGradient(x, y, r * 0.4, x, y, r * 3.5)
        glow.add_color_stop_rgba(0.0, 0.92, 0.91, 0.84, 0.55)
        glow.add_color_stop_rgba(0.4, 0.78, 0.76, 0.68, 0.18)
        glow.add_color_stop_rgba(1.0, 0.55, 0.53, 0.46, 0.00)
        cr.arc(x, y, r * 3.5, 0, 2 * math.pi)
        cr.set_source(glow)
        cr.fill()

        # Disc in local coords, rotated so lit side faces the sun
        # limb_angle: direction from moon toward sun in world (y-up) coords
        # canonical: lit side on +x (right); cr.rotate(-limb_angle) orients it correctly
        cr.save()
        cr.translate(x, y)
        cr.rotate(-limb_angle)

        cr.arc(0, 0, r, 0, 2 * math.pi)
        cr.clip()
        cr.set_source_rgba(0.16, 0.20, 0.45, 0.03)
        cr.paint()

        t = math.cos(phase * 2 * math.pi)
        cr.set_source_rgba(0.96, 0.94, 0.86, 1.0)
        if t < -0.95:
            # Full moon: fill entire disc
            cr.arc(0, 0, r, 0, 2 * math.pi)
            cr.fill()
        else:
            # Waxing OR waning: always draw lit side on +x; limb_angle rotation handles direction
            cr.move_to(0, -r)
            cr.arc(0, 0, r, -math.pi / 2, math.pi / 2)
            cr.save()
            cr.scale(t, 1.0)
            cr.arc_negative(0, 0, r, math.pi / 2, -math.pi / 2)
            cr.restore()
            cr.close_path()
            cr.fill()
        cr.restore()

    # ── Weather icon (Cairo-drawn, no external files) ─────────────────────────

    def _draw_wx_icon(self, cr, cx, cy, size, sym):
        """Draw a weather icon centred at (cx, cy) fitting in size × size."""
        if not sym:
            return
        s = size * 0.5
        cr.save()

        # ── helpers ──────────────────────────────────────────────────────────

        def _sun(ox=0.0, oy=0.0, r=None, alpha=0.95):
            r = r if r is not None else s * 0.44
            cr.set_source_rgba(1.0, 0.88, 0.22, alpha)
            cr.arc(cx + ox, cy + oy, r * 0.48, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(1.0, 0.88, 0.22, alpha * 0.70)
            cr.set_line_width(max(1.0, r * 0.14))
            for i in range(8):
                a = i * math.pi / 4
                cr.move_to(cx + ox + r * 0.63 * math.cos(a),
                           cy + oy + r * 0.63 * math.sin(a))
                cr.line_to(cx + ox + r * 0.92 * math.cos(a),
                           cy + oy + r * 0.92 * math.sin(a))
                cr.stroke()

        def _cloud(ox=0.0, oy=0.0, r=None, gray=0.82, alpha=0.92):
            r = r if r is not None else s * 0.50
            g = gray
            cr.push_group()
            cr.set_source_rgba(g, g + 0.02, g + 0.04, 1.0)
            for dx, dy, ri in [(-0.50, 0.12, 0.52),
                                ( 0.45, 0.12, 0.52),
                                (-0.05, -0.12, 0.70)]:
                cr.arc(cx + ox + dx * r, cy + oy + dy * r,
                       ri * r, 0, 2 * math.pi)
                cr.fill()
            cr.rectangle(cx + ox - r * 0.97, cy + oy + r * 0.02,
                         r * 1.94, r * 0.60)
            cr.fill()
            cr.pop_group_to_source()
            cr.paint_with_alpha(alpha)

        def _drops(n=2, ox=0.0, oy=0.0, r=None):
            r = r if r is not None else s
            spacing = r * 0.38
            x0d = cx + ox - spacing * (n - 1) / 2
            for i in range(n):
                xi = x0d + i * spacing
                cr.set_source_rgba(0.40, 0.68, 1.00, 0.92)
                cr.set_line_width(max(1.2, r * 0.11))
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                cr.move_to(xi, cy + oy + r * 0.44)
                cr.line_to(xi - r * 0.07, cy + oy + r * 0.72)
                cr.stroke()

        def _snow_dots(n=2, ox=0.0, oy=0.0, r=None):
            r = r if r is not None else s
            spacing = r * 0.38
            x0d = cx + ox - spacing * (n - 1) / 2
            cr.set_source_rgba(0.78, 0.92, 1.00, 0.90)
            for i in range(n):
                xi = x0d + i * spacing
                yi = cy + oy + r * 0.60
                if size >= 22:
                    # small 6-arm asterisk
                    cr.set_line_width(max(1.0, r * 0.10))
                    cr.set_line_cap(cairo.LINE_CAP_ROUND)
                    arm = max(1.5, r * 0.14)
                    for a in (0, math.pi / 3, 2 * math.pi / 3):
                        cr.move_to(xi - arm * math.cos(a), yi - arm * math.sin(a))
                        cr.line_to(xi + arm * math.cos(a), yi + arm * math.sin(a))
                        cr.stroke()
                else:
                    cr.arc(xi, yi, max(1.5, r * 0.11), 0, 2 * math.pi)
                    cr.fill()

        def _bolt(ox=0.0, oy=0.0, r=None):
            r = r if r is not None else s
            cr.set_source_rgba(1.00, 0.92, 0.18, 0.97)
            cr.set_line_width(max(1.5, r * 0.16))
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            pts = [(0.10, 0.08), (-0.08, 0.40),
                   (0.06, 0.40), (-0.10, 0.78)]
            cr.move_to(cx + ox + r * pts[0][0], cy + oy + r * pts[0][1])
            for px, py in pts[1:]:
                cr.line_to(cx + ox + r * px, cy + oy + r * py)
            cr.stroke()

        def _fog(ox=0.0, oy=0.0, r=None):
            r = r if r is not None else s
            cr.set_source_rgba(0.72, 0.78, 0.86, 0.80)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_width(max(1.5, r * 0.14))
            for yi_f, x1_f, x2_f in [(-0.30, -0.90, 0.90),
                                       ( 0.02, -0.75, 0.75),
                                       ( 0.34, -0.82, 0.60)]:
                cr.move_to(cx + ox + x1_f * r, cy + oy + yi_f * r)
                cr.line_to(cx + ox + x2_f * r, cy + oy + yi_f * r)
                cr.stroke()

        # ── symbol → composition ─────────────────────────────────────────────
        has_thunder  = 'thunder'  in sym
        has_rain     = 'rain'     in sym
        has_snow     = 'snow'     in sym
        has_sleet    = 'sleet'    in sym
        has_showers  = 'showers'  in sym
        has_heavy    = 'heavy'    in sym
        has_light    = 'light'    in sym
        is_sun_part  = has_showers and not has_thunder

        if sym == 'clearsky':
            _sun()
        elif sym == 'fair':
            _sun(ox=-s*0.14, oy=-s*0.18, r=s*0.36)
            _cloud(ox=s*0.10, oy=s*0.16, r=s*0.40, gray=0.76)
        elif sym == 'partlycloudy':
            _sun(ox=-s*0.20, oy=-s*0.22, r=s*0.32)
            _cloud(ox=s*0.08, oy=s*0.12, r=s*0.46, gray=0.74)
        elif sym in ('cloudy', 'overcast'):
            _cloud(r=s*0.54)
        elif sym == 'fog':
            _fog()
        elif has_thunder:
            cloud_gray = 0.42 if has_heavy else 0.52
            _cloud(oy=-s*0.14, r=s*0.46, gray=cloud_gray, alpha=0.95)
            if has_rain or has_sleet:
                _drops(1, ox=-s*0.25, oy=s*0.04)
            elif has_snow:
                _snow_dots(1, ox=-s*0.25, oy=s*0.04)
            _bolt(oy=s*0.06)
        else:
            # cloud + precipitation (with optional partial sun for showers)
            n_precip = 1 if has_light else (3 if has_heavy else 2)
            cloud_gray = 0.62 if has_heavy else (0.72 if has_light else 0.66)
            if is_sun_part:
                _sun(ox=-s*0.22, oy=-s*0.28, r=s*0.30)
                _cloud(ox=s*0.06, oy=s*0.10, r=s*0.44,
                       gray=cloud_gray, alpha=0.90)
            else:
                _cloud(oy=-s*0.12, r=s*0.46, gray=cloud_gray, alpha=0.92)
            if has_snow:
                _snow_dots(n_precip, oy=s*0.04)
            elif has_sleet:
                _drops(max(1, n_precip - 1), ox=-s*0.15, oy=s*0.04)
                _snow_dots(1, ox=s*0.20, oy=s*0.04)
            else:
                _drops(n_precip, oy=s*0.04)

        cr.restore()

    # ── Weekly forecast column (accordion) ───────────────────────────────────

    def _draw_weekly_forecast(self, cr, W, H):
        daily = self._clouds.get('daily_forecast', [])
        if not daily:
            self._weekly_card_rects = []
            return

        CARD_W   = 210
        DAY_H    = 52
        HOUR_H   = 28
        DAY_GAP  = 5
        HOUR_GAP = 2
        MARGIN   = 14
        x0       = W - CARD_W - MARGIN - self._insets[2]
        tz_off   = self.cfg.get('timezone_offset', 0)
        today_str = self._today_str

        # Compute max days that fit without overflowing screen height
        y_start  = 74 + self._insets[1]
        max_h    = H - y_start - MARGIN - self._insets[3]
        n_hourly = len(self._selected_day_slots)
        expanded_h = (DAY_H + DAY_GAP) + n_hourly * (HOUR_H + HOUR_GAP) + DAY_GAP
        remaining  = max_h - expanded_h
        extra_days = max(0, int(remaining // (DAY_H + DAY_GAP)))
        # 1 selected day is always shown; up to 6 more fit
        max_days   = 1 + extra_days if self._selected_day else int(max_h // (DAY_H + DAY_GAP))
        max_days   = min(max_days, 7)

        rects = []
        y     = y_start

        for day in daily[:max_days]:
            date_str = day.get('date', '')
            sym      = day.get('symbol', '')
            temp_max = day.get('temp_max')
            temp_min = day.get('temp_min')
            precip   = day.get('precip', 0.0)
            accent   = _WX_ACCENT.get(sym, (0.72, 0.82, 1.00))
            cond_lbl = _WX_LABEL.get(sym, sym.replace('_', ' ').title() if sym else '--')
            selected = (self._selected_day == date_str)

            if date_str == today_str:
                day_name = _t('Today')
            else:
                try:
                    day_name = _day_name(datetime.date.fromisoformat(date_str).weekday())
                except Exception:
                    day_name = '--'

            # ── Day card ─────────────────────────────────────────────────────
            rects.append((date_str, x0, y, CARD_W, DAY_H))

            self._rrect(cr, x0, y, CARD_W, DAY_H, 9)
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.62 if selected else 0.48)
            cr.fill_preserve()
            cr.set_source_rgba(*accent, 0.55 if selected else 0.20)
            cr.set_line_width(1.8 if selected else 1.0)
            cr.stroke()

            if selected:
                cr.set_source_rgba(*accent, 0.85)
                cr.rectangle(x0, y + 8, 3, DAY_H - 16)
                cr.fill()

            # Weather icon — centre of card
            self._draw_wx_icon(cr, x0 + 104, y + 26, 32, sym)

            # Left column: day name + condition
            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(11)
            cr.set_source_rgba(*accent, 1.0 if selected else 0.92)
            cr.move_to(x0 + 10, y + 20)
            cr.show_text(day_name)

            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(9)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.90 if selected else 0.68)
            cr.move_to(x0 + 10, y + 36)
            cr.show_text(_t(cond_lbl))

            if precip >= 0.2:
                cr.set_font_size(8.5)
                cr.set_source_rgba(0.50, 0.82, 1.00, 0.85)
                cr.move_to(x0 + 10, y + 48)
                cr.show_text(f"{precip:.1f} mm")

            if temp_max is not None:
                cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(15)
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
                s = f"{temp_max:.0f}°"
                te = cr.text_extents(s)
                cr.move_to(x0 + CARD_W - 12 - te.width, y + 22)
                cr.show_text(s)

            if temp_min is not None:
                cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                cr.set_font_size(10)
                cr.set_source_rgba(0.75, 0.82, 1.0, 0.58)
                s = f"{temp_min:.0f}°"
                te = cr.text_extents(s)
                cr.move_to(x0 + CARD_W - 12 - te.width, y + 38)
                cr.show_text(s)

            y += DAY_H + DAY_GAP

            # ── Hourly accordion (only for selected day) ──────────────────────
            if selected:
                slots = self._selected_day_slots
                xi = x0 + 10   # indent hourly cards slightly
                wi = CARD_W - 10

                for slot in slots:
                    try:
                        raw = slot['ts'].rstrip('Z')
                        dt_local = (datetime.datetime.fromisoformat(raw)
                                    + datetime.timedelta(hours=tz_off))
                        time_lbl = f"{dt_local.hour:02d}:00"
                    except Exception:
                        time_lbl = '--:--'

                    sym_h    = slot.get('symbol', '')
                    cond_h   = _t(_WX_LABEL.get(sym_h,
                                                 sym_h.replace('_', ' ').title() if sym_h else '--'))
                    temp_h = slot.get('temp', 0.0)
                    prcp_h = slot.get('precip', 0.0)
                    acc_h  = _WX_ACCENT.get(sym_h, (0.72, 0.82, 1.00))

                    # Background
                    self._rrect(cr, xi, y, wi, HOUR_H, 6)
                    cr.set_source_rgba(0.04, 0.07, 0.16, 0.55)
                    cr.fill_preserve()
                    cr.set_source_rgba(*acc_h, 0.14)
                    cr.set_line_width(0.5)
                    cr.stroke()

                    ty = y + HOUR_H * 0.64

                    # Time — accent, bold
                    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL,
                                        cairo.FONT_WEIGHT_BOLD)
                    cr.set_font_size(9)
                    cr.set_source_rgba(*acc_h, 0.95)
                    cr.move_to(xi + 7, ty)
                    cr.show_text(time_lbl)

                    # Small weather icon
                    self._draw_wx_icon(cr, xi + 42, y + HOUR_H * 0.50, 18, sym_h)

                    # Condition (+ precip inline)
                    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL,
                                        cairo.FONT_WEIGHT_NORMAL)
                    cr.set_font_size(8.5)
                    if prcp_h >= 0.1:
                        cr.set_source_rgba(0.55, 0.85, 1.00, 0.85)
                        cr.move_to(xi + 56, ty)
                        cr.show_text(f"{cond_h}  {prcp_h:.1f}mm")
                    else:
                        cr.set_source_rgba(1.0, 1.0, 1.0, 0.72)
                        cr.move_to(xi + 56, ty)
                        cr.show_text(cond_h)

                    # Temperature — right-aligned, bold
                    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL,
                                        cairo.FONT_WEIGHT_BOLD)
                    cr.set_font_size(10)
                    cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
                    t_str = f"{temp_h:.0f}°"
                    te = cr.text_extents(t_str)
                    cr.move_to(xi + wi - 8 - te.width, ty)
                    cr.show_text(t_str)

                    y += HOUR_H + HOUR_GAP

                y += DAY_GAP  # breathing room after expanded section

        self._weekly_card_rects = rects

    # ── HUD cards ────────────────────────────────────────────────────────────

    def _draw_cards(self, cr, W, H, now, sun_el, phase, age, m_el=None):
        cfg     = self.cfg
        enabled = cfg.get('cards', DEFAULT_CONFIG['cards'])
        lat, lon = cfg['latitude'], cfg['longitude']
        clouds  = self._clouds

        CW, CH, GAP = 198, 60, 10
        START_X     = 18
        START_Y     = H * 0.72
        col = row = 0

        IC = 20     # icon size in px
        ICA = 0.68  # icon alpha

        def emit(title, value, sub=None, icon_fn=None):
            nonlocal col, row
            cx = START_X + col * (CW + GAP)
            cy = START_Y + row * (CH + GAP)
            self._card(cr, cx, cy, CW, CH, title, value, sub)
            if icon_fn:
                cr.save()
                cr.new_path()   # clear current point left by _card's show_text
                icon_fn(cx + CW - IC - 8, cy + (CH - IC) / 2)
                cr.new_path()   # ensure nothing bleeds into next draw call
                cr.restore()
            col += 1
            if col >= 3:
                col = 0
                row += 1

        def ic_clock(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_source_rgba(0.75, 0.85, 1.0, ICA)
            cr.set_line_width(1.3)
            cr.arc(icx, icy, r - 0.5, 0, 2 * math.pi)
            cr.stroke()
            # hour hand
            h_a = (now.hour % 12 + now.minute / 60) / 12 * 2 * math.pi - math.pi / 2
            cr.set_line_width(2.0)
            cr.move_to(icx, icy)
            cr.line_to(icx + (r - 4) * 0.58 * math.cos(h_a),
                       icy + (r - 4) * 0.58 * math.sin(h_a))
            cr.stroke()
            # minute hand
            m_a = now.minute / 60 * 2 * math.pi - math.pi / 2
            cr.set_line_width(1.2)
            cr.move_to(icx, icy)
            cr.line_to(icx + (r - 2) * 0.82 * math.cos(m_a),
                       icy + (r - 2) * 0.82 * math.sin(m_a))
            cr.stroke()
            cr.arc(icx, icy, 1.5, 0, 2 * math.pi)
            cr.fill()

        def ic_pin(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r * 0.9
            cr.set_source_rgba(0.75, 0.85, 1.0, ICA)
            cr.set_line_width(1.3)
            # Circle body
            cr.arc(icx, icy - r * 0.30, r * 0.58, 0, 2 * math.pi)
            cr.stroke()
            # Inner dot
            cr.arc(icx, icy - r * 0.30, r * 0.20, 0, 2 * math.pi)
            cr.fill()
            # Pointed tail
            cr.move_to(icx - r * 0.48, icy - r * 0.08)
            cr.line_to(icx, icy + r * 0.88)
            cr.line_to(icx + r * 0.48, icy - r * 0.08)
            cr.stroke()

        def ic_sunrise(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r * 1.05
            cr.set_source_rgba(1.0, 0.75, 0.25, ICA)
            cr.set_line_width(1.3)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            # Horizon line
            cr.move_to(icx - r * 0.95, icy)
            cr.line_to(icx + r * 0.95, icy)
            cr.stroke()
            # Sun semi-circle
            cr.arc(icx, icy, r * 0.50, math.pi, 0)
            cr.stroke()
            # Rays (top only)
            for a_deg in (-60, -30, 0, 30, 60):
                a = math.radians(a_deg - 90)
                cr.move_to(icx + r * 0.65 * math.cos(a), icy + r * 0.65 * math.sin(a))
                cr.line_to(icx + r * 0.90 * math.cos(a), icy + r * 0.90 * math.sin(a))
                cr.stroke()
            # Up arrow
            cr.set_source_rgba(0.55, 1.0, 0.55, ICA * 0.80)
            cr.set_line_width(1.2)
            cr.move_to(icx, icy - r * 0.55)
            cr.line_to(icx, icy + r * 0.30)
            cr.stroke()
            cr.move_to(icx - r * 0.28, icy - r * 0.28)
            cr.line_to(icx, icy - r * 0.55)
            cr.line_to(icx + r * 0.28, icy - r * 0.28)
            cr.stroke()

        def ic_solar_noon(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r * 1.10
            cr.set_source_rgba(1.0, 0.88, 0.22, ICA)
            cr.set_line_width(1.3)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            # Sun disc
            cr.arc(icx, icy - r * 0.35, r * 0.38, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(1.0, 0.88, 0.22, ICA * 0.65)
            # Full rays around
            for i in range(8):
                a = i * math.pi / 4
                cr.move_to(icx + r * 0.55 * math.cos(a),
                           icy - r * 0.35 + r * 0.55 * math.sin(a))
                cr.line_to(icx + r * 0.80 * math.cos(a),
                           icy - r * 0.35 + r * 0.80 * math.sin(a))
                cr.stroke()
            # Horizon line
            cr.set_source_rgba(1.0, 0.88, 0.22, ICA * 0.45)
            cr.set_line_width(1.0)
            cr.move_to(icx - r * 0.95, icy + r * 0.65)
            cr.line_to(icx + r * 0.95, icy + r * 0.65)
            cr.stroke()

        def ic_moon_phase(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r
            # Dark disc
            cr.set_source_rgba(0.10, 0.12, 0.22, 0.90)
            cr.arc(icx, icy, r - 0.5, 0, 2 * math.pi)
            cr.fill()
            # Outline
            cr.set_source_rgba(0.75, 0.82, 1.0, ICA * 0.60)
            cr.set_line_width(0.8)
            cr.arc(icx, icy, r - 0.5, 0, 2 * math.pi)
            cr.stroke()
            # Lit crescent with correct limb orientation
            t = math.cos(phase * 2 * math.pi)
            cr.set_source_rgba(0.96, 0.94, 0.86, 0.95)
            cr.save()
            cr.translate(icx, icy)
            cr.rotate(-self._moon_limb_angle)
            rr = r - 1.5
            if t < -0.95:
                cr.arc(0, 0, rr, 0, 2 * math.pi)
                cr.fill()
            elif t > 0.95:
                pass  # new moon — nothing lit
            else:
                cr.move_to(0, -rr)
                cr.arc(0, 0, rr, -math.pi / 2, math.pi / 2)
                cr.save()
                cr.scale(t, 1.0)
                cr.arc_negative(0, 0, rr, math.pi / 2, -math.pi / 2)
                cr.restore()
                cr.close_path()
                cr.fill()
            cr.restore()

        def ic_moon_rise(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r
            cr.set_source_rgba(0.75, 0.82, 1.0, ICA)
            cr.set_line_width(1.2)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            # Crescent (simple left-facing)
            cr.arc(icx + r * 0.08, icy, r * 0.62, math.pi * 0.55, math.pi * 1.45)
            cr.stroke()
            cr.arc_negative(icx + r * 0.35, icy, r * 0.52,
                            math.pi * 1.45, math.pi * 0.55)
            cr.stroke()
            # Up/down arrows (rise left, set right)
            cr.set_source_rgba(0.55, 1.0, 0.55, ICA * 0.75)
            cr.set_line_width(1.0)
            ax = icx - r * 0.75
            cr.move_to(ax, icy + r * 0.25)
            cr.line_to(ax, icy - r * 0.60)
            cr.stroke()
            cr.move_to(ax - r * 0.22, icy - r * 0.35)
            cr.line_to(ax, icy - r * 0.60)
            cr.line_to(ax + r * 0.22, icy - r * 0.35)
            cr.stroke()
            cr.set_source_rgba(1.0, 0.60, 0.55, ICA * 0.75)
            ax2 = icx + r * 0.90
            cr.move_to(ax2, icy - r * 0.60)
            cr.line_to(ax2, icy + r * 0.25)
            cr.stroke()
            cr.move_to(ax2 - r * 0.22, icy + r * 0.0)
            cr.line_to(ax2, icy + r * 0.25)
            cr.line_to(ax2 + r * 0.22, icy + r * 0.0)
            cr.stroke()

        def ic_daylight(ix, iy, pct=0.5, is_night=False):
            r = IC / 2
            icx, icy = ix + r, iy + r * 1.05
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            # Track arc (full semicircle)
            cr.set_source_rgba(0.75, 0.85, 1.0, ICA * 0.28)
            cr.set_line_width(2.5)
            cr.arc(icx, icy, r * 0.75, math.pi, 0)
            cr.stroke()
            if not is_night:
                # Elapsed arc
                cr.set_source_rgba(1.0, 0.80, 0.22, ICA * 0.85)
                end_a = math.pi - pct / 100.0 * math.pi
                cr.arc_negative(icx, icy, r * 0.75, math.pi, end_a)
                cr.stroke()
                # Sun position dot on arc
                sun_a = math.pi - pct / 100.0 * math.pi
                cr.set_source_rgba(1.0, 0.88, 0.22, 0.95)
                cr.arc(icx + r * 0.75 * math.cos(sun_a),
                       icy + r * 0.75 * math.sin(sun_a), 2.5, 0, 2 * math.pi)
                cr.fill()
            # Horizon base line
            cr.set_source_rgba(0.75, 0.85, 1.0, ICA * 0.40)
            cr.set_line_width(1.0)
            cr.move_to(icx - r * 0.85, icy)
            cr.line_to(icx + r * 0.85, icy)
            cr.stroke()

        # ── Cloud badge — top right (always) ─────────────────────────────────
        if enabled.get('cloud_cover', True):
            _wdirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
                      'S','SSW','SW','WSW','W','WNW','NW','NNW']
            _wlbl  = _wdirs[int((clouds.get('wind_dir', 0) + 11.25) / 22.5) % 16]
            extra  = []
            if clouds.get('temp') is not None:
                extra.append(f"{clouds['temp']:.0f}°C")
            if clouds.get('wind_speed', 0) > 0.5:
                extra.append(f"{_wlbl} {clouds['wind_speed']:.0f} m/s")
            # Own layout instead of _card: _card's subtitle row assumes a taller card and
            # overlapped the value here. Width/x match the weekly forecast column below (y=74).
            bx, by, bw, bh = W - 224, 18, 210, 50
            cr.save()
            self._rrect(cr, bx, by, bw, bh, 9)
            cr.set_source_rgba(0, 0, 0, 0.42)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.13)
            cr.set_line_width(1)
            cr.stroke()
            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(9.5)
            cr.set_source_rgba(0.75, 0.82, 1.0, 0.70)
            cr.move_to(bx + 11, by + 15)
            cr.show_text(_t('CLOUD COVER'))
            value = f"{clouds['total']:.0f}%"
            cr.set_font_size(15.5)
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.move_to(bx + 11, by + 33)
            cr.show_text(value)
            if extra:
                vx = bx + 11 + cr.text_extents(value).x_advance + 8
                cr.set_font_size(9.5)
                cr.set_source_rgba(0.85, 0.90, 1.0, 0.75)
                cr.move_to(vx, by + 33)
                cr.show_text('  ·  '.join(extra))
            cr.set_font_size(9)
            cr.set_source_rgba(0.65, 0.78, 1.0, 0.60)
            cr.move_to(bx + 11, by + bh - 6)
            cr.show_text(f"Lo {clouds['low']:.0f}%  Mid {clouds['mid']:.0f}%  Hi {clouds['high']:.0f}%")
            cr.restore()
            # Cloud cover weather icon
            wx_sym = clouds.get('symbol', '')
            if wx_sym:
                cr.new_path()
                self._draw_wx_icon(cr, bx + bw - 22, by + 22, 26, wx_sym)

        if enabled.get('clock'):
            emit(_t('LOCAL TIME'), now.strftime('%H:%M:%S'),
                 _fmt_date(now), icon_fn=ic_clock)

        if enabled.get('location'):
            city = self._city_name
            if city:
                emit(_t('LOCATION'), city,
                     f"{'N' if lat >= 0 else 'S'}{abs(lat):.3f}°  "
                     f"{'E' if lon >= 0 else 'W'}{abs(lon):.3f}°",
                     icon_fn=ic_pin)
            else:
                emit(_t('LOCATION'),
                     f"{'N' if lat >= 0 else 'S'} {abs(lat):.4f}°",
                     f"{'E' if lon >= 0 else 'W'} {abs(lon):.4f}°",
                     icon_fn=ic_pin)

        if enabled.get('sunrise_sunset'):
            sr = self._sunrise.strftime('%H:%M') if self._sunrise else '--:--'
            ss = self._sunset.strftime('%H:%M')  if self._sunset  else '--:--'
            emit(_t('SUNRISE / SUNSET'), f'{sr}  ·  {ss}',
                 f'Solar elev: {sun_el:+.1f}°', icon_fn=ic_sunrise)

        if enabled.get('solar_noon'):
            sn = self._s_noon.strftime('%H:%M') if self._s_noon else '--:--'
            emit(_t('SOLAR NOON'), sn, f'Max elev: {self._max_el:.1f}°',
                 icon_fn=ic_solar_noon)

        if enabled.get('moon_phase'):
            el_str = f'  El: {m_el:+.1f}' if m_el is not None else ''
            emit(_t('MOON PHASE'), _t(_PHASE_NAMES[phase_index(phase)]),
                 f'Age: {age:.1f}d{el_str}', icon_fn=ic_moon_phase)

        if enabled.get('moon_rise_set'):
            mr = self._moonrise.strftime('%H:%M') if self._moonrise else '--:--'
            ms = self._moonset.strftime('%H:%M')  if self._moonset  else '--:--'
            emit(_t('MOONRISE / MOONSET'), f'{mr}  /  {ms}', icon_fn=ic_moon_rise)

        if enabled.get('daylight_remaining') and self._sunrise and self._sunset:
            now_s = now.hour * 3600 + now.minute * 60 + now.second
            sr_s  = self._sunrise.hour * 3600 + self._sunrise.minute * 60
            ss_s  = self._sunset.hour  * 3600 + self._sunset.minute  * 60
            if sr_s <= now_s <= ss_s:
                rem = ss_s - now_s
                pct = (now_s - sr_s) / max(1, ss_s - sr_s) * 100
                emit(_t('DAYLIGHT LEFT'),
                     f'{rem // 3600}h {(rem % 3600) // 60:02d}m',
                     _t('pct_elapsed').format(pct=int(pct)),
                     icon_fn=lambda ix, iy, p=pct: ic_daylight(ix, iy, p, False))
            else:
                until = (sr_s - now_s) % 86400
                emit(_t('DAYLIGHT LEFT'),
                     _t('sunrise_in').format(h=until // 3600, m=(until % 3600) // 60),
                     _t('Night'),
                     icon_fn=lambda ix, iy: ic_daylight(ix, iy, 0, True))

    def _card(self, cr, x, y, w, h, title, value, sub=None):
        cr.save()
        self._rrect(cr, x, y, w, h, 9)
        cr.set_source_rgba(0, 0, 0, 0.42)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.13)
        cr.set_line_width(1)
        cr.stroke()

        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(9.5)
        cr.set_source_rgba(0.75, 0.82, 1.0, 0.70)
        cr.move_to(x + 11, y + 17)
        cr.show_text(title)

        cr.set_font_size(15.5)
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.move_to(x + 11, y + 37)
        cr.show_text(value)

        if sub:
            cr.set_font_size(9)
            cr.set_source_rgba(0.65, 0.78, 1.0, 0.60)
            cr.move_to(x + 11, y + h - 6)
            cr.show_text(sub)
        cr.restore()

    def _rrect(self, cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r,     r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r,  0,            math.pi / 2)
        cr.arc(x + r,     y + h - r, r,  math.pi / 2,  math.pi)
        cr.arc(x + r,     y + r,     r,  math.pi,      3 * math.pi / 2)
        cr.close_path()
