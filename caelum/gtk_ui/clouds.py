"""Cairo cloud rendering."""

import functools
import math
import random

import cairo

from ..core.sky import _clamp, band_slots

# ─── Cloud field ─────────────────────────────────────────────────────────────
# Each layer is a fixed pool of clouds spread along a strip STRIP screens wide that wraps
# around and scrolls with the wind (drift, in screen widths). Cover sets how many clouds of
# the pool are shown, so a weather update adds or removes clouds instead of reshuffling.

STRIP = 4.0
_LOW_PITCH = 0.14   # band slot spacing (screen widths) ≈ width over which a cumulus hides the sun
_MID_PITCH = 0.08

@functools.lru_cache(maxsize=32)
def _pool(layer, n):
    """First n clouds of a layer: (strip position 0–1, seed for that cloud's shape)."""
    return tuple((random.Random(f'{layer}:{i}:pos').random(), f'{layer}:{i}') for i in range(n))

_band_slots = functools.lru_cache(maxsize=32)(band_slots)

def _band(layer, cover, pitch, drift, W, body, reach):
    """
    Yield (screen x, fade, rng) for band clouds near the body. They fade out with distance
    from it (gone at reach × pitch), so the band never shows as a row across the sky.
    """
    bx = body[0]
    for u, k in _band_slots(layer, cover, STRIP, pitch):
        x = ((u - drift) % STRIP) * W
        for x in (x, x - STRIP * W):
            fade = _clamp((reach * pitch * W - abs(x - bx)) / (0.6 * pitch * W), 0.0, 1.0)
            if fade > 0:
                yield x, fade, random.Random(f'{layer}:band:{k}:shape')

def _visible(pool, drift, W, margin):
    """Yield (screen x, rng) for pool clouds within margin of the screen."""
    for u, seed in pool:
        x = ((u * STRIP - drift) % STRIP) * W
        if x > STRIP * W - margin:
            x -= STRIP * W
        if -margin < x < W + margin:
            yield x, random.Random(seed)

# ─── Cloud rendering ─────────────────────────────────────────────────────────

def _soft_puff(cr, cx, cy, rx, ry, r, g, b, alpha):
    """Soft elliptical cloud puff with natural liquid-water-content density profile."""
    if rx <= 0 or ry <= 0 or alpha <= 0:
        return
    cr.save()
    cr.translate(cx, cy)
    cr.scale(rx, ry)
    pat = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    pat.add_color_stop_rgba(0.00, r, g, b, alpha)
    pat.add_color_stop_rgba(0.28, r, g, b, alpha * 0.92)  # dense core
    pat.add_color_stop_rgba(0.58, r, g, b, alpha * 0.50)
    pat.add_color_stop_rgba(0.82, r, g, b, alpha * 0.12)  # sharp edge falloff
    pat.add_color_stop_rgba(1.00, r, g, b, 0.0)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.set_source(pat)
    cr.fill()
    cr.restore()

def _draw_overcast_sheet(cr, W, H, total, top_col, dark_col):
    """Uniform gray ceiling for heavily overcast skies (total > 65%)."""
    t  = _clamp((total - 65) / 35.0, 0.0, 1.0)
    rt, gt, bt = top_col
    rd, gd, bd = dark_col
    sr = (rd + rt) * 0.52;  sg = (gd + gt) * 0.52;  sb = (bd + bt) * 0.54
    y0    = H * 0.72
    alpha = t * 0.52
    grad  = cairo.LinearGradient(0, 0, 0, y0)
    grad.add_color_stop_rgba(0.00, sr, sg, sb, alpha * 0.95)
    grad.add_color_stop_rgba(0.38, sr, sg, sb, alpha * 0.85)
    grad.add_color_stop_rgba(0.72, sr, sg, sb, alpha * 0.35)
    grad.add_color_stop_rgba(1.00, sr, sg, sb, 0.0)
    cr.rectangle(0, 0, W, y0)
    cr.set_source(grad)
    cr.fill()

def draw_cirrus(cr, W, H, coverage, col, drift=0.0):
    """High-altitude ice clouds: thin wispy streaks with fade envelope and parallel fibers."""
    if coverage < 5:
        return
    r, g, b = col
    n      = int((coverage / 100.0 * 10 + 1) * STRIP)
    a_base = 0.08 + 0.13 * (coverage / 100.0)

    for cx, rng in _visible(_pool('high', n), drift, W, 0.2 * W):
        cy     = rng.uniform(0.02, 0.26) * H
        length = rng.uniform(0.08, 0.30) * W
        thick  = rng.uniform(0.005, 0.013) * H
        tilt   = rng.uniform(-0.22, 0.22)
        n_seg  = rng.randint(7, 13)
        curve  = rng.uniform(-0.08, 0.08) * length  # gentle hook curvature

        # Main streak — alpha envelope bright at centre, fading at both ends
        for j in range(n_seg):
            t   = j / max(1, n_seg - 1)
            env = 1.0 - (abs(t - 0.5) * 2) ** 1.6
            sx  = cx + (t - 0.5) * length * math.cos(tilt)
            sy  = (cy + (t - 0.5) * length * math.sin(tilt)
                   + rng.uniform(-thick, thick)
                   + curve * (t - 0.5) ** 2)   # slight curve toward one end
            sw  = length / n_seg * 1.9 * rng.uniform(0.6, 1.4)
            sh  = thick * rng.uniform(0.6, 1.8)
            _soft_puff(cr, sx, sy, sw, sh, r, g, b, a_base * rng.uniform(0.5, 1.0) * env)

        # Parallel fiber ghost (mare's tails character)
        if rng.random() < 0.65:
            off = rng.uniform(0.6, 1.8) * thick * 2
            for j in range(n_seg // 2):
                t   = j / max(1, n_seg // 2 - 1)
                env = 1.0 - (abs(t - 0.5) * 2) ** 1.4
                sx  = cx + (t - 0.5) * length * 0.68 * math.cos(tilt)
                sy  = cy + off + (t - 0.5) * length * 0.68 * math.sin(tilt)
                _soft_puff(cr, sx, sy,
                           length / n_seg * 1.2, thick * 0.65,
                           r, g, b, a_base * 0.38 * env)

def _altocumulus_clump(cr, cx, cy, cw, ch, a, col, shade, rng):
    r, g, b = col
    rs, gs, bs = shade
    for _ in range(rng.randint(2, 4)):
        ox = rng.uniform(-cw * 0.38, cw * 0.38)
        oy = rng.uniform(-ch * 0.28, ch * 0.05)
        pw = cw * rng.uniform(0.35, 0.72)
        ph = ch * rng.uniform(0.58, 1.10)
        _soft_puff(cr, cx + ox, cy + oy, pw, ph,
                   r, g, b, a * rng.uniform(0.72, 1.00))
        # Shadow underside: darker, flatter, slightly below centre
        _soft_puff(cr, cx + ox, cy + oy + ph * 0.30, pw * 0.85, ph * 0.20,
                   rs, gs, bs, a * 0.30)

def draw_altocumulus(cr, W, H, coverage, col, drift=0.0, body=None):
    """
    Mid-level clouds: compact rounded puffs with lit top and shadowed underside.
    body=(x, y, r): the sun/moon, which the drifting band of patches passes over.
    """
    if coverage < 5:
        return
    r, g, b = col
    shade  = (r * 0.68, g * 0.70, b * 0.72)   # shadow underside colour
    n      = int((coverage / 100.0 * 24 + 3) * STRIP)
    a_base = 0.70 + 0.28 * (coverage / 100.0)

    for cx, rng in _visible(_pool('mid', n), drift, W, 0.08 * W):
        cy = rng.uniform(0.08, 0.58) * H
        cw = rng.uniform(0.022, 0.062) * W
        ch = rng.uniform(0.012, 0.030) * H
        _altocumulus_clump(cr, cx, cy, cw, ch, a_base * rng.uniform(0.65, 1.00),
                           col, shade, rng)

    if body:
        # A patch of clumps per slot, centred on the body's height
        for cx, fade, rng in _band('mid', coverage, _MID_PITCH, drift, W, body, 1.0):
            for _ in range(rng.randint(1, 2)):
                _altocumulus_clump(cr,
                                   cx + rng.uniform(-0.020, 0.020) * W,
                                   body[1] + rng.uniform(-0.015, 0.015) * H,
                                   rng.uniform(0.030, 0.050) * W, rng.uniform(0.016, 0.028) * H,
                                   a_base * fade * rng.uniform(0.85, 1.00), col, shade, rng)

def _cumulus_cloud(cr, W, H, cx, base_y, cw, ch, a_base, top_col, dark_col, rng, anvil=False):
    rt, gt, bt = top_col
    rd, gd, bd = dark_col

    # 1. Ground shadow — faint dark ellipse on terrain for large nearby clouds
    if base_y > 0.60 * H:
        _soft_puff(cr, cx, H * 0.73,
                   cw * 0.50, H * 0.010,
                   rd * 0.45, gd * 0.45, bd * 0.50,
                   a_base * 0.20)

    # 2. Flat dark base — wide, horizontally compressed (the cloud's LCL line)
    _soft_puff(cr, cx, base_y, cw * 1.08, ch * 0.16,
               rd, gd, bd, a_base * 0.90)
    _soft_puff(cr, cx, base_y - ch * 0.05, cw * 0.95, ch * 0.09,
               rd, gd, bd, a_base * 0.55)   # sharp inner edge

    # 3. Main body — several overlapping puffs rising from the base
    n_body = rng.randint(4, 7)
    for j in range(n_body):
        ox  = (j / max(1, n_body - 1) - 0.5) * cw * 0.80
        dim = 1.0 - abs(ox / (cw * 0.5)) * 0.14   # edge puffs slightly darker
        _soft_puff(cr,
                   cx + ox, base_y + rng.uniform(-ch * 0.18, ch * 0.06),
                   cw * rng.uniform(0.28, 0.54),
                   ch * rng.uniform(0.55, 0.92),
                   rt * dim, gt * dim, bt * dim,
                   a_base * rng.uniform(0.80, 1.00))

    # 4. Cauliflower second tier — smaller puffs on top
    n_top = rng.randint(2, 5)
    for j in range(n_top):
        ox = (j / max(1, n_top - 1) - 0.5) * cw * 0.55
        _soft_puff(cr,
                   cx + ox, base_y - ch * rng.uniform(0.38, 0.72),
                   cw * rng.uniform(0.18, 0.36),
                   ch * rng.uniform(0.30, 0.55),
                   rt, gt, bt, a_base * rng.uniform(0.65, 0.90))

    # 5. Bright sunlit specular highlight at the very top
    _soft_puff(cr,
               cx + rng.uniform(-cw * 0.10, cw * 0.10),
               base_y - ch * rng.uniform(0.62, 0.90),
               cw * 0.20, ch * 0.26,
               min(1.0, rt + 0.07), min(1.0, gt + 0.05), min(1.0, bt + 0.02),
               a_base * 0.60)

    # 6. Cumulonimbus anvil — flat spreading top for thunderstorm clouds
    if anvil:
        anvil_y = base_y - ch * 0.88
        _soft_puff(cr, cx, anvil_y, cw * 1.55, ch * 0.16,
                   rd * 0.75, gd * 0.75, bd * 0.80, a_base * 0.70)
        _soft_puff(cr, cx, anvil_y - ch * 0.06, cw * 1.35, ch * 0.10,
                   rd * 0.65, gd * 0.65, bd * 0.72, a_base * 0.45)

def draw_cumulus(cr, W, H, coverage, top_col, dark_col, wmo=0, drift=0.0, body=None):
    """
    Low cumulus: crisp flat base, cauliflower puff tower, specular highlight,
    ground shadow. Cumulonimbus anvil for thunderstorm WMO codes (≥95).
    body=(x, y, r): the sun/moon, which the drifting band of clouds passes over.
    """
    if coverage < 5:
        return
    is_cb  = wmo >= 95
    n      = int((coverage / 100.0 * 8 + 1) * STRIP)
    a_base = 0.48 + 0.42 * (coverage / 100.0)

    for i, (cx, rng) in enumerate(_visible(_pool('low', n), drift, W, 0.4 * W)):
        # Cloud base sits near the horizon (LCL level)
        base_y = rng.uniform(0.54, 0.70) * H
        big    = is_cb and i % 5 == 0
        if big:
            cw = rng.uniform(0.18, 0.34) * W
            ch = rng.uniform(0.20, 0.34) * H
        else:
            cw = rng.uniform(0.07, 0.21) * W
            ch = rng.uniform(0.06, 0.13) * H
        _cumulus_cloud(cr, W, H, cx, base_y, cw, ch, a_base, top_col, dark_col, rng,
                       anvil=big)

    if body:
        # One cloud per slot, its dense lower body at the body's height
        for cx, fade, rng in _band('low', coverage, _LOW_PITCH, drift, W, body, 1.5):
            cw = rng.uniform(0.14, 0.18) * W
            ch = rng.uniform(0.09, 0.13) * H
            if body[1] + ch * 0.20 > 0.70 * H:
                continue   # body at the horizon: the general clouds cover it
            _cumulus_cloud(cr, W, H, cx, body[1] + ch * 0.20, cw, ch,
                           max(a_base, 0.95) * fade, top_col, dark_col, rng)
