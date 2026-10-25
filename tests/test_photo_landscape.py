import os
import struct
import tempfile
import unittest
from unittest import mock

import cairo

from caelum.gtk_ui import landscape, photo_landscape as P


def scene(path, w=900, h=600, sky=True):
    """A test 'photo': blue sky over green ground with a hill, saved as PNG or JPEG."""
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    cr = cairo.Context(surf)
    cr.set_source_rgb(0.25, 0.5, 0.9) if sky else cr.set_source_rgb(0.2, 0.5, 0.2)
    cr.paint()
    cr.set_source_rgb(0.2, 0.45, 0.15)
    cr.rectangle(0, h * 0.6, w, h)
    cr.fill()
    cr.arc(w * 0.3, h * 0.6, h * 0.2, 3.1416, 0)        # a hill up to 0.4 h
    cr.fill()
    if path.endswith('.png'):
        surf.write_to_png(path)
    else:
        from gi.repository import Gdk
        Gdk.pixbuf_get_from_surface(surf, 0, 0, w, h).savev(path, 'jpeg', ['quality'], ['90'])


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def write(path, data):
    with open(path, 'wb') as f:
        f.write(data)


def with_exif(path):
    """Add an EXIF block (an empty TIFF directory) right after the JPEG's start marker."""
    data = read(path)
    tiff = b'II*\x00\x08\x00\x00\x00' + b'\x00\x00' + b'\x00\x00\x00\x00'
    app1 = b'\xff\xe1' + struct.pack('>H', 2 + 6 + len(tiff)) + b'Exif\x00\x00' + tiff
    write(path, data[:2] + app1 + data[2:])


class PhotoLandscapeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(landscape.sandbox, 'data_dir', return_value=self.tmp.name)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def photo(self, name='p.png', **kw):
        path = os.path.join(self.tmp.name, name)
        scene(path, **kw)
        return path

    def test_build_install_remove(self):
        folder, meta = P.build(self.photo())
        self.assertTrue(3 <= meta['top'] <= P._TALLEST + 2, meta)
        self.assertEqual((meta['bottom'], meta['south']), (P.BOTTOM, 0.25))
        mask = cairo.ImageSurface.create_from_png(os.path.join(folder, 'photo-mask.png'))
        self.assertEqual((mask.get_width(), mask.get_height()), (2 * P.HALF_W, round((meta['top'] + P.BOTTOM) * 10)))
        data, stride = mask.get_data(), mask.get_stride()
        alpha = lambda x, y: data[y * stride + 4 * x + 3]
        self.assertEqual(alpha(100, 0), 0)                                # sky at the top
        self.assertEqual(alpha(100, mask.get_height() - 1), 255)           # ground at the bottom
        self.assertEqual(alpha(10, 300), alpha(2 * P.HALF_W - 11, 300))    # mirrored
        self.assertTrue(P.preview(folder, meta).get_width() > 0)
        P.install(folder, meta)
        self.assertFalse(os.path.exists(folder))
        self.assertTrue(P.installed())
        self.assertIn('photo', landscape.available())
        P.remove()
        self.assertFalse(P.installed())
        self.assertEqual(os.listdir(landscape.personal_dir()), ['landscapes.json'])

    def test_metadata_is_dropped(self):
        path = self.photo('p.jpg')
        with_exif(path)
        self.assertIn(b'Exif', read(path))
        folder, _meta = P.build(path)
        self.assertNotIn(b'Exif', read(os.path.join(folder, 'photo.jpg')))
        P.discard(folder)

    def test_refusals(self):
        with self.assertRaisesRegex(P.PhotoError, 'No sky'):
            P.build(self.photo(sky=False))
        with self.assertRaisesRegex(P.PhotoError, 'too small'):
            P.build(self.photo(w=200, h=150))
        text = os.path.join(self.tmp.name, 'notes.png')
        write(text, b'not an image')
        with self.assertRaises(P.PhotoError):
            P.build(text)
        with self.assertRaisesRegex(P.PhotoError, 'too large'), \
                mock.patch.object(P, 'MAX_BYTES', 10):
            P.build(self.photo())
        # Refused before anything is written
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, 'caelum')))


if __name__ == '__main__':
    unittest.main()
