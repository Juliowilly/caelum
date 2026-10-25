import struct
import unittest
import zlib

from caelum.core import metar, observed, radar
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


def rain(r):
    return {'rain': r}


SKY_FEW = {'layers': [(19, 1700)], 'sensed_top': 99999, 'source': 'airport'}
AIR = {'temp': 32.0, 'humidity': 67, 'wind_speed': 5.1, 'wind_dir': 190.0, 'source': 'airport'}


class MergeWeatherTest(unittest.TestCase):
    def test_observed_dry_beats_forecast_rain(self):
        w = merge_weather(OM, MET, rain(DRY))
        self.assertEqual((w['precip'], w['wmo'], w['sources']['rain']), (0.0, 3, 'rainviewer'))

    def test_observed_rain_shows_when_forecasts_are_dry(self):
        w = merge_weather(OM, dict(MET, precip=0.0, wmo=3), rain(WET))
        self.assertEqual((w['precip'], w['wmo'], w['symbol']), (2.5, 63, 'rain'))

    def test_thunder(self):
        # an airport reports it; radar can't, so a radar-seen shower keeps the model's storm code
        self.assertEqual(merge_weather(OM, MET, rain(dict(WET, thunder=True, precip=8.0)))['wmo'], 99)
        self.assertEqual(merge_weather(OM, dict(MET, wmo=95), rain(WET))['wmo'], 95)
        self.assertEqual(merge_weather(OM, dict(MET, wmo=95), rain(DRY))['wmo'], 3)

    def test_without_observation_forecasts_decide(self):
        w = merge_weather(dict(OM, precip=3.0, wmo=63), dict(MET, precip=0.0, wmo=3))
        self.assertEqual(w['precip'], 0.0)
        self.assertEqual(w['sources'], {'rain': 'met_forecast', 'sky': 'models', 'air': 'met_forecast'})
        self.assertIsNone(w['station'])

    def test_open_meteo_alone(self):
        w = merge_weather(dict(OM, precip=3.0, wmo=63), None)
        self.assertEqual((w['precip'], w['sources']['rain'], w['sources']['air']), (3.0, 'om_forecast', None))

    def test_observed_sky_replaces_the_models_clouds(self):
        # A manned airport reporting a few low clouds: the models' 95 % cover goes
        w = merge_weather(OM, MET, {'rain': DRY, 'sky': SKY_FEW, 'station': ('ABCD', 5.6)})
        self.assertEqual((w['low'], w['mid'], w['high'], w['total']), (19, 0, 0, 19))
        self.assertEqual((w['wmo'], w['symbol'], w['sources']['sky']), (1, 'fair', 'airport'))
        self.assertEqual(w['station'], ('ABCD', 5.6))

    def test_automatic_station_keeps_the_models_high_cloud(self):
        sky = {'layers': [], 'sensed_top': 12000, 'source': 'airport'}
        w = merge_weather(OM, MET, {'sky': sky})
        self.assertEqual((w['low'], w['high']), (0, OM['high']))

    def test_met_alone_cloud_total_counts_as_mid(self):
        w = merge_weather(None, MET, {'sky': dict(SKY_FEW, layers=[], sensed_top=5000)})
        self.assertEqual((w['low'], w['mid']), (0, MET['total']))

    def test_observed_air(self):
        w = merge_weather(OM, MET, {'air': AIR, 'station': ('ABCD', 5.6)})
        self.assertEqual((w['temp'], w['humidity'], w['wind_speed'], w['wind_dir']), (32.0, 67, 5.1, 190.0))
        self.assertEqual(w['sources']['air'], 'airport')
        w = merge_weather(OM, MET, {'air': dict(AIR, wind_dir=None)})
        self.assertEqual(w['wind_dir'], MET['wind_dir'])      # variable wind: keep the model's

    def test_met_still_gives_the_forecast(self):
        w = merge_weather(OM, MET, {'rain': DRY, 'sky': SKY_FEW, 'air': AIR})
        self.assertEqual(w['daily_forecast'], MET['daily_forecast'])


class ObservedTest(unittest.TestCase):
    FIELD = {'precip': 0.0, 'snow': False, 'thunder': True, 'temp': 30.0, 'humidity': 70, 'wind_speed': 4.0,
             'wind_dir': 200.0, 'layers': [(44, 2000)], 'auto': False, 'sensed_top': 99999,
             'station': 'ABCD', 'km': 8.0, 'time': 0.0}
    NORDIC = {'precip': 1.2, 'snow': False, 'thunder': None, 'source': 'met_radar',
              'air': {'temp': 7.0, 'humidity': 85, 'wind_speed': 6.0, 'wind_dir': 150.0}}

    def setUp(self):
        self.saved = observed.nowcast, observed.rainviewer, observed.airport

    def tearDown(self):
        observed.nowcast, observed.rainviewer, observed.airport = self.saved

    def use(self, nowcast=None, rv=None, field=None):
        calls = []
        def stub(name, result):
            def f(lat, lon):
                calls.append(name)
                return result
            return f
        observed.nowcast, observed.rainviewer, observed.airport = (
            stub('nowcast', nowcast), stub('rainviewer', rv), stub('airport', field))
        return calls

    def test_nordic_radar_gives_rain_and_air(self):
        calls = self.use(nowcast=self.NORDIC, rv=WET, field=self.FIELD)
        o = observed.observe(60, 10)
        self.assertEqual((o['rain']['source'], o['rain']['precip']), ('met_radar', 1.2))
        self.assertEqual(o['air']['source'], 'met_radar')
        self.assertEqual(o['sky']['source'], 'airport')               # clouds still from the airport
        self.assertTrue(o['rain']['thunder'])                         # lightning from the airport
        self.assertNotIn('rainviewer', calls)

    def test_radar_elsewhere_airport_for_sky_and_air(self):
        self.use(rv=WET, field=self.FIELD)
        o = observed.observe(48, 2)
        self.assertEqual((o['rain']['source'], o['sky']['source'], o['air']['source']),
                         ('rainviewer', 'airport', 'airport'))
        self.assertEqual(o['station'], ('ABCD', 8.0))

    def test_airport_only(self):
        self.use(field=self.FIELD)
        self.assertEqual(observed.observe(6, 1)['rain']['source'], 'airport')

    def test_nothing_observed(self):
        self.use()
        self.assertEqual(observed.observe(0, 0), {'rain': None, 'sky': None, 'air': None, 'station': None})

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
        o = parse(METAR_DRY)
        self.assertEqual((o['precip'], o['thunder'], o['temp'], o['humidity']), (0.0, False, 32.0, 67))
        self.assertEqual((o['wind_dir'], o['wind_speed']), (190.0, 5.1))
        self.assertEqual((o['layers'], o['auto'], o['sensed_top']), ([(19, 1700)], False, 99999))

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

    def test_wind_units_variable_and_calm(self):
        base = 'METAR ABCD 251300Z {} 9999 FEW020 10/05 Q1011'
        self.assertEqual(parse(base.format('27010MPS'))['wind_speed'], 10.0)
        self.assertEqual(parse(base.format('27036KMH'))['wind_speed'], 10.0)
        self.assertEqual(parse(base.format('27020G35KT'))['wind_speed'], 10.3)
        self.assertIsNone(parse(base.format('VRB03KT'))['wind_dir'])
        self.assertIsNone(parse(base.format('00000KT'))['wind_dir'])

    def test_freezing_temperatures(self):
        o = parse('METAR ABCD 251300Z 01005KT 9999 FEW020 M02/M05 Q1030')
        self.assertEqual(o['temp'], -2.0)
        self.assertAlmostEqual(o['humidity'], 80, delta=1)

    def test_sky_rules(self):
        model = (60, 40, 10)
        sky = lambda raw: metar.sky(parse('METAR ABCD 251300Z 01005KT 9999 ' + raw + ' 10/05 Q1011'), model)
        self.assertEqual(sky('FEW017'), (19, 0, 0))                # an observer reports every layer
        self.assertEqual(sky('FEW008 SCT030CB OVC090'), (44, 100, 0))
        self.assertEqual(sky('SKC'), (0, 0, 0))
        self.assertEqual(sky('CAVOK'), (0, 40, 10))                # nothing below 5,000 ft; above unknown
        self.assertEqual(sky('AUTO NCD'), (0, 40, 10))             # a ceilometer sees ~12,000 ft
        self.assertEqual(sky('AUTO BKN100'), (0, 75, 10))
        self.assertEqual(sky('VV002'), (100, 0, 0))                # fog hides the sky


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
