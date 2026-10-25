import unittest

from caelum.core.geoip import parse_ipapi, parse_ipwhois
from caelum.core.net import coord, get_json


class CoordTest(unittest.TestCase):
    def test_two_decimals(self):
        self.assertEqual(coord(48.858372), '48.86')
        self.assertEqual(coord(-33.86881), '-33.87')

    def test_no_negative_zero(self):
        self.assertEqual(coord(-0.001), '0.00')


class GetJsonTest(unittest.TestCase):
    def test_refuses_plain_http(self):
        with self.assertRaises(ValueError):
            get_json('http://example.com/')


class GeoIpTest(unittest.TestCase):
    WHOIS = {'success': True, 'latitude': 35.6895, 'longitude': 139.6917,
             'timezone': {'id': 'Asia/Tokyo', 'offset': 32400}}
    IPAPI = {'latitude': 48.8566, 'longitude': 2.3522, 'timezone': 'Europe/Paris', 'utc_offset': '+0100'}

    def test_ipwhois(self):
        self.assertEqual(parse_ipwhois(self.WHOIS),
                         {'lat': 35.6895, 'lon': 139.6917, 'timezone': 'Asia/Tokyo', 'offset': 32400})

    def test_ipapi_offset_string(self):
        self.assertEqual(parse_ipapi(self.IPAPI)['offset'], 3600)
        self.assertEqual(parse_ipapi(dict(self.IPAPI, utc_offset='-0930'))['offset'], -34200)

    def test_failures_and_garbage_are_rejected(self):
        self.assertIsNone(parse_ipwhois(dict(self.WHOIS, success=False)))
        self.assertIsNone(parse_ipwhois(dict(self.WHOIS, latitude='6.1')))
        self.assertIsNone(parse_ipwhois(dict(self.WHOIS, latitude=True)))
        self.assertIsNone(parse_ipwhois(dict(self.WHOIS, longitude=500)))
        self.assertIsNone(parse_ipwhois(dict(self.WHOIS, timezone={'id': 'X', 'offset': 99999})))
        self.assertIsNone(parse_ipwhois(['not', 'a', 'dict']))
        self.assertIsNone(parse_ipapi(dict(self.IPAPI, error=True)))
        self.assertIsNone(parse_ipapi(dict(self.IPAPI, utc_offset='1 hour')))

    def test_timezone_name_is_capped(self):
        loc = parse_ipwhois(dict(self.WHOIS, timezone={'id': 'A' * 500, 'offset': 0}))
        self.assertEqual(len(loc['timezone']), 64)


if __name__ == '__main__':
    unittest.main()
