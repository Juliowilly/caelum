"""Panorama projection, sky/cloud colour palettes and small math helpers."""

import math

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

def sky_color_adaptive(el, clouds, m_bright):
    r, g, b, a = sky_color(el)
    cf = clouds['total'] / 100.0
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
