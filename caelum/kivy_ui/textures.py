"""Gradient textures standing in for Cairo's RadialGradient / LinearGradient.

Kivy has no gradient fills, so each gradient is baked once into a small texture and stretched
over a Rectangle; linear filtering keeps it smooth. Stops use Cairo's convention:
[(offset 0..1, (r, g, b, a)), ...].
"""

import math

from kivy.graphics.texture import Texture

_CACHE = {}
_CACHE_MAX = 256

# _soft_puff's density profile (gtk_ui/clouds.py), as alpha multipliers
PUFF_PROFILE = [(0.00, 1.00), (0.28, 0.92), (0.58, 0.50), (0.82, 0.12), (1.00, 0.00)]


def _q(stops):
    """Quantise stops so near-identical gradients share a cache entry."""
    return tuple((round(o, 3), tuple(round(c, 3) for c in col)) for o, col in stops)


def _interp(stops, s):
    if s <= stops[0][0]:
        return stops[0][1]
    for (o0, c0), (o1, c1) in zip(stops, stops[1:]):
        if s <= o1:
            t = 0.0 if o1 == o0 else (s - o0) / (o1 - o0)
            return tuple(a + (b - a) * t for a, b in zip(c0, c1))
    return stops[-1][1]


def _to_bytes(colors):
    out = bytearray()
    for r, g, b, a in colors:
        out += bytes((int(max(0.0, min(1.0, r)) * 255 + 0.5), int(max(0.0, min(1.0, g)) * 255 + 0.5),
                      int(max(0.0, min(1.0, b)) * 255 + 0.5), int(max(0.0, min(1.0, a)) * 255 + 0.5)))
    return bytes(out)


def _store(key, tex):
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = tex
    return tex


def _make(w, h, data):
    tex = Texture.create(size=(w, h), colorfmt='rgba')
    tex.blit_buffer(data, colorfmt='rgba', bufferfmt='ubyte')
    tex.mag_filter = tex.min_filter = 'linear'
    tex.wrap = 'clamp_to_edge'
    return tex


def radial(stops, inner=0.0, size=128):
    """Circular gradient filling the texture; `inner` is the inner-circle radius as a fraction
    of the outer one (Cairo RadialGradient with r0 = inner * r1)."""
    stops = _q(stops)
    key = ('radial', stops, round(inner, 3), size)
    if key in _CACHE:
        return _CACHE[key]
    lut_n = 256
    lut = [_interp(stops, i / (lut_n - 1)) for i in range(lut_n)]
    clear = (0.0, 0.0, 0.0, 0.0)
    half = size / 2.0
    colors = []
    for y in range(size):
        dy = (y + 0.5 - half) / half
        for x in range(size):
            dx = (x + 0.5 - half) / half
            d = math.sqrt(dx * dx + dy * dy)
            if d > 1.0:
                colors.append(clear)
                continue
            s = (d - inner) / (1.0 - inner) if inner < 1.0 else 0.0
            colors.append(lut[int(max(0.0, min(1.0, s)) * (lut_n - 1))])
    return _store(key, _make(size, size, _to_bytes(colors)))


def radial_alpha(profile, size=128):
    """White radial texture with an alpha profile [(offset, alpha)]; tint it with Color()."""
    return radial([(o, (1.0, 1.0, 1.0, a)) for o, a in profile], size=size)


def vertical(stops, height=64):
    """Top-to-bottom gradient (offset 0 = top, as in Cairo). Texture row 0 is the bottom."""
    stops = _q(stops)
    key = ('vertical', stops, height)
    if key in _CACHE:
        return _CACHE[key]
    colors = [_interp(stops, 1.0 - (j + 0.5) / height) for j in range(height)]
    return _store(key, _make(1, height, _to_bytes(colors)))
