import struct
import unittest
import zlib

from caelum.core import rain_now, radar
from caelum.core.metar import nearest, parse
from caelum.core.weather import merge_weather

OM = {'total': 95, 'low': 60, 'mid': 40, 'high': 10, 'precip': 0.0, 'snow': False, 'wmo': 3, 'ts': 't'}
MET = {'total': 90, 'precip': 1.0, 'snow': False, 'wmo': 65, 'ts': 't', 'temp': 20.0, 'humidity': 80,
       'wind_speed': 4.0, 'wind_dir': 220.0, 'symbol': 'heavyrain',
       'forecast': [], 'hourly_forecast': [], 'daily_forecast': [{'date': 'd'}]}
DRY = {'precip': 0.0, 'snow': False, 'thunder': None, 'source': 'rainviewer'}
WET = dict(DRY, precip=2.5)

METAR_DRY = 'METAR ABCD 251230Z 19010KT 160V230 9999 FEW017 32/25 Q1011 NOSIG'
# Seen in the wild: two reports run together, truncated pressure group
METAR_GARBLED = 'METAR ABCD 251300Z 19011KT 150V210 9999 FEW017 32/26 Q110 XXXXYYYY SAAO20 ZZZZ 251300 METAR '


class MergeWeatherTest(unittest.TestCase):
    def test_observed_dry_beats_forecast_rain(self):
        w = merge_weather(OM, MET, DRY)
        self.assertEqual((w['precip'], w['wmo'], w['rain_source']), (0.0, 3, 'rainviewer'))

    def test_observed_rain_shows_when_forecasts_are_dry(self):
        w = merge_weather(OM, dict(MET, precip=0.0, wmo=3), WET)
        self.assertEqual((w['precip'], w['wmo']), (2.5, 63))

    def test_thunder(self):
        # an airport reports it; radar can't, so a radar-seen shower keeps the model's storm code
        self.assertEqual(merge_weather(OM, MET, dict(WET, thunder=True, precip=8.0))['wmo'], 99)
        self.assertEqual(merge_weather(OM, dict(MET, wmo=95), WET)['wmo'], 95)
        self.assertEqual(merge_weather(OM, dict(MET, wmo=95), DRY)['wmo'], 3)

    def test_airport_is_named(self):
        w = merge_weather(OM, MET, dict(DRY, source='airport', station='ABCD', km=5.6))
        self.assertEqual((w['rain_source'], w['rain_station']), ('airport', ('ABCD', 5.6)))

    def test_without_observation_met_forecast_decides(self):
        w = merge_weather(dict(OM, precip=3.0, wmo=63), dict(MET, precip=0.0, wmo=3))
        self.assertEqual((w['precip'], w['rain_source']), (0.0, 'met_forecast'))

    def test_open_meteo_alone(self):
        w = merge_weather(dict(OM, precip=3.0, wmo=63), None)
        self.assertEqual((w['precip'], w['rain_source']), (3.0, 'om_forecast'))

    def test_met_still_gives_temperature_wind_and_forecast(self):
        w = merge_weather(OM, MET, DRY)
        self.assertEqual((w['temp'], w['wind_speed'], w['wind_dir']), (20.0, 4.0, 220.0))
        self.assertEqual(w['daily_forecast'], MET['daily_forecast'])


class SelectorTest(unittest.TestCase):
    def setUp(self):
        self.saved = rain_now.SOURCES

    def tearDown(self):
        rain_now.SOURCES = self.saved

    def test_first_covering_source_wins(self):
        calls = []
        def src(name, result):
            def f(lat, lon):
                calls.append(name)
                return result
            return f
        rain_now.SOURCES = (src('nordic', None), src('radar', WET), src('airport', DRY))
        self.assertEqual(rain_now.observe(0, 0), WET)
        self.assertEqual(calls, ['nordic', 'radar'])     # the airport isn't even asked

    def test_nothing_covers(self):
        rain_now.SOURCES = (lambda lat, lon: None,)
        self.assertIsNone(rain_now.observe(0, 0))

    def test_order_is_most_accurate_first(self):
        self.assertEqual([f.__name__ for f in self.saved], ['met_nowcast', 'rainviewer', '_airport'])

    def test_nordic_radar_isnt_asked_elsewhere(self):
        self.assertIsNone(radar.met_nowcast(6.1, 1.2))      # returns before any request


class RadarTest(unittest.TestCase):
    def test_rate_from_dbz(self):
        self.assertEqual(radar.rate_from_dbz(5), 0.0)
        self.assertAlmostEqual(radar.rate_from_dbz(23), 1.0, delta=0.15)    # Marshall–Palmer
        self.assertAlmostEqual(radar.rate_from_dbz(40), 11.5, delta=0.5)

    @staticmethod
    def png(w, h, rgba_at):
        raw = b''.join(b'\x00' + b''.join(rgba_at(x, y) for x in range(w)) for y in range(h))
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))

    def test_png_pixels_reads_straight_alpha(self):
        data = self.png(5, 5, lambda x, y: bytes((x * 10, y * 10, 7, 0x6e)))
        px = radar.png_pixels(data, 2, 3, 1)
        self.assertEqual(len(px), 9)
        self.assertEqual(px[0], bytes((10, 20, 7, 0x6e)))      # not premultiplied
        self.assertEqual(px[-1], bytes((30, 40, 7, 0x6e)))

    def test_png_pixels_clips_at_the_edge(self):
        data = self.png(4, 4, lambda x, y: b'\x00\x00\x00\x00')
        self.assertEqual(len(radar.png_pixels(data, 0, 0, 1)), 4)

    def test_palette_maps_colours_to_reflectivity(self):
        pal = radar._palette()
        self.assertGreater(len(pal), 100)
        dbz = sorted(d for d, _snow in pal.values())
        self.assertLessEqual(dbz[0], 0)
        self.assertGreaterEqual(dbz[-1], 60)
        self.assertTrue(any(snow for _d, snow in pal.values()))


class MetarParseTest(unittest.TestCase):
    def test_dry_report(self):
        self.assertEqual(parse(METAR_DRY), {'precip': 0.0, 'snow': False, 'thunder': False})

    def test_garbled_report_is_rejected(self):
        self.assertIsNone(parse(METAR_GARBLED))
        self.assertIsNone(parse('not a metar'))
        self.assertIsNone(parse(None))

    def test_rain_intensities(self):
        base = 'METAR ABCD 251300Z 19011KT 9999 {} BKN017 26/24 Q1011'
        self.assertEqual(parse(base.format('-RA'))['precip'], 0.5)
        self.assertEqual(parse(base.format('RA'))['precip'], 2.5)
        self.assertEqual(parse(base.format('+SHRA'))['precip'], 8.0)
        self.assertEqual(parse(base.format('DZ'))['precip'], 0.3)

    def test_thunder_and_snow(self):
        base = 'METAR ABCD 251300Z 19011KT 9999 {} BKN017 01/00 Q1011'
        self.assertTrue(parse(base.format('TSRA'))['thunder'])
        self.assertTrue(parse(base.format('VCTS TS'))['thunder'])
        self.assertTrue(parse(base.format('-SN'))['snow'])

    def test_vicinity_trend_recent_and_remarks_are_not_now(self):
        base = 'METAR ABCD 251300Z 19011KT 9999 {} 26/24 Q1011'
        for tail in ('VCSH', 'RERA', 'NOSIG TEMPO RA', 'RMK RAB05'):
            self.assertEqual(parse(base.format(tail))['precip'], 0.0, tail)


class MetarNearestTest(unittest.TestCase):
    NOW = 1_800_000_000.0
    LAT, LON = 45.0, 5.0

    def rep(self, dlat, age_min, raw=METAR_DRY, icao='ABCD'):
        return {'icaoId': icao, 'lat': self.LAT + dlat, 'lon': self.LON, 'obsTime': self.NOW - age_min * 60,
                'rawOb': raw}

    def test_latest_good_report_of_the_airport(self):
        reports = [self.rep(0.05, 0, METAR_GARBLED), self.rep(0.05, 30), self.rep(0.05, 60, METAR_DRY.replace('NOSIG', 'RA'))]
        obs = nearest(reports, self.LAT, self.LON, now=self.NOW)
        self.assertEqual((obs['station'], obs['precip']), ('ABCD', 0.0))   # 30-min-old report, not the garbled one
        self.assertAlmostEqual(obs['km'], 5.6, delta=0.1)

    def test_too_far_or_too_old(self):
        self.assertIsNone(nearest([self.rep(0.5, 0)], self.LAT, self.LON, now=self.NOW))
        self.assertIsNone(nearest([self.rep(0.05, 120)], self.LAT, self.LON, now=self.NOW))
        self.assertIsNone(nearest([], self.LAT, self.LON, now=self.NOW))
        self.assertIsNone(nearest(None, self.LAT, self.LON, now=self.NOW))

    def test_nearer_airport_wins(self):
        far = self.rep(0.2, 0, METAR_DRY.replace('NOSIG', 'RA'), 'FARR')
        near = self.rep(0.02, 20, icao='NEAR')
        self.assertEqual(nearest([far, near], self.LAT, self.LON, now=self.NOW)['station'], 'NEAR')


if __name__ == '__main__':
    unittest.main()
