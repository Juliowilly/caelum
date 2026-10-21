"""Phone sensors via plyer: compass heading and a one-shot GPS fix.

Everything degrades to "not available" off-device (plyer raises NotImplementedError on
desktop Linux), so the UI falls back to drag-to-look and the configured location.
"""

from kivy.logger import Logger
from kivy.utils import platform

from ..core.orientation import heading_from_sensors


class Compass:
    """Polls accelerometer + magnetometer and turns them into an azimuth."""

    def __init__(self):
        self.available = False
        try:
            from plyer import accelerometer, compass
            accelerometer.enable()
            compass.enable()
            self._accel, self._mag = accelerometer, compass
            self.available = True
        except Exception as exc:   # NotImplementedError off-device; sensor missing on some phones
            Logger.info(f'Caelum: no compass ({exc.__class__.__name__})')

    def heading(self):
        if not self.available:
            return None
        try:
            accel = self._accel.acceleration
            mag = self._mag.field
        except Exception:
            return None
        if not accel or not mag or None in accel or None in mag:
            return None
        return heading_from_sensors(accel, mag)

    def stop(self):
        if self.available:
            for sensor in (self._accel, self._mag):
                try:
                    sensor.disable()
                except Exception:
                    pass


def request_location(on_fix):
    """Ask for one GPS fix on Android and call on_fix(lat, lon) once. No-op elsewhere."""
    if platform != 'android':
        return
    try:
        from android.permissions import Permission, request_permissions
        from plyer import gps
    except ImportError:
        return

    def _on_location(**kw):
        try:
            gps.stop()
        except Exception:
            pass
        if 'lat' in kw and 'lon' in kw:
            on_fix(float(kw['lat']), float(kw['lon']))

    def _start(_permissions, grants):
        if not any(grants):
            Logger.info('Caelum: location permission denied, keeping configured location')
            return
        try:
            gps.configure(on_location=_on_location)
            gps.start(minTime=1000, minDistance=0)
        except Exception as exc:
            Logger.warning(f'Caelum: GPS unavailable: {exc}')

    request_permissions([Permission.ACCESS_COARSE_LOCATION, Permission.ACCESS_FINE_LOCATION],
                        _start)
