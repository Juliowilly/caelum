"""
Photographed landscapes along the horizon: bands of CC0 panoramas from Poly Haven with the sky cut
out (built by packaging/make-landscapes.py). They are mapped by azimuth and elevation like the
sky, so they turn with the facing direction, and relit to the sun's elevation.
Personal landscapes (e.g. made from the user's own photos) sit in the same format in
<data dir>/caelum/landscapes/; they stay on the user's machine.
"""

import json
import math
import os
import re

import gi
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf
import cairo

from . import sandbox

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'landscapes')
# Panorama projection, as in sky_to_screen: 240° across 88 % of the width, horizon at 72 % of the
# height, 66 % of the height per 90° of elevation
_SPAN, _X0, _XW, _HORIZON, _YH = 240.0, 0.06, 0.88, 0.72, 0.66
# Transparent rows above the photo: the repeating pattern mustn't blend ground into the sky. The
# GOOD filter, shrinking the band ~2.5×, reaches a few rows past the top; 2 rows left a thin line
_PAD = 8


_NAME = re.compile(r'^[a-z0-9_-]{1,40}$')
_RESERVED = ('hills', 'none')          # the drawn hills and no landscape


def personal_dir():
    return os.path.join(sandbox.data_dir(), 'caelum', 'landscapes')


def _catalog():
    """name → (directory, metadata) of every landscape installed; shipped ones win a name clash."""
    out = {}
    for d in (_DIR, personal_dir()):
        try:
            with open(os.path.join(d, 'landscapes.json')) as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict):
            continue
        for name, m in meta.items():
            if _NAME.match(name) and name not in _RESERVED and name not in out and isinstance(m, dict):
                out[name] = (d, m)
    return out


def available():
    """Names of the landscapes installed: shipped with Caelum, then the user's own."""
    return list(_catalog())


def personal():
    """(name, label) of the user's own landscapes."""
    return [(name, str(m.get('label') or name)) for name, (d, m) in _catalog().items() if d != _DIR]


class Landscape:
    def __init__(self, name):
        d, meta = _catalog()[name]
        self.top, self.bottom, self.south = float(meta['top']), float(meta['bottom']), float(meta['south'])
        pix  = GdkPixbuf.Pixbuf.new_from_file(os.path.join(d, name + '.jpg'))
        mask = cairo.ImageSurface.create_from_png(os.path.join(d, name + '-mask.png'))
        self.w, self.h = pix.get_width(), pix.get_height()
        # The photo (opaque) and its sky cut-out are kept apart: the cut-out is applied after
        # relighting, so the soft edges get darkened as much as the rest
        self.surf = cairo.ImageSurface(cairo.FORMAT_RGB24, self.w, self.h + _PAD)
        cr = cairo.Context(self.surf)
        Gdk.cairo_set_source_pixbuf(cr, pix, 0, _PAD)
        cr.paint()
        self.mask = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.w, self.h + _PAD)
        cr = cairo.Context(self.mask)
        cr.set_source_surface(mask, 0, _PAD)
        cr.paint()

    def render(self, W, H, facing, light, sat):
        """
        The landscape for a W×H view facing `facing`°, relit by `light` (rgb multiplier) with
        colour saturation `sat`. Returns (surface, y) — the surface is drawn at height y.
        """
        y_top = max(0, math.floor(H * _HORIZON - H * _YH * self.top / 90.0))
        out = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H - y_top)
        cr  = cairo.Context(out)
        # Screen → photo: column by azimuth (wrapping round the panorama), row by elevation
        px_per_deg = self.w / 360.0
        k   = _SPAN / (_XW * W) * px_per_deg
        az0 = facing - _SPAN / 2 - _X0 * W * _SPAN / (_XW * W)        # azimuth at x = 0
        u0  = self.w * self.south + (az0 - 180.0) * px_per_deg
        kv  = self.h / (self.top + self.bottom) * 90.0 / (_YH * H)
        v0  = self.h / (self.top + self.bottom) * (self.top - _HORIZON * 90.0 / _YH) + kv * y_top + _PAD
        matrix = cairo.Matrix(k, 0, 0, kv, u0 % self.w, v0)

        def pattern(surf):
            pat = cairo.SurfacePattern(surf)
            pat.set_matrix(matrix)
            pat.set_extend(cairo.Extend.REPEAT)
            pat.set_filter(cairo.Filter.GOOD)
            return pat
        cr.set_source(pattern(self.surf))
        cr.paint()
        # Night vision: fade the colours
        if sat < 0.99:
            cr.set_operator(cairo.Operator.HSL_SATURATION)
            cr.set_source_rgb(0.5, 0.5, 0.5)
            cr.paint_with_alpha(1.0 - sat)
        if light != (1.0, 1.0, 1.0):
            cr.set_operator(cairo.Operator.MULTIPLY)
            cr.set_source_rgb(*light)
            cr.paint()
        # Cut the sky out
        cr.set_operator(cairo.Operator.DEST_IN)
        cr.set_source(pattern(self.mask))
        cr.paint()
        return out, y_top
