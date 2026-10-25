# PyInstaller spec for the Windows build. Run by build.sh inside MSYS2 UCRT64.
# One folder, not one file: a single self-extracting exe starts slower and antivirus tools flag
# that kind of exe more often.

import os
import sys

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, '..', '..'))
APP_ID = 'io.github.juliowilly.Caelum'
ICON = os.path.join(ROOT, 'data', f'{APP_ID}-512.png')   # PyInstaller turns it into .ico (Pillow)

a = Analysis(
    [os.path.join(SPECPATH, 'caelum_launcher.py')],
    pathex=[ROOT],
    datas=collect_data_files('caelum', excludes=['kivy_ui/**']) + [
        (ICON, 'data'),   # window and tray icon (caelum/gtk_ui/app.py looks in <bundle>/data)
        (os.path.join(sys.prefix, 'etc', 'ssl', 'certs', 'ca-bundle.crt'), 'certs'),
    ],
    hiddenimports=['serial'],                  # USB serial compass
    excludes=['caelum.kivy_ui', 'kivy', 'dbus', 'tkinter'],
    hooksconfig={
        'gi': {
            'module-versions': {'Gtk': '3.0', 'Gdk': '3.0'},
            'icons': ['Adwaita', 'hicolor'],
            'themes': ['Adwaita'],
            'languages': ['en_GB', 'fr', 'es', 'de', 'pt', 'pt_BR', 'it'],
        },
    },
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='caelum',
    icon=ICON,
    console=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name='caelum')
