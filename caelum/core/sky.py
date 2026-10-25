"""Panorama projection, sky/cloud colour palettes and small math helpers."""

import math
import random

_FACING = 180.0   # azimuth the panorama is centred on; updated each frame from config

def set_facing(az):
    global _FACING
    _FACING = az

def get_facing():
    return _FACING

def _seg_dist(px, py, ax, ay, bx, by):
    """Distance from point (px,py) to line segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax)*dx + (py - ay)*dy) / (dx*dx + dy*dy)))
    return math.hypot(px - ax - t*dx, py - ay - t*dy)

# ─── Sky coordinate → screen ─────────────────────────────────────────────────

def sky_to_screen(el, az, W, H):
    """
    Panoramic projection: 240° wide, centred on _FACING azimuth.
    Returns None when body is below the horizon or outside the 240° field of view
    (clamping would pile those objects up along the screen edges).
    """
    if el < 0:
        return None
    rel = ((az - _FACING + 180.0) % 360.0) - 180.0   # -180..+180, 0 = centre
    if abs(rel) > 120.0:
        return None
    t   = (rel + 120.0) / 240.0
    x   = W * 0.06 + t * (W * 0.88)
    y   = H * 0.72 - (H * 0.66) * _clamp(el / 90.0, 0.0, 1.0)
    return x, y

# ─── Color helpers ────────────────────────────────────────────────────────────

def _lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

_SKY = {
    # No light pollution — true dark sky at night, natural transitions
    'night':    (0.00, 0.00, 0.04, 0.94),   # deep space black
    'astro':    (0.01, 0.01, 0.08, 0.86),
    'nautical': (0.03, 0.05, 0.18, 0.70),
    'civil':    (0.08, 0.06, 0.24, 0.54),
    'dawn':     (0.48, 0.18, 0.10, 0.38),
    'sunrise':  (0.82, 0.40, 0.06, 0.28),
    'morning':  (0.38, 0.60, 0.90, 0.20),
    'noon':     (0.16, 0.48, 0.96, 0.16),
    'afternoon':(0.26, 0.54, 0.92, 0.20),
    'sunset':   (0.78, 0.35, 0.07, 0.30),
    'dusk':     (0.32, 0.10, 0.22, 0.52),
}

def sky_color(el):
    S = _SKY
    if el < -18:   return S['night']
    if el < -12:   return _lerp(S['night'],    S['astro'],    (el + 18) / 6)
    if el < -6:    return _lerp(S['astro'],    S['nautical'], (el + 12) / 6)
    if el < -0.83: return _lerp(S['nautical'], S['civil'],    (el + 6)  / 5.17)
    if el < 3:     return _lerp(S['civil'],    S['dawn'],     (el + 0.83) / 3.83)
    if el < 8:     return _lerp(S['dawn'],     S['sunrise'],  (el - 3)  / 5)
    if el < 20:    return _lerp(S['sunrise'],  S['morning'],  (el - 8)  / 12)
    if el < 50:    return _lerp(S['morning'],  S['noon'],     (el - 20) / 30)
    return S['noon']

# ─── Sky brightness ──────────────────────────────────────────────────────────
# Faintest naked-eye magnitude by sun elevation (°): daylight hides everything but the moon,
# Venus appears around sunset, then Jupiter, Mars, and the rest as twilight deepens.
_LIMIT_MAG = ((10.0, -4.6), (0.0, -3.5), (-3.0, -1.5), (-6.0, 1.0),
              (-9.0, 3.0), (-12.0, 4.5), (-18.0, 6.0))

def limiting_magnitude(sun_el):
    pts = _LIMIT_MAG
    if sun_el >= pts[0][0]:
        return pts[0][1]
    for (e0, m0), (e1, m1) in zip(pts, pts[1:]):
        if sun_el >= e1:
            return m0 + (m1 - m0) * (e0 - sun_el) / (e0 - e1)
    return pts[-1][1]

def naked_eye_visibility(mag, sun_el):
    """0–1: fades in over one magnitude as the sky darkens past the object's brightness."""
    return _clamp(limiting_magnitude(sun_el) - mag, 0.0, 1.0)

# ─── Cloud optics ────────────────────────────────────────────────────────────
# Cloud cover is a fraction of sky area, not a dimmer: where there is no cloud the sun
# is at full strength. Each layer blocks a different share of the light where it is.
_LAYER_OPACITY = {'low': 1.0, 'mid': 0.7, 'high': 0.2}

def cloud_layers(clouds):
    """(low, mid, high) cover in %. A total with no layer split counts as mid-level."""
    low, mid, high = clouds.get('low', 0), clouds.get('mid', 0), clouds.get('high', 0)
    if clouds.get('total', 0) > 0 and low == 0 and mid == 0 and high == 0:
        mid = clouds['total']
    return low, mid, high

def opaque_cover(clouds):
    """Fraction 0–1 of sky light blocked, weighting each layer by its optical thickness."""
    clear = 1.0
    for name, cov in zip(('low', 'mid', 'high'), cloud_layers(clouds)):
        clear *= 1.0 - _LAYER_OPACITY[name] * _clamp(cov / 100.0, 0.0, 1.0)
    return 1.0 - clear

def overcast_deck(clouds):
    """How closed the cloud deck is, 0–1: from ~65% opaque cover to a solid ceiling at ~95%."""
    return _clamp((opaque_cover(clouds) - 0.65) / 0.30, 0.0, 1.0)

def mid_sheet(clouds):
    """How closed the mid-level layer is, 0–1: altocumulus merging into altostratus."""
    return _clamp((cloud_layers(clouds)[1] - 60) / 40.0, 0.0, 1.0)

def veil_transmission(clouds):
    """
    Uniform dimming of the sun/moon by layers dense enough to form a continuous sheet.
    Broken cloud does not dim the sun everywhere; it hides it only where a cloud is drawn
    in front of it (see band_slots). Cirrus is a thin veil at any cover.
    """
    low, mid, high = cloud_layers(clouds)
    t  = 1.0 - 0.15 * _clamp(high / 100.0, 0.0, 1.0)         # cirrostratus
    t *= 1.0 - 0.55 * mid_sheet(clouds)                       # altostratus sheet
    t *= 1.0 - 0.85 * _clamp((low - 70) / 30.0, 0.0, 1.0)    # stratus / stratocumulus deck
    return t

# ─── Low cloud layer: real clouds on a flat layer, seen in perspective ───────
# Cumulus sit on a plane LOW_BASE_KM up. Positions are in km east (x) / north (y) of the
# observer, on a tile that repeats every LOW_TILE_KM and moves with the wind. Overhead clouds
# look big and move fast; distant ones shrink and crowd toward the horizon, and any line of
# sight is blocked with a chance equal to the cover.
LOW_BASE_KM = 1.5
LOW_TILE_KM = 50.0
LOW_NEAR_KM = 12.0   # drawn one by one up to here; beyond, a distant cloud bank

_low_pool = []

def _low_pool_upto(n):
    while len(_low_pool) < n:
        rng = random.Random(f'lowc:{len(_low_pool)}')
        half = LOW_TILE_KM / 2
        size = min(0.6 + rng.expovariate(1 / 0.9), 4.0)       # diameter, km
        _low_pool.append((rng.uniform(-half, half), rng.uniform(-half, half),
                          size, size * rng.uniform(0.45, 0.80)))  # thickness, km
    return _low_pool

# Mean footprint (km²) of the size distribution above
_LOW_MEAN_AREA = sum(math.pi * c[2] ** 2 / 4 for c in _low_pool_upto(4000)) / 4000

def low_cloud_count(cover):
    """Clouds on the tile so their (overlapping) footprints cover `cover` % of the layer."""
    f = _clamp(cover / 100.0, 0.0, 0.97)
    return int(-math.log(1.0 - f) * LOW_TILE_KM ** 2 / _LOW_MEAN_AREA)

def low_clouds(cover, offset, max_km=LOW_NEAR_KM):
    """[(x, y, size, thickness, index)] within max_km of the observer, nearest last."""
    ox, oy = offset
    half, tile = LOW_TILE_KM / 2, LOW_TILE_KM
    out = []
    n = low_cloud_count(cover)
    for i, (x0, y0, size, thick) in enumerate(_low_pool_upto(n)[:n]):
        x = (x0 + ox + half) % tile - half
        y = (y0 + oy + half) % tile - half
        if x * x + y * y <= max_km * max_km:
            out.append((x, y, size, thick, i))
    out.sort(key=lambda c: -(c[0] ** 2 + c[1] ** 2))      # far to near, for painting
    return out

def plane_to_sky(x, y, h):
    """(elevation°, azimuth°) of a point x km east, y km north, h km up."""
    return (math.degrees(math.atan2(h, math.hypot(x, y))),
            math.degrees(math.atan2(x, y)) % 360.0)

def band_slots(layer, cover, strip, pitch):
    """
    Clouds of the band that drifts past the sun/moon: fixed slots every `pitch` along a
    wrap-around strip of length `strip`, each shown with a chance equal to the cover.
    A slot's cloud is about `pitch` wide, so as the band drifts the body is hidden for
    that share of the time. Returns [(centre, slot index)] of the slots shown; a cover
    change only adds or removes slots, it never moves the others.
    """
    out = []
    for k in range(int(round(strip / pitch))):
        if random.Random(f'{layer}:band:{k}').random() * 100 < cover:
            out.append(((k + 0.5) * pitch, k))
    return out

def sky_color_adaptive(el, clouds, m_bright):
    r, g, b, a = sky_color(el)
    cf = opaque_cover(clouds)
    r = r + (0.50 - r) * cf * 0.40
    g = g + (0.50 - g) * cf * 0.38
    b = b + (0.50 - b) * cf * 0.32
    a = min(0.72, a + cf * 0.12)
    if el < -0.83 and m_bright > 0.35:
        mf = (m_bright - 0.35) / 0.65
        r = r + (0.12 - r) * mf * 0.18
        g = g + (0.16 - g) * mf * 0.18
        b = b + (0.32 - b) * mf * 0.28
        a = min(0.72, a + mf * 0.05)
    return r, g, b, a

# ─── Opaque sky (wallpaper hidden) ───────────────────────────────────────────
# (sun elevation °, zenith rgb, horizon rgb). The horizon is paler than the zenith by day
# (haze), warm around sunrise/sunset and barely lighter than the zenith at night.
_OPAQUE_SKY = (
    (-18, (0.010, 0.012, 0.030), (0.025, 0.030, 0.055)),
    (-12, (0.015, 0.020, 0.055), (0.050, 0.060, 0.120)),
    (-6,  (0.040, 0.060, 0.160), (0.200, 0.180, 0.320)),
    (-2,  (0.100, 0.150, 0.340), (0.520, 0.400, 0.450)),
    (2,   (0.200, 0.320, 0.580), (0.860, 0.660, 0.520)),
    (8,   (0.220, 0.420, 0.740), (0.800, 0.780, 0.760)),
    (20,  (0.200, 0.440, 0.820), (0.700, 0.800, 0.920)),
    (50,  (0.170, 0.450, 0.880), (0.660, 0.800, 0.940)),
)

def opaque_sky(el, clouds, m_bright):
    """
    Colours for a sky painted fully opaque, independent of the wallpaper:
    (zenith, horizon, ground_top, ground_bottom) rgb. Cloud cover greys the sky towards an
    overcast grey as bright as the daylight; moonlight lifts the night sky a little.
    """
    pts = _OPAQUE_SKY
    if el <= pts[0][0]:
        zen, hor = pts[0][1], pts[0][2]
    elif el >= pts[-1][0]:
        zen, hor = pts[-1][1], pts[-1][2]
    else:
        for (e0, z0, h0), (e1, z1, h1) in zip(pts, pts[1:]):
            if el < e1:
                t = (el - e0) / (e1 - e0)
                zen, hor = _lerp(z0, z1, t), _lerp(h0, h1, t)
                break
    # Between scattered clouds the sky stays blue (the clouds are drawn on their own);
    # only a closing layer turns it grey
    grey_out = 0.95 * opaque_cover(clouds) ** 2
    if grey_out > 0:
        day  = _clamp((el + 6) / 16, 0.0, 1.0)
        grey = _lerp((0.05, 0.05, 0.065), (0.62, 0.65, 0.70), day)
        zen  = _lerp(zen, grey, grey_out)
        hor  = _lerp(hor, tuple(min(1.0, c * 1.12) for c in grey), grey_out)
    if el < -6 and m_bright > 0:
        moon = _clamp(m_bright, 0.0, 1.0) * _clamp((-6 - el) / 6, 0.0, 1.0)
        zen  = _lerp(zen, (0.05, 0.08, 0.17), moon * 0.45)
        hor  = _lerp(hor, (0.08, 0.10, 0.18), moon * 0.45)
    ground_top = (hor[0] * 0.30, hor[1] * 0.33, hor[2] * 0.26)
    ground_bot = tuple(c * 0.45 for c in ground_top)
    return zen, hor, ground_top, ground_bot

def moon_brightness(phase, m_el):
    illumination = (1 - math.cos(phase * 2 * math.pi)) / 2
    return illumination * _clamp((m_el + 10) / 40.0, 0, 1)

# ─── Cloud palette by sun elevation ──────────────────────────────────────────

def _cloud_palette(sun_el):
    """Return (top_rgb, dark_rgb, cirrus_rgb) tuned for no light pollution."""
    if sun_el > 20:   # midday: blinding white tops, steel-blue undersides
        return (1.00, 1.00, 1.00), (0.58, 0.64, 0.76), (0.90, 0.94, 1.00)
    if sun_el > 5:    # morning/afternoon: ivory tops, warm gray undersides
        t   = (sun_el - 5) / 15.0
        top = (1.00, 0.92 + t * 0.08, 0.78 + t * 0.22)
        drk = (0.56 + t * 0.06, 0.52 + t * 0.10, 0.44 + t * 0.24)
        cir = (0.96, 0.92 + t * 0.04, 0.80 + t * 0.20)
        return top, drk, cir
    if sun_el > -2:   # golden hour: salmon-pink, not fire — tropical look
        t   = (sun_el + 2) / 7.0
        top = (1.00, 0.62 + t * 0.30, 0.38 + t * 0.40)
        drk = (0.42 + t * 0.14, 0.22 + t * 0.30, 0.18 + t * 0.26)
        cir = (1.00, 0.72 + t * 0.20, 0.48 + t * 0.32)
        return top, drk, cir
    if sun_el > -10:  # twilight: lavender fading to violet-gray
        t   = (sun_el + 10) / 8.0
        top = (0.40 + t * 0.60, 0.30 + t * 0.32, 0.50 + t * 0.50)
        drk = (0.18 + t * 0.24, 0.14 + t * 0.08, 0.26 + t * 0.18)
        cir = (0.46 + t * 0.54, 0.38 + t * 0.34, 0.56 + t * 0.44)
        return top, drk, cir
    # Full night — silver-gray, faintly blue (starlight)
    return (0.32, 0.35, 0.50), (0.16, 0.18, 0.30), (0.36, 0.38, 0.54)
