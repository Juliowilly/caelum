# Android build for the Kivy front-end (caelum/kivy_ui). Build with: buildozer android debug
[app]
title = Caelum
package.name = caelum
package.domain = io.github.juliowilly

source.dir = .
source.include_exts = py
# Only main.py and the platform-agnostic core + Kivy UI go into the APK
source.exclude_dirs = tests, data, packaging, build, dist, bin, .git, .buildozer, .venv-kivy, caelum/gtk_ui
source.exclude_patterns = desktop_tracker.py, compass_bridge.py, compass_server.py

version.regex = __version__ = ['"](.*)['"]
version.filename = %(source.dir)s/caelum/__init__.py

requirements = python3,kivy==2.3.1,plyer

# The 240° panorama is designed for wide screens
orientation = landscape, landscape-reverse
fullscreen = 1

icon.filename = %(source.dir)s/data/io.github.juliowilly.Caelum-512.png

# Location for the one-shot GPS fix; compass sensors need no permission
android.permissions = ACCESS_COARSE_LOCATION, ACCESS_FINE_LOCATION
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
