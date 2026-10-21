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
- **Real-time weather** — cloud layers, rain, snow, rainbow from Open-Meteo + MET Norway (no API key needed)
- **Weekly forecast** — accordion-style column; click a day to expand hourly slots
- **Cairo-drawn weather icons** — no external image files
- **Astronomical info cards** — clock, location, sunrise/sunset, solar noon, moon phase, moonrise/moonset, daylight remaining
- **Compass rose** — live panorama rotation from phone compass (PhyPhox), hardware sensor, or manual setting
- **i18n** — English, Français, Español, Deutsch, Português, Italiano; auto-detects system locale
- **Clean mode** — hide all cards with Ctrl+H
- **Lockscreen/wallpaper export** — save the live sky frame as your desktop background

## Install

### Debian / Ubuntu (.deb)

Download `caelum_<version>_all.deb` from the [Releases](https://github.com/Juliowilly/caelum/releases) page, or build it yourself (see below), then:

```bash
sudo apt install ./caelum_1.0.1_all.deb
caelum &
```

apt pulls in the GTK dependencies. Caelum then appears in the app grid.

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

## Building packages

```bash
make deb      # → dist/caelum_<version>_all.deb  (needs only dpkg-deb)
make wheel    # → dist/caelum-<version>-py3-none-any.whl
make clean
```

The version comes from `caelum/__init__.py`.

## Project layout

```
caelum/
  core/       platform-agnostic: astronomy, weather, config, i18n, star catalog, sky palettes
  gtk_ui/     Linux desktop front-end: GTK window, Cairo drawing, settings dialog, autostart
data/         .desktop entry, icon, AppStream metainfo
packaging/    build-deb.sh
```

`caelum/core` must never import GTK or Cairo, so it can be reused by the planned Kivy mobile port.

## Configuration

Right-click or click the gear button (bottom-right) to open Settings:
- Location (auto-detect or manual coordinates)
- Timezone
- Language
- Facing direction (or live compass from phone via [PhyPhox](https://phyphox.org))
- Toggle individual cards and visual features

Settings are saved to `~/.config/caelum/config.json` (an older `config.json` next to `desktop_tracker.py` is migrated automatically on first run).

## Phone Compass (PhyPhox)

1. Install [PhyPhox](https://phyphox.org) on your phone
2. Start the Magnetometer experiment and enable Remote Access
3. Run the bridge on your laptop (`compass_bridge.py` is in the source repository, not the .deb):
   ```bash
   python3 compass_bridge.py http://<phone-ip>:8080
   ```
4. In Settings → Phone compass URL: `http://localhost:8888/heading`

## Controls

| Key / Action | Effect |
|---|---|
| Ctrl+H | Toggle clean mode |
| Ctrl+S | Open settings |
| Ctrl+Q | Quit |
| Right-click | Open settings |
| Click compass | Set facing direction |
| Click forecast day | Expand hourly accordion |

## Data Sources

| Data | Source |
|---|---|
| Weather (clouds, rain, temp) | [Open-Meteo](https://open-meteo.com) + [MET Norway](https://api.met.no) |
| Astronomy | Meeus *Astronomical Algorithms* |
| City name | [Nominatim](https://nominatim.openstreetmap.org) (OpenStreetMap) |

All sources are free and require no API key.

## License

MIT
