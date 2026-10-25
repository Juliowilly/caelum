"""
A landscape from the user's own photo (Settings → Sky → Your own photo), built on this computer.
The sky is cut out, the scene spread over half the horizon and mirrored over the other half, so
the band closes on itself without a seam. The result goes to the personal landscapes folder,
without the photo's metadata (place, camera, date), and never leaves the computer.
"""

import json
import math
import os
import shutil
import statistics
import tempfile

import gi
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, GLib
import cairo

from . import landscape

NAME = 'photo'
LABEL = 'Your photo'
MAX_BYTES = 50 * 1024 * 1024
MAX_PIXELS = 120_000_000        # phone panoramas reach ~80 MP
MIN_WIDTH = 400
_FORMATS = ('jpeg', 'png')
_DECODE = 4000                  # longest side decoded: more than the band can use
HALF_W = 1800                   # half the band: 180° at 10 px per degree, like the shipped bands
BOTTOM = 40.0                   # the screen shows down to ~38° below the horizon
_AW = 480                       # width the sky is analysed at
_SKYLINE, _TALLEST = 10.0, 35.0  # elevation (°) of the typical skyline, and the most for the tallest


class PhotoError(Exception):
    """Why the photo can't be used, in English as shown to the user (the caller translates)."""


def _clip(v):
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def _sky_prob(r, g, b):
    """0–1: clear blue sky (blue leads and is bright enough) or pale haze/cloud."""
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    sat = max(r, g, b) - min(r, g, b)
    p_blue = _clip((b - max(r, g) - 0.03) / 0.08) * _clip((b - 0.30) / 0.10)
    p_haze = _clip((lum - 0.60) / 0.10) * _clip((0.22 - sat) / 0.10) if b >= g - 0.02 else 0.0
    return max(p_blue, p_haze)


def _load(path):
    """The photo, upright and decoded no larger than needed. Raises PhotoError."""
    try:
        size = os.path.getsize(path)
        fmt, w, h = GdkPixbuf.Pixbuf.get_file_info(path)
    except (OSError, GLib.Error, TypeError):
        raise PhotoError("This photo couldn't be read")
    if fmt is None or fmt.get_name() not in _FORMATS:
        raise PhotoError('Choose a JPEG or PNG photo')
    if size > MAX_BYTES or w * h > MAX_PIXELS:
        raise PhotoError('This photo is too large')
    k = min(1.0, _DECODE / max(w, h, 1))
    try:
        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, max(1, round(w * k)), max(1, round(h * k)), True)
    except GLib.Error:
        raise PhotoError("This photo couldn't be read")
    pix = pix.apply_embedded_orientation() or pix
    if pix.get_width() < MIN_WIDTH:
        raise PhotoError('This photo is too small')
    return pix


def _probabilities(pix):
    """Sky probability per pixel of the (small) analysis image, rows of floats."""
    w, h, n, stride = pix.get_width(), pix.get_height(), pix.get_n_channels(), pix.get_rowstride()
    data = pix.read_pixel_bytes().get_data()
    rgb, prob = [], []
    for y in range(h):
        o = y * stride
        row = [(data[i] / 255, data[i + 1] / 255, data[i + 2] / 255) for i in range(o, o + w * n, n)]
        rgb.append(row)
        prob.append([_sky_prob(*c) for c in row])
    # Sky colour by height, from the sure-sky pixels of each row: haze and pale sky that the
    # colour test alone misses match it
    last = None
    for y in range(h):
        sure = [c for c, p in zip(rgb[y], prob[y]) if p > 0.9]
        if len(sure) > w * 0.03:
            last = tuple(statistics.median(c[i] for c in sure) for i in range(3))
        if last is not None:
            prob[y] = [max(p, _clip((0.10 - max(abs(c[0] - last[0]), abs(c[1] - last[1]),
                                                abs(c[2] - last[2]))) / 0.04))
                       for c, p in zip(rgb[y], prob[y])]
    return prob


def _skyline(prob, w, h):
    """Per column, the first row of solid ground (three ground rows in a row) from the top."""
    first = []
    for x in range(w):
        y0 = int(h * 0.9)             # a column of sky to the bottom is a gap: keep some ground
        run = 0
        for y in range(h):
            run = run + 1 if prob[y][x] <= 0.5 else 0
            if run == 3:
                y0 = min(y0, y - 2)
                break
        first.append(y0)
    # Narrow spikes in the skyline are wisps, haze or poles: a grey opening of 7 columns
    def win(v, fn):
        pad = [v[0]] * 3 + v + [v[-1]] * 3
        return [fn(pad[i:i + 7]) for i in range(len(v))]
    height = win(win([h - f for f in first], min), max)
    return [h - v for v in height]


def _mask(prob, first, w, h):
    """Opacity 0–255 per analysis pixel: ground below the skyline, minus sky seen through trees."""
    holes_to = statistics.median(first) + 0.35 * (h - statistics.median(first))
    alpha = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if y >= first[x] and not (y < holes_to and prob[y][x] > 0.7):
                alpha[y][x] = 255
    # Pull the edge in by a pixel: edge pixels still hold the photo's bright sky, which would show
    # as a pale rim once the ground is darkened for dusk and night
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if alpha[y][x]:
                out[y][x] = min(alpha[yy][xx] for yy in range(max(0, y - 1), min(h, y + 2))
                                for xx in range(max(0, x - 1), min(w, x + 2)))
    return out


def _paint_halves(cr, src, sx, sy, ty, filt):
    """The photo (or its mask) on the left half of the band and mirrored on the right."""
    for x0, flip in ((0, False), (HALF_W, True)):
        cr.save()
        cr.rectangle(x0, 0, HALF_W, 1e6)
        cr.clip()
        if flip:
            cr.translate(2 * HALF_W, ty)
            cr.scale(-sx, sy)
        else:
            cr.translate(0, ty)
            cr.scale(sx, sy)
        if isinstance(src, GdkPixbuf.Pixbuf):
            Gdk.cairo_set_source_pixbuf(cr, src, 0, 0)
        else:
            cr.set_source_surface(src, 0, 0)
        cr.get_source().set_extend(cairo.Extend.PAD)     # beyond the photo's top: more of its sky
        cr.get_source().set_filter(filt)
        cr.paint()
        cr.restore()


def build(path):
    """
    Build the landscape from the photo at `path` into a new temporary folder next to the personal
    landscapes folder. Returns (folder, metadata). Raises PhotoError when the photo won't do.
    """
    pix = _load(path)
    W1, H1 = pix.get_width(), pix.get_height()
    ah = max(8, round(H1 * _AW / W1))
    small = pix.scale_simple(_AW, ah, GdkPixbuf.InterpType.BILINEAR)
    prob = _probabilities(small)
    first = _skyline(prob, _AW, ah)
    if sum(f > 2 for f in first) < _AW * 0.5:
        raise PhotoError('No sky found at the top of this photo')
    # Geometry: the typical skyline at _SKYLINE degrees and the photo's bottom at -BOTTOM, unless
    # that lifts the tallest feature above _TALLEST
    r_top, r_med = min(first), statistics.median(first)
    s = (_SKYLINE + BOTTOM) / max(1.0, ah - r_med)           # degrees per analysis row
    if (ah - r_top) * s - BOTTOM > _TALLEST:
        s = (_TALLEST + BOTTOM) / max(1.0, ah - r_top)
    top = float(max(3, math.ceil((ah - r_top) * s - BOTTOM + 2)))
    rows = round((top + BOTTOM) * 10)
    ra0 = ah - (top + BOTTOM) / s                            # analysis row at the band's top

    alpha = _mask(prob, first, _AW, ah)
    stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, _AW)
    buf = bytearray(stride * ah)
    for y in range(ah):
        for x in range(_AW):
            buf[y * stride + 4 * x + 3] = alpha[y][x]             # black, premultiplied
    small_mask = cairo.ImageSurface.create_for_data(buf, cairo.FORMAT_ARGB32, _AW, ah, stride)

    band = cairo.ImageSurface(cairo.FORMAT_RGB24, 2 * HALF_W, rows)
    _paint_halves(cairo.Context(band), pix, HALF_W / W1, 10 * s * ah / H1, -ra0 * 10 * s, cairo.Filter.GOOD)
    mask = cairo.ImageSurface(cairo.FORMAT_ARGB32, 2 * HALF_W, rows)
    _paint_halves(cairo.Context(mask), small_mask, HALF_W / _AW, 10 * s, -ra0 * 10 * s, cairo.Filter.BILINEAR)

    base = os.path.dirname(landscape.personal_dir())
    os.makedirs(base, exist_ok=True)
    folder = tempfile.mkdtemp(prefix='new-landscape-', dir=base)
    try:
        # Saved from the pixels alone: no EXIF (place, camera, date) is carried over
        Gdk.pixbuf_get_from_surface(band, 0, 0, 2 * HALF_W, rows).savev(
            os.path.join(folder, NAME + '.jpg'), 'jpeg', ['quality'], ['85'])
        mask.write_to_png(os.path.join(folder, NAME + '-mask.png'))
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder, {'top': top, 'bottom': BOTTOM, 'south': 0.25, 'label': LABEL}


def preview(folder, meta, width=640):
    """What Caelum shows facing south (240° of the band) over a plain day sky, as a surface."""
    pix = GdkPixbuf.Pixbuf.new_from_file(os.path.join(folder, NAME + '.jpg'))
    mask = cairo.ImageSurface.create_from_png(os.path.join(folder, NAME + '-mask.png'))
    bw, bh = pix.get_width(), pix.get_height()
    photo = cairo.ImageSurface(cairo.FORMAT_RGB24, bw, bh)
    cr = cairo.Context(photo)
    Gdk.cairo_set_source_pixbuf(cr, pix, 0, 0)
    cr.paint()
    view = bw * 240 / 360
    k = width / view
    height = round(bh * k * 1.6)                     # some sky above the landscape
    out = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
    cr = cairo.Context(out)
    sky = cairo.LinearGradient(0, 0, 0, height)
    sky.add_color_stop_rgb(0, 0.16, 0.42, 0.85)
    sky.add_color_stop_rgb(1, 0.62, 0.78, 0.95)
    cr.set_source(sky)
    cr.paint()
    cr.translate(0, height - bh * k)
    cr.scale(k, k)
    x0 = bw * meta['south'] - view / 2               # south in the middle, like the default view
    cr.rectangle(0, 2, view, bh - 2)        # the top rows are sky; the pattern wraps ground into row 0
    cr.clip()
    photo_pat, mask_pat = cairo.SurfacePattern(photo), cairo.SurfacePattern(mask)
    for pat in (photo_pat, mask_pat):
        pat.set_extend(cairo.Extend.REPEAT)
        pat.set_matrix(cairo.Matrix(x0=x0))
    cr.set_source(photo_pat)
    cr.mask(mask_pat)
    return out


def install(folder, meta):
    """Make the built landscape the user's photo landscape (replacing any earlier one)."""
    dest = landscape.personal_dir()
    os.makedirs(dest, exist_ok=True)
    for suffix in ('.jpg', '-mask.png'):
        os.replace(os.path.join(folder, NAME + suffix), os.path.join(dest, NAME + suffix))
    shutil.rmtree(folder, ignore_errors=True)
    _update_index(lambda index: index.__setitem__(NAME, meta))


def discard(folder):
    shutil.rmtree(folder, ignore_errors=True)


def remove():
    """Delete the user's photo landscape."""
    dest = landscape.personal_dir()
    _update_index(lambda index: index.pop(NAME, None))
    for suffix in ('.jpg', '-mask.png'):
        try:
            os.remove(os.path.join(dest, NAME + suffix))
        except FileNotFoundError:
            pass


def installed():
    return any(name == NAME for name, _label in landscape.personal())


def _update_index(change):
    """Edit landscapes.json in the personal folder, replacing it in one step."""
    path = os.path.join(landscape.personal_dir(), 'landscapes.json')
    try:
        with open(path) as f:
            index = json.load(f)
        if not isinstance(index, dict):
            index = {}
    except (OSError, ValueError):
        index = {}
    change(index)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(index, f, indent=2)
    os.replace(tmp, path)
