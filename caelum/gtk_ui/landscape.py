"""
Photographed landscapes along the horizon: bands of CC0 panoramas from Poly Haven with the sky cut
out (built by packaging/make-landscapes.py). They are mapped by azimuth and elevation like the
sky, so they turn with the facing direction, and relit to the sun's elevation.
"""

import json
import math
import os

import gi
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf
import cairo

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'landscapes')
# Panorama projection, as in sky_to_screen: 240° across 88 % of the width, horizon at 72 % of the
# height, 66 % of the height per 90° of elevation
_SPAN, _X0, _XW, _HORIZON, _YH = 240.0, 0.06, 0.88, 0.72, 0.66
_PAD = 2   # transparent rows above the photo: the repeating pattern mustn't blend ground into the sky


def available():
    """Names of the landscapes shipped with this install."""
    try:
        with open(os.path.join(_DIR, 'landscapes.json')) as f:
            return list(json.load(f))
    except (OSError, ValueError):
        return []


class Landscape:
    def __init__(self, name):
        with open(os.path.join(_DIR, 'landscapes.json')) as f:
            meta = json.load(f)[name]
        self.top, self.bottom, self.south = meta['top'], meta['bottom'], meta['south']
        pix  = GdkPixbuf.Pixbuf.new_from_file(os.path.join(_DIR, name + '.jpg'))
        mask = cairo.ImageSurface.create_from_png(os.path.join(_DIR, name + '-mask.png'))
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
