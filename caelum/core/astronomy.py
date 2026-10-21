"""Sun, moon, planet and star positions (Meeus / Schlyter)."""

import datetime
import math

from .catalog import _STARS

def _bv_to_rgb(bv):
    """Convert B-V color index to approximate RGB for star rendering."""
    if bv < -0.20: return (0.55, 0.65, 1.00)   # hot blue O/B
    if bv < -0.05: return (0.70, 0.82, 1.00)   # blue-white B/A
    if bv <  0.25: return (0.95, 0.96, 1.00)   # white A/F
    if bv <  0.58: return (1.00, 0.95, 0.75)   # yellow-white F/G
    if bv <  1.00: return (1.00, 0.80, 0.48)   # yellow-orange K
    if bv <  1.50: return (1.00, 0.58, 0.28)   # orange K/M
    return                (1.00, 0.38, 0.16)   # deep orange-red M

def _ra_dec_to_alt_az(ra_h, dec_deg, lat_deg, lon_deg, dt_utc):
    """Convert equatorial coordinates to local alt/az (J2000 approx)."""
    jd    = _julian_day(dt_utc)
    GMST  = (280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360
    LST   = (GMST + lon_deg) % 360
    HA    = math.radians((LST - ra_h * 15.0) % 360)
    dec   = math.radians(dec_deg)
    lat   = math.radians(lat_deg)
    sin_a = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(HA)
    alt   = math.degrees(math.asin(max(-1.0, min(1.0, sin_a))))
    cos_A = ((math.sin(dec) - math.sin(math.radians(alt)) * math.sin(lat))
             / (math.cos(math.radians(alt)) * math.cos(lat) + 1e-10))
    az    = math.degrees(math.acos(max(-1.0, min(1.0, cos_A))))
    if math.sin(HA) > 0:
        az = 360.0 - az
    return alt, az

_star_cache = {'key': None, 'data': []}

def _get_star_positions(lat, lon, dt_utc):
    """Compute and cache star alt/az positions (refreshed every minute)."""
    key = (round(lat, 3), round(lon, 3),
           dt_utc.year, dt_utc.month, dt_utc.day,
           dt_utc.hour, dt_utc.minute)
    if _star_cache['key'] == key:
        return _star_cache['data']
    data = []
    seen = set()
    for ra_h, dec_deg, mag, bv in _STARS:
        uid = (round(ra_h, 3), round(dec_deg, 3))
        if uid in seen:
            continue
        seen.add(uid)
        alt, az = _ra_dec_to_alt_az(ra_h, dec_deg, lat, lon, dt_utc)
        if alt > -1.0:   # include slightly below horizon (refraction)
            data.append((alt, az, mag, bv, ra_h, dec_deg))
    _star_cache['key']  = key
    _star_cache['data'] = data
    return data

# ─── Astronomy ───────────────────────────────────────────────────────────────

def _julian_day(dt):
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jdn = (dt.day + (153 * m + 2) // 5 + 365 * y
           + y // 4 - y // 100 + y // 400 - 32045)
    return jdn + (dt.hour - 12) / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0

def solar_position(lat_deg, lon_deg, dt_utc):
    """Return (elevation°, azimuth°) for the sun."""
    lat = math.radians(lat_deg)
    n   = _julian_day(dt_utc) - 2451545.0
    L   = math.radians((280.46 + 0.9856474 * n) % 360)
    g   = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 4e-7 * n)
    dec = math.asin(math.sin(eps) * math.sin(lam))
    ra_h = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) / 15.0
    if ra_h < 0:
        ra_h += 24
    gmst = (18.697375 + 24.065709824279 * n) % 24
    ha   = math.radians(((gmst + lon_deg / 15.0) % 24 - ra_h) * 15)
    sin_el = (math.sin(lat) * math.sin(dec)
              + math.cos(lat) * math.cos(dec) * math.cos(ha))
    el = math.degrees(math.asin(max(-1.0, min(1.0, sin_el))))
    cos_az = ((math.sin(dec) - math.sin(math.radians(el)) * math.sin(lat))
              / (math.cos(math.radians(el)) * math.cos(lat) + 1e-10))
    az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
    if math.sin(ha) > 0:
        az = 360.0 - az
    return el, az

def moon_position(lat_deg, lon_deg, dt_utc):
    """Return (elevation°, azimuth°) for the moon — Meeus Ch.47, ~0.3° accuracy."""
    lat = math.radians(lat_deg)
    jd  = _julian_day(dt_utc)
    T   = (jd - 2451545.0) / 36525.0

    D  = math.radians((297.8501921 + 445267.1114034 * T) % 360)
    M  = math.radians((357.5291092 +  35999.0502909 * T) % 360)
    Mp = math.radians((134.9633964 + 477198.8675055 * T) % 360)
    F  = math.radians(( 93.2720950 + 483202.0175233 * T) % 360)
    L0 = math.radians((218.3164477 + 481267.88123421 * T) % 360)

    dL = (6.288774 * math.sin(Mp)
        + 1.274027 * math.sin(2*D - Mp)
        + 0.658314 * math.sin(2*D)
        + 0.213618 * math.sin(2*Mp)
        - 0.185116 * math.sin(M)
        - 0.114332 * math.sin(2*F)
        + 0.058793 * math.sin(2*(D - Mp))
        + 0.057066 * math.sin(2*D - M - Mp)
        + 0.053322 * math.sin(2*D + Mp)
        + 0.045758 * math.sin(2*D - M))

    dB = (5.128122 * math.sin(F)
        + 0.280602 * math.sin(Mp + F)
        + 0.277693 * math.sin(Mp - F)
        + 0.173237 * math.sin(2*D - F)
        + 0.055413 * math.sin(2*D + F - Mp)
        + 0.046271 * math.sin(2*D - F - Mp)
        + 0.032573 * math.sin(2*D + F))

    lam  = L0 + math.radians(dL)
    beta = math.radians(dB)

    eps     = math.radians(23.4393 - 0.013004 * T)
    sin_dec = (math.sin(beta) * math.cos(eps)
               + math.cos(beta) * math.sin(eps) * math.sin(lam))
    dec = math.asin(max(-1.0, min(1.0, sin_dec)))
    ra  = math.atan2(
            math.sin(lam) * math.cos(beta) * math.cos(eps) - math.sin(beta) * math.sin(eps),
            math.cos(lam) * math.cos(beta))

    GMST = math.radians((280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360)
    ha   = GMST + math.radians(lon_deg) - ra

    sin_el = (math.sin(lat) * math.sin(dec)
              + math.cos(lat) * math.cos(dec) * math.cos(ha))
    el = math.degrees(math.asin(max(-1.0, min(1.0, sin_el))))
    cos_az = ((math.sin(dec) - math.sin(math.radians(el)) * math.sin(lat))
              / (math.cos(math.radians(el)) * math.cos(lat) + 1e-10))
    az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
    if math.sin(ha) > 0:
        az = 360.0 - az
    return el, az

def _find_event(lat, lon, date, tz_off, event):
    THRESHOLD = -0.833
    prev_el = None
    for m in range(1440):
        h, mi = divmod(m, 60)
        utc = (datetime.datetime(date.year, date.month, date.day, h, mi)
               - datetime.timedelta(hours=tz_off))
        el, _ = solar_position(lat, lon, utc)
        if prev_el is not None:
            if event == 'rise' and prev_el < THRESHOLD <= el:
                frac = (THRESHOLD - prev_el) / (el - prev_el)
                tot  = m - 1 + frac
                return datetime.time(int(tot // 60) % 24, int(tot % 60))
            if event == 'set' and prev_el > THRESHOLD >= el:
                frac = (prev_el - THRESHOLD) / (prev_el - el)
                tot  = m - 1 + frac
                return datetime.time(int(tot // 60) % 24, int(tot % 60))
        prev_el = el
    return None

def _find_moon_event(lat, lon, date, tz_off, event):
    """Scan the day at 1-min resolution to find moonrise or moonset."""
    prev_el = None
    for m in range(1440):
        h, mi = divmod(m, 60)
        utc = (datetime.datetime(date.year, date.month, date.day, h, mi)
               - datetime.timedelta(hours=tz_off))
        el, _ = moon_position(lat, lon, utc)
        if prev_el is not None:
            if event == 'rise' and prev_el < 0 <= el:
                frac = -prev_el / (el - prev_el + 1e-9)
                tot  = m - 1 + frac
                return datetime.time(int(tot // 60) % 24, int(tot % 60))
            if event == 'set' and prev_el > 0 >= el:
                frac = prev_el / (prev_el - el + 1e-9)
                tot  = m - 1 + frac
                return datetime.time(int(tot // 60) % 24, int(tot % 60))
        prev_el = el
    return None

def _solar_noon(lat, lon, date, tz_off):
    best_el, best_m = -90, 720
    for m in range(360, 960):
        h, mi = divmod(m, 60)
        utc = (datetime.datetime(date.year, date.month, date.day, h, mi)
               - datetime.timedelta(hours=tz_off))
        el, _ = solar_position(lat, lon, utc)
        if el > best_el:
            best_el, best_m = el, m
    return datetime.time(best_m // 60, best_m % 60), best_el

def moon_phase_age(dt_utc):
    known_new = datetime.datetime(2000, 1, 6, 18, 14)
    synodic   = 29.530588853
    delta     = (dt_utc - known_new).total_seconds() / 86400.0
    age       = delta % synodic
    return age / synodic, age

# ─── Planets ─────────────────────────────────────────────────────────────────

def _kepler_E(M_deg, e, tol=1e-6):
    M = math.radians(M_deg % 360)
    E = M
    for _ in range(100):
        dE = (M - E + e * math.sin(E)) / (1 - e * math.cos(E))
        E += dE
        if abs(dE) < tol:
            break
    return E

# Schlyter simplified orbital elements at J2000
# (a_AU, e, I_deg, N_deg, w_deg, M0_deg, M_rate_deg_per_day)
_PLANET_ELEMS = {
    'Mercury': (0.387098, 0.205635,  7.0050,  48.3313,  29.1241, 174.7948, 4.0923344368),
    'Venus':   (0.723330, 0.006773,  3.3946,  76.6799,  54.8910,  50.4161, 1.6021302244),
    'Mars':    (1.523688, 0.093405,  1.8497,  49.5574, 286.5016,  19.3730, 0.5240207766),
    'Jupiter': (5.202534, 0.048498,  1.3030, 100.4542, 273.8777,  19.8950, 0.0830853001),
    'Saturn':  (9.554909, 0.055509,  2.4847, 113.6634, 339.3939, 316.9670, 0.0334442282),
}

_PLANET_COLORS = {
    'Mercury': (0.85, 0.80, 0.75),
    'Venus':   (1.00, 0.95, 0.80),
    'Mars':    (1.00, 0.60, 0.35),
    'Jupiter': (1.00, 0.90, 0.70),
    'Saturn':  (0.95, 0.88, 0.65),
}

# Approximate average visual magnitudes — drives glow/disc radius scaling
_PLANET_MAG = {
    'Mercury':  0.0,
    'Venus':   -4.0,
    'Mars':    -1.0,
    'Jupiter': -2.2,
    'Saturn':   0.7,
}

_planet_cache = {'key': None, 'data': []}

def planet_positions(lat, lon, dt_utc):
    key = (round(lat, 3), round(lon, 3),
           dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour)
    if _planet_cache['key'] == key:
        return _planet_cache['data']

    jd    = _julian_day(dt_utc)
    d     = jd - 2451545.0
    GMST  = math.radians((280.46061837 + 360.98564736629 * d) % 360)
    lat_r = math.radians(lat)
    eps   = math.radians(23.4393 - 0.013004 * (d / 36525.0))

    # Sun's ecliptic position for geocentric conversion
    L_s   = math.radians((280.46 + 0.9856474 * d) % 360)
    g_s   = math.radians((357.528 + 0.9856003 * d) % 360)
    lam_s = (L_s + math.radians(1.915) * math.sin(g_s)
             + math.radians(0.020) * math.sin(2 * g_s))
    R_s   = 1.00014 - 0.01671 * math.cos(g_s) - 0.000140 * math.cos(2 * g_s)
    xs    = R_s * math.cos(lam_s)
    ys    = R_s * math.sin(lam_s)

    planets = []
    for name, (a, e, I, N, w, M0, M_rate) in _PLANET_ELEMS.items():
        M_deg = (M0 + M_rate * d) % 360
        E     = _kepler_E(M_deg, e)
        xv    = a * (math.cos(E) - e)
        yv    = a * math.sqrt(1.0 - e * e) * math.sin(E)
        v     = math.degrees(math.atan2(yv, xv))
        r     = math.sqrt(xv * xv + yv * yv)
        N_r   = math.radians(N)
        I_r   = math.radians(I)
        vw    = math.radians(v + w)
        # Heliocentric ecliptic
        xh = r * (math.cos(N_r) * math.cos(vw) - math.sin(N_r) * math.sin(vw) * math.cos(I_r))
        yh = r * (math.sin(N_r) * math.cos(vw) + math.cos(N_r) * math.sin(vw) * math.cos(I_r))
        zh = r * math.sin(vw) * math.sin(I_r)
        # Geocentric equatorial
        xg, yg, zg = xh + xs, yh + ys, zh
        xe = xg
        ye = yg * math.cos(eps) - zg * math.sin(eps)
        ze = yg * math.sin(eps) + zg * math.cos(eps)
        dist = math.sqrt(xe * xe + ye * ye + ze * ze) + 1e-30
        ra   = math.atan2(ye, xe)
        dec  = math.asin(max(-1.0, min(1.0, ze / dist)))
        ha   = GMST + math.radians(lon) - ra
        sin_el = (math.sin(lat_r) * math.sin(dec)
                  + math.cos(lat_r) * math.cos(dec) * math.cos(ha))
        el = math.degrees(math.asin(max(-1.0, min(1.0, sin_el))))
        cos_az = ((math.sin(dec) - math.sin(math.radians(el)) * math.sin(lat_r))
                  / (math.cos(math.radians(el)) * math.cos(lat_r) + 1e-10))
        az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
        if math.sin(ha) > 0:
            az = 360.0 - az
        planets.append((name, el, az, _PLANET_COLORS[name]))

    _planet_cache['key']  = key
    _planet_cache['data'] = planets
    return planets
