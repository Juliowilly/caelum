"""Cairo cloud rendering."""

import functools
import math
import random

import cairo

from ..core.sky import (
    LOW_BASE_KM, LOW_NEAR_KM, _clamp, band_slots, get_facing, low_clouds, plane_to_sky,
)

# ─── Cloud field ─────────────────────────────────────────────────────────────
# Each layer is a fixed pool of clouds spread along a strip STRIP screens wide that wraps
# around and scrolls with the wind (drift, in screen widths). Cover sets how many clouds of
# the pool are shown, so a weather update adds or removes clouds instead of reshuffling.

STRIP = 4.0
_MID_PITCH = 0.08   # band slot spacing (screen widths) ≈ width of an altocumulus patch

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

def _soft_puff(cr, cx, cy, rx, ry, r, g, b, alpha, edge=None):
    """
    Soft elliptical cloud puff with natural liquid-water-content density profile.
    edge: width (px) of the fading rim, so big puffs keep a crisp outline; default is
    proportional to the size (soft).
    """
    if rx <= 0 or ry <= 0 or alpha <= 0:
        return
    cr.save()
    cr.translate(cx, cy)
    cr.scale(rx, ry)
    pat = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    if edge is not None and edge < 0.6 * max(rx, ry):
        e = max(edge / max(rx, ry), 0.12)
        pat.add_color_stop_rgba(0.00,        r, g, b, alpha)
        pat.add_color_stop_rgba(1.0 - e,     r, g, b, alpha * 0.90)
        pat.add_color_stop_rgba(1.0 - e / 2, r, g, b, alpha * 0.40)
        pat.add_color_stop_rgba(1.00,        r, g, b, 0.0)
    else:
        pat.add_color_stop_rgba(0.00, r, g, b, alpha)
        pat.add_color_stop_rgba(0.28, r, g, b, alpha * 0.92)  # dense core
        pat.add_color_stop_rgba(0.58, r, g, b, alpha * 0.50)
        pat.add_color_stop_rgba(0.82, r, g, b, alpha * 0.12)  # sharp edge falloff
        pat.add_color_stop_rgba(1.00, r, g, b, 0.0)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.set_source(pat)
    cr.fill()
    cr.restore()

def deck_colour(top_col, dark_col):
    """Grey of a cloud base seen from below: the palette's mix, mostly desaturated."""
    c = [0.55 * d + 0.45 * t for t, d in zip(top_col, dark_col)]
    lum = 0.30 * c[0] + 0.59 * c[1] + 0.11 * c[2]
    return tuple(0.88 * (lum + (v - lum) * 0.35) for v in c)

def draw_mid_sheet(cr, W, H, sheet, top_col, dark_col):
    """
    Altostratus: a smooth, pale grey sheet with no visible cells, the sun a dim disc
    through it ("ground glass"). Paler than a low deck: it is higher and thinner.
    """
    if sheet <= 0:
        return
    r, g, b = (min(1.0, v * 1.12) for v in deck_colour(top_col, dark_col))
    a = 0.70 * sheet ** 1.2
    y_hor = H * 0.72
    grad = cairo.LinearGradient(0, 0, 0, y_hor)
    grad.add_color_stop_rgba(0.00, r * 0.92, g * 0.92, b * 0.94, a)
    grad.add_color_stop_rgba(1.00, r,        g,        b,        a * 0.85)
    cr.rectangle(0, 0, W, y_hor)
    cr.set_source(grad)
    cr.fill()

def _deck_cells(tex, W, H, deck, rgb):
    """Paint the deck's cells into tex, seamless across its left/right edges (width W)."""
    r, g, b = rgb
    y_hor  = H * 0.72
    a_cell = 0.48 * deck
    y, k = 0.0, 0
    while y < y_hor - H * 0.01:
        ch = max(H * 0.022, 0.17 * (y_hor - y))     # row height shrinks toward the horizon
        cw = ch * 3.4
        a_row = a_cell * _clamp(ch / (0.04 * H), 0.25, 1.0)   # far rows blend together
        n = max(1, round(W / (cw * 0.75)))
        for i in range(n):
            rng = random.Random(f'deck:{k}:{i}')
            x0 = (i + rng.uniform(-0.25, 0.25)) * W / n
            cy = y + ch * 0.5 + rng.uniform(-0.15, 0.15) * ch
            dark = rng.uniform(0.70, 0.84)
            rx, ry = cw * rng.uniform(0.45, 0.62), ch * rng.uniform(0.40, 0.55)
            a_c, a_rim = a_row * rng.uniform(0.6, 1.0), a_row * 0.45 * rng.uniform(0.5, 1.0)
            for x in (x0 - W, x0, x0 + W):          # wrap copies keep the texture seamless
                if x + cw < 0 or x - cw > W:
                    continue
                _soft_puff(tex, x, cy, rx, ry, r * dark, g * dark, b * (dark + 0.03), a_c)
                # Paler thin rim on the lit side, offset a little upward
                _soft_puff(tex, x + cw * 0.10, cy - ch * 0.22, cw * 0.30, ch * 0.16,
                           min(1, r * 1.15), min(1, g * 1.15), min(1, b * 1.12), a_rim)
        y += ch * 0.80
        k += 1

_deck_tex = {'key': None, 'surf': None}

def draw_deck(cr, W, H, deck, top_col, dark_col, drift=0.0):
    """
    Overcast stratocumulus/stratus deck seen from below: a grey ceiling over the whole sky,
    with rows of flat cells that shrink and flatten toward the horizon (perspective) and drift
    with the low-cloud wind. While the deck is not closed (deck < 1) the base is thinner and
    the gaps between cells let the sky through. The cells are painted once into a seamless
    texture that slides with the drift.
    """
    if deck <= 0:
        return
    rgb = deck_colour(top_col, dark_col)
    r, g, b = rgb
    y_hor = H * 0.72

    # Base ceiling: darker overhead, paler toward the horizon where you look through more of it
    a = 0.92 * deck ** 1.2
    grad = cairo.LinearGradient(0, 0, 0, y_hor)
    grad.add_color_stop_rgba(0.00, r * 0.86, g * 0.86, b * 0.88, a)
    grad.add_color_stop_rgba(0.60, r,        g,        b,        a * 0.96)
    grad.add_color_stop_rgba(1.00, min(1, r * 1.12), min(1, g * 1.12), min(1, b * 1.10), a * 0.90)
    cr.rectangle(0, 0, W, y_hor)
    cr.set_source(grad)
    cr.fill()

    # Cells: thick parts darker, thinner edges paler. The texture is made at the target's
    # device scale (the cloud layer renders at half size), so it is copied pixel for pixel.
    sx  = cr.get_matrix().xx
    key = (W, H, sx, round(deck, 2), tuple(round(v, 2) for v in rgb))
    if key != _deck_tex['key']:
        surf = cr.get_target().create_similar(cairo.Content.COLOR_ALPHA,
                                              int(W * sx), int(y_hor * sx) + 1)
        tex = cairo.Context(surf)
        tex.scale(sx, sx)
        _deck_cells(tex, W, H, deck, rgb)
        _deck_tex.update(key=key, surf=surf)
    shift = (drift * W) % W
    cr.save()
    cr.scale(1 / sx, 1 / sx)
    for x in (-shift, W - shift):
        cr.set_source_surface(_deck_tex['surf'], round(x * sx), 0)
        cr.paint()
    cr.restore()

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

def _cumulus_cloud(cr, W, H, cx, base_y, cw, ch, a_base, top_col, dark_col, rng, anvil=False,
                   side=1.0):
    """
    side: 1 = seen from the side (near the horizon: flat dark base, sunlit cauliflower top),
    0 = seen from below (overhead: shaded grey underside, no base line or sunlit top).
    """
    rd, gd, bd = dark_col
    # Body colour: sunlit white from the side, grey underside from below
    under = tuple(0.62 * d + 0.38 * t for t, d in zip(top_col, dark_col))
    rt, gt, bt = (side * t + (1 - side) * u for t, u in zip(top_col, under))
    # Small (distant) clouds get fewer puffs: the detail wouldn't show
    detail = _clamp(cw / (0.10 * W), 0.25, 3.0)
    shrink = 1.0 / math.sqrt(max(detail, 1.0))   # many smaller puffs on big clouds
    edge   = 0.012 * W                            # crisp outline, whatever the size
    spread = 0.80 if detail >= 0.4 else 0.45      # small clouds: one compact lump

    # 1. Ground shadow — faint dark ellipse on terrain for large nearby clouds
    if base_y > 0.60 * H and cw > 0.10 * W:
        _soft_puff(cr, cx, H * 0.73,
                   cw * 0.50, H * 0.010,
                   rd * 0.45, gd * 0.45, bd * 0.50,
                   a_base * 0.20)

    # The cloud is built at full strength in its own group and laid down once at a_base,
    # so overlapping puffs read as one solid shape instead of stacked translucent lobes
    a_cloud, a_base = a_base, 1.0
    cr.save()
    cr.rectangle(cx - cw * 1.7, base_y - ch * 2.2, cw * 3.4, ch * 3.4)
    cr.clip()
    cr.push_group()

    # 2. Flat dark base — wide, horizontally compressed (the cloud's LCL line), side view only
    if side > 0.05:
        a_flat = a_base * side * min(1.0, detail * 2.0)   # faint on small, distant clouds
        _soft_puff(cr, cx, base_y, cw * 1.08, ch * 0.16,
                   rd, gd, bd, a_flat * 0.90)
        _soft_puff(cr, cx, base_y - ch * 0.05, cw * 0.95, ch * 0.09,
                   rd, gd, bd, a_flat * 0.55)   # sharp inner edge

    # 3. Main body — several overlapping puffs rising from the base
    n_body = max(3, round(rng.randint(4, 7) * detail))
    for j in range(n_body):
        ox  = (j / max(1, n_body - 1) - 0.5) * cw * spread
        dim = 1.0 - abs(ox / (cw * 0.5)) * 0.14 * side   # side view: edge puffs darker
        _soft_puff(cr,
                   cx + ox, base_y + rng.uniform(-ch * 0.18, ch * 0.06),
                   cw * rng.uniform(0.28, 0.54) * shrink,
                   ch * rng.uniform(0.55, 0.92),
                   rt * dim, gt * dim, bt * dim,
                   a_base * rng.uniform(0.80, 1.00), edge)
    # 4. Cauliflower second tier — smaller puffs on top
    # Distant clouds: a small flat lump is all that shows
    n_top = max(1, round(rng.randint(2, 5) * detail)) if detail >= 0.4 else 0
    for j in range(n_top):
        ox = (j / max(1, n_top - 1) - 0.5) * cw * 0.55
        _soft_puff(cr,
                   cx + ox, base_y - ch * rng.uniform(0.38, 0.72),
                   cw * rng.uniform(0.18, 0.36) * shrink,
                   ch * rng.uniform(0.30, 0.55),
                   rt, gt, bt, a_base * rng.uniform(0.65, 0.90), edge)

    # 5. Bright sunlit specular highlight at the very top (side view)
    if side > 0.05 and detail >= 0.4:
        _soft_puff(cr,
                   cx + rng.uniform(-cw * 0.10, cw * 0.10),
                   base_y - ch * rng.uniform(0.62, 0.90),
                   cw * 0.20 * shrink, ch * 0.26,
                   min(1.0, top_col[0] + 0.07), min(1.0, top_col[1] + 0.05),
                   min(1.0, top_col[2] + 0.02), a_base * 0.60 * side)

    # 6. Cumulonimbus anvil — flat spreading top for thunderstorm clouds
    if anvil:
        anvil_y = base_y - ch * 0.88
        _soft_puff(cr, cx, anvil_y, cw * 1.55, ch * 0.16,
                   rd * 0.75, gd * 0.75, bd * 0.80, a_base * 0.70)
        _soft_puff(cr, cx, anvil_y - ch * 0.06, cw * 1.35, ch * 0.10,
                   rd * 0.65, gd * 0.65, bd * 0.72, a_base * 0.45)

    cr.pop_group_to_source()
    cr.paint_with_alpha(a_cloud)
    cr.restore()

def _distant_bank(cr, W, H, coverage, top_col, dark_col, a_base, px_deg, py_deg):
    """
    Clouds beyond LOW_NEAR_KM: within a few degrees of the horizon, where perspective packs
    them together, so even scattered cloud shows as a nearly continuous low bank.
    Fixed to azimuths, so it turns with the view.
    """
    el_max = math.degrees(math.atan2(LOW_BASE_KM, LOW_NEAR_KM))
    sat    = 1.0 - (1.0 - coverage / 100.0) ** 4     # share of the bank that is cloud
    col    = tuple(0.80 * t + 0.20 * d for t, d in zip(top_col, dark_col))
    facing = get_facing()
    for k in range(72):
        rng = random.Random(f'bank:{k}')
        if rng.random() > sat:
            continue
        rel = ((k * 5.0 + rng.uniform(0, 5.0) - facing + 180.0) % 360.0) - 180.0
        if abs(rel) > 130.0:
            continue
        cx = W * 0.06 + (rel + 120.0) * px_deg
        el = rng.uniform(0.8, el_max * 0.8)
        cy = H * 0.72 - el * py_deg
        cw = rng.uniform(5.0, 10.0) * px_deg
        ch = rng.uniform(1.0, 2.0) * py_deg
        a  = a_base * rng.uniform(0.45, 0.85) * (0.6 + 0.4 * el / el_max)   # haze near 0°
        _soft_puff(cr, cx, cy, cw, ch, *col, a)
        _soft_puff(cr, cx, cy + ch * 0.45, cw * 1.05, ch * 0.30, *dark_col, a * 0.6)

def draw_cumulus(cr, W, H, coverage, top_col, dark_col, wmo=0, offset=(0.0, 0.0)):
    """
    Low cumulus on a flat layer LOW_BASE_KM up, drawn in perspective: crisp flat base,
    cauliflower puff tower, specular highlight. Cumulonimbus anvil for thunderstorm WMO
    codes (≥95). offset (km east, km north) is how far the wind has carried the layer.
    """
    if coverage < 5:
        return
    is_cb  = wmo >= 95
    a_base = 0.78 + 0.17 * (coverage / 100.0)   # cumulus are nearly opaque
    px_deg = W * 0.88 / 240.0          # panorama scale (see sky_to_screen)
    py_deg = H * 0.66 / 90.0
    facing = get_facing()
    h      = LOW_BASE_KM

    _distant_bank(cr, W, H, coverage, top_col, dark_col, a_base, px_deg, py_deg)

    for x, y, size, thick, i in low_clouds(coverage, offset):
        d       = math.hypot(x, y)
        _el, az = plane_to_sky(x, y, h)
        rel     = ((az - facing + 180.0) % 360.0) - 180.0
        half_w  = math.degrees(min(size / 2 / max(d, 0.05), 1.3))
        if abs(rel) - half_w > 120.0:
            continue
        # Vertical extent: far and near edge of the base, and the top of the tower
        el_far  = math.degrees(math.atan2(h, d + size / 2))
        el_near = math.degrees(math.atan2(h, max(d - size / 2, 0.02)))
        el_top  = math.degrees(math.atan2(h + thick, d + size * 0.15))
        lo, hi  = min(el_far, el_top), min(max(el_near, el_top), 89.0)
        cx      = W * 0.06 + (rel + 120.0) * px_deg
        cw      = 2 * half_w * px_deg
        if cw < 0.012 * W:
            continue   # a speck: part of the distant bank's look
        # The cumulus shape spans ~0.55·ch below its base line to ~1.2·ch above it
        extent  = max((hi - lo) * py_deg, 3.0)
        ch      = extent / 1.75
        base_y  = H * 0.72 - lo * py_deg - 0.55 * ch
        haze    = 1.0 - 0.55 * _clamp((d - 4.0) / 8.0, 0.0, 1.0)   # distant ones fade into haze
        rng     = random.Random(f'lowc:{i}:shape')
        side    = _clamp(1.0 - (0.5 * (lo + hi) - 12.0) / 30.0, 0.0, 1.0)   # 12° → 42°
        _cumulus_cloud(cr, W, H, cx, base_y, cw, ch, a_base * haze, top_col, dark_col, rng,
                       anvil=is_cb and size > 2.5, side=side)
