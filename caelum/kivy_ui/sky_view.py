"""Kivy sky canvas — port of the GTK draw path (gtk_ui/window.py) for a full-screen phone app.

Geometry comes from caelum.core.sky.sky_to_screen(), which returns Cairo coordinates (y down);
_k() flips them to Kivy's y-up widget space. Differences from the desktop overlay:
  * the sky is opaque (there is no wallpaper behind a phone app), so gradient alphas are dropped;
  * the ground silhouette is always drawn, since below the horizon would otherwise be empty;
  * clouds, rain, meteors, crepuscular rays and the HUD cards are not ported yet.
"""

import datetime
import math
import random
import time

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, Line, Mesh, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from ..core.astronomy import (
    _PLANET_MAG, _bv_to_rgb, _get_star_positions, _ra_dec_to_alt_az,
    moon_phase_age, moon_position, planet_positions, solar_position,
)
from ..core.catalog import _CONSTELLATIONS
from ..core.i18n import _PHASE_NAMES, _fmt_date, _t
from ..core.sky import _clamp, moon_brightness, set_facing, sky_color_adaptive, sky_to_screen
from ..core.weather import _NO_CLOUDS
from .textures import PUFF_PROFILE, radial, radial_alpha, vertical

_DIRS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']


def _rel_x(az, facing, W):
    """Screen x of an azimuth, unclamped by elevation (as the GTK limb/glow code does inline)."""
    rel = ((az - facing + 180.0) % 360.0) - 180.0
    return W * 0.06 + _clamp((rel + 120.0) / 240.0, 0.0, 1.0) * (W * 0.88)


def _bezier(p0, p1, p2, p3, n=8):
    pts = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        pts.append((u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]))
    return pts


class SkyView(Widget):

    def __init__(self, cfg, compass=None, time_override=None, **kw):
        super().__init__(**kw)
        self.cfg = cfg
        self.compass = compass
        self.time_override = time_override   # fixed UTC datetime for previews/screenshots
        self.facing = float(cfg.get('facing', 180.0))
        self._drag_x = None
        self._twinkle = []      # [(Color, base_alpha, phase_offset)]
        self._labels = {}
        self._redraw_soon = Clock.create_trigger(self.redraw)   # coalesces to once per frame
        self.bind(size=self._redraw_soon, pos=self._redraw_soon)
        Clock.schedule_interval(self.redraw, 1.0)
        Clock.schedule_interval(self._tick, 0.1)

    # ── Time, heading, input ─────────────────────────────────────────────────

    def utc_now(self):
        if self.time_override is not None:
            return self.time_override
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    def _tick(self, _dt):
        hdg = self.compass.heading() if self.compass else None
        if hdg is not None:
            # Low-pass on the circle so the panorama doesn't jitter or spin through 0/360
            diff = ((hdg - self.facing + 180.0) % 360.0) - 180.0
            if abs(diff) > 0.3:
                self.facing = (self.facing + diff * 0.2) % 360.0
                self._redraw_soon()
                return
        t = time.time()
        for col, base, off in self._twinkle:
            col.a = _clamp(base * (1.0 + 0.14 * math.sin(t * 2.7 + off)), 0.0, 1.0)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._drag_x = touch.x
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self._drag_x is None:
            return super().on_touch_move(touch)
        # Drag right → look further left (the sky follows the finger)
        self.facing = (self.facing - (touch.x - self._drag_x) * 240.0 / max(1.0, self.width)) % 360.0
        self._drag_x = touch.x
        self._redraw_soon()
        return True

    def on_touch_up(self, touch):
        self._drag_x = None
        return super().on_touch_up(touch)

    # ── Drawing helpers ──────────────────────────────────────────────────────

    def _k(self, x, y):
        """Cairo (y-down, widget-relative) → Kivy window coordinates."""
        return self.x + x, self.y + self.height - y

    def _blit(self, tex, cx, cy, rx, ry=None, rgba=(1, 1, 1, 1)):
        """Draw `tex` centred on Cairo point (cx, cy) with radii rx, ry."""
        ry = rx if ry is None else ry
        x, y = self._k(cx, cy)
        Color(*rgba)
        Rectangle(texture=tex, pos=(x - rx, y - ry), size=(2 * rx, 2 * ry))

    def _band(self, tex, top, height):
        """Full-width vertical-gradient strip starting at Cairo y=top."""
        Color(1, 1, 1, 1)
        x, y = self._k(0, top + height)
        Rectangle(texture=tex, pos=(x, y), size=(self.width, height))

    def _label(self, text, size):
        key = (text, round(size))
        tex = self._labels.get(key)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=size)
            lbl.refresh()
            tex = self._labels[key] = lbl.texture
            if len(self._labels) > 300:
                self._labels.pop(next(iter(self._labels)))
        return tex

    def _text(self, text, cx, cy, size, rgba):
        """Text whose top-left corner is at Cairo point (cx, cy)."""
        tex = self._label(text, size)
        x, y = self._k(cx, cy)
        Color(*rgba)
        Rectangle(texture=tex, pos=(x, y - tex.height), size=tex.size)

    # ── Frame ────────────────────────────────────────────────────────────────

    def redraw(self, *_):
        W, H = self.width, self.height
        if W < 2 or H < 2:
            return
        cfg = self.cfg
        set_facing(self.facing)
        utc = self.utc_now()
        lat, lon = cfg['latitude'], cfg['longitude']
        scale = cfg.get('aster_scale', 1.0) * dp(1)

        sun_el, sun_az = solar_position(lat, lon, utc)
        m_el, m_az = moon_position(lat, lon, utc)
        phase, age = moon_phase_age(utc)
        m_bright = moon_brightness(phase, m_el)

        self._twinkle = []
        self.canvas.clear()
        with self.canvas:
            self._draw_sky(W, H, sun_el, m_bright)
            self._draw_horizon_effects(W, H, sun_el, sun_az)
            if sun_el < -5:
                self._draw_stars(W, H, _clamp((-5 - sun_el) / 13, 0, 1), lat, lon, utc, m_bright)
            self._draw_silhouette(W, H)
            if sun_el > -2:
                pos = sky_to_screen(max(sun_el, 0.5), sun_az, W, H)
                if pos:
                    self._draw_sun(*pos, sun_el, scale)
            if 0 <= m_el <= 15:
                self._draw_moon_preglow(W, H, m_el, m_az, phase)
            if m_el > 0:
                pos = sky_to_screen(m_el, m_az, W, H)
                if pos:
                    sun_x = _rel_x(sun_az, self.facing, W)
                    sun_y = H * 0.72 - (H * 0.66) * (sun_el / 90.0)
                    # Direction from moon to sun, y up (same as the GTK limb_angle)
                    limb = math.atan2(pos[1] - sun_y, sun_x - pos[0])
                    self._draw_moon(*pos, phase, scale, limb)
            self._draw_planets(W, H, planet_positions(lat, lon, utc), scale)
            self._draw_hud(W, H, utc, phase)

    # ── Sky, horizon ─────────────────────────────────────────────────────────

    def _draw_sky(self, W, H, sun_el, m_bright):
        r, g, b, _a = sky_color_adaptive(sun_el, _NO_CLOUDS, m_bright)
        tex = vertical([
            (0.0, (min(1, r * 1.15), min(1, g * 1.15), min(1, b * 1.15), 1.0)),
            (0.6, (r, g, b, 1.0)),
            (1.0, (r * 0.70, g * 0.70, b * 0.70, 1.0)),
        ])
        self._band(tex, 0, H)

    def _draw_horizon_effects(self, W, H, sun_el, sun_az):
        y0 = H * 0.72
        if -10.0 < sun_el < -0.5:                       # Belt of Venus
            anti_az = (sun_az + 180.0) % 360.0
            if abs(((anti_az - self.facing + 180.0) % 360.0) - 180.0) < 120.0:
                i = round(_clamp(1.0 - abs(sun_el + 5.0) / 5.0, 0.0, 1.0) ** 1.4, 2)
                tex = radial([(0.00, (0.88, 0.52, 0.72, i * 0.42)), (0.18, (0.72, 0.38, 0.62, i * 0.28)),
                              (0.45, (0.45, 0.20, 0.48, i * 0.12)), (1.00, (0.0, 0.0, 0.0, 0.0))])
                self._blit(tex, _rel_x(anti_az, self.facing, W), y0, W * 0.58)
        if -12.0 < sun_el < 0.0:                        # Pre-glow
            i = round(_clamp(1.0 - abs(sun_el) / 12.0, 0.0, 1.0) ** 1.5, 2)
            tex = radial([(0.00, (1.00, 0.45, 0.02, i * 0.60)), (0.22, (1.00, 0.30, 0.01, i * 0.32)),
                          (0.55, (0.80, 0.15, 0.00, i * 0.10)), (1.00, (0.0, 0.0, 0.0, 0.0))])
            self._blit(tex, _rel_x(sun_az, self.facing, W), y0, W * 0.52)
        if -6.0 < sun_el < 15.0:                        # Golden-hour band
            i = round(_clamp(1.0 - abs(sun_el - 2.0) / 8.0, 0.0, 1.0) ** 2.0, 2)
            if i > 0.01:
                gh = H * 0.22
                self._band(vertical([(0.00, (0, 0, 0, 0)), (0.50, (1.00, 0.55, 0.06, i * 0.10)),
                                     (0.78, (1.00, 0.38, 0.02, i * 0.20)),
                                     (1.00, (1.00, 0.22, 0.01, i * 0.16))]), y0 - gh, gh)
        hz = H * 0.18                                   # Atmospheric haze
        hr, hg, hb, ha = (0.82, 0.88, 1.00, 0.09) if sun_el > 0 else (0.06, 0.07, 0.14, 0.06)
        self._band(vertical([(0.0, (hr, hg, hb, 0.0)), (1.0, (hr, hg, hb, ha))]), y0 - hz, hz)

    def _draw_silhouette(self, W, H):
        rng = random.Random(0xA5B2)
        y0 = H * 0.72
        peaks = []
        x = 0.0
        while x < W + W * 0.05:
            seg = rng.uniform(W * 0.014, W * 0.048)
            shape = rng.random()
            if shape < 0.25:
                ht = rng.uniform(H * 0.06, H * 0.13)
            elif shape < 0.55:
                ht = rng.uniform(H * 0.02, H * 0.055)
            else:
                ht = rng.uniform(0.0, H * 0.018)
            peaks.append((x + seg * 0.5, y0 - ht, seg))
            x += seg
        # Same Bézier outline as the GTK version, flattened to points
        pts = [(0.0, y0)]
        cur = (0.0, y0)
        for i, (px, py, sw) in enumerate(peaks):
            if i == 0:
                pts += _bezier(cur, (px - sw * 0.40, y0), (px - sw * 0.15, py), (px, py))
            else:
                ppx, ppy, psw = peaks[i - 1]
                mid = (ppx + px) / 2.0
                pts += _bezier(cur, (ppx + psw * 0.30, ppy), (mid - sw * 0.12, y0), (mid, y0))
                pts += _bezier((mid, y0), (mid + sw * 0.12, y0), (px - sw * 0.20, py), (px, py))
            cur = (px, py)
        lpx, _, lsw = peaks[-1]
        pts += _bezier(cur, (lpx + lsw * 0.30, y0), (W, y0), (W, y0))
        # The outline is a height field, so a strip down to the bottom edge fills it
        verts = []
        for px, py in pts:
            kx, ky = self._k(px, py)
            verts += [kx, ky, 0, 0, kx, self.y, 0, 0]
        Color(0.03, 0.05, 0.03, 1.0)   # opaque ground; desktop uses 0.72 alpha over the wallpaper
        Mesh(vertices=verts, indices=list(range(len(verts) // 4)), mode='triangle_strip')

    # ── Stars ────────────────────────────────────────────────────────────────

    def _draw_stars(self, W, H, intensity, lat, lon, utc, m_bright):
        puff = radial_alpha(PUFF_PROFILE)
        rng = random.Random(42)

        rng_bg = random.Random(0xC7D9)                  # faint background field
        bg_limit = intensity * (1.0 - m_bright * 0.88)
        for _ in range(420):
            bsx, bsy = rng_bg.uniform(0, W), rng_bg.uniform(0, H * 0.72)
            ba = bg_limit * rng_bg.uniform(0.03, 0.16)
            if ba < 0.015:
                rng_bg.random()
                continue
            br = rng_bg.uniform(0.3, 0.65) * dp(1)
            x, y = self._k(bsx, bsy)
            Color(0.88, 0.90, 0.96, ba)
            Ellipse(pos=(x - br, y - br), size=(2 * br, 2 * br), segments=8)

        if intensity > 0.4 and m_bright < 0.80:         # airglow
            ag_a = (intensity - 0.4) / 0.6 * 0.036 * (1.0 - m_bright / 0.80)
            self._band(vertical([(0.0, (0, 0, 0, 0)), (1.0, (0.28, 0.65, 0.30, ag_a))]), H * 0.57, H * 0.15)

        if intensity > 0.5 and m_bright < 0.7:          # Milky Way
            mw_alpha = (intensity - 0.5) * 2 * 0.07 * (1.0 - m_bright / 0.7)
            pdx, pdy = 1.2 * W, -0.45 * H
            plen = math.hypot(pdx, pdy)
            nx, ny = -pdy / plen, pdx / plen
            for i in range(180):
                t = i / 179.0
                cx, cy = W * (-0.1 + t * 1.2), H * (0.55 - t * 0.45)
                spread = rng.gauss(0, H * 0.09)
                bx = cx + nx * spread + rng.uniform(-W * 0.01, W * 0.01)
                by = cy + ny * spread + rng.uniform(-H * 0.01, H * 0.01)
                bw, bh = W * rng.uniform(0.05, 0.14), H * rng.uniform(0.05, 0.13)
                self._blit(puff, bx, by, bw, bh, (0.60, 0.65, 0.80, mw_alpha * rng.uniform(0.3, 1.0)))

        limiting_mag = 6.5 - m_bright * 3.5
        star_data = _get_star_positions(lat, lon, utc)
        star_screen = {}
        for alt, az, _mag, _bv, ra_h, dec_deg in star_data:
            pos = sky_to_screen(alt, az, W, H)
            if pos is not None:
                star_screen[(round(ra_h, 2), round(dec_deg, 1))] = pos

        if self.cfg.get('show_constellations', True):
            line_alpha = 0.28 * intensity * max(0.0, 1.0 - m_bright * 0.8)
            if line_alpha > 0.01:
                Color(0.55, 0.65, 0.95, line_alpha)
                for _name, polylines in _CONSTELLATIONS:
                    for polyline in polylines:
                        run = []
                        for ra_h, dec_deg in polyline + [None]:
                            pt = star_screen.get((round(ra_h, 2), round(dec_deg, 1))) if ra_h is not None else None
                            if pt is None:
                                if len(run) >= 4:
                                    Line(points=run, width=dp(0.8))
                                run = []
                            else:
                                run += self._k(*pt)

        for alt, _az, mag, bv, ra_h, dec_deg in star_data:
            pos = star_screen.get((round(ra_h, 2), round(dec_deg, 1)))
            if pos is None:
                continue
            moon_fade = _clamp((limiting_mag - mag) / 2.0, 0.0, 1.0)
            if moon_fade <= 0:
                continue
            sr, sg, sb = _bv_to_rgb(bv)
            elev_fade = _clamp((alt + 1.0) / 12.0, 0.0, 1.0)
            alpha = intensity * elev_fade * moon_fade * _clamp((6.0 - mag) / 6.5, 0.05, 1.0)
            radius = max(0.4, (5.5 - mag) * 0.38) * dp(1)
            phase_off = (ra_h * 7919.0 + abs(dec_deg) * 3571.0) % (2 * math.pi)
            x, y = self._k(*pos)
            col = Color(sr, sg, sb, alpha)
            Ellipse(pos=(x - radius, y - radius), size=(2 * radius, 2 * radius), segments=12)
            self._twinkle.append((col, alpha, phase_off))
            if mag < 2.0:
                glow_r = radius * 3.5 + 1.5
                self._blit(puff, pos[0], pos[1], glow_r, glow_r, (sr, sg, sb, alpha * 0.35 * intensity))

        m42_alt, m42_az = _ra_dec_to_alt_az(5.5875, -5.391, lat, lon, utc)   # Orion Nebula
        if m42_alt > 0:
            pos = sky_to_screen(m42_alt, m42_az, W, H)
            if pos:
                nf = intensity * _clamp((m42_alt + 1.0) / 18.0, 0.0, 1.0) * (1.0 - m_bright * 0.75)
                if nf > 0.01:
                    nw, nh = W * 0.013, H * 0.020
                    self._blit(puff, pos[0], pos[1], nw, nh, (0.85, 0.55, 0.72, nf * 0.38))
                    self._blit(puff, pos[0], pos[1], nw * 0.55, nh * 0.55, (0.50, 0.72, 0.80, nf * 0.28))

    # ── Sun, moon, planets ───────────────────────────────────────────────────

    def _draw_sun(self, x, y, el, scale):
        # Desktop blends these with Cairo SCREEN; plain alpha blending is close on an opaque sky
        r = 16 * scale
        t = round(_clamp(el / 20.0, 0.0, 1.0), 2)
        self._blit(radial([(0.00, (1.0, 0.80 + 0.18 * t, 0.30 + 0.55 * t, 0.50)),
                           (0.18, (1.0, 0.65 + 0.15 * t, 0.18 + 0.25 * t, 0.18)),
                           (0.45, (1.0, 0.50, 0.10, 0.05)), (1.00, (0.0, 0.0, 0.0, 0.0))]), x, y, r * 16)
        self._blit(radial([(0.00, (1.0, 1.0, 0.88 + 0.12 * t, 0.92)),
                           (0.25, (1.0, 0.90 + 0.10 * t, 0.55 + 0.35 * t, 0.75)),
                           (0.65, (1.0, 0.70, 0.28, 0.28)), (1.00, (0.0, 0.0, 0.0, 0.0))]), x, y, r * 5)
        self._blit(radial([(0.00, (1.0, 1.0, 1.0, 1.00)), (0.50, (1.0, 1.0, 0.95, 0.90)),
                           (1.00, (1.0, 0.90, 0.60, 0.00))]), x, y, r * 1.2)

    def _draw_moon_preglow(self, W, H, m_el, m_az, phase):
        illumination = (1 - math.cos(phase * 2 * math.pi)) / 2
        if illumination <= 0.10 or not sky_to_screen(0.1, m_az, W, H):
            return
        i = round(_clamp(1.0 - m_el / 15.0, 0.0, 1.0) * illumination, 2)
        tex = radial([(0.00, (0.90, 0.90, 0.82, i * 0.38)), (0.28, (0.76, 0.76, 0.68, i * 0.16)),
                      (0.60, (0.55, 0.55, 0.48, i * 0.05)), (1.00, (0.0, 0.0, 0.0, 0.0))])
        self._blit(tex, _rel_x(m_az, self.facing, W), H * 0.72, W * 0.35)

    def _draw_moon(self, x, y, phase, scale, limb_angle):
        r = 32 * scale
        self._blit(radial([(0.0, (0.92, 0.91, 0.84, 0.55)), (0.4, (0.78, 0.76, 0.68, 0.18)),
                           (1.0, (0.55, 0.53, 0.46, 0.00))], inner=0.4 / 3.5), x, y, r * 3.5)
        kx, ky = self._k(x, y)
        Color(0.16, 0.20, 0.45, 0.03)
        Ellipse(pos=(kx - r, ky - r), size=(2 * r, 2 * r))
        Color(0.96, 0.94, 0.86, 1.0)
        t = math.cos(phase * 2 * math.pi)
        if t < -0.95:
            Ellipse(pos=(kx - r, ky - r), size=(2 * r, 2 * r))
            return
        # Lit region in local coords (lit limb on +x), as strips between the limb and the
        # terminator at equal heights; rotating by limb_angle turns the lit side to the sun.
        ca, sa = math.cos(limb_angle), math.sin(limb_angle)
        verts = []
        n = 48
        for i in range(n + 1):
            th = -math.pi / 2 + math.pi * i / n
            ly = r * math.sin(th)
            for lx in (r * math.cos(th), t * r * math.cos(th)):
                verts += [kx + lx * ca - ly * sa, ky + lx * sa + ly * ca, 0, 0]
        Mesh(vertices=verts, indices=list(range(len(verts) // 4)), mode='triangle_strip')

    def _draw_planets(self, W, H, planets, scale):
        glow = radial_alpha([(0.0, 0.60), (0.5, 0.22), (1.0, 0.0)])
        for name, el, az, (r, g, b) in planets:
            if el <= 0:
                continue
            pos = sky_to_screen(el, az, W, H)
            if pos is None:
                continue
            radius = max(3.5, (5.5 - _PLANET_MAG.get(name, 0.0) * 0.50)) * scale
            self._blit(glow, pos[0], pos[1], radius * 3.5, rgba=(r, g, b, 1.0))
            kx, ky = self._k(*pos)
            Color(r, g, b, 0.95)
            Ellipse(pos=(kx - radius, ky - radius), size=(2 * radius, 2 * radius))
            if name == 'Saturn':
                rw, rh = radius * 2.1, radius * 2.1 * 0.32
                Color(r, g, b, 0.50)
                Line(ellipse=(kx - rw, ky - rh, 2 * rw, 2 * rh), width=max(1.0, radius * 0.18))
            self._text(name, pos[0] + radius + 3, pos[1] - 6 * scale, 11 * scale, (r, g, b, 0.72))

    # ── HUD ──────────────────────────────────────────────────────────────────

    def _draw_hud(self, W, H, utc, phase):
        tz = (time.localtime().tm_gmtoff / 3600.0 if self.time_override is None
              else self.cfg.get('timezone_offset', 0))
        now = utc + datetime.timedelta(hours=tz)
        pad, s = dp(16), dp(1)
        self._text(now.strftime('%H:%M'), pad, pad, 34 * s, (1, 1, 1, 0.90))
        self._text(_fmt_date(now), pad, pad + 44 * s, 14 * s, (1, 1, 1, 0.70))
        self._text(_t(_PHASE_NAMES[int(phase * 8) % 8]), pad, pad + 64 * s, 14 * s, (0.96, 0.94, 0.86, 0.70))
        src = _t('compass') if self.compass and self.compass.available else _t('drag to look around')
        hdg = f'{_DIRS[int((self.facing + 22.5) % 360 // 45)]}  {self.facing:.0f}°  ·  {src}'
        self._text(hdg, pad, pad + 84 * s, 12 * s, (0.75, 0.85, 1.0, 0.60))
