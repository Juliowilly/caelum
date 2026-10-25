"""
Cairo rain and snow. Drops fall continuously (positions follow the clock, not a fresh random
scatter each frame) in depth layers: the far ones fall behind the landscape, the near ones in
front of it. Heavy precipitation also hides the distance behind a veil, and storms flash.
"""

import functools
import math
import random

import cairo

from ..core.sky import _clamp, get_facing

_HORIZON = 0.72   # screen height of the horizon, as in sky_to_screen
_REF_AREA = 1920 * 1080

# Rain layers, far to near: drops per 1080p screen at light / heavy rain, fall speed (screen
# heights per second), streak length (fraction of the screen height), line width, opacity,
# and the share of the wind slant the layer shows (near drops cross the view faster)
_RAIN = (
    dict(n=(300, 1500), speed=0.55, length=0.012, width=0.8, alpha=0.45, slant=0.7),
    dict(n=(90, 450),   speed=1.10, length=0.024, width=1.0, alpha=0.40, slant=0.85),
    dict(n=(14, 110),   speed=2.20, length=0.050, width=1.4, alpha=0.38, slant=1.0),
)
# Snow layers: flakes, fall speed, radius (fraction of the height), opacity, sway amplitude
_SNOW = (
    dict(n=(300, 1200), speed=0.030, radius=0.0016, alpha=0.70, sway=0.004),
    dict(n=(90, 380),   speed=0.055, radius=0.0028, alpha=0.85, sway=0.008),
    dict(n=(16, 80),    speed=0.100, radius=0.0050, alpha=0.90, sway=0.014),
)
FAR, NEAR = (0,), (1, 2)   # layers drawn behind / in front of the landscape


@functools.lru_cache(maxsize=16)
def _seeds(kind, layer, n):
    """n drops of a layer: (x 0–1, phase 0–1, size jitter 0.7–1.3, sway phase)."""
    rng = random.Random(f'{kind}:{layer}')
    return tuple((rng.random(), rng.random(), rng.uniform(0.7, 1.3), rng.uniform(0, 2 * math.pi))
                 for _ in range(n))


def _count(spec, inten, W, H):
    lo, hi = spec['n']
    return int((lo + (hi - lo) * inten) * W * H / _REF_AREA)


@functools.lru_cache(maxsize=8)
def _tile(kind, layer, W, H, inten, slant):
    """
    One layer's drops, drawn once into an alpha-only tile (screen-wide, half a screen high,
    seamless both ways) that is then scrolled as they fall: a frame costs one composite per
    layer however heavy the rain.
    """
    th = H // 2
    spec = (_SNOW if kind == 'snow' else _RAIN)[layer]
    surf = cairo.ImageSurface(cairo.FORMAT_A8, W, th)
    cr = cairo.Context(surf)
    n = _count(spec, inten, W, H) // 2
    for x0, ph, k, _sw in _seeds(kind, layer, n):
        x, y = x0 * W, ph * th
        if kind == 'snow':
            r = spec['radius'] * H * k
            for ox in (-W, 0, W):
                for oy in (-th, 0, th):
                    cr.new_sub_path()
                    cr.arc(x + ox, y + oy, r, 0, 2 * math.pi)
        else:
            length = spec['length'] * H * k
            dx = slant * spec['slant'] * length
            for ox in (-W, 0, W):
                for oy in (-th, 0):
                    cr.move_to(x + ox, y + oy)
                    cr.rel_line_to(dx, length)
    if kind == 'snow':
        cr.fill()
    else:
        cr.set_line_cap(cairo.LineCap.ROUND)
        cr.set_line_width(spec['width'] * H / 1080)
        cr.stroke()
    return surf


def _scroll(cr, surf, ox, oy, rgb, alpha):
    pat = cairo.SurfacePattern(surf)
    pat.set_extend(cairo.Extend.REPEAT)
    # Whole-pixel steps keep this a plain copy (no resampling): cheap
    pat.set_filter(cairo.Filter.NEAREST)
    pat.set_matrix(cairo.Matrix(x0=-(round(ox) % surf.get_width()), y0=-(round(oy) % surf.get_height())))
    cr.set_source_rgba(*rgb, alpha)
    cr.mask(pat)


def draw_rain(cr, W, H, t, layers, inten, slant, rgb):
    """Rain streaks of the given layers at time t (seconds), slanting and drifting with the wind."""
    inten, slant = round(inten, 2), round(slant, 2)
    for i in layers:
        spec = _RAIN[i]
        fall = spec['speed'] * H * t
        _scroll(cr, _tile('rain', i, W, H, inten, slant),
                slant * spec['slant'] * fall, fall, rgb, spec['alpha'])


def draw_snow(cr, W, H, t, layers, inten, slant, rgb):
    """Snowflakes of the given layers at time t: they drift with the wind and sway as they fall."""
    inten, slant = round(inten, 2), round(slant, 2)
    for i in layers:
        spec = _SNOW[i]
        fall = spec['speed'] * H * t
        sway = spec['sway'] * H * math.sin(t * (0.7 + 0.2 * i) + i)
        _scroll(cr, _tile('snow', i, W, H, inten, 0.0),
                slant * 4 * spec['speed'] * fall + sway, fall, rgb, spec['alpha'])


def draw_veil(cr, W, H, inten, snow, rgb):
    """
    Rain or snow hides the distance: a haze the colour of the horizon sky over the far
    landscape, strongest at the horizon, fading up into the sky and down to the foreground.
    """
    # Moderate rain (2 mm/h) already hides most of a mountain 10 km away
    a = min(inten * (2.2 if snow else 1.7), 0.85)
    if a < 0.02:
        return
    top = H * 0.30
    g = cairo.LinearGradient(0, top, 0, H)

    def stop(y, k):
        g.add_color_stop_rgba((y - top) / (H - top), *rgb, a * k)
    # Thickest at the horizon (the most air in the way), still dimming the far hills and
    # mountain tops above it, thinning out towards the foreground
    stop(top, 0.0)
    stop(H * 0.52, 0.45)
    stop(H * 0.64, 0.80)
    stop(H * _HORIZON, 1.0)
    stop(H * 0.77, 0.55)
    stop(H, 0.10)
    cr.set_source(g)
    cr.rectangle(0, top, W, H - top)
    cr.fill()


def draw_shafts(cr, W, H, inten, cover, slant, rgb, seed):
    """
    Showers seen from afar under a broken sky: grey curtains of rain hanging from the clouds
    to the horizon at fixed azimuths (they turn with the view). Hidden under a full overcast,
    where it rains everywhere and the veil does the job.
    """
    show = _clamp((0.92 - cover) / 0.25, 0.0, 1.0) * _clamp(inten * 6.0, 0.0, 1.0)
    if show < 0.02:
        return
    rng = random.Random(f'shafts:{seed}')
    y_top, y_bot = H * 0.40, _HORIZON * H + 2
    for _ in range(3):
        az = rng.uniform(0, 360)
        rel = ((az - get_facing() + 180.0) % 360.0) - 180.0
        if abs(rel) > 130:
            continue
        x = W * 0.06 + (rel + 120.0) / 240.0 * W * 0.88
        w = W * rng.uniform(0.04, 0.09)
        a = show * rng.uniform(0.50, 0.75)
        lean = slant * (y_bot - y_top) * 0.35
        # Soft across, fading in under the cloud base, dense at the ground
        cr.save()
        m = cairo.Matrix(1, 0, lean / (y_bot - y_top), 1, -lean * y_top / (y_bot - y_top), 0)
        cr.transform(m)
        across = cairo.LinearGradient(x - w, 0, x + w, 0)
        for s, f in ((0.0, 0.0), (0.25, 0.55), (0.42, 0.9), (0.5, 1.0), (0.6, 0.8), (0.78, 0.45), (1.0, 0.0)):
            across.add_color_stop_rgba(s, *rgb, a * f)
        down = cairo.LinearGradient(0, y_top, 0, y_bot)
        down.add_color_stop_rgba(0.0, 0, 0, 0, 0.0)
        down.add_color_stop_rgba(0.35, 0, 0, 0, 0.8)
        down.add_color_stop_rgba(1.0, 0, 0, 0, 1.0)
        cr.rectangle(x - w, y_top, 2 * w, y_bot - y_top)
        cr.clip()
        cr.set_source(across)
        cr.mask(down)
        cr.restore()


class Storm:
    """Lightning: now and then the sky flashes (behind the landscape, which stays a silhouette),
    sometimes with a visible bolt."""

    def __init__(self):
        self._flash = None   # (start time, bolt points or None)

    def draw(self, cr, W, H, t, heavy):
        if self._flash is None:
            # About one flash every 12 s (heavier storms: 7 s) at 10 frames a second
            if random.random() < (0.014 if heavy else 0.008):
                self._flash = (t, self._bolt(W, H) if random.random() < 0.5 else None)
            return
        start, bolt = self._flash
        age = t - start
        if age > 0.6:
            self._flash = None
            return
        # Two or three quick pulses, decaying
        level = max(0.0, 1.0 - age / 0.6) * (0.55 + 0.45 * math.cos(age * 40) ** 2)
        cr.set_source_rgba(0.88, 0.88, 1.0, 0.30 * level)
        cr.paint()
        if bolt:
            cr.save()
            cr.set_line_join(cairo.LineJoin.ROUND)
            for width, alpha in ((9.0, 0.10), (4.0, 0.25), (1.6, 0.95)):
                cr.move_to(*bolt[0])
                for p in bolt[1:]:
                    cr.line_to(*p)
                cr.set_source_rgba(0.92, 0.92, 1.0, alpha * level)
                cr.set_line_width(width * H / 1080)
                cr.stroke()
            cr.restore()

    @staticmethod
    def _bolt(W, H):
        """A jagged path from the cloud base down to the horizon."""
        x, y = random.uniform(0.1, 0.9) * W, H * 0.30
        pts = [(x, y)]
        while y < _HORIZON * H:
            y += random.uniform(0.012, 0.035) * H
            x += random.gauss(0, 0.012) * W
            pts.append((x, min(y, _HORIZON * H + 4)))
        return pts
