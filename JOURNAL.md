# Background Sky — Work Journal

Project: Native Ubuntu Desktop Sun & Moon Tracker Widget
Working dir: `/home/juliowilly/Nextcloud/Lenovo-Ideacentre-QIO-510S-23ISU_Ubuntu_24.04LTS/Background_sky/`
Stack: Python 3 · PyGObject (GTK 3) · Cairo

---

## Session 1 — Initial Build

**Goal:** Build the widget from scratch per `TASK_SPECIFICATION.md`.

### Steps

1. **Set up tmux alias** — Added `alias work-sky='tmux new-session -A -s sky -c "..."'` to `~/.bashrc` so the session can be resumed after disconnection.

2. **Installed dependencies** — `sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0`
   - `python3-gi-cairo` was missing initially; the app crashed with `TypeError: Couldn't find foreign struct converter for 'cairo.Context'`. Fixed by installing it.

3. **Built `desktop_tracker.py`** — First full working version. Features:
   - Borderless transparent GTK3 overlay (`Gdk.WindowTypeHint.DESKTOP`)
   - Sky gradient (`_SKY` palette) from deep night to solar noon
   - Sun at correct position via solar elevation/azimuth formula
   - Moon with crescent phase rendering
   - Parabolic arc path (removed later at user request)
   - 6 HUD info cards (clock, location, sunrise/sunset, solar noon, moon phase, daylight remaining)
   - Clean mode (Ctrl+H hides all cards)
   - Settings dialog (right-click)

4. **Fixed window size — not fullscreen** — Window appeared as a band in the middle, then as a tiny square.
   - Root cause: `display.get_primary_monitor()` returns `None` on this machine (no monitor marked as primary in X11).
   - Fix: `monitor = display.get_primary_monitor() or display.get_monitor(0)`
   - Additional fix: `GLib.idle_add(_force_fullscreen)` — must run after mainloop starts.

5. **Moon position wrong — -67.82°** — Moon was below the horizon according to the code, but user could see it in the sky.
   - Root cause: old Schlyter simplified orbital formula accumulates ~26-year error. Gave -67.82° for the actual date.
   - Fix: Replaced with **Meeus Chapter 47** simplified algorithm (~0.3° accuracy). Correct result: +53.64°.

6. **Clouds added** — Fetches real-time cloud cover from Open-Meteo (free, no API key).
   - Three layers: `cloud_cover_high` (cirrus), `cloud_cover_mid` (altocumulus), `cloud_cover_low` (cumulus).
   - Cloud types rendered as soft elliptical radial-gradient puffs (`_soft_puff()`).
   - Reference photos of user's actual sky (altocumulus) used to calibrate size and density.
   - Milky Way diffuse band added for dark-sky nights.

7. **Removed arc path** — User did not want the arc trajectory guide shown.

8. **No-light-pollution sky** — User's core request: "I want to see the sky that I will have if there is no light pollution."
   - `_SKY` night palette changed to near-black (RGB ≈ 0, 0, 0.04; alpha 0.94).
   - Cloud night palette changed to cool blue-gray (no warm orange pollution tint).
   - Moon glow set to cool silver-white only (not warm orange).
   - `_draw_body_glow_on_clouds()` added: radial silver glow from moon position illuminates nearby clouds.
   - 500 stars with colour variation (blue-white hot stars to warm-white cool stars).
   - Milky Way diffuse band via 120 `_soft_puff` globs along a diagonal path.

---

## Session 2 — Visual Refinements

### Issues reported by user after first launch

**"Sky too bright"**
- Cause: Gradient bottom stop was only `a * 0.30` opacity — bright desktop wallpaper bled through at the horizon.
- Fix: Night sky bottom gradient raised to `a * 0.70`; mid-stop to `a * 0.88`.

**"Moon too small"**
- Initial: `r = 16 * scale` px — tiny on 1920px screen.
- First fix: raised to `r = 40 * scale`.
- User feedback: 2x size requested (not 2.5x). Changed to `r = 32 * scale`.

**"No clouds visible / can't distinguish them"**
- Cause 1: Night cloud color `(0.12, 0.14, 0.22)` was almost identical to sky color → no contrast.
  - Fix: Night cloud color changed to visible silver-gray `(0.34, 0.36, 0.50)`.
- Cause 2: Cloud body glow too weak (alpha 0.38). Raised to 0.60.
- Cause 3: If Open-Meteo returns non-zero total but all individual layers = 0, no clouds drawn.
  - Fix: Fallback distributes `total` to mid-level if all layers are zero.
- Cause 4: Altocumulus base alpha too low (0.55). Raised to 0.72.

**"Dark side of the moon — too dark / not realistic"**
- Real life: the unlit side shows faint earthshine — barely perceptible bluish glow.
- Fix: Dark-side fill alpha changed from `1.0` (solid black) to `0.10` (nearly invisible).

**"Line of light cutting across the starry mantle — vertically at a slight angle"**
- Identified as the Milky Way band appearing as a THIN LINE rather than a wide diffuse band.
  - The original 120 puffs were laid along a 1D path with no perpendicular spread → looked like a stripe.
- Fix: Added perpendicular spread using the band's normal vector (`nx`, `ny`).
  - Puffs now scattered ±18% of screen height perpendicular to the band direction.
  - Puff count raised to 180; sizes increased; Gaussian spread for natural variation.
  - Result: wide soft cloud-like band, not a line.

**"Moon too white"**
- Moon glow was blue-white (`0.85, 0.88, 1.0`). Real moonlight is silver-ivory.
- Fix: glow changed to warm silver `(0.92, 0.91, 0.84)`, lit crescent changed to ivory `(0.96, 0.94, 0.86)`.
- Cloud illumination at night updated to match: warm silver instead of blue.

**"Moon is vertical — mine is horizontal, dark side up, bright side down"**
- Root cause: crescent was always drawn with terminator vertical (lit side left or right). At tropical latitudes (~6°N), the ecliptic meets the horizon steeply, so the moon's crescent is nearly horizontal — the lit limb faces downward toward the set sun.
- Fix: compute **limb angle** = direction from moon to sun projected on screen (extrapolated below horizon). Apply `cr.rotate(-limb_angle)` to the crescent disc so the lit side always faces the sun.
- Unified the waxing/waning rendering to always draw lit side on +x (canonical right), then let rotation orient it. Full moon special-cased (`t < -0.95` → fill full disc).
- For Togo at night with sun below western horizon: result is a horizontal crescent bowl, dark side up, bright side facing lower-right toward the sun — matches what the user sees.

---

## Config file

`config.json` — auto-generated, user-editable:
- `latitude`, `longitude` — location (default: Lomé, Togo)
- `timezone_offset` — UTC offset (default: 0)
- `aster_scale` — sun/moon size multiplier (0.5–3.0)
- `facing` — panorama centre azimuth (0=N, 90=E, 180=S default, 270=W)
- `cards` — per-card visibility toggles
- `clean_mode` — hide all cards (Ctrl+H)
- `show_constellations` — constellation lines on/off
- `show_silhouette` — horizon tree/bush silhouette on/off
- `show_compass` — compass rose on/off
- `keep_above` / `sticky` — window layer options

---

## Session 3 — Constellation Lines + Hover Names + Gear Button + Timezone + Geolocation + On/Off Toggle

### Changes

**Constellation lines**
- Added 7 missing catalog stars for constellation endpoints (Meissa, Vindemiatrix, Seginus, Tarazed, Alshain, Sheliak, Sulafat)
- `_CONSTELLATIONS` data structure: 23 constellations, each `(name, [polylines])`
- Lines drawn in soft blue, fade under moonlight, break automatically at below-horizon stars
- `_get_star_positions` updated to return 6-tuples `(alt, az, mag, bv, ra_h, dec_deg)`
- `show_constellations` config key added; toggle in settings dialog

**Constellation name on hover**
- Mouse motion events added to `self.da` (`POINTER_MOTION_MASK`)
- `_on_motion` tracks `_mouse_x/_mouse_y` and calls `_hit_test_constellation`
- `_hit_test_constellation`: tests distance from mouse to each visible line segment (`_seg_dist`, threshold 22px)
- `_star_screen_cache` dict stored on `self` after each draw pass; used for hit-testing without recomputing
- Hovered constellation lines brighten (alpha ×2.8, lighter colour); name label follows mouse
- `_draw_const_label`: small dark pill with white bold text, clamped to window bounds
- Hover is cleared when sun_el >= -5 (daytime — no constellations drawn)

**Settings gear button**
- `_draw_gear_btn(cr, cx, cy, r)`: dark disc, 8-tooth gear shape in white, center hole
- Drawn in bottom-right corner `(W-28, H-28)` on every frame, including clean mode
- `_on_click` checks `math.hypot(click - gear_center) <= 20` before right-click check
- Gear position stored in `self._gear_cx/cy` set in `_on_draw`

**Global On/Off toggle**
- `app_enabled` config key; gear button turns red-tinted when off
- When off: `cairo.Operator.SOURCE` clears the window to fully transparent; only gear is drawn
- Toggle in Settings dialog at the top

**Moon movement card**
- Moon elevation added to Moon Phase card subtitle: `Age: 8.5d  El: +35.6°`
- Moon IS moving at ~13°/hour (2–3px/min at 1080p); confirmed working

**Timezone selector**
- `_TZ_LIST`: 39 `(offset_hours, label)` tuples covering all UTC offsets including half-hours
- `Gtk.ComboBoxText` in Settings, pre-selected via `_tz_index(offset)` finding closest match
- `_save()` reads combo active index to get offset value

**Auto-detect coordinates**
- "Detect automatically" button in Settings calls `ip-api.com/json/` asynchronously
- Returns `lat`, `lon`, `timezone` (name), `offset` (seconds → divide by 3600)
- Fills lat/lon entries and sets timezone combo; displays detected city name as status

---

## Session 4 — Planets + Moonrise/Moonset + Compass + Shooting Stars + Silhouette + Autostart + Rain

> **Hardware note:** This machine is a **Lenovo ThinkPad T460s** (Ubuntu 24.04 LTS), not a Lenovo Ideacentre AIO. The T460s has no built-in magnetometer, so hardware compass falls back to manual facing selection or external sources.

### New features

**Naked-eye planets (Mercury, Venus, Mars, Jupiter, Saturn)**
- `_kepler_E(M_deg, e)`: iterative Kepler equation solver
- `_PLANET_ELEMS`: Schlyter simplified orbital elements at J2000
- `planet_positions(lat, lon, dt_utc)` → list of `(name, el, az, rgb)`, cached per hour
- `_draw_planets()`: colored glow disc + disc + name label; Saturn gets elliptical ring stroke
- Planet colors: Mercury=gray, Venus=warm white, Mars=orange-red, Jupiter=warm yellow, Saturn=pale gold

**Moonrise / Moonset card**
- `_find_moon_event(lat, lon, date, tz_off, event)`: scans 1440 minutes, detects horizon crossing
- `self._moonrise`, `self._moonset` computed in `_refresh_day` alongside sunrise/sunset
- New HUD card: "MOONRISE / MOONSET  HH:MM  /  HH:MM"
- Toggle in Settings under Visible Cards

**Functional compass rose (top-left)**
- `_draw_compass(cr, cx, cy, r)`: dark circle, 8 tick marks, N/E/S/W labels (N in red), red/white diamond needle always pointing North
- **Blue FOV wedge**: 240° sector showing the panorama's field of view, centred on `facing` direction
- **Facing arrow**: thin blue line from pivot pointing toward the configured facing direction
- `show_compass` config key; toggle in Settings
- Facing direction selector in Settings: 8 options N/NE/E/SE/S/SW/W/NW

**Panorama rotates with facing direction**
- `_FACING` module-level float, updated each frame from `cfg['facing']`
- `sky_to_screen(el, az, W, H)` now uses `_FACING`: `rel = ((az - _FACING + 180) % 360) - 180`; panorama is always 240° centred on facing
- Limb-angle calculation in `_on_draw` updated to use `_FACING` for correct crescent tilt at any facing
- Default: 180° (South). User sets their screen's real-world facing direction; panorama and compass wedge match reality

**Star twinkling**
- Per-star phase offset: `phase_off = (ra_h * 7919 + abs(dec_deg) * 3571) % 2π`
- `alpha *= 1 + 0.14 * sin(t_sec * 2.7 + phase_off)` — each star shimmers independently

**Shooting stars / meteors**
- `_maybe_spawn_meteor(W, H)`: 0.6% chance/frame to spawn; seeded from `time.time()`
- `_draw_meteors(cr, W, H)`: LinearGradient streak animates along trajectory; fades in/out using `sin(t * pi)`
- Meteors only spawn at night (called from inside `if sun_el < -5` block)
- Main tick changed from 1000ms to 100ms for smooth animation

**Horizon silhouette**
- `_draw_horizon_silhouette(cr, W, H)`: seeded-random (`0xA5B2`) irregular polygon of trees, bushes, and flat ground at `y = H * 0.88`; dark green-black fill `(0.04, 0.07, 0.04, 0.72)`
- `show_silhouette` config key; toggle in Settings

**Autostart on GNOME login**
- `_AUTOSTART_PATH = ~/.config/autostart/sky-tracker.desktop`
- `set_autostart(enabled)`: creates/removes `.desktop` file for GNOME autostart
- `autostart_enabled()`: checks file existence
- Toggle in Settings labeled "Start with GNOME session"

**Rain / Snow overlay**
- `fetch_cloud_layers` URL extended with `precipitation,snowfall` parameters
- `_NO_CLOUDS` extended: `'precip': 0.0, 'snow': False`
- `_draw_rain(cr, W, H, precip, snow)`: rain = angled blue streaks; snow = soft white circles; both seeded from `time.time() * 8` for animated variation

**Cloud Cover card now toggleable**
- Previously hardcoded as always-on at top-right
- Now respects `enabled.get('cloud_cover', True)` — toggle in Settings under Visible Cards

**Hardware compass detection chain**
- `_detect_compass()` probes in order: IIO sysfs → iio-sensor-proxy D-Bus → USB serial → HTTP URL
- `_poll_compass()` runs every 500ms in a background thread; updates `_hw_heading` via `GLib.idle_add`
- When `_hw_heading` is set, `_FACING` tracks it live — panorama rotates in real time as the laptop moves
- Falls back to manual facing selector when no hardware/network source is detected

**Phone compass via PhyPhox + compass_bridge.py**
- Termux:API could not be installed (signature mismatch — Termux source vs APK source differ); Termux:API removed from Play Store
- PhyPhox (RWTH Aachen, Play Store) used instead: magnetometer experiment with remote access exposes raw X/Y/Z µT values at `http://<phone-ip>:8080/get?magX&magY&magZ`
- `compass_bridge.py` runs on the laptop: polls PhyPhox every 500ms, computes heading, serves plain float at `http://localhost:8888/heading`
- Formula: `atan2(x, y)` — Redmi Note 14 Pro has mirrored X axis vs standard Android convention; `atan2(-x, y)` swaps East/West
- `compass_url = "http://localhost:8888/heading"` in config.json; `_detect_compass` Method 4 picks it up at startup
- Phone IP can change via DHCP — if bridge stops working, check new IP with GSConnect and restart: `python3 compass_bridge.py http://<new-ip>:8080`
- Keep PhyPhox open and running (▶) on phone — MIUI kills it when backgrounded

---

## Key keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+H   | Toggle clean mode (hide/show cards) |
| Ctrl+S   | Open settings dialog |
| Ctrl+Q   | Quit |
| Right-click | Open settings dialog |

---

## Dependencies

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
```

## Run

```bash
DISPLAY=:0 python3 desktop_tracker.py &
```

Or via tmux alias: `work-sky` (attaches to existing session or creates new one in project dir).

---

## Session 5 — Weekly Forecast Accordion + Weather Icons + Info Card Icons + Bug Fixes + i18n + GitHub

### Weekly forecast accordion (replaced hourly strip)
- Removed `_draw_forecast_strip` (~113 lines of dead code) — bottom hourly strip was replaced by accordion
- `_draw_weekly_forecast`: day cards stack vertically (right column); clicking a day expands hourly slots inline underneath it
- Layout: `CARD_W=210`, `DAY_H=52`, `HOUR_H=28`; accordion uses cumulative `y` variable (not fixed grid)
- `self._weekly_card_rects` — list of `(date_str, x, y, w, h)` hit-rects updated each frame for click detection
- `self._selected_day` — ISO date string of the open day; `self._selected_day_slots` — hourly slots cached in `_on_click` (not filtered every frame)
- Overflow boundary check: `max_days` computed from remaining screen height so accordion never goes off-screen

### Cairo-drawn weather icons (`_draw_wx_icon`)
- `_cloud()` uses `cr.push_group()` to prevent double-paint artifacts at circle overlaps
- Symbol routing: `has_thunder`, `has_rain`, `has_snow`, `has_showers`, `has_heavy`, `has_light` flags
- Snow asterisks (6-arm) for size ≥ 22px, dots for smaller
- Icons shown on weekly day cards (32px), hourly rows (18px), and cloud cover badge

### Astronomical info card icons + city name + moon aspect
- `ic_clock`, `ic_pin`, `ic_sunrise`, `ic_solar_noon`, `ic_moon_phase`, `ic_moon_rise`, `ic_daylight` — all Cairo-drawn
- `self._moon_limb_angle` stored each frame so `ic_moon_phase` draws crescent correctly oriented
- `self._city_name` — fetched async from Nominatim on startup; shown in LOCATION card
- `_fetch_city_name` retried after weather fetch if city is still None

### "Lines on cards" bug fix
- Root cause: `cr.show_text()` leaves a current point; `cr.save()`/`cr.restore()` does NOT save the Cairo path; `cr.arc()` with a live current point draws a connecting line before the arc (visible when stroked)
- Fix: `cr.new_path()` before AND after every `icon_fn` call in `emit()`; also before `_draw_wx_icon` for the cloud badge

### Comprehensive review — 14 fixes applied
1. Removed dead `_draw_forecast_strip` method + `show_forecast` config key + Settings toggle
2. **UTC fix**: `_on_draw` now computes `utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)` first, then `now = utc + timedelta(hours=tz_off)` — previously astronomical math used local time as UTC
3. Removed `planet_positions()` cache-warm call in the `else` branch
4. `_weather_fetching` dedup flag — prevents parallel weather fetches (GLib timer fires while previous fetch is still running)
5. Astronomy cache (1s TTL): `solar_position`, `moon_position`, `moon_phase_age`, `moon_brightness` called at most once per second; stored in `self._astro_cache`
6. Star positions already cached per-minute by `_get_star_positions` — no change needed
7. `self._today_str` updated in `_refresh_day`, used in `_draw_weekly_forecast` instead of recomputing each frame
8. `self._selected_day_slots` cached in `_on_click`; `_draw_weekly_forecast` reads it directly
9. Removed `import datetime as _dt` from inside methods — fixed all `_dt.*` refs to use module-level `datetime`
10. Weekly forecast overflow boundary check
11. Lockscreen export thread safety: `_render_frame_to_surface()` now runs on main thread (GTK/Cairo requirement); only file I/O and `gsettings` subprocess calls go to background thread
12. City name retry after weather fetch
13. `_clear_weather_fetching` idle callback resets dedup flag
14. `_draw_stars` fallback also fixed to use `datetime.timezone.utc` (was `utcnow()`)

### i18n — 6 languages
- `_LANG` global, `_t(key)` lookup function, `_set_lang(setting)` (accepts `'auto'` → reads system locale)
- `_DAYS_SHORT`, `_MONTHS_SHORT` — per-language short day/month name tables
- `_fmt_date(dt)` replaces `strftime('%a %d %b %Y')` — fully translated date string
- `_TRANSLATIONS` dict: **en, fr, es, de, pt, it** — covers card titles, moon phases, weather conditions, all Settings labels
- Parametric strings use format keys: `_t('pct_elapsed').format(pct=72)` → `'72% du jour écoulé'` in French
- Language selector added to top of Settings dialog; change takes effect immediately without restart
- `"language": "auto"` added to `DEFAULT_CONFIG`; persisted in `config.json`

### Published to GitHub
- App renamed **Caelum** (Latin for *sky*) throughout — settings window title, autostart .desktop, User-Agent strings, lockscreen export filename
- `README.md` and `.gitignore` added
- Repo: **https://github.com/Juliowilly/caelum** (public)
- SSH key (`id_ed25519`) added to GitHub account via `gh auth login`

---

## Session 6 — Code review fixes (12 issues)

**Goal:** Fix all 12 issues identified in a comprehensive code review at the end of Session 5.

### Bugs fixed

1. **`_apply_clouds` stale hourly slots** — When new weather data arrived every 30 min, the expanded forecast accordion kept showing the old hourly slots. `_apply_clouds` now re-derives `_selected_day_slots` from the fresh data when a day is expanded.

2. **`_save` didn't clear selected day on location change** — After changing location and saving, the old hourly slots from the previous location persisted until the user manually closed the accordion. `_save` now resets `_selected_day` and `_selected_day_slots` before triggering the weather fetch.

### Performance

3. **`_WMO_PRECIP` dict moved to module-level** — Was being recreated inside `fetch_open_meteo` on every HTTP call. Now a module-level constant `_WMO_PRECIP`.

4. **`sky_to_screen` double-call per star eliminated** — `_draw_stars` built `star_screen` (first pass) then called `sky_to_screen` again for the same stars in the drawing loop. Second pass now reads from `star_screen` directly, halving the projection math at night.

5. **`_PHASE_NAMES` moved to module-level** — Was a local list recreated inside `_draw_cards` on every frame (once per second). Now `_PHASE_NAMES` constant at module level.

### Dead code / cleanup

6. **`_WX_DAYS` removed** — `['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']` was unused since i18n replaced it with `_day_name()`. Deleted.

### i18n

7. **`_FACING_OPTIONS` translated** — Direction labels like `'N  — Facing North'` were hardcoded English. `_FACING_OPTIONS` changed to 3-tuples `(az, abbrev, dir_key)`. Settings combo now builds labels as `f'{abbrev}  — {_t(dir_key)}'` at open time. Added 8 direction keys to all 5 non-English translation dicts (fr, es, de, pt, it).

### Missing asset

8. **`LICENSE` file created** — README claimed MIT but no LICENSE file existed. MIT license added to the repo.

### .gitignore

9. **`config.json` and `TASK_SPECIFICATION.md` added to `.gitignore`** — `config.json` contains personal coordinates and should not be committed. `TASK_SPECIFICATION.md` is an internal planning document. Also corrected the lockscreen filename from `sky-tracker-lockscreen.png` to `caelum-lockscreen.png`.

### Comment fix

10. **Wrong comment in `_render_frame_to_surface`** — Said "White background" but the code paints black. Fixed to "Black background".

---

## Session 7 — Second code review pass (3 fixes)

**Goal:** Second comprehensive review pass — found and fixed 3 more issues.

### Bug
1. **Weather timer was 60 seconds instead of 30 minutes** — `GLib.timeout_add(60 * 1000, ...)` made HTTP requests to Open-Meteo and MET Norway once per minute. MET Norway data updates hourly; Open-Meteo every 15 min. README and Settings hint both said "every 30 min". Fixed to `30 * 60 * 1000`.

### Dead code
2. **`if utc is not None:` guard in `_draw_stars` was always True** — `utc` is assigned unconditionally at the top of the function when `None`. The twinkling alpha calculation was always running. Removed the dead conditional and de-indented the three lines.

### i18n
3. **`'click to set facing'` compass label not translated** — Hardcoded English string in `_draw_compass`. Added to all 5 language dicts and wrapped with `_t()`.

---

## Session 9 — Third code review pass (3 fixes)

**Goal:** Full review of all remaining sections (cloud drawing, planet drawing, compass, meteors, rain,
sun/moon, weather icons, weekly forecast, HUD cards, SettingsDialog).

### Fixes
- **Stale hint text in SettingsDialog** (`desktop_tracker.py:4030`) — hint still said
  "Weather refreshes every 30 min via Open-Meteo." Updated to reflect the actual dual-timer
  schedule: "Open-Meteo every 15 min · MET Norway every 1 h."
- **Dead `cr.set_line_width(0)` in snow path** (`_draw_rain`) — snow flakes are drawn with
  `cr.arc()` + `cr.fill()`; `set_line_width` only affects `stroke()`, so the call had no
  effect. Removed.
- **Planet name label ignores `scale`** (`_draw_planets`) — all planet geometry (disc radius,
  glow radius) already multiplied by `scale`; the name label was hardcoded to 9 px. Changed
  to `9 * scale` so labels stay proportional at all asteroid-scale settings.

---

## Session 8 — Independent weather timers per source

**Goal:** User clarified the original 60 s timer was intentional; requested separate intervals per source.

### Refactor
- **Split `_fetch_weather_async` into two independent paths:**
  - `_fetch_om_async` — Open-Meteo, every **15 minutes** (current conditions: clouds, precipitation, WMO code)
  - `_fetch_met_async` — MET Norway, every **1 hour** (forecast, hourly accordion, temperature, wind, symbol)
- Each path has its own dedup flag (`_om_fetching`, `_met_fetching`) and caches its last raw result (`_last_om`, `_last_met`).
- On completion, either path calls `merge_weather(_last_om, _last_met)` so the merged view always uses the freshest data from both sources simultaneously.
- `_fetch_weather_async` kept as a combined helper (startup + location change); it now just calls both sub-fetchers.
- `_save` clears `_last_om` and `_last_met` when location changes so stale data from the old location is not merged with fresh data for the new one.

---

## Session 10 — Multi-platform strategy, package split, Linux packaging

**Goal:** Decide the mobile framework and the Linux packaging path, then implement packaging.

### Decision 1 — Mobile framework: **Kivy**
| Need | Kivy | BeeWare (Toga) |
|---|---|---|
| Cairo-style drawing (11 radial + ~8 linear gradients, hundreds of puffs, 10 fps) | OpenGL canvas, fast; gradients via textures/shaders → drawing layer rewritten | `toga.Canvas` has no radial gradients, slow with many shapes → **disqualifying** |
| Compass / GPS | `plyer.compass`, `plyer.gps` (Android + iOS) | Location yes, compass needs native bridge code |
| Background service | python-for-android services | weak |
| Native widgets | not native (only the settings screen needs any) | strength, but barely used here |

- The app is ~95% custom canvas, so Kivy wins. Mobile app = full-screen sky app.
- **Not possible with either:** an Android *live wallpaper* (needs a Java/Kotlin `WallpaperService`).
  iOS has no third-party live wallpapers at all. Revisit later as a Kotlin shell + Chaquopy if wanted.
- Correction to an earlier note: Python apps *can* ship on the iOS App Store (both Kivy and BeeWare embed CPython).

### Decision 2 — Linux packaging: **pyproject.toml + .deb**
- pyproject: standard, gives a `caelum` command, prerequisite for everything else.
- .deb: native for Ubuntu; apt resolves `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0`.
- Flatpak deferred: sandbox conflicts with `gsettings` wallpaper export, autostart file writing,
  `/sys` IIO and serial compass access.
- Install-script-only rejected: no upgrade/uninstall story.

### Package split (`desktop_tracker.py` → `caelum/`)
Split mechanically by line ranges (no code retyped); pyflakes clean before and after.
```
caelum/core/      config.py  weather.py  sky.py  i18n.py  catalog.py  astronomy.py   (no GTK/Cairo imports)
caelum/gtk_ui/    window.py  settings.py  clouds.py  autostart.py  app.py
```
- `_FACING` module global → `core.sky.set_facing()` / `get_facing()` (a `global` can't cross modules).
- `desktop_tracker.py` is now a compatibility shim, so existing autostart entries and
  `python3 desktop_tracker.py` keep working. Also runnable as `python3 -m caelum`.

### Installed-app fixes
- **Config moved to `$XDG_CONFIG_HOME/caelum/config.json`** (`~/.config/caelum/`). The package dir is read-only
  once installed. The old `config.json` beside `desktop_tracker.py` is copied over on first run (tested: byte-identical).
- **Autostart `Exec`** now uses the installed `caelum` command if on PATH, else `python3 -m caelum` with `Path=` set
  to the checkout. Previously it hardcoded `python3 <__file__>`, which would break inside a package.
- **`locale.getdefaultlocale()` replaced** with an env lookup (LC_ALL → LC_MESSAGES → LANG → LANGUAGE).
  It is removed in Python 3.15 and the exception was swallowed, so "auto" language would have silently become English.
- `config.json` untracked (`git rm --cached`). It was added to `.gitignore` in Session 6 but never removed from the index.

### Packaging files
- `pyproject.toml` (setuptools, `caelum` gui-script, version from `caelum/__init__.py` = 1.0.0, extra `[compass]`)
- `data/io.github.juliowilly.Caelum.{desktop,svg,metainfo.xml}`. desktop-file-validate and appstreamcli both pass.
- `packaging/build-deb.sh` builds with `dpkg-deb --root-owner-group` only (no debhelper). It installs to
  `/usr/lib/python3/dist-packages/caelum`, `/usr/bin/caelum`, and the share dirs; postinst runs `py3compile`, prerm runs `py3clean`.
  Forces `umask 022` (this machine's umask 002 produced group-writable dirs).
- `Makefile`: `run`, `deb`, `wheel`, `clean`.

### Verified
- App runs from the extracted .deb, via the shim, and via a `pipx install --system-site-packages .` with no tracebacks.
- Machine is now on **Ubuntu 26.04.1 LTS** with Python 3.14.

### Release
- Published **v1.0.0** on GitHub Releases with `caelum_1.0.0_all.deb` attached
  (https://github.com/Juliowilly/caelum/releases/tag/v1.0.0). The tag points at this journal commit; code is identical to `3591643`.

### v1.0.1 — app icon on windows
- The SVG icon existed in v1.0.0 but only the launcher used it: windows set no icon and no app id,
  so the Settings window got a generic icon in the dock / Alt+Tab, and source runs had no icon at all.
- `gtk_ui/app.py` `_set_app_identity()`: `GLib.set_prgname('io.github.juliowilly.Caelum')`
  (= Wayland app_id / X11 WM_CLASS, which GNOME matches to the .desktop file), application name "Caelum",
  default window icon from the icon theme when installed, else loaded from `data/` in the checkout.
- README now shows the logo at the top; version bumped to 1.0.1 (`__init__.py`, metainfo release entry).
- Published https://github.com/Juliowilly/caelum/releases/tag/v1.0.1 with `caelum_1.0.1_all.deb`.
  v1.0.0 left unchanged.

### Next session
- Install the .deb locally and test (`sudo apt install ./dist/caelum_1.0.0_all.deb`).
- Start the Kivy front-end (`caelum/kivy_ui/`) on top of `caelum/core`: projection + sky gradient + sun/moon first,
  then clouds via a soft-puff texture.

---

## Session 11 — Kivy mobile port, milestone 1 (clear sky)

**Goal:** Start the Kivy front-end on top of `caelum.core`, as decided in Session 10.

### Dev environment
- Kivy 2.3.1 has no wheels for Python 3.14 (the system Python). Installed `uv` (pipx) and made a
  Python 3.13 venv: `.venv-kivy/` (gitignored). The APK build is unaffected: python-for-android builds
  its own Python 3.11, and all of `caelum/` was compile-checked under 3.11.

### New: `caelum/kivy_ui/`
- `sky_view.py`: `SkyView` widget, a port of the GTK draw path. Sky gradient, Belt of Venus, pre-glow,
  golden-hour band, haze, faint star field, airglow, Milky Way, catalog stars with twinkle, constellation
  lines, M42, sun bloom, moon pre-glow, moon glow and phase disc, planets with Saturn's ring and labels,
  horizon silhouette, and a HUD (time, date, moon phase, facing).
  - Reuses `sky_to_screen()` etc. unchanged; `_k()` flips Cairo y-down to Kivy y-up.
  - **Opaque sky**: the desktop sky is translucent over the wallpaper, but a phone app has nothing
    behind it, so gradient alphas are dropped and the ground is always drawn opaque.
  - Moon lit region = triangle strip between the limb and the terminator at equal heights, rotated
    by the same `limb_angle` as the desktop. This handles crescent (concave) and gibbous alike.
  - Redraw once a second; twinkle updates star `Color` alphas at 10 Hz without rebuilding.
    Drag/compass changes go through `Clock.create_trigger`, so at most one redraw per frame.
  - Measured on the T460s: night 7 ms / 1350 instructions, day 1 ms / 66 instructions.
  - Desktop SCREEN blending for the sun is approximated with normal alpha blending.
- `textures.py`: Cairo gradients baked into small cached textures (radial with inner radius,
  vertical, alpha-only puff profile tinted with `Color`). LRU-capped at 256.
- `sensors.py`: `Compass` (plyer accelerometer + magnetometer, no-op off-device) and
  `request_location()` (Android runtime permission + one-shot plyer GPS fix, saved to config).
- `app.py`: `CaelumApp`. On Android the config lives in `App.user_data_dir`. Preview flags:
  `--time`, `--facing`, `--size`, `--screenshot`. Run with `python -m caelum.kivy_ui`.
- HUD strings `compass` / `drag to look around` translated into all 5 languages.

### New in core
- `core/orientation.py`: `heading_from_sensors(accel, mag)`, built like Android's
  `getRotationMatrix` (east = mag × up, north = up × east). Upright: heading of the back camera (-z),
  so the screen shows the sky behind the phone. Flat: heading of the top edge.
- `tests/test_orientation.py`: 4 tests (portrait at 6 azimuths, landscape, flat, degenerate readings).
- `core/config.set_config_dir()` for platforms with their own data dir.

### Packaging
- `buildozer.spec` (landscape, fullscreen, location permissions, API 34 / min 24, arm64 + armv7;
  version read from `caelum/__init__.py`) and root `main.py` (Buildozer entry point).
- `data/io.github.juliowilly.Caelum-512.png` app icon, rendered from the SVG.
- The .deb and the wheel now exclude `caelum/kivy_ui` (verified: 0 kivy_ui files in the .deb).

### Verified
- Desktop previews at 22:00, 18:05 and 13:00 UTC render correctly; GTK app still runs; tests and pyflakes pass.
- **Not yet verified on a phone**: the APK has not been built; compass and GPS code is untested on hardware.

### Next
- Build the APK with Buildozer (needs Java 17 + several GB of Android SDK/NDK) and test on the Redmi Note 14 Pro.
  Its magnetometer X axis is mirrored (Session 4), so the heading may need a per-device flip.
- Milestone 2: weather fetch + clouds (soft-puff texture), rain/snow, meteors.
- Portrait layout: the 240° panorama is squeezed on a narrow screen, so it needs a narrower FOV.

---

## Session 12 — Finish the Linux desktop phase: Snap Store, Flathub, Launchpad PPA

**Decision (user):** pause the APK and finish Linux distribution first. Targets: **Snap Store**,
**Flathub**, **Launchpad PPA** (AppImage dropped: no real store, and Snap + Flatpak cover the distros).

### Step 1 — sandbox-aware app (`caelum/gtk_ui/sandbox.py`)
- `kind()` detects `flatpak` (`/.flatpak-info`) / `snap` (`$SNAP_NAME`) / plain install.
- **Wallpaper export**: replaced the `gsettings` subprocess calls with in-process `Gio.Settings`
  (schema/key looked up first, because GSettings aborts on unknown schemas). It runs on the main thread via
  `GLib.idle_add` after the PNG is written in the worker thread. URI built with `GLib.filename_to_uri`
  (the old `f'file://{path}'` broke on paths with spaces). Flatpak uses the Wallpaper portal
  (`SetWallpaperFile`, fd passed, `set-on` = background/lockscreen/both), since dconf is out of reach there.
  The snap writes the PNG to `$SNAP_USER_COMMON/.cache` so the path survives refreshes.
- **Autostart**: snap keeps writing `~/.config/autostart/caelum.desktop` (HOME is the snap's, and snapd
  launches it through snapcraft.yaml `autostart:`), with `Exec=caelum`. Flatpak uses the Background portal
  (`RequestBackground`, `autostart`, `commandline=['caelum']`), with the choice remembered in a marker file.
- Tested with `GSETTINGS_BACKEND=memory` (real wallpaper untouched); GTK app still runs.

### Step 2 — Debian source package (`debian/`, for the PPA and `make deb`)
- debhelper 13 + pybuild + `pybuild-plugin-pyproject`; `dh-sequence-python3` is required in Build-Depends.
  Without it dh_python3 never ran: files landed in `python3.14/dist-packages` with stray `__pycache__`
  and no `python3` dependency. Depends are now computed (`python3:any`, `python3-gi`, `python3-cairo`).
- Unit tests run during the build (`PYBUILD_TEST_ARGS=-s tests -v`; pybuild already supplies
  `-m unittest discover`). Lintian: only `initial-upload-closes-no-bugs` and `no-manual-page`.
- `packaging/build-deb.sh` now runs `dpkg-buildpackage` on a copy of the tree (tracked + new,
  non-ignored files). The hand-rolled dpkg-deb script is gone, leaving one recipe for GitHub and the PPA.
- pyproject `license` switched to the table form: Ubuntu 24.04 has setuptools 68, which predates PEP 639.

### Step 3 — Flatpak (`flatpak/io.github.juliowilly.Caelum.yml`)
- GNOME 51 runtime (it provides Python, PyGObject and pycairo); pip installs the package offline.
- Tools installed per-user: added a `--user` Flathub remote (only the system one existed), then
  `org.flatpak.Builder` + `org.gnome.Platform//51` + `org.gnome.Sdk//51`.
- `--disable-rofiles-fuse` needed (FUSE helper can't start when the builder itself is a Flatpak).
- Runs; `sandbox.kind()` = flatpak inside; icon found. The wallpaper/autostart portals have not been
  exercised yet (that would change the real desktop), so they await a manual test.
- flatpak-builder-lint: manifest clean; build only fails `appstream-missing-screenshots`, because the
  screenshot URLs point at the not-yet-pushed `v1.1.0` tag.

### Step 4 — Snap (`snap/snapcraft.yaml`)
- core24 + gnome extension; stage `python3`, `python3-gi`, `python3-gi-cairo` from 24.04; plugs
  `network`, `gsettings`; `autostart: caelum.desktop`; desktop Icon rewritten to `${SNAP}/…`.
- First LXD build failed: "Timed out waiting for networking". The container got IPv6 but no IPv4
  because **ufw blocks DHCP on lxdbr0**. Fix (user, sudo): allow in + route in/out on lxdbr0.

### Bugs found while making store screenshots (pre-existing, fixed in core)
- **Objects outside the 240° view piled up on the screen edges**: `sky_to_screen` clamped azimuth
  instead of hiding, so stars behind the viewer formed vertical columns at x≈6% and x≈94%, and
  constellation lines spanned the whole screen between them. Now returns None outside ±120°.
- **Moon phase name was rounded down**: `int(phase*8)` called a 10.7-day moon "First Quarter".
  New `astronomy.phase_index()` rounds to the nearest of the 8 names (used by GTK and Kivy).
- `tests/test_sky.py`: projection edges, out-of-view, below-horizon, phase naming (8 tests total: 4 orientation + 4 sky).

### Metadata for the stores
- Screenshots rendered off-screen by a scratch script (fixed UTC time, clear sky, real forecast):
  `data/screenshots/night.png`, `dusk.png`.
- metainfo: screenshots, branding colours, display/controls, bugtracker/VCS URLs, 1.1.0 release notes;
  compass bullet reworded (hardware sensors aren't available in sandboxes).
- Version **1.1.0** (`caelum/__init__.py`, `debian/changelog` 1.1.0-1, metainfo).

### Step 5 — store accounts
- Snap Store: logged in as `juliowilly`; **name `caelum` registered** (`snapcraft register`).
- Local LXD builds still fail: new containers get no IPv4 (DHCP unanswered on lxdbr0 even after the
  ufw rules), so the snap is built with `snapcraft remote-build` on Launchpad (also gives arm64).
- GPG key for Launchpad: RSA 4096, fingerprint `0F8F7EF1922EFA195490DF4E747D0A3BC76874C6`;
  its UID had a typo (`cjw.` instead of `jw.`), to be corrected before publishing to the keyserver.
- Maintainer email changed to **jw.adamagaba@gmail.com** in `debian/{control,changelog,copyright}`
  (user's choice, used everywhere from now on).

### Step 6 — Launchpad PPA (`ppa:juliowilly/caelum`)
- New signing key (correct UID `jw.adamagaba@gmail.com`), fingerprint
  `8ADAFA29057A27BE2DD54CC839C70230203512C3`; the typo key was never published.
  `gpg --send-keys` silently didn't land, so it was uploaded via `POST /pks/add` (HTTP 200, "inserted").
- Launchpad sent the confirmation **unencrypted**: the key is sign-only, so instead of decrypting a
  mail you clear-sign the paragraph shown on the token page and paste the signed block back.
- `packaging/ppa-upload.sh [--upload] [REV]`: builds from HEAD only (refuses a dirty tree), makes one
  `orig.tar.gz` (git archive minus debian/) shared by all series, and creates per-series versions
  `1.1.0-1~ubuntu24.04.1` (noble) / `~ubuntu26.04.1` (resolute). First upload uses `-sa`, the rest `-sd`;
  signed with `-k <fingerprint>`.
- Lintian: added a CC0-1.0 stanza for the metainfo file in debian/copyright (it was flagged as
  inconsistent with MIT). `binary-nmu-debian-revision-in-source` is a false positive of the PPA version format.
- **PPA builds succeeded** (2026-10-21 ~20:25 UTC): noble 8m32s (Python 3.12), resolute 9m20s (Python 3.14);
  the 8 unit tests ran and passed in both. Gotcha: `api.launchpad.net` served **stale** build status
  ("Currently building") for ~20 min after both had finished; `launchpad.net/api/devel/...` was current.
- Upload gotcha: dput's first attempt failed with a DNS error; re-running `dput` on the already-signed
  `.changes` files worked (no rebuild needed).

### Step 7 — snap via `snapcraft remote-build`
- The first run froze in uninterruptible I/O (`wchan request_wait_answer` = FUSE): GSConnect's **stale
  SFTP mount of the phone** (`sftp://192.168.1.90:1741/` under `/run/user/1000/gvfs`) hung everything that
  enumerated mounts. Fixed with `gio mount -f -u sftp://192.168.1.90:1741/`. A frozen process with that
  wchan points at this mount first.
- The second run is stuck at "Trying to get project juliowilly-craft-remote-build", caught in the same
  Launchpad API slowness (4–10 s per request).
