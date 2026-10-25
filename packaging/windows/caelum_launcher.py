"""Entry point of the Windows build (PyInstaller): the bundle's certificates and a log file, then
the GTK app.

`caelum.exe --selftest <file>` checks the bundle (GTK, Cairo, HTTPS) without opening the sky and
writes the result to <file>; the CI runs it on every build.
"""

import os
import sys


def _bundle_setup():
    if not getattr(sys, 'frozen', False):
        return
    # MSYS2's OpenSSL looks for certificates where MSYS2 is installed, not in the bundle
    certs = os.path.join(sys._MEIPASS, 'certs', 'ca-bundle.crt')
    if os.path.exists(certs):
        os.environ.setdefault('SSL_CERT_FILE', certs)
    # A windowed exe has no console: keep errors in a log, overwritten at each start
    if sys.stderr is None:
        log_dir = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'caelum')
        try:
            os.makedirs(log_dir, exist_ok=True)
            sys.stdout = sys.stderr = open(os.path.join(log_dir, 'caelum.log'), 'w',
                                           encoding='utf-8', buffering=1)
        except OSError:
            pass


def _selftest(out_path):
    lines, ok = [], True

    def check(name, fn):
        nonlocal ok
        try:
            lines.append(f'ok    {name}: {fn()}')
        except Exception as e:
            ok = False
            lines.append(f'FAIL  {name}: {type(e).__name__}: {e}')

    def gtk():
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        return f'GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}'

    def cairo_png():
        import cairo
        import io
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
        buf = io.BytesIO()
        surf.write_to_png(buf)
        return f'cairo {cairo.cairo_version_string()}, PNG {len(buf.getvalue())} bytes'

    def https():
        from caelum.core.net import get_json
        # A neutral place (Paris): the self-test never sends the user's location
        reply = get_json('https://api.open-meteo.com/v1/forecast?latitude=48.86&longitude=2.35'
                         '&current=temperature_2m')
        return f"Open-Meteo replied ({len(reply.get('current', {}))} current fields)"

    def caelum():
        from caelum import __version__
        from caelum.gtk_ui import window   # noqa: F401  (imports every module the sky needs)
        from caelum.gtk_ui.landscape import available
        return f'Caelum {__version__}, landscapes {sorted(available())}'

    for name, fn in (('gtk', gtk), ('cairo', cairo_png), ('https', https), ('caelum', caelum)):
        check(name, fn)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return 0 if ok else 1


if __name__ == '__main__':
    _bundle_setup()
    if len(sys.argv) == 3 and sys.argv[1] == '--selftest':
        sys.exit(_selftest(sys.argv[2]))
    from caelum.gtk_ui.app import main
    main()
