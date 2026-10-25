"""Settings dialog."""

import json
import threading
import urllib.request

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, GObject, Gtk

from .. import __version__
from ..core.config import DEFAULT_CONFIG, save_config
from ..core.i18n import _LANG_OPTIONS, _set_lang, _t
from .autostart import autostart_enabled, set_autostart

# ─── Timezone list ───────────────────────────────────────────────────────────
# (utc_offset_hours, display_label)
_TZ_LIST = [
    (-12,   'UTC-12'),
    (-11,   'UTC-11  (Samoa, Niue)'),
    (-10,   'UTC-10  (Hawaii)'),
    (-9.5,  'UTC-09:30  (Marquesas)'),
    (-9,    'UTC-09  (Alaska)'),
    (-8,    'UTC-08  (Los Angeles, Vancouver)'),
    (-7,    'UTC-07  (Denver, Phoenix)'),
    (-6,    'UTC-06  (Chicago, Mexico City)'),
    (-5,    'UTC-05  (New York, Lima, Bogota)'),
    (-4,    'UTC-04  (Santiago, Caracas, Halifax)'),
    (-3.5,  'UTC-03:30  (Newfoundland)'),
    (-3,    'UTC-03  (Buenos Aires, Brasilia, Montevideo)'),
    (-2,    'UTC-02  (South Georgia)'),
    (-1,    'UTC-01  (Azores, Cape Verde)'),
    ( 0,    'UTC+00  (London, Lisbon, Accra, Lome, Abidjan)'),
    ( 1,    'UTC+01  (Paris, Berlin, Lagos, Kinshasa, Madrid)'),
    ( 2,    'UTC+02  (Cairo, Johannesburg, Athens, Helsinki)'),
    ( 3,    'UTC+03  (Nairobi, Moscow, Riyadh, Istanbul)'),
    ( 3.5,  'UTC+03:30  (Tehran)'),
    ( 4,    'UTC+04  (Dubai, Baku, Tbilisi)'),
    ( 4.5,  'UTC+04:30  (Kabul)'),
    ( 5,    'UTC+05  (Karachi, Tashkent, Yekaterinburg)'),
    ( 5.5,  'UTC+05:30  (Mumbai, Delhi, Colombo)'),
    ( 5.75, 'UTC+05:45  (Kathmandu)'),
    ( 6,    'UTC+06  (Dhaka, Almaty, Bishkek)'),
    ( 6.5,  'UTC+06:30  (Yangon)'),
    ( 7,    'UTC+07  (Bangkok, Jakarta, Hanoi)'),
    ( 8,    'UTC+08  (Beijing, Singapore, Perth, Manila)'),
    ( 8.75, 'UTC+08:45  (Eucla)'),
    ( 9,    'UTC+09  (Tokyo, Seoul, Yakutsk)'),
    ( 9.5,  'UTC+09:30  (Adelaide, Darwin)'),
    (10,    'UTC+10  (Sydney, Melbourne, Vladivostok)'),
    (10.5,  'UTC+10:30  (Lord Howe)'),
    (11,    'UTC+11  (Solomon Islands, Noumea)'),
    (12,    'UTC+12  (Auckland, Fiji, Kamchatka)'),
    (12.75, 'UTC+12:45  (Chatham Islands)'),
    (13,    'UTC+13  (Apia, Nuku\'alofa)'),
    (14,    'UTC+14  (Kiribati, Line Islands)'),
]

def _tz_index(offset):
    """Return the index in _TZ_LIST closest to offset."""
    best, best_d = 0, float('inf')
    for i, (o, _) in enumerate(_TZ_LIST):
        d = abs(o - offset)
        if d < best_d:
            best, best_d = i, d
    return best

# ─── Facing-direction options ────────────────────────────────────────────────
# (azimuth_degrees, compass_abbrev, direction_i18n_key)
_FACING_OPTIONS = [
    (  0, 'N',  'Facing North'),
    ( 45, 'NE', 'Facing North-East'),
    ( 90, 'E',  'Facing East'),
    (135, 'SE', 'Facing South-East'),
    (180, 'S',  'Facing South (default)'),
    (225, 'SW', 'Facing South-West'),
    (270, 'W',  'Facing West'),
    (315, 'NW', 'Facing North-West'),
]

# ─── Layout helpers ──────────────────────────────────────────────────────────

def _separator_header(row, before):
    if before is not None and row.get_header() is None:
        row.set_header(Gtk.Separator())

def _group(page, title):
    """A titled boxed list, GNOME-settings style; returns the ListBox to add rows to."""
    head = Gtk.Label(xalign=0)
    head.set_markup(f'<b>{GLib.markup_escape_text(title)}</b>')
    head.set_margin_top(14)
    head.set_margin_bottom(6)
    page.pack_start(head, False, False, 0)
    lb = Gtk.ListBox()
    lb.set_selection_mode(Gtk.SelectionMode.NONE)
    lb.set_header_func(_separator_header)
    frame = Gtk.Frame()
    frame.add(lb)
    page.pack_start(frame, False, False, 0)
    return lb

def _row(lb, title, widget=None, subtitle=None, stacked=False):
    """Title (and dim subtitle) on the left, widget on the right — or below when stacked."""
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    text.set_hexpand(True)
    text.set_valign(Gtk.Align.CENTER)
    text.pack_start(Gtk.Label(label=title, xalign=0), False, False, 0)
    if subtitle:
        sub = Gtk.Label(xalign=0)
        sub.set_markup(f'<small>{GLib.markup_escape_text(subtitle)}</small>')
        sub.set_line_wrap(True)
        sub.set_max_width_chars(40)
        sub.get_style_context().add_class('dim-label')
        text.pack_start(sub, False, False, 0)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if stacked else Gtk.Orientation.HORIZONTAL,
                  spacing=6 if stacked else 12)
    for side in ('top', 'bottom'):
        getattr(box, f'set_margin_{side}')(8)
    for side in ('start', 'end'):
        getattr(box, f'set_margin_{side}')(12)
    box.pack_start(text, True, True, 0)
    if widget is not None:
        if not stacked:
            widget.set_valign(Gtk.Align.CENTER)
        box.pack_start(widget, stacked, stacked, 0)
    row = Gtk.ListBoxRow()
    row.set_activatable(False)
    row.set_can_focus(False)   # focus goes to the switch/entry, not a ring round the row
    row.add(box)
    lb.add(row)
    return row

def _page():
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    for side in ('start', 'end'):
        getattr(page, f'set_margin_{side}')(18)
    page.set_margin_bottom(18)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.add(page)
    return scroll, page

# ─── Settings dialog ──────────────────────────────────────────────────────────

class SettingsDialog(Gtk.Window):

    def __init__(self, parent):
        super().__init__(title='Caelum — Settings')
        self.par = parent
        self.cfg = parent.cfg
        self.set_default_size(440, 640)
        self.set_transient_for(parent)
        self.set_destroy_with_parent(True)

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        switcher = Gtk.StackSwitcher()
        switcher.set_stack(stack)
        header.set_custom_title(switcher)
        self.set_titlebar(header)
        self.add(stack)

        for name, title, build in (('sky',      _t('Sky'),      self._build_sky),
                                   ('display',  _t('Display'),  self._build_display),
                                   ('location', _t('Location'), self._build_location),
                                   ('system',   _t('System'),   self._build_system)):
            scroll, page = _page()
            build(page)
            stack.add_titled(scroll, name, title)
        # Reopen on the tab used last
        stack.show_all()
        stack.set_visible_child_name(getattr(parent, '_settings_page', 'sky'))
        stack.connect('notify::visible-child-name',
                      lambda st, _p: setattr(parent, '_settings_page', st.get_visible_child_name()))

    def _switch(self, key, default):
        """Switch bound to a config key; saves and redraws on change."""
        sw = Gtk.Switch()
        sw.set_active(self.cfg.get(key, default))
        sw.connect('notify::active', lambda s, p: (
            self.cfg.update({key: s.get_active()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        return sw

    # ── Sky ──────────────────────────────────────────────────────────────────

    def _build_sky(self, page):
        lb = _group(page, _t('Background'))
        _row(lb, _t('Opaque Sky'), self._switch('opaque_sky', True),
             _t('Off: your own wallpaper shows through, lit and tinted by Caelum'))

        lb = _group(page, _t('Sky Features'))
        _row(lb, _t('Constellation Lines'), self._switch('show_constellations', True))
        _row(lb, _t('Horizon Silhouette'), self._switch('show_silhouette', True))
        _row(lb, _t('Rainbow'), self._switch('show_rainbow', True))
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.5, 3.0, 0.1)
        sc.set_value(self.cfg.get('aster_scale', 1.0))
        sc.set_digits(1)
        sc.connect('value-changed', lambda s: (
            self.cfg.update({'aster_scale': s.get_value()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        _row(lb, _t('Aster Size'), sc, _t('Size of the sun, moon and planets'), stacked=True)

    # ── Display ──────────────────────────────────────────────────────────────

    def _build_display(self, page):
        lb = _group(page, _t('Overlay'))
        _row(lb, _t('Sky Overlay Active'), self._switch('app_enabled', True),
             _t('Off: only the gear stays on screen'))
        _row(lb, _t('Clean Mode  (Ctrl+H)'), self._switch('clean_mode', False),
             _t('Hide the info cards and the forecast column'))
        _row(lb, _t('Click Through to Desktop'), self._switch('click_through', True),
             _t('Clicks reach your desktop; click the compass or a card to explore the sky'))

        lb = _group(page, _t('On-screen Widgets'))
        _row(lb, _t('Compass Rose'), self._switch('show_compass', True))
        _row(lb, _t('Horizon Direction Labels'), self._switch('show_horizon_labels', True))
        _row(lb, _t('Weekly Forecast Column'), self._switch('show_weekly_forecast', True))
        sw_ic = self._switch('show_info_cards', False)
        _row(lb, _t('Astronomical Info Cards'), sw_ic)

        lb = _group(page, _t('Visible Cards'))
        card_labels = {
            'clock':              _t('Clock & Date'),
            'location':           _t('Location & Coordinates'),
            'sunrise_sunset':     _t('Sunrise & Sunset'),
            'solar_noon':         _t('Solar Noon & Elevation'),
            'moon_phase':         _t('Moon Phase & Age'),
            'moon_rise_set':      _t('Moon Rise & Set'),
            'daylight_remaining': _t('Daylight Remaining'),
            'cloud_cover':        _t('Cloud Cover'),
        }
        cards = self.cfg.setdefault('cards', dict(DEFAULT_CONFIG['cards']))
        for key, lbl in card_labels.items():
            sw = Gtk.Switch()
            sw.set_active(cards.get(key, True))
            sw.connect('notify::active', self._card_toggle, key)
            _row(lb, lbl, sw)
        # The card list only matters while the info cards are shown
        sw_ic.bind_property('active', lb, 'sensitive', GObject.BindingFlags.SYNC_CREATE)

    # ── Location ─────────────────────────────────────────────────────────────

    def _build_location(self, page):
        lb = _group(page, _t('Location'))
        det_btn = Gtk.Button(label=_t('Detect automatically'))
        det_btn.connect('clicked', self._detect_location)
        self._det_status = Gtk.Label(label='', xalign=0)
        self._det_status.set_line_wrap(True)
        det_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        det_box.pack_start(det_btn, False, False, 0)
        det_box.pack_start(self._det_status, False, False, 0)
        for side in ('top', 'bottom'):
            getattr(det_box, f'set_margin_{side}')(8)
        for side in ('start', 'end'):
            getattr(det_box, f'set_margin_{side}')(12)
        det_row = Gtk.ListBoxRow()
        det_row.set_activatable(False)
        det_row.set_can_focus(False)
        det_row.add(det_box)
        lb.add(det_row)

        for lbl, key, default in [
            (_t('Latitude  (+N / -S)'), 'latitude',  6.1375),
            (_t('Longitude (+E / -W)'), 'longitude', 1.2123),
        ]:
            e = Gtk.Entry()
            e.set_width_chars(12)
            e.set_text(str(self.cfg.get(key, default)))
            setattr(self, f'_e_{key}', e)
            _row(lb, lbl, e)

        self._tz_combo = Gtk.ComboBoxText()
        for offset, label in _TZ_LIST:
            self._tz_combo.append_text(label)
        self._tz_combo.set_active(_tz_index(self.cfg.get('timezone_offset', 0)))
        _row(lb, _t('Timezone'), self._tz_combo, stacked=True)

        btn = Gtk.Button(label=_t('Save & Apply'))
        btn.get_style_context().add_class('suggested-action')
        btn.set_halign(Gtk.Align.END)
        btn.set_margin_top(10)
        btn.connect('clicked', self._save)
        page.pack_start(btn, False, False, 0)

        lb = _group(page, _t('Facing & Compass'))
        hw_cmp = getattr(self.par, '_has_compass', False)
        if not hw_cmp:
            self._facing_combo = Gtk.ComboBoxText()
            cur_facing = float(self.cfg.get('facing', 180.0))
            for _, abbrev, dir_key in _FACING_OPTIONS:
                self._facing_combo.append_text(f'{abbrev}  — {_t(dir_key)}')
            best_i = min(range(len(_FACING_OPTIONS)),
                         key=lambda i: abs(_FACING_OPTIONS[i][0] - cur_facing))
            self._facing_combo.set_active(best_i)
            self._facing_combo.connect('changed', self._on_facing_changed)
            _row(lb, _t('Screen facing direction'), self._facing_combo,
                 _t('The compass direction your screen looks toward'), stacked=True)

        cmp_stat = getattr(self.par, '_compass_status', 'Not detected')
        self._cmp_status_lbl = Gtk.Label(xalign=1)
        self._cmp_status_lbl.set_markup(f'<b>{cmp_stat}</b>')
        _row(lb, _t('Compass sensor'), self._cmp_status_lbl)

        self._e_compass_port = Gtk.Entry()
        self._e_compass_port.set_placeholder_text('/dev/ttyUSB0')
        self._e_compass_port.set_text(self.cfg.get('compass_port', ''))
        self._e_compass_port.set_hexpand(True)
        conn_btn = Gtk.Button(label=_t('Connect'))
        conn_btn.connect('clicked', self._connect_compass)
        port_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        port_row.pack_start(self._e_compass_port, True, True, 0)
        port_row.pack_start(conn_btn, False, False, 0)
        _row(lb, _t('External serial compass port'), port_row,
             'Arduino/USB dongle sending one heading per line. '
             'Needs python3-serial.', stacked=True)

    # ── System ───────────────────────────────────────────────────────────────

    def _build_system(self, page):
        lb = _group(page, _t('General'))
        self._lang_combo = Gtk.ComboBoxText()
        cur_lang = self.cfg.get('language', 'auto')
        for code, label in _LANG_OPTIONS:
            self._lang_combo.append(code, label)
        self._lang_combo.set_active_id(cur_lang if cur_lang in dict(_LANG_OPTIONS) else 'auto')
        self._lang_combo.connect('changed', self._on_lang_changed)
        _row(lb, _t('Language'), self._lang_combo)
        sw_as = Gtk.Switch()
        sw_as.set_active(autostart_enabled())
        sw_as.connect('notify::active', lambda s, p: set_autostart(s.get_active()))
        _row(lb, _t('Start with GNOME session'), sw_as)

        lb = _group(page, _t('Wallpaper'))
        _LS_OPTIONS = [
            ('off',        _t('Disabled')),
            ('background', _t('Desktop background only')),
            ('lockscreen', _t('Lock screen only')),
            ('both',       _t('Both background & lock screen')),
        ]
        ls_combo = Gtk.ComboBoxText()
        cur_ls   = self.cfg.get('lockscreen_export', 'off')
        for key, label in _LS_OPTIONS:
            ls_combo.append(key, label)
        ls_combo.set_active_id(cur_ls if cur_ls in dict(_LS_OPTIONS) else 'off')
        def _on_ls_changed(combo):
            mode = combo.get_active_id() or 'off'
            self.cfg.update({'lockscreen_export': mode})
            save_config(self.cfg)
            self.par._export_lockscreen_bg()
        ls_combo.connect('changed', _on_ls_changed)
        _row(lb, _t('Export sky as wallpaper'), ls_combo,
             _t('Save the live sky as your wallpaper every 5 minutes'), stacked=True)

        lb = _group(page, _t('About'))
        version = Gtk.Label(label=__version__, xalign=1)
        version.set_selectable(True)
        _row(lb, 'Caelum', version)
        _row(lb, _t('Weather'), None, 'Open-Meteo every 15 min · MET Norway every 1 h')

    def _on_lang_changed(self, combo):
        code = combo.get_active_id() or 'auto'
        self.cfg['language'] = code
        save_config(self.cfg)
        _set_lang(code)
        self.par.da.queue_draw()

    def _connect_compass(self, _btn):
        self.cfg['compass_port'] = self._e_compass_port.get_text().strip()
        save_config(self.cfg)
        self.par._detect_compass()
        if self.par._has_compass:
            GLib.timeout_add(500, self.par._poll_compass)
        status = getattr(self.par, '_compass_status', 'Not detected')
        self._cmp_status_lbl.set_markup(f'<b>{status}</b>')
        self.par.da.queue_draw()

    def _on_facing_changed(self, combo):
        idx = combo.get_active()
        if 0 <= idx < len(_FACING_OPTIONS):
            self.cfg['facing'] = float(_FACING_OPTIONS[idx][0])
            save_config(self.cfg)
            self.par.da.queue_draw()

    def _card_toggle(self, sw, _param, key):
        self.cfg['cards'][key] = sw.get_active()
        save_config(self.cfg)
        self.par.da.queue_draw()

    def _detect_location(self, _btn):
        self._det_status.set_text('Detecting...')
        def _work():
            try:
                url = 'http://ip-api.com/json/?fields=status,lat,lon,timezone,offset'
                with urllib.request.urlopen(url, timeout=10) as r:
                    data = json.loads(r.read().decode())
                if data.get('status') == 'success':
                    GLib.idle_add(self._apply_location, data)
                else:
                    GLib.idle_add(self._det_status.set_text, 'Detection failed')
            except Exception as exc:
                GLib.idle_add(self._det_status.set_text, f'Error: {exc}')
        threading.Thread(target=_work, daemon=True).start()

    def _apply_location(self, data):
        lat    = data.get('lat', 6.1375)
        lon    = data.get('lon', 1.2123)
        offset = data.get('offset', 0) / 3600.0
        tz_name = data.get('timezone', '')
        self._e_latitude.set_text(f'{lat:.4f}')
        self._e_longitude.set_text(f'{lon:.4f}')
        self._tz_combo.set_active(_tz_index(offset))
        self._det_status.set_markup(f'<small>{tz_name}  ({lat:.4f}, {lon:.4f})</small>')
        return False

    def _save(self, _btn):
        try:
            self.cfg['latitude']  = float(self._e_latitude.get_text())
            self.cfg['longitude'] = float(self._e_longitude.get_text())
            idx = self._tz_combo.get_active()
            if 0 <= idx < len(_TZ_LIST):
                self.cfg['timezone_offset'] = _TZ_LIST[idx][0]
            save_config(self.cfg)
            self.par._refresh_day()
            self.par._selected_day       = None
            self.par._selected_day_slots = []
            self.par._last_om  = None
            self.par._last_met = None
            self.par._fetch_weather_async()
            self.par._city_name = None
            self.par._fetch_city_name()
            self.par.da.queue_draw()
        except ValueError:
            pass

