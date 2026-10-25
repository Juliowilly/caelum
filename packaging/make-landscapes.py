#!/usr/bin/env python3
"""
Build the landscape images shipped in caelum/data/landscapes/ from Poly Haven panoramas (CC0).

Developer tool only (needs numpy and Pillow; Caelum itself doesn't):
    python3 packaging/make-landscapes.py [CACHE_DIR]

For each panorama it downloads the 8K tonemapped JPEG (cached), keeps the band from `top`° above
to BOTTOM° below the horizon, cuts the sky out, and writes
    <name>.jpg        the photo band (RGB)
    <name>-mask.png   its opacity, in the alpha channel (255 = ground, 0 = sky)
plus landscapes.json with the band's geometry, which the app reads.
"""

import json
import os
import sys
import urllib.request

import numpy as np
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'caelum', 'data', 'landscapes')
OUT_W = 3600        # 10 px per degree: sharp at 1080p, fine at 4K
BOTTOM = 40.0       # the screen shows down to ~38° below the horizon

# name: Poly Haven slug, author, how much sky to keep above the tallest feature, cut-out tuning,
# and `south`: the panorama column (0–1) that faces south, Caelum's default view
LANDSCAPES = {
    'plain':     dict(slug='noon_grass',           author='Greg Zaal',       tol=0.10, b_min=0.30, south=0.50),
    'mountains': dict(slug='alps_field',           author='Andreas Mischok', tol=0.04, b_min=0.62, south=0.50),
    'sea':       dict(slug='spiaggia_di_mondello', author='Andreas Mischok', tol=0.10, b_min=0.30, south=0.00),
}
URL = 'https://dl.polyhaven.org/file/ph-assets/HDRIs/extra/Tonemapped%20JPG/{}.jpg'
SCAN_TOP = 50.0     # elevation scanned for features; the saved band is trimmed to what is used


def fetch(slug, cache):
    path = os.path.join(cache, slug + '.jpg')
    if not os.path.exists(path):
        print('downloading', slug)
        urllib.request.urlretrieve(URL.format(slug), path)
    return path


def load_band(path, top):
    im = Image.open(path).convert('RGB')
    w, h = im.size
    y0 = int(round(h * (0.5 - top / 180)))
    y1 = int(round(h * (0.5 + BOTTOM / 180)))
    band = im.crop((0, y0, w, y1))
    return band.resize((OUT_W, round(band.height * OUT_W / w)), Image.LANCZOS)


def sky_prob(a, b_min):
    """0–1 per pixel: clear blue sky (blue leads and is bright enough) or pale haze/cloud."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    blue = b - np.maximum(r, g)
    sat = a.max(-1) - a.min(-1)
    p_blue = np.clip((blue - 0.03) / 0.08, 0, 1) * np.clip((b - b_min) / 0.10, 0, 1)
    p_haze = np.clip((lum - 0.60) / 0.10, 0, 1) * np.clip((0.22 - sat) / 0.10, 0, 1) * (b >= g - 0.02)
    return np.maximum(p_blue, p_haze)


def _win(x, k, fn):
    pad = np.concatenate([x[-(k // 2):], x, x[:k // 2]])      # the panorama wraps around
    return fn(np.lib.stride_tricks.sliding_window_view(pad, k), axis=1)


def _open1d(x, k):
    """Grey opening (min then max filter): removes peaks narrower than k columns."""
    return _win(_win(x, k, np.min), k, np.max)


def cutout(band, top, tol, b_min):
    """Opacity 0–1 of the band, and the elevation of its tallest feature."""
    a = np.asarray(band).astype(np.float32) / 255
    h, w = a.shape[:2]
    horizon = round(h * top / (top + BOTTOM))
    p = sky_prob(a, b_min)
    # Sky colour by height, learnt from the sure-sky pixels of each row (the sky changes mostly
    # with elevation); rows near the horizon with none borrow from the row above
    model = np.zeros((h, 3), np.float32)
    last = None
    for y in range(h):
        sure = p[y] > 0.9
        if sure.sum() > w * 0.03:
            last = np.median(a[y][sure], axis=0)
        if last is not None:
            model[y] = last
    dist = np.abs(a - model[:, None, :]).max(-1)
    p = np.maximum(p, np.clip((tol - dist) / 0.04, 0, 1) * (model.sum(-1) > 0)[:, None])
    # Skyline: sky runs down each column from the top until the first solid run of ground
    ground = p <= 0.5
    run = np.zeros(ground.shape, np.int32)
    for y in range(h - 1, -1, -1):
        run[y] = np.where(ground[y], (run[y + 1] + 1) if y + 1 < h else 1, 0)
    solid = run >= 3
    first = np.where(solid.any(0), solid.argmax(0), h)
    first = np.minimum(first, horizon + 2)            # nothing below the horizon is sky
    # Narrow spikes in the skyline are cloud wisps, haze or poles
    height = _open1d(horizon + 2 - first, 9)
    first = horizon + 2 - height
    yy = np.arange(h)[:, None]
    alpha = (yy >= first[None, :]).astype(np.float32)
    # Sky seen through canopies and between trees
    alpha[(p > 0.7) & (yy < horizon - 3)] = 0
    return alpha, height.max() * (top + BOTTOM) / h


def build(name, spec, cache):
    src = fetch(spec['slug'], cache)
    alpha, tallest = cutout(load_band(src, SCAN_TOP), SCAN_TOP, spec['tol'], spec['b_min'])
    top = float(np.ceil(tallest + 2))
    band = load_band(src, top)
    h = band.height
    alpha = alpha[-h:]                                 # same rows, trimmed from the top
    # Pull the edge in by a pixel before softening it: edge pixels still hold the photo's bright sky,
    # which would show as a pale rim once the ground is darkened for dusk and night
    mask = (Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))
            .filter(ImageFilter.GaussianBlur(0.8)))
    band.save(os.path.join(OUT_DIR, name + '.jpg'), quality=82, optimize=True, progressive=True)
    # Opacity in the alpha channel (black otherwise), which is how cairo reads a PNG mask
    Image.merge('LA', (Image.new('L', mask.size, 0), mask)).save(
        os.path.join(OUT_DIR, name + '-mask.png'), optimize=True)
    print(f'{name}: {spec["slug"]} {band.size[0]}x{h}, top {top:.0f}°')
    return dict(top=top, bottom=BOTTOM, south=spec['south'],
                source=f'https://polyhaven.com/a/{spec["slug"]}', author=spec['author'], license='CC0-1.0')


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser('~'), '.cache', 'caelum-landscapes')
    os.makedirs(cache, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {name: build(name, spec, cache) for name, spec in LANDSCAPES.items()}
    with open(os.path.join(OUT_DIR, 'landscapes.json'), 'w') as f:
        json.dump(meta, f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main()
