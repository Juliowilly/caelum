"""Compass heading from raw phone sensors (accelerometer + magnetometer), platform-agnostic."""

import math


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return None if n < 1e-9 else (v[0] / n, v[1] / n, v[2] / n)


def heading_from_sensors(accel, mag):
    """Azimuth (0=N, 90=E) the phone is pointing at, or None if the readings are unusable.

    Both vectors are in Android device axes (x right, y up the screen, z out of the screen);
    `accel` is the accelerometer reading at rest, i.e. pointing *up*. Same construction as
    Android's SensorManager.getRotationMatrix(): east = mag x up, north = up x east.

    Held upright, the heading is where the back camera looks (-z), so the sky on screen
    matches the sky behind the phone. Lying flat, it falls back to the top edge (+y).
    """
    up = _norm(accel)
    east = _norm(_cross(mag, up)) if up else None
    if not east:
        return None
    north = _cross(up, east)
    # Upright when gravity lies mostly in the screen plane
    if abs(up[2]) < 0.8:
        e, n = -east[2], -north[2]
    else:
        e, n = east[1], north[1]
    if abs(e) < 1e-9 and abs(n) < 1e-9:
        return None
    return math.degrees(math.atan2(e, n)) % 360.0
