<p align="center">
  <img src="data/io.github.juliowilly.Caelum.svg" width="128" alt="Caelum icon">
</p>

<h1 align="center">Caelum</h1>

A native desktop widget that turns your screen background into a live, photorealistic sky — showing the real position of the sun, moon, planets, and stars for your location, with real-time weather and astronomical data.

![Platform](https://img.shields.io/badge/platform-Linux-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Panoramic sky view** — 240° horizon panorama, centred on your screen's real-world facing direction
- **Sun & Moon** — accurate positions via Meeus algorithms; moon shows correct crescent orientation for your latitude
- **Planets** — Mercury, Venus, Mars, Jupiter, Saturn rendered with colour and Saturn's rings
- **Stars** — 500-star catalog with twinkling, Milky Way band, shooting meteors, airglow
- **Constellation lines** — 23 constellations with hover-to-name
- **Photo landscapes** — a real panorama along the horizon (plain with trees, mountains or seaside), turning with your facing direction and relit by the sun and moon; or drawn hills, or nothing
- **Real-time weather** — cloud layers, rain, snow, rainbow from Open-Meteo + MET Norway (no API key needed)
- **Weekly forecast** — accordion-style column; click a day to expand hourly slots
- **Cairo-drawn weather icons** — no external image files
- **Astronomical info cards** — clock, location, sunrise/sunset, solar noon, moon phase, moonrise/moonset, daylight remaining
- **Compass rose** — live panorama rotation from phone compass (PhyPhox), hardware sensor, or manual setting
- **i18n** — English, Français, Español, Deutsch, Português, Italiano; auto-detects system locale
- **Clean mode** — hide all cards with Ctrl+H
- **Lockscreen/wallpaper export** — save the live sky frame as your desktop background

## Install

| | |
|---|---|
| **Ubuntu PPA** (24.04, 26.04) | `sudo add-apt-repository ppa:juliowilly/caelum && sudo apt install caelum` |
| **Snap Store** | `sudo snap install caelum` |
| **Flatpak** (any distro) | download `caelum-<version>.flatpak` from [Releases](https://github.com/Juliowilly/caelum/releases), then `flatpak install --user caelum-<version>.flatpak` |
| **.deb** | download from [Releases](https://github.com/Juliowilly/caelum/releases), then `sudo apt install ./caelum_*_all.deb` |

Inside Flatpak and Snap the hardware compass sensors (IIO, USB serial) are not available: pick
the direction your screen faces in Settings instead. Wallpaper export and autostart use the
desktop portals under Flatpak.

Each release on GitHub has a `SHA256SUMS` file: download it next to the package and run
`sha256sum -c --ignore-missing SHA256SUMS` to check the download.

### pipx

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
pipx install --system-site-packages git+https://github.com/Juliowilly/caelum
caelum &
```

`--system-site-packages` lets the venv use the distro's PyGObject/pycairo instead of compiling them.

### From source

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
python3 -m caelum &          # or: python3 desktop_tracker.py
```

Start automatically with GNOME via Settings → *Start with GNOME session*.

## Mobile (Android, in progress)

A Kivy front-end lives in `caelum/kivy_ui/`. It currently draws the sky gradient, twilight
glows, stars and Milky Way, constellations, sun, moon phase, planets and the horizon. The view
follows the phone's compass when held up to the sky, or you can drag to look around. Weather and
clouds are not ported yet.

Preview it on the desktop (Kivy needs Python ≤ 3.13):

```bash
uv venv -p 3.13 .venv-kivy && uv pip install -p .venv-kivy "kivy[base]==2.3.1" plyer
.venv-kivy/bin/python -m caelum.kivy_ui                      # drag to look around
.venv-kivy/bin/python -m caelum.kivy_ui --time 2026-10-21T22:00 --screenshot night.png
```

Build an APK with [Buildozer](https://buildozer.readthedocs.io): `buildozer android debug`, using `buildozer.spec`.

## Building packages

```bash
make test     # unit tests
make deb      # → dist/caelum_<version>_all.deb   (debian/, needs devscripts dh-python pybuild-plugin-pyproject)
make snap     # → caelum_<version>_amd64.snap     (snap/snapcraft.yaml, needs snapcraft + LXD)
make flatpak  # builds and installs the Flatpak    (flatpak/…yml, needs org.flatpak.Builder + GNOME 51 SDK)
make flatpak-bundle  # → dist/caelum-<version>.flatpak  (single file for GitHub Releases)
make clean
```

The version comes from `caelum/__init__.py` (and `debian/changelog` for the .deb).

## Project layout

```
caelum/
  core/       platform-agnostic: astronomy, weather, config, i18n, star catalog, sky palettes, compass math
  gtk_ui/     Linux desktop front-end: GTK window, Cairo drawing, settings dialog, autostart
  kivy_ui/    mobile front-end (Kivy): sky canvas, gradient textures, phone sensors
main.py       Android entry point (required by Buildozer)
tests/        python3 -m unittest discover -s tests
data/         .desktop entry, icon, AppStream metainfo, store screenshots
debian/       Debian source package (PPA + make deb)
snap/         snapcraft.yaml
flatpak/      Flatpak manifest (local builds and the release bundle)
packaging/    build-deb.sh
```

`caelum/core` must never import GTK, Cairo or Kivy; both front-ends build on it.

## Configuration

Click the gear button (bottom-right) to open Settings. It has four tabs: **Sky** (opaque sky or your own
wallpaper, sky features, aster size), **Display** (overlay, clean mode, click-through, on-screen widgets,
info cards), **Location** (place, timezone, facing direction, compass) and **System** (language,
autostart, wallpaper export, version):
- Location (auto-detect or manual coordinates)
- Timezone
- Language
- Facing direction (or live compass from phone via [PhyPhox](https://phyphox.org))
- Toggle individual cards and visual features
- Opaque sky (on by default): Caelum paints the whole sky itself, bright blue by day and black at night,
  so the wallpaper no longer matters. Off, the sky is a tint over your wallpaper; then a dark navy
  wallpaper works best (e.g. a gradient `#05081A` → `#1A2440` at 72 % height → `#0A0C14`).
  For the wallpaper itself (seen in the Activities overview, or when Caelum isn't running), set
  turn on "Live sky as wallpaper": Caelum saves its own sky as the wallpaper every minute. GNOME's lock
  screen shows the desktop wallpaper, blurred, so the lock screen follows the sky too.
- Click through to desktop (on by default): clicks on the sky reach the desktop icons and windows
  below; only the gear, compass and forecast cards respond. Clicking the compass or a card starts
  *explore mode*: the whole sky takes the mouse (constellation names on hover) until it is idle for 20 s,
  you click empty sky or press Esc. Turn click-through off to keep the whole sky interactive.

Settings are saved to `~/.config/caelum/config.json` (an older `config.json` next to `desktop_tracker.py` is migrated automatically on first run).

## Controls

| Key / Action | Effect |
|---|---|
| Ctrl+H | Toggle clean mode (keys work once Caelum has focus: click the gear, compass or a card) |
| Ctrl+S | Open settings |
| Ctrl+Q | Quit |
| Right-click | Open settings (on the sky only when click-through is off) |
| Click compass | Set facing direction |
| Click forecast day | Expand hourly accordion |
| Esc / click empty sky | Leave explore mode (back to click-through) |

## Data Sources

| Data | Source |
|---|---|
| Forecast, and the weather now where nothing observes it | [Open-Meteo](https://open-meteo.com) + [MET Norway](https://api.met.no) |
| Is it raining now? | The most accurate free source covering your location, in this order: weather radar ([MET Norway Nowcast](https://api.met.no/weatherapi/nowcast/2.0/documentation) in the Nordic countries, [RainViewer](https://www.rainviewer.com/api.html) elsewhere), else the nearest airport's observations (METAR within 30 km, via [aviationweather.gov](https://aviationweather.gov/data/api/)), else the forecast (MET Norway, then Open-Meteo). Settings → Location → Weather Data shows which one is in use |
| Clouds now | The nearest airport's reported cloud layers (METAR within 30 km); the models fill in the layers an automatic station can't see (usually high cloud) |
| Temperature, humidity, wind now | MET Norway Nowcast in the Nordic countries, else the nearest airport, else the forecast |
| Astronomy | Meeus *Astronomical Algorithms* |
| City name | [Nominatim](https://nominatim.openstreetmap.org) (OpenStreetMap) |
| Settings → Detect location | [ipwho.is](https://ipwho.is), falling back to [ipapi.co](https://ipapi.co) (only when you click it) |

All sources are free and require no API key or account.

**Privacy**: all requests use HTTPS. The weather, radar, airport-report and city-name services receive your coordinates
rounded to 2 decimals (about 1 km), never more precise; RainViewer only learns which ~300 km map
tile you are in. Nothing else about you is sent, and Caelum
collects no statistics.

## License

MIT

The landscape photos in `caelum/data/landscapes/` are panoramas from [Poly Haven](https://polyhaven.com),
released under CC0: [noon_grass](https://polyhaven.com/a/noon_grass) by Greg Zaal,
[alps_field](https://polyhaven.com/a/alps_field) and [spiaggia_di_mondello](https://polyhaven.com/a/spiaggia_di_mondello)
by Andreas Mischok. `packaging/make-landscapes.py` rebuilds them (cut-out of the sky, resize).
