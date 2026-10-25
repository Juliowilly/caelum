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
- **remote-build abandoned**: it hung 3× at "Trying to get project … (attempt 1/6)" with its socket in
  CLOSE-WAIT and the main thread on a lock (never retried). Back to local LXD.
- **Real cause of the LXD "networking" timeouts** (not the firewall, whose lxdbr0 rules were correct):
  LXD sometimes **fails to attach a new container's veth to lxdbr0** on first start (`ip link show
  master lxdbr0` empty, the container's static IPv4 gets "No route to host"). `lxc restart` attaches it
  (IPv4 at once). During builds a watcher restarts any snapcraft container with no IPv4 after 20 s.
- **core24 ships Python 3.12**, so snapcraft silently drops `python3` from stage-packages and
  `command: usr/bin/python3` failed the pack check ("usr/bin/python3 does not exist"). Now
  `command: bin/caelum`, a launcher that `exec /usr/bin/python3 -m caelum`; only `python3-gi(-cairo)` are staged.
- Changing override-build after a run gave "variable 'version' can be set only once": stale part
  state, fixed with `snapcraft clean caelum` (keeps the downloaded GNOME SDK).
- **Built `caelum_1.1.0_amd64.snap` (3.1 MB)**: launcher, cpython-312 `_gi`, desktop entry with the
  `${SNAP}` icon, plugs network + gsettings (+ gnome extension set), no linter warnings, no kivy_ui.
- User tested the local snap (`snap install --dangerous`): works.
- **Uploaded to the Snap Store: revision 1 → `latest/beta`** (amd64), passed automated review in ~1 min.
  https://snapcraft.io/caelum. Store listing had no icon: added top-level `icon:` to snapcraft.yaml
  (ships with the next revision). Screenshots must be added on the web listing page.

### Step 8 — store screenshots
- Rendered off-screen at fixed UTC times with a scratch config (`clean_mode` off, all cards on, facing S)
  and the real forecast; per-shot cloud cover and a neutral background for daytime (the overlay is
  translucent, so over black a day sky looks muddy). Set in `data/screenshots/`: **sunset** (lead
  image), **night**, **day**, **settings**, plus dusk. 1920×1080, 176–576 KB each. A rain scene was
  dropped: at 88% cover it still read as blue sky with puffs.
- Settings shot: the dialog's content moved into a `Gtk.OffscreenWindow` and captured with
  `get_pixbuf()`. Off-screen the toplevel's themed background is transparent (labels looked clipped),
  so it's filled with the panel colour sampled from inside the dialog.
- metainfo lists sunset (default), night, day, settings (URLs pinned to the v1.1.0 tag).
- **Bug fixed — cloud-cover badge overlap** (pre-existing): the badge used `_card` at 44 px, whose
  subtitle baseline (`y+h-6` = y+38) sat on the value baseline (y+37), hiding "Lo"; temperature/wind ran
  past the right edge. Own layout now: 210×50 at `W-224` (aligned with the forecast column, which starts
  at y=74), temp/wind beside the percentage, Lo/Mid/Hi on its own row, icon 26 px on the right.
- **Snap Store featured banner** `data/store/banner.png`: 1920×640 (the store requires exactly 3:1;
  min 720×240, max 4320×1440, 1920×640 recommended, PNG/JPEG ≤ 2 MB). Built from the sunset scene in
  clean mode (no cards/compass/labels, facing 230°), cropped to the y=240–880 band, with icon,
  "Caelum" (Ubuntu Sans Light) and the tagline "The real sky, live on your desktop" right-aligned,
  110 px from the edges.

### Step 9 — release 1.1.1 on every channel
- Tagged **v1.1.0 at `aeb08e4`**, the commit embedded in the PPA orig tarball (`git get-tar-commit-id`);
  snap revision 1 has the same app code.
- The badge fix, store icon and screenshots came after those uploads, so everything is released as
  **1.1.1** (`caelum/__init__.py`, `debian/changelog` 1.1.1-1, metainfo release + screenshot URLs → v1.1.1).
- `.deb` 1.1.1-1 built via debian/ (8 tests pass in the build).
- PPA 1.1.1 sources signed and uploaded for noble + resolute (accepted 07:53 UTC, builds queued).
- Snap 1.1.1 built locally in LXD (no NIC-attach problem this time); **revision 2 → beta**, user tested
  it (only harmless GTK messages: atk-bridge is built in; appmenu-gtk-module comes from the host's
  GTK_MODULES), then **promoted to stable**. `sudo snap install caelum` now works.
- **GitHub release v1.1.1** with `caelum_1.1.1-1_all.deb` + `caelum_1.1.1_amd64.snap`; the downloaded
  assets' SHA-256 match the local builds.

### Step 10 — Flathub ruled out; `.flatpak` bundle instead
- Flathub-style build of a manifest pinned to `v1.1.1` (git source + commit) passed **all** linters
  (manifest, builddir, repo), with screenshot mirroring done like Flathub's infra (`flathub-build` itself
  can't run here because of rofiles-fuse, so its command was run by hand with `--disable-rofiles-fuse`
  plus the `ostree commit … screenshots/x86_64` step). The flatpak builder sandbox can't see `/tmp`,
  so builds must run from inside the home directory.
- **Flathub's Generative AI policy blocks the planned submission**: AI agents must not open or automate
  submission PRs or write PR descriptions, commit messages or reviewer replies; "Flathub manifests must
  not contain AI-generated or AI-assisted content"; AI-generated code and packaging must be disclosed and
  may be rejected. Caelum's code and packaging are largely AI-assisted, and the manifest was AI-written.
  Not submitted. A Flathub submission would have to be the user's own work, with disclosure.
- Instead: **`caelum-1.1.1.flatpak` single-file bundle** (3.5 MB, `--runtime-repo` = Flathub, so the
  GNOME 51 runtime installs automatically), built from the v1.1.1 repo. Tested: installs, version 1.1.1,
  runs. Added to the v1.1.1 GitHub release (checksum verified after download); release notes updated.
  `make flatpak-bundle` added; README install table points at the bundle instead of Flathub.
- **PPA 1.1.1 built**: noble 2m46s, resolute 3m04s, both "Successfully built". All channels are now on
  1.1.1: PPA, Snap Store stable (rev 2), GitHub release (.deb, .snap, .flatpak).

---

## Session 13 — Realistic cloud occlusion of the sun and moon (before the APK)

**Problem (user):** the sun and moon very often looked hidden behind clouds while the real sky was
open with a few scattered clouds.

**Cause:** cloud cover was used as a dimmer. The whole sun was faded by the *total* cover
(`1 - (total-10)/75`: 40% → 60% opacity, 50% → 47%), the moon slightly faster, and the sun was drawn
on top of the clouds anyway, so it looked veiled rather than behind a cloud. Cirrus counted like
thick low cloud: 80% cirrus alone left the sun at ~33% and greyed the sky with the overcast sheet.

### Fix — cover is a fraction of sky area; each layer has its own thickness
- New in `caelum/core/sky.py` (no GTK, unit-tested):
  - `cloud_layers()`: (low, mid, high); a total with no layer split counts as mid (moved from window).
  - `opaque_cover()`: light blocked with per-layer opacity low 1.0 / mid 0.7 / high 0.2.
    Used for the sky's grey tint (`sky_color_adaptive`) and the overcast sheet (was `total`).
  - `veil_transmission()`: uniform dimming only from layers that form a continuous sheet:
    cirrus ≤ 15%, altostratus above 60% mid, stratus deck above 70% low. Broken cloud: none.
  - `body_occluders(clouds, seed)`: per hourly slot, low/mid each put a cloud in front of the
    sun/moon with chance = that layer's cover (30% cover → hidden ~30% of the hours).
- `gtk_ui/clouds.py`: `draw_cumulus` / `draw_altocumulus` take `avoid=(x, y, r)` (re-sample any
  cloud that would reach the body's core) and `cover=(x, y)` (a dense cumulus, or a patch of
  altocumulus clumps, drawn across the body). Single-cloud helpers `_cumulus_cloud`,
  `_altocumulus_clump` split out of the loops.
- `gtk_ui/window.py`: sun/moon/planet visibility come from `veil_transmission` (sun ≥ 0.10,
  moon `veil^1.2`, stars and planets `veil^2`). Clouds, rain and silhouette moved out of `_draw_sky`
  into `_draw_weather`, drawn **after** the sun, moon and planets so clouds really pass in front.
  The silhouette now also covers a sun/moon sitting on the horizon.

### Verified
- Off-screen renders (scratch harness, fixed UTC, facing the body) before/after: 60% low cloud,
  80% cirrus only, mid 40 + high 50, 95% overcast, and night with the moon. Sun fully bright when
  clear, behind a lit cloud when covered; cirrus-only now a bright sun through thin streaks;
  overcast unchanged.
- 5 new tests (`CloudOpticsTest`), 13 pass; pyflakes clean.
- Not changed: overcast still looks like big puffs on a grey sheet rather than a uniform deck, and
  the cloud pattern is reshuffled hourly (no drift yet). Both are candidates for the next step.

### Drifting clouds (replaces the hourly reshuffle and the occluder roll)
- **Cloud field** (`gtk_ui/clouds.py`): each layer is a fixed pool of clouds on a wrap-around strip
  `STRIP` = 4 screens wide, seeded per cloud (`'low:7'` …), so cover only sets *how many* of the
  pool are shown. A weather update adds/removes clouds; it never reshuffles the sky. Pool positions
  and band slots are `lru_cache`d.
- **Wind drift** (`window._advance_cloud_drift`): per-layer offsets integrate
  `side × wind × deg_per_ms / 240°` each frame (`_CLOUD_DRIFT` low 0.020 / mid 0.012 / high
  0.007 °/s per m/s: higher = farther = slower across the view). `side` = sin(wind_to − facing),
  at least ±0.25 so wind toward/away from you still moves something; wind ≥ 1.5 m/s (winds aloft
  are rarely calm); dt capped at 1 s so there is no jump after suspend. Initial offsets come from
  the wall clock, so each start doesn't show the same sky. 5 m/s → a low cloud crosses the sun in
  ~6–8 min.
- **Band past the sun/moon** (replaces `body_occluders` + avoid/cover): calibrating the general
  clouds so drawn area = cover would need dozens of cumulus per screen (measured: 8/screen covers
  ~17% at 60% cover). Instead `core.sky.band_slots()` puts fixed slots every ~one cloud width
  (low 0.14 W, mid 0.08 W) on the strip at the body's height, each shown with chance = cover; as
  the band drifts the body is hidden that share of the time. Band clouds fade out within
  1.5 (low) / 1.0 (mid) pitches of the body, so they never show as a row. Slots are stable:
  more cover only adds slots (tested).
- **Performance — cloud layer cached** (`_draw_clouds` → `_render_clouds`): the app redraws at
  10 Hz and was already **~123 ms/frame at 1920×1080** (software Cairo, mostly fills: clouds and the
  full-screen body glow), i.e. CPU-bound before this session. Drift is ~1 px/s, so the cloud layer
  (sheet, layers, glow) is rendered into a `create_similar` surface and re-rendered only when the key
  changes: size, weather dict/ts, drift snapped to whole pixels, sun elevation in 0.25° steps, body
  position in px. Steady state now **18–33 ms/frame** (same harness, same scene, old code 123 ms).

### Verified (drift)
- Time-lapses (frame every 4 min, 5 m/s wind from the east): 60% low, a cloud slides over the sun
  for ~15 min, then clear; 30% low, sun clear the whole 32 min; mid 40 + high 50, small clumps pass
  the sun without hiding it; night 60%, a cloud drifts in and covers the moon.
- 14 tests pass (band coverage share ≈ cover, cover change keeps existing slots); pyflakes clean.
- Still open: overcast as a uniform deck; general cumulus stay near the horizon (only the band
  reaches the sun's height).

### Overcast deck and altostratus sheet (replaces `_draw_overcast_sheet`)
- Before: above 65% *total* a translucent grey gradient (max alpha 0.52) with the usual white puffs
  on it, so 95% overcast read as fair-weather clouds on a grey sky.
- `core.sky.overcast_deck()`: 0 → 1 as opaque cover goes 65% → 95% (cirrus never closes it);
  `mid_sheet()`: 0 → 1 as mid cover goes 60% → 100% (also used by `veil_transmission`).
- `clouds.draw_deck()`: stratocumulus/stratus ceiling seen from below — a desaturated grey base
  (`deck_colour()` from the cloud palette, so sunset/night tint it), darker overhead and paler toward
  the horizon, alpha `0.92·deck^1.2` (fades in continuously); rows of flat cells, darker thick
  cores with a pale rim, shrinking toward the horizon (perspective), far rows blended.
  The cells are painted once into a seamless texture (wrap copies at ±W, cached on size, deck
  strength and colour) that slides with the low-layer drift. Per-row parallax was dropped for this:
  at < 1 px/s it wasn't visible, and painting ~900 cells per drift step cost ~150 ms.
- `clouds.draw_mid_sheet()`: altostratus, a smooth pale sheet with no cells, alpha `0.70·sheet^1.2`;
  the sun shows as a dim "ground-glass" disc (veil) through it.
- `_render_clouds` order: cirrus → altocumulus → mid sheet → deck → cumulus. Layers above the deck
  fade with `1 − deck`; altocumulus also with `1 − 0.85·sheet`; cumulus puffs (white sunlit tops,
  not seen from under a ceiling) with `1 − deck²`. New helper `_draw_faded` (push_group +
  paint_with_alpha).

### Verified (overcast)
- Renders: low 80% (thin deck forming, puffs still distinct), low 95% and low 100% + rain (grey
  ceiling with cells, sun as a diffuse bright patch), mid 100% (pale sheet, dim sun disc), low 95% at
  sunset (warm-tinted deck) and at night with the moon (dark deck, soft moon glow).
- 1920×1080 overcast: full cloud re-render on a drift step 256 → 80 ms after the deck texture
  (happens ~every 1.5 s at 4 m/s); cached frames ~27 ms.
- 16 tests pass (deck/sheet thresholds); pyflakes clean.

### Planets no longer drawn in daylight
- Before: planets were drawn whenever above the horizon (only clouds hid them), so Venus and Mercury
  sat next to the noon sun.
- `core.sky.limiting_magnitude(sun_el)`: faintest naked-eye magnitude, interpolated through
  (sun el °, mag) = (10, −4.6) (0, −3.5) (−3, −1.5) (−6, 1.0) (−9, 3.0) (−12, 4.5) (−18, 6.0).
  `naked_eye_visibility(mag, sun_el)` fades an object in over one magnitude past that limit.
- `_draw_planets(…, sun_el)` multiplies glow, disc, Saturn's ring and label alpha by it (planet
  magnitudes are the fixed `_PLANET_MAG` values). Result: none in daylight; around sunset Venus
  (−4.0) first, then Jupiter (≈ −2° sun), Mars (≈ −4°), Mercury/Saturn (≈ −6°…−7°).
- Verified: clear-sky renders 12:00 → 18:45 UTC facing the sunset: no planets at noon or sunset,
  Mercury fades in at −6.3°, stars follow. 2 new tests (none in daylight, twilight order); 18 pass.

### Low clouds in perspective across the whole sky (replaces near-horizon cumulus + low band)
- Before: general cumulus were drawn only 0.54–0.70 H (2°–25° up), so at high cover the middle of
  the sky was empty except the band of clouds drifting past the sun.
- **Model** (`core.sky`): cumulus are objects on a flat layer `LOW_BASE_KM` = 1.5 km up, positions in
  km east/north on a `LOW_TILE_KM` = 50 km tile that wraps. Sizes 0.6 km + exp(mean 0.9) (≤ 4 km),
  thickness 45–80 % of the size; pool seeded per cloud and grown lazily. `low_cloud_count(cover)` =
  −ln(1 − cover)·tile² / mean footprint, so overlapping footprints cover exactly `cover` of the layer
  (tested: random sight lines blocked 20/50/80 % ± 6). More cover only adds clouds (tested).
  `plane_to_sky(x, y, h)` gives elevation/azimuth.
- **Drawing** (`clouds.draw_cumulus`): clouds within `LOW_NEAR_KM` = 12 km, far to near, projected:
  width from azimuth span (size / horizontal distance), height from the near/far edge of the base and
  the tower top; the cumulus shape is fitted inside that extent. Beyond 12 km (< 7° up)
  `_distant_bank`: soft flat lumps fixed to azimuths, filled `1 − (1 − cover)^4` (perspective packs
  distant clouds together). Specks < 1.2 % W are left to the bank.
- **Look**: `side` (from mean elevation, 12° → 42°) blends a side view (flat dark base, sunlit
  white cauliflower, highlight) into a view from below (grey shaded underside, no base line or sunlit
  top). Puffs get a fixed-width edge (`_soft_puff(edge=1.2 % W)`) so big clouds stay crisp; big clouds
  get up to 3× more, smaller puffs; distant ones are one compact lump and fade into haze (−55 % at
  12 km). Each cloud is composited as one shape (push_group clipped to its box, then
  `paint_with_alpha`), so overlapping puffs don't show as translucent lobes. Cumulus opacity
  0.78–0.95 (was 0.48–0.90).
- **Motion**: the layer is carried bodily by the wind (`_low_offset` km, wind at cloud base =
  1.5 × surface, `_LOW_WIND_FACTOR`), so overhead clouds move fast, distant ones slowly, and clouds
  approach or recede when the wind blows along the view. The sun/moon is now hidden by geometry alone;
  the low band (`_LOW_PITCH`) is gone (the mid-level band stays).
- **Performance**: cloud cache now rendered at **half resolution** and upscaled (bilinear); the deck
  texture is built at that device scale. Redrawn at once on scene changes (size, weather, facing —
  now in the key since clouds are fixed to azimuths —, sun/moon), and for motion at most once per
  second (drift snapped to half-res px, low offset to 8 m). `_draw_faded` skips layers under 2 %
  (95 % cover was drawing ~380 invisible cumulus). 1920×1080 full cloud redraw: 46 / 61 / 126 / 194
  / 42 ms at 10 / 30 / 60 / 80 / 95 % low cover; cached frames 22–30 ms.

### Verified (perspective clouds)
- Full-res renders at 10–95 %: overhead grey-bottomed clouds, white side-lit cumulus toward the
  horizon, a distant bank on it; 30 % leaves the upper sky mostly clear; 80 % blends into the
  forming deck; overcast/altostratus/sunset/night unchanged.
- Time-lapse 60 %, 3-min steps: sun clear in 4 of 9 frames; night 60 %: clouds cross the moon.
- 21 tests pass; pyflakes clean.

### Release 1.2.0 (2026-10-25)
- Version bump: `caelum/__init__.py` 1.2.0, `debian/changelog` 1.2.0-1, metainfo `<release>` with
  notes; screenshot URLs pinned to the `v1.2.0` tag.
- **Store screenshots re-rendered**: the 1.1.1 `day.png` (veiled sun at 55 %, Venus/Mercury in
  daylight) and `sunset.png` showed exactly what this release fixes. Re-rendered off-screen
  (scratch harness: `SkyTracker` with window/network stubbed, fixed UTC) with the same composition
  (all cards on, facing S, Lomé, cover 55 % Lo35/Mid40/Hi25 at 10:00 and 45 % Lo25/Mid35/Hi20 at
  17:35) and the live MET/Open-Meteo forecast, dated 2026-10-25 so the forecast weekdays match.
  `night.png` (0 % cover) and `settings.png` are unaffected and kept. `dusk.png` stays unused.
- **Builds**: `.deb` 1.2.0-1 (8 tests pass in the build). Snap: the first `snapcraft pack` reused
  stale part state and produced **`caelum_1.1.1_amd64.snap`** although the tree was 1.2.0; after
  `snapcraft clean caelum` it packed `caelum_1.2.0_amd64.snap` (checked `meta/snap.yaml` and
  `caelum/__init__.py` inside). The shell lacked the `lxd` group (socket "permission denied") though
  the user is a member: `sg lxd -c "snapcraft pack"`. No veth/IPv4 trouble this time.
  Flatpak bundle `caelum-1.2.0.flatpak` (207 KB; 1.1.1's 3.5 MB came from the Flathub-style build
  with mirrored screenshots), installed over the user's 1.1.1 test install: runs 1.2.0.
- **GitHub release v1.2.0** with the .deb, .snap and .flatpak; downloaded assets' SHA-256 match.
- **PPA**: 1.2.0 sources signed and uploaded for noble + resolute; accepted, builds started.
- **Snap Store**: revision 3 → beta; user tested it → **promoted to stable**.
- **PPA 1.2.0 built**: noble and resolute both "Successfully built" (~3 min each, started 09:38 UTC).
  Gotcha: this time **both** API endpoints (`api.launchpad.net` and `launchpad.net/api/devel`) kept
  reporting "Currently building" 20 min after the builds had finished; the build web pages
  (`…/+archive/ubuntu/caelum/+build/<id>`) were correct. All channels are now on 1.2.0.

### Version shown in Settings and `caelum --version` (unreleased)
- **`caelum --version` / `-V`** prints `Caelum X.Y.Z` and exits; `--help` also works. `main()` in
  `gtk_ui/app.py` parses args with argparse before any window is made, so it works from the installed
  `caelum` gui-script, `python3 -m caelum` and the snap's `bin/caelum` launcher.
- **Settings dialog**: a small dim, selectable "Caelum X.Y.Z" label under the hint at the bottom,
  from `caelum.__version__`. Checked with an off-screen dialog screenshot.
- Motivation: the user had no easy way to tell which build (local .deb 1.0.1, PPA, snap, flatpak) was running.

### Fresh weather right after suspend/hibernate (unreleased)
- **Symptom** (user): after waking the PC the sky kept the pre-sleep weather for up to 15 min / 1 h.
- **Cause**: `GLib.timeout_add` runs on the monotonic clock, which Linux stops during suspend and
  hibernate, so the 15 min (Open-Meteo) and 1 h (MET Norway) timers resumed where they had paused.
  Also, a fetch fired while the network was still down returned `None` and nothing retried until the next
  full interval.
- **Fix** (`gtk_ui/window.py`): the two weather timers are replaced by `_watch_weather` (every 5 s)
  with **wall-clock due times** per source (`_due`, `_REFRESH`).
  - **Resume detection**: when the wall clock advanced >60 s more than the monotonic clock between two
    checks (`_SLEPT`), `_on_resume` makes both sources due now, drops the astro and cloud caches, and
    exports the lock-screen/wallpaper image at once. Once the fresh weather lands it exports again
    (`_export_pending`).
  - **Failed fetch**: back-off retry 15 s → 30 s → 1 min → 2 min → 5 min (`_RETRY`) instead of waiting a
    full interval.
  - **Network back**: `Gio.NetworkMonitor` `network-changed` makes any failing source due immediately.
- **Verified**: scratch harness with stubbed fetches. Startup fetches both; nothing refetches 5 s later.
  A simulated 3 h sleep with the network down → both refetched, retry in 15 s, wallpaper exported. Network
  back → both fetched, next in 900/3600 s, exported again. Live 10 s run fetched real data with no failures.
  21 tests pass, pyflakes clean.

### Click-through to the desktop (unreleased)
- **Symptom** (user): with Caelum running you can't use the desktop (icons, right-click menu, drag & drop).
- **Cause**: the overlay is a full-screen window that takes every click. GNOME on Wayland ignores the
  `DESKTOP` type hint, so it is an ordinary window stacked above the DING desktop-icons window.
- **Fix**: `SkyTracker._update_input_region` (called at the end of each draw) sets the window's input shape
  with `Gtk.Widget.input_shape_combine_region`. Only these take input: the gear (44 px box), the compass
  (manual mode only), and the weekly forecast day cards (not in clean mode). Every other click reaches
  whatever is below. The region is reapplied only when the rects change. It works on X11 and on Wayland
  (`wl_surface.set_input_region`).
- **Trade-off**: constellation hover names and right-click-anywhere need input over the whole sky. New
  setting **"Click Through to Desktop"** (`click_through`, default on; fr/es/de/pt strings). Turn it off
  to get the old behaviour. Keyboard shortcuts work once Caelum has focus (click the gear, compass or a card).
  The Settings hint and README no longer say "right-click".
- **Verified**: live run with default config: 9 rects (gear, compass, 7 day cards). Clean mode → 2.
  Switch off → region reset to the whole window. 21 tests pass, pyflakes clean. Whether clicks actually
  pass through on the user's GNOME Wayland desktop is still **to be confirmed by the user**.

### Explore mode: constellation names with click-through on (unreleased)
- User asked to get hover names back after clicking the compass or a card.
- A click on the compass or a forecast day card calls `_start_explore`. For `_EXPLORE_IDLE` (20 s) the
  input region is dropped, so the whole sky takes input again (hover names, right-click → Settings).
  Each pointer motion over the sky extends the deadline. Explore mode ends when the deadline passes,
  on a left click on empty sky (consumed; it also deselects the day), or on Esc. The 100 ms tick
  redraws, and `_update_input_region` restores the control rects within a frame.
- While it is active, a pill left of the gear says "Exploring the sky · click empty sky or Esc to return to
  the desktop" (fr/es/de/pt). This tells the user why the desktop isn't responding.
- **Verified** (live run, pointer motion stubbed out, idle shortened to 3 s): 9 rects → card click →
  whole window, day selected → idle → 9 rects. Explore + empty-sky click → 9 rects. Hint rendered and
  checked. 21 tests pass, pyflakes clean. Note: in a live run a real pointer moving over the window
  keeps explore mode on, which is the intended behaviour.

### Opaque sky option (unreleased)
- **Why**: the sky overlay is translucent: 6–20 % alpha by day, 50–72 % at night. The wallpaper
  therefore sets most of the daytime look. Renders over six wallpapers showed no static wallpaper works all
  day: black → black noon; bright blue → blue night; white → washed out. Dark navy is the best compromise
  but gives a dim noon. The wallpaper/lock-screen export rendered over black, so its noon was black too.
- **`core/sky.py` `opaque_sky(el, clouds, m_bright)`** → (zenith, horizon, ground top, ground bottom).
  - Keyframes by sun elevation (`_OPAQUE_SKY`, −18° … 50°): near-black night; violet/rose twilight
    horizon; warm horizon at ±2°; blue day zenith with a hazy pale horizon.
  - Clouds grey it out by `0.95·opaque_cover²`: blue sky stays between scattered clouds, and a closed
    deck turns grey as bright as the daylight.
  - Moonlight lifts the night a little.
  - Ground below the horizon (0.72 H) is a darkened, greener version of the horizon colour.
- **`_draw_sky`** paints that gradient fully opaque under the usual translucent tint when
  `opaque_sky` is on (new switch "Opaque Sky", default off, fr/es/de/pt). The tint, horizon effects,
  stars, clouds and silhouette are unchanged on top.
- **Export** (`_render_frame_to_surface`) always uses it (`_exporting` flag) instead of painting black
  first, so the exported wallpaper/lock screen now has a proper daytime sky.
- **Verified**: 5 new tests (brightens monotonically with the sun; clear day blue with paler
  horizon; night near-black; overcast day grey; full moon lifts the night). 26 tests pass, pyflakes clean.
  Rendered 8 scenes (noon clear/30 %/overcast, golden hour, sunset, dusk, night, night 60 %) over a
  white wallpaper: none of it shows through.
- **Opaque sky on by default** (user's choice). `load_config` fills missing keys from `DEFAULT_CONFIG`,
  so existing installs switch to it too on upgrade. They can turn it off in Settings.
- **No bundled wallpaper**: with the opaque sky on, the wallpaper only shows in the Activities overview
  and when Caelum isn't running. The existing export ("Desktop background") already sets the wallpaper
  to Caelum's own sky every 5 min, and with the opaque sky it now has a proper day sky. A static image
  would be wrong for most of the day. README points to the export instead.

### Release 1.3.0 (2026-10-25)
- Contents: version in Settings + `--version`; weather refresh after suspend; click-through; explore
  mode; opaque sky (on by default; export always opaque).
- Version bump: `__init__.py`, `debian/changelog` 1.3.0-1, metainfo release notes, and screenshots pinned
  to `v1.3.0`. `appstreamcli validate` passes.
- Screenshots: `day.png` and `sunset.png` re-rendered with the opaque sky over the real forecast (scratch
  `shots.py`, which now also takes a night shot). `night.png` kept: the new 21:00 full-moon render was
  washed out, and the old 02:30 dark sky looks the same with the opaque sky. `settings.png` kept.
- **Builds**: `.deb` 1.3.0-1; snap after `snapcraft clean caelum` → `caelum_1.3.0_amd64.snap`
  (`meta/snap.yaml` and the bundled `__init__.py` both say 1.3.0); flatpak bundle 217 KB, installed and
  `flatpak run … --version` → "Caelum 1.3.0".
- **GitHub release v1.3.0** with the .deb, .snap and .flatpak; downloaded assets' SHA-256 match.
- **PPA**: 1.3.0 sources signed and uploaded for noble + resolute.
- **Snap Store**: revision 4 → beta, waiting for the user's test before promoting to stable.

### Settings dialog redesign (unreleased)
- **Why**: the user couldn't find the "Opaque Sky" switch (they wanted their own wallpaper back). The
  dialog was one long column of ~30 controls with few headings, and the new switch sat unexplained between
  Clean Mode and Click Through.
- **New layout** (`gtk_ui/settings.py`): a header bar with a `Gtk.StackSwitcher` and four tabs:
  - **Sky**: Background (Opaque Sky), Sky Features (constellations, silhouette, rainbow, aster size).
  - **Display**: Overlay (active, clean mode, click-through), On-screen Widgets, Visible Cards. The card
    list is greyed out while the info cards are off (`bind_property`).
  - **Location**: detect / lat / lon / timezone + Save & Apply (suggested-action); Facing & Compass.
  - **System**: General (language, autostart), Wallpaper (export), About (version, weather sources).
- Each group is a titled boxed `Gtk.ListBox` in a frame, with separators (GNOME-settings style). Helpers
  are `_group`, `_row` (title + dim subtitle, widget at the right or stacked below), `_page` and
  `SettingsDialog._switch(key, default)`, which replaces ten copies of the switch boilerplate.
  Subtitles explain the non-obvious switches. For Opaque Sky: "Off: your own wallpaper shows through,
  lit and tinted by Caelum".
- Rows aren't focusable, so there's no focus ring round the first row; switches stay keyboard-reachable.
  The dialog reopens on the last tab used (`parent._settings_page`). Size 440×640, resizable.
- **i18n**: 21 new strings in fr/es/de/pt/it. Also added the Italian strings 1.3.0 missed (Opaque Sky,
  Click Through, the explore hint).
- **Verified**: screenshots of all four tabs in English and French. Programmatic check: the Opaque Sky
  switch updates `cfg`, saves once and redraws; the tab is remembered across reopen. 26 tests pass,
  pyflakes clean. `data/screenshots/settings.png` is still the old dialog; update it at the next release.

### Photo landscapes along the horizon (released in 1.4.0)
- **Request**: replace the dark horizon band with a green plain with a few trees. Also offer mountains
  and the sea, using real images rather than drawings.
- **Source**: Poly Haven 360° panoramas, **CC0**, so they are fine for Debian/PPA, snap and flatpak.
  Unsplash/Pexels-style licences are not. Out of 997, picked for clear skies (clean cut-out) and fit:
  - `noon_grass` (Greg Zaal): green field ringed with trees.
  - `alps_field` (Andreas Mischok): meadow in an Alpine valley.
  - `spiaggia_di_mondello` (Andreas Mischok): sandy beach, open sea, pines, headlands.
  The thumbnails are camera renders, not panoramas, so I chose from contact sheets of the 8K tonemapped
  JPEGs' horizon bands.
- **`packaging/make-landscapes.py`** (dev-only: numpy + Pillow): downloads the panorama, keeps
  +top°…−40° at 3600 px wide (10 px/°), and cuts the sky out:
  - Sky probability: blue leading and bright enough (`b_min`), or pale low-saturation haze.
  - Then a per-row sky colour model learnt from sure-sky pixels (`tol`), which catches the pale sky
    near the horizon.
  - A skyline per column from the top (first run of ≥ 3 ground pixels, never below the horizon).
  - A 1-D grey opening (9 px, wrapping) drops cloud wisps and poles.
  - Sky-coloured pixels above the horizon become holes (sky through canopies).
  - Mask eroded 1 px then blurred 0.8 px: no pale rim when darkened.
  - Per-photo tuning: the Alps need `b_min` 0.62 and `tol` 0.04, because hazy blue-grey cliffs are close
    to the sky colour; at the defaults the central massif lost its top half.
  - `top` = tallest feature + 2° (38°/30°/28°). Output: `<name>.jpg` (q82), `<name>-mask.png`
    (opacity in the alpha channel, which is how cairo reads it), `landscapes.json`. ~2 MB in total.
- **`gtk_ui/landscape.py`** (as first written; the relight was later reworked, see Release 1.4.0): the
  photo and mask become one premultiplied ARGB surface. `render()` maps
  screen → photo with a single cairo pattern matrix. Columns follow azimuth through `sky_to_screen`'s
  constants, wrapping the panorama with `Extend.REPEAT`. Rows follow elevation. `south` is the panorama
  column facing south. Then relighting: HSL_SATURATION towards grey (night vision) and MULTIPLY by the
  light colour, both masked by the photo's own alpha so the sky stays untouched. Two transparent rows
  above the photo stop the repeating pattern blending ground into the top edge; that showed as a grey
  line across the sky.
- **`core/sky.py` `landscape_light(el, clouds, m_bright)`** → (rgb multiplier, saturation). Keyframes
  run from −12° to 16°: full sun → warm low sun → violet twilight → dark night. Overcast dims by up to
  40 % and cools. Moonlight lifts the night. Saturation fades to 0.15.
- **Window**: `_draw_landscape` replaces the silhouette as the last layer of `_draw_weather`, so the sun,
  moon and clouds go behind real trees and mountains. It is cached per (size, facing, light quantised to
  1/64, saturation to 1/32). Cost: +2 ms per cached frame at 1080p; a re-render is 62 ms, only when the
  light changes. If the files are missing it falls back to the drawn hills.
- **Config**: `landscape` = plain (default) | mountains | sea | hills | none, replacing
  `show_silhouette`. Migration: an old config with the silhouette off gets `none`.
- **Settings**: Sky tab → Background → "Landscape" combo with "Real photos, relit by the sun and moon".
  It lists only the photos actually installed. The Horizon Silhouette switch is gone. fr/es/de/pt/it strings.
- **Packaging**: pyproject `package-data` (covers .deb/PPA via pybuild and flatpak via pip; checked the
  .deb ships all 7 files); snap installs `caelum/data` explicitly; `debian/copyright` CC0 stanza;
  README credits.
- **Verified**: renders of all three landscapes at noon / golden hour / sunset / moonlit night;
  the Sky tab screenshot; the migration (silhouette off → none, on → plain); 8 new tests (lighting
  model, shipped data complete and covering the screen). 34 tests pass, including inside the
  .deb build; pyflakes clean.
### Release 1.3.1 (2026-10-25)
- The user asked to release every version in turn: 1.3.0 (snap promoted to stable, rev 4), then 1.3.1
  (Settings redesign only), then 1.4.0 (landscapes).
- 1.3.1 is built from branch `release-1.3.1` at `017cb4a` (the Settings commit). Master already had the
  landscapes on top. The branch is merged back into master afterwards.
- Version bump: `__init__.py`, `debian/changelog` 1.3.1-1, metainfo release notes, screenshots pinned
  to `v1.3.1`. `settings.png` is now the new dialog (Sky tab, captured from this code) over
  `night.png`, the same composition as before.

### Release 1.4.0 (2026-10-25)
- Photo landscapes, on master after the 1.3.1 merge.
- **Night-time rim fix found while making the screenshots**: the moonlit night showed pale outlines
  around the tree canopies and the holes in the leaves. Cause: the relight was MULTIPLY masked by the
  photo's alpha, so a half-transparent edge pixel got only half the darkening and stayed brighter
  than both the dark ground and the night sky.
  - Darkening the edge colours in the generator (min-filter near the cut) did not remove the rim, and
    it left blotchy dark edges in daylight. Reverted.
  - Fix in `gtk_ui/landscape.py`: the photo stays opaque (RGB24) and the cut-out is a separate
    surface. `render()` paints the photo, desaturates and multiplies with plain paints, then applies the
    cut-out last with DEST_IN through the same pattern matrix. Edges are now darkened exactly like the
    rest; the day render is unchanged. Re-render cost 53 ms (was 62).
- New screenshots: day, sunset and night with the plain landscape. `settings.png` is the Sky tab
  with the Landscape row, over the new night shot. Metainfo captions updated, URLs pinned to `v1.4.0`.
- Version bump: `__init__.py`, `debian/changelog` 1.4.0-1, metainfo release notes.
- **Released**:
  - GitHub `v1.4.0` with the deb, snap and flatpak; the downloaded assets' SHA-256 match the local builds.
  - The deb and snap both ship all 7 landscape files. Flatpak installed locally reports 1.4.0 and has them.
  - PPA 1.4.0-1 uploaded for noble and resolute.
  - Snap revision 6 → **beta**. 1.3.1 (rev 5) is also beta-only. Stable stays at 1.3.0 (rev 4)
    until the user tests the beta.
- The user tested the beta. Snap rev 5 (1.3.1), then rev 6 (1.4.0), promoted to **stable**.
- **Next release**: rework the rain rendering, especially so it fits the landscapes and the new
  opaque background (the user's request).

### Rain and snow reworked for the landscapes (released in 1.5.0)
- **Request**: improve the rain, especially with the photo landscapes and the opaque sky.
- **What was wrong** (renders of plain/mountains/sea at day, dusk, night, plus snow):
  - Rain was 1 px bluish ticks re-scattered at random 8 times a second, so it flickered rather than fell.
  - It was drawn before the landscape, so trees and mountains hid all of it.
  - Rain didn't change the scene: distant mountains stayed sharp and rain clouds looked like dry overcast.
  - Lightning flashed the whole screen, landscape included, for any rain above 4 mm/h.
  - Snow was a few static specks.
- **New `gtk_ui/precip.py`**:
  - **Depth layers**: one far rain layer falls behind the landscape; mid and near layers fall in front.
    Each layer has its own speed, streak length, width and opacity. Positions follow the clock, so
    drops fall continuously.
  - **Performance**: each layer is drawn once into an alpha-only (A8) tile, a screen wide and half a
    screen high, seamless both ways. Each frame scrolls it with whole-pixel offsets and a NEAREST
    filter. Re-stroking ~1,600 lines every frame cost 35 ms. A fractional offset with the default
    filter cost even more (pixman's slow path). Now rain adds ~7 ms to a frame at 1080p; the far
    layer is 2 ms.
  - **Wind**: `rain_slant` takes the wind component across the view, so a head or tail wind falls
    straight.
  - **Drop colour**: based on the horizon sky colour, made a little paler. Drops show against the
    sky and more so against the ground. They are dark at night and pale by day.
  - **Veil**: after the landscape, a haze in the horizon-sky colour. It is thickest at the horizon,
    reaches up over the mountain tops and thins towards the foreground. Strength is min(1.7 ×
    intensity, 0.85), or 2.2 × for snow, so 2 mm/h already hides most of a distant mountain.
  - **Rain shafts**: under a broken sky (deck < 0.92), up to 3 grey curtains hang from the cloud base
    to the horizon at azimuths fixed for the hour, so they turn with the view and lean with the wind.
  - **`Storm`**: only for thunderstorm codes (WMO 95–99). The sky flashes in 2–3 decaying pulses
    about every 7–12 s, half the time with a jagged bolt. It is drawn before the landscape, which
    stays a dark silhouette.
  - **Snow**: three layers of flakes that drift with the wind and sway. They are bigger and more
    numerous, coloured from the horizon sky towards white, with a whiter veil.
- **Scene**:
  - Rain clouds darken: deck and cumulus undersides −38 % and tops −15 % at full intensity.
  - `landscape_light` darkens wet ground by up to 15 % (full at 2 mm/h).
- `precip_intensity` and `rain_slant` live in `core/sky.py` so they can be tested without cairo.
  The old `_draw_rain` is gone. 4 new tests (38 in total); pyflakes clean.

### Security review and fixes (released in 1.5.0)
- **Question**: does the app put its users at risk? I reviewed every network call, file write,
  D-Bus/device access and the packaging permissions.
- **Already sound**:
  - No subprocess, shell, `eval` or pickle anywhere; network replies and the config are parsed as JSON only.
  - It writes only its config, the exported wallpaper PNG in the cache dir, and the autostart entry.
    The autostart entry is built from the app's own path, never from network data.
  - The snap is strict (`network`, `gsettings`); the flatpak has network, display and dri, with no
    filesystem access.
  - Key events are only seen while Caelum has focus, and nothing is logged.
- **Fixed**:
  1. Detect location used **plain-HTTP** `ip-api.com`, whose free tier has no TLS. Anyone on the
     network path could read the request or forge the reply. The forged timezone name would then go
     unescaped into `set_markup`, i.e. Pango markup injection.
     - New `core/geoip.py`: ipwho.is over HTTPS, with ipapi.co as fallback.
     - Replies are validated: numeric lat/lon in range, offset within ±14 h, timezone name capped at
       64 characters. Otherwise the reply is rejected.
     - The name is escaped before display.
  2. Coordinates went to Open-Meteo, MET Norway and Nominatim with 4 decimals (~11 m: a house).
     `core/net.coord()` now rounds to 2 decimals (~1 km). Checked live: same weather, and Nominatim
     still says "Lomé, Togo".
  3. The compass status label (which can carry serial exception text) is now escaped too.
  4. New **`core/net.get_json`**: refuses non-HTTPS URLs, sends the versioned User-Agent everywhere,
     and caps replies at 4 MB. All 4 lookups use it. `urllib`/`json` are gone from the GTK modules.
  5. **`make checksums`** writes `dist/SHA256SUMS` for the deb, flatpak and snap. It was uploaded to
     the v1.4.0 release (hashes match the assets), and the README tells users how to check.
  6. The "phone compass URL" feature no longer exists in the app. I removed `compass_bridge.py`, its
     README section (which told users to open PhyPhox's unencrypted remote access), and the stale
     snap/flatpak permission comments.
  7. README: services listed, plus a Privacy note (HTTPS only, 2-decimal coordinates, no statistics).
- 7 new tests (`tests/test_net.py`): rounding, HTTP refused, both geo-IP parsers and their
  rejections. 45 pass; pyflakes clean.

### Release 1.5.0 (2026-10-25)
- The rain/snow rework and the security fixes.
- New store screenshot `rain.png`: mountains, 3 mm/h, wind across the view, forecast column shown.
  Rendered off-screen like the 1.4.0 ones. Other screenshots unchanged; URLs pinned to `v1.5.0`.
- Version bump: `__init__.py`, `debian/changelog` 1.5.0-1, metainfo release notes.
- First release with `SHA256SUMS` among the assets (`make checksums`).
- **Released**:
  - GitHub `v1.5.0` with the deb, snap, flatpak and `SHA256SUMS`; the downloaded assets pass `sha256sum -c`.
  - The deb build ran the 45 tests. The deb and snap contain the landscapes, `precip.py`, `geoip.py`
    and `net.py`. The flatpak installed locally reports 1.5.0.
  - The source tarball has no `compass_bridge.py` or `config.json`.
  - PPA 1.5.0-1 uploaded for noble and resolute.
  - Snap revision 7 → **beta**; stable stays at 1.4.0 (rev 6) until the user tests it.

### Snap updates while Caelum runs (unreleased)
- **Problem** (the user, testing the 1.5.0 beta): `snap refresh caelum --beta` failed with
  `cannot refresh "caelum": snap "caelum" has running apps (caelum)`. Because of snapd's refresh
  app awareness, a running app also holds back the automatic updates (up to 14 days). Caelum runs
  all session long, so it was effectively never updated in the background.
- **Fix**: `refresh-mode: ignore-running` on the app in `snapcraft.yaml`. snapcraft accepts it for
  non-service apps. snapd then refreshes while Caelum runs; the running process keeps its own
  revision, which snapd retains.
- The confined app can't relaunch itself: executing `/snap/bin/caelum` (→ `/usr/bin/snap`) gives
  "Permission denied" inside the sandbox, checked with `snap run --shell caelum`. So:
  - `sandbox.installed_update()` compares `/snap/caelum/current` with `$SNAP_REVISION`. If they
    differ, it reads the new version from `meta/snap.yaml`.
  - `_check_update` runs every minute. When there is an update, a pill next to the gear says
    "Caelum 1.5.1 is installed · restart Caelum to use it". It uses the same `_draw_hint` as the
    explore pill, which wins while exploring; fr/es/de/pt/it strings added. It is not drawn into
    the exported wallpaper.
  - Autostart picks up the new revision at the next login anyway.
- Checked: the logic with faked revisions (same rev → None, newer → '1.5.1', not a snap → None)
  and a render of the pill. The real refresh path can only be checked once a build with this
  setting is installed: snapd reads `refresh-mode` from the installed revision, so the update *to*
  this version still needs Caelum closed one last time.

### Rain on screen but not outside (unreleased)
- **Report** (25 Oct, ~13:15 UTC, Lomé): the app showed rain, but outside it was dry.
- **Data at that moment**:
  - Open-Meteo `current` (15-minute estimate of now): 95 % cloud, 0 mm, WMO 3 (overcast). Its next
    hour, in 15-minute steps, was dry too.
  - MET Norway: `next_1_hours` of the 13:00 step said **heavyrain, 1.0 mm**, from a run updated
    at 11:18; dry from 14:00.
- **Cause**: `merge_weather` took the *larger* precipitation of the two sources and preferred MET's
  weather code. So a two-hour-old forecast of rain for the coming hour overrode a fresh "dry now".
- **Fix**: rain, snow and the weather code for *now* come from Open-Meteo whenever it answered;
  MET fills them in only when Open-Meteo is unreachable. MET still provides temperature, humidity,
  wind and all the forecast cards. Neither source observes anything in Togo (no radar or gauges
  in the feed; both are models), but Open-Meteo's is the fresher estimate.
- `tests/test_weather.py` (4 tests, the first being the 25 Oct case): 49 pass.
  Live check after the fix: 0.0 mm, WMO 3, cloud 92 %.

### Rain from real observations: nearest airport, then MET Norway (unreleased)
- The user disagreed with the previous fix: Open-Meteo is not accurate for rain, and they wanted
  MET Norway's *real* data, not its forecast.
- **Checked**:
  - MET's radar-based Nowcast 2.0 answers HTTP 422 for Lomé; it covers the Nordic countries only
    (OK for Oslo).
  - `locationforecast`'s `instant` block (temperature, pressure, cloud, humidity, wind) has no
    precipitation. Rain only exists there as `next_1_hours`, a forecast.
  - So MET has no measured rain for Togo.
  - The real observation available is **METAR** from Lomé airport (DXXX), every
    30 min, free, no key, through aviationweather.gov's API.
  - Today 07:30–13:00 it reported no rain and FEW017. Both models said ~95 % cloud.
  - The 13:00 report was garbled: two METARs run together, `Q110`.
- **The user chose**: the airport observation first; without one, MET Norway; Open-Meteo last.
- **New `core/metar.py`**:
  - `fetch_metar` queries a ±0.3° box around the rounded coordinates. It returns `[]` when there is
    no station and `None` on network failure, so retries back off only on real failures.
  - `parse(raw)` reads the present-weather groups (`-RA`, `+SHRA`, `TSRA`, `DZ`, `-SN`, `TS`…)
    up to RMK/NOSIG/BECMG/TEMPO. It ignores vicinity (VCSH) and recent (RERA) weather, and rejects
    malformed reports (bad header, two METARs in one).
  - Rates: light/moderate/heavy rain 0.5/2.5/8 mm/h, drizzle 0.1/0.3/0.6.
  - `nearest` takes the latest good report of the nearest airport within 30 km, at most 90 min old.
- **`merge_weather(om, met, obs)`**: the observation sets precip, snow and WMO; `_observed_wmo`
  keeps the model's cloud code but strips any rain code when the airport is dry. Without an
  observation, MET's next-hour forecast decides. Open-Meteo decides only alone.
- **Window**: a third source `metar`, due every 10 min, with the same back-off/resume/network
  handling. It is cleared on location change.
- README: data sources and privacy line updated.
- Tests rewritten and extended (merge order, the real Lomé reports including the garbled one,
  intensities, thunder/snow, vicinity/trend/remarks, nearest/too far/too old): 59 pass.
- Live: Lomé → airport dry → no rain on screen. Kara → DXNG at 26 km used. Oslo → ENGM is ~35 km,
  beyond the limit → MET forecast.
- Possible next step, not done: METAR cloud groups (FEW/SCT/BKN/OVC) are real cloud data too.
  Today the airport said FEW while both models said 95 %.

### Rain now: the most accurate free source for the user's location (unreleased)
- The user found the airport change "too personal" (built around Lomé). The METAR lookup was
  already location-independent, but radar beats an airport wherever radar exists, so the best
  source really does depend on where the user is. Asked for: a script that picks the most
  accurate free source for the location.
- **New `core/rain_now.observe(lat, lon)`**: tries the sources in order of accuracy and keeps the
  first that covers the place:
  1. **MET Norway Nowcast 2.0** (`radar.met_nowcast`): radar + stations every 5 min, only asked
     inside a Nordic box. It must report `radar_coverage: ok`. It gives `precipitation_rate`; snow
     when the air is ≤ 1 °C.
  2. **RainViewer** (`radar.rainviewer`): worldwide composite of national radars, free and keyless.
     - Zoom 7 is the free maximum; zoom 8 returns a "Zoom Level Not Supported" image.
     - Reads the **coverage tile** first: transparent = radar, black = none (Lomé is black). It is
       cached 24 h per point.
     - Then reads the latest radar frame (at most 30 min old) as a 3×3-pixel neighbourhood (~3 km).
     - The free API serves only the "Universal Blue" palette, whatever scheme is asked for (scheme 0
       came back in colour). Its colours map back to dBZ through RainViewer's published table,
       generated into `caelum/data/radar_colors.json` by `packaging/make-radar-colors.py`. The table
       has a rain half and a snow half, so a pixel also says rain or snow.
     - Rate: Marshall–Palmer, Z = 200 R^1.6, from 15 dBZ. A neighbourhood mean under 0.1 mm/h
       counts as dry (a stray pixel).
     - A small pure-Python PNG reader (`png_pixels`) decodes straight (not premultiplied) RGBA.
       Reading through cairo premultiplied the semi-transparent light-rain colours, so ⅓ of the
       pixels missed the table.
  3. **Nearest airport METAR** within 30 km, at most 90 min old (`metar`, from the previous step).
  - None of them covers the place → the forecasts decide: MET Norway's next hour, then Open-Meteo.
- **Thunder**: radar can't see lightning (`thunder: None`), so a shower seen by radar keeps the
  model's thunderstorm code. An airport reports TS itself.
- **Merge**: `rain_source` (met_radar | rainviewer | airport | met_forecast | om_forecast) plus
  `rain_station` for airports.
- **Window**: the `rain` source runs every 10 min in a thread. An observation older than 30 min
  (the source stopped answering) is dropped, so the forecasts take over. It is cleared on
  location change.
- **Settings → Location → Weather Data → "Rain now"** shows the source in use, e.g. "Airport DXXX,
  N km away" or "Radar (RainViewer)", with a one-line explanation. fr/es/de/pt/it strings added.
- **Live check, 25 Oct ~13:40 UTC**:
  - Oslo and Bergen → MET radar. Bergen raining: 1.9 mm/h on MET, 1.28 on RainViewer; the others
    dry on both.
  - London, Paris, New York, Tokyo → RainViewer.
  - Lomé → DXXX. Nairobi → HKJK at 12 km.
  - About 0.5–2 s per lookup.
- Packaging: `data/*.json` added to the package data. README: sources (RainViewer credited) and
  privacy (RainViewer only learns the ~300 km tile).
- Tests made location-neutral (generic station ABCD; the garbled report kept as an anonymised
  example). New tests: selector order and short-circuit, no Nordic request elsewhere, dBZ→rate,
  PNG reader (straight alpha, edge clipping), palette sanity, airport naming. 68 pass.

### Clouds, temperature and wind observed too (unreleased)

The user asked whether the rain approach could cover the other weather data. Each kind of data now
comes from the best observation that covers the place, with the forecasts as the fallback.

- `caelum/core/observed.py` replaces `rain_now.py`. `observe(lat, lon)` returns
  `{rain, sky, air, station}`, each part None when nothing observes it:
  - rain: Nowcast → RainViewer → airport (as before);
  - sky: the nearest airport's cloud layers;
  - air (temperature, humidity, wind): Nowcast (its station measurements) → airport.
  - When radar gives the rain, the airport still says whether there is thunder.
- `metar.parse` now also reads wind (KT/MPS/KMH; VRB or calm → no direction), temperature/dew point
  (humidity with Magnus), cloud layers, VV (fog = overcast at the ground), AUTO and the clear-sky
  groups.
  - `sensed_top` is how high the report vouches for the sky: manned 99,999 ft; AUTO/CLR/NCD
    12,000 ft (ceilometer); CAVOK/NSC 5,000 ft; SKC everything.
- `metar.sky(obs, model)`: cover per layer (low < 6,500 ft, mid < 20,000 ft, high above). FEW 19,
  SCT 44, BKN 75, OVC 100 %. A layer the report can't vouch for (less than half of it in sight,
  and no reported cloud in it) keeps the model's value: e.g. cirrus over an automatic station.
- `merge_weather(om, met, obs)`:
  - `sources = {rain, sky, air}` and `station` replace `rain_source` / `rain_station`;
  - rain is applied before sky, so a dry observation of a forecast shower gets its clear/fair/
    cloudy code from the observed clouds (found by a test: it showed "cloudy" under a FEW sky);
  - the badge symbol follows the observed code;
  - a variable wind keeps the model's direction.
- Settings → Location → Weather Data: three rows (Rain now, Clouds now, Temperature & wind) plus a
  note under the group. fr/es/de/pt/it strings added.
- **Live check, 25 Oct ~13:45 UTC**:
  - Lomé: rain, clouds and air from DXXX: FEW017, 32 °C.
  - Oslo: rain and air from MET Nowcast; no clouds (ENGM is ~35 km away), so the models give them.
  - London (EGLL), Paris (LFPB), New York (KJRB), Tokyo (RJTT): rain from RainViewer, clouds and air
    from the airport. Nairobi: everything from HKJK (12 km).
  - The first run got nothing for Paris and Tokyo: one aviationweather.gov request failed in a
    burst of requests. The window retries every 10 min.
- Tests: observe() order and fallbacks, wind units, freezing temperatures, the sky rules, merge
  of sky and air. 75 pass.

### Release 1.5.1 (2026-10-25)

The user asked to release 1.5.1. It brings the snap refresh fix and the observed weather (rain,
clouds, temperature, humidity and wind). The user's running copy was still snap rev 6 (1.4.0):
the 1.5.0 refresh had been refused because the app was running.
- Version bump: `__init__`, debian/changelog, metainfo `<release>` and screenshots pinned to
  v1.5.1. The screenshots were not re-rendered: only Settings changed.
- **Snap Store upload rejected**: `refresh-mode is not allowed` for a non-daemon app. The Store
  only accepts the key for services, so the 9b500ae fix was wrong (it had only been checked with a
  local build).
  - Removed. snapd 2.77 holds automatic updates until Caelum quits, sends a notification, and
    forces the update after 14 days. A manual `snap refresh caelum` still refuses while Caelum
    runs: quit it first.
  - The "restart to use it" note stays for forced updates.
  - Only the snap was rebuilt (still 1.5.1, from the commit after the v1.5.1 tag). The GitHub
    .snap and SHA256SUMS were replaced. The .deb, flatpak and PPA packages don't contain
    snapcraft.yaml.
- The user tested beta ("beta works"). Snap rev 9 (1.5.1) promoted to stable. 1.5.0 (rev 7)
  never went to stable.

### Lock screen: what GNOME really shows (unreleased)

The user asked for the live app on the lock screen instead of a screenshot. Findings (read-only):
- No app window can be drawn above GNOME's lock screen. Only a Shell extension with
  `session-modes: ["unlock-dialog"]` can draw there; GNOME 50's extensionSystem.js supports it.
- GNOME 50's unlockDialog.js draws the **desktop** background (BackgroundManager) with a
  Shell.BlurEffect. It never reads `org.gnome.desktop.screensaver picture-uri`. That has been the
  case since GNOME 3.36, so Caelum's "Lock screen only" choice never showed anything on supported
  Ubuntus.
- extensions.gnome.org has rejected AI-generated extensions since Dec 2025, so an extension
  could only ship in Caelum's own .deb.
- Options given: A (extension, near-live sharp sky), B (fix the setting, export every minute),
  C (B now, A later). Recommended C. **The user chose B**; A stays undecided.

Done (B):
- Settings → System → Wallpaper: the four-way combo became one switch, "Live sky as wallpaper",
  with "Updated every minute. The lock screen shows it too, blurred by GNOME". fr/es/de/pt/it
  strings replaced (pt in the Brazilian forms the file already uses).
- The export runs every 60 s instead of every 5 min.
  - Measured with the render harness at 960×540: render 3–38 ms, PNG 46–78 ms. Roughly ×4 at
    1080p, with the PNG written in a thread.
  - GNOME's background.js watches the file and reloads it on CHANGES_DONE_HINT, so only the file
    is rewritten; the settings are re-set to the same URI.
- `config._upgrade` gathers the settings migrations:
  - background/both → both;
  - lockscreen → **off**: it never showed anything, and turning it into 'both' would take over the
    user's desktop wallpaper unasked.
- tests/test_config.py: the migrations. 77 tests pass.
- Settings → System → About → Weather now reads "Observations every 10 min · forecasts every
  15 min (Open-Meteo) and 1 h (MET Norway)". It was hard-coded English and didn't mention
  observations. Now translated into fr/es/de/pt/it; a comment at `_REFRESH` points to it. Checked
  in German, the longest: it wraps cleanly.

### Release 1.5.2 (2026-10-25)

The user asked to release 1.5.2: the wallpaper switch (every minute) and the About line.
- Version bump: `__init__`, debian/changelog (it also corrects 1.5.1's claim that the snap refreshes
  while running), metainfo `<release>`, screenshots pinned to v1.5.2. The screenshots were not
  re-rendered: only Settings changed.
- PPA: `ppa-upload.sh` refused to run because of four untracked photos in the folder (the user's
  IMG_20261025_*.jpg, left untouched). The source is `git archive HEAD`, so the clean-tree check now
  ignores untracked files.

### Personal landscapes (unreleased)

The user asked to turn four of their own photos into a landscape. The photos and the landscape
made from them stay on the user's machine: never in the repo or the packages.
- **App**: landscapes are also read from `<data dir>/caelum/landscapes/`, in the shipped format
  (`landscapes.json` + `<name>.jpg` + `<name>-mask.png`, plus an optional `label`).
  - `sandbox.data_dir()`: in the snap it is `$SNAP_USER_COMMON/.local/share` (revision-independent,
    like the cache); otherwise `$XDG_DATA_HOME` (Flatpak sets it per app).
  - Shipped names win a clash; `hills`/`none` and odd names are refused.
  - Settings lists them after the shipped landscapes.
- **Bug fixed on the way**: `_PAD` 2 → 8. Shrinking the band ~2.5× with the GOOD filter reached
  past the 2 transparent rows into the wrapped bottom row, drawing a thin dark line across the sky
  at the band's top. The shipped bands escaped it only by their sub-pixel offset at 1080p.
- **Building the landscape** (scratchpad tools, not committed: they need OpenCV):
  - OpenCV's panorama stitcher joined the 4 phone shots (half size) into a ~74° view.
  - The black border was filled: reflected lawn at the bottom, sky at the top. The edge rims
    were trimmed, and the right edge stops before a brick pile so the mirror join runs along a
    plain wall.
  - Contrast ×1.12, colour ×1.12, brightness ×0.96 (the noon shots were hazy).
  - Magnified ×1.6 vertically and stretched to 180° horizontally, then mirrored to close the
    360° band, so both joins are seamless. South (0.25) faces the middle of the yard; top 28°.
  - The sky was cut out with make-landscapes.py's `cutout()`; walls and roofs stay.
  - Checked in renders at noon (facing the yard and away), sunset and night.
- Tests: personal catalog (order, clashes, no folder). 80 pass.

### Release 1.5.3 (2026-10-25)

The user asked to release 1.5.3: personal landscapes and the landscape-edge line fix. Version bump
in `__init__`, debian/changelog, metainfo (screenshots pinned to v1.5.3, not re-rendered: the
shipped landscapes look the same).
- The user tested beta ("beta works"; their snap now runs 1.5.3 rev 11). Rev 11 promoted to stable.
  1.5.2 (rev 10) never went to stable: its changes reach stable users with 1.5.3.

### Your own photo as landscape (unreleased)

The user didn't want a landscape that exists only on their machine ("Any update must be global"),
and asked for risks to be flagged first. I warned that shipping a photo of a private place would
publish it, and that the default location in the code was too precise (fixed in 1.5.4). The user
chose the general feature and said not to use their photos.

- **Settings → Sky → Your own photo**: "Choose…" opens the native file chooser (the file portal in
  the snap — `GTK_USE_PORTAL=1` there — and the Flatpak, so no new file permission is needed). The
  build runs in a thread, then a preview dialog (the 240° seen facing south) offers "Use it" /
  "Cancel". "Remove" deletes it. The menu lists it as "Your photo".
- `caelum/gtk_ui/photo_landscape.py`, GdkPixbuf + cairo only (no numpy/OpenCV, so the .deb, snap
  and Flatpak need nothing new):
  - Checks: JPEG/PNG only (sniffed by GdkPixbuf, not the name), ≤ 50 MB, ≤ 120 MP, ≥ 400 px
    wide. Decoded at ≤ 4000 px on the long side, then turned upright (EXIF orientation).
  - Sky cut-out ported from make-landscapes.py to pure Python on a 480 px-wide copy: colour test,
    sky colour per row, skyline (first 3 ground rows), 7-column opening, gaps in canopies, 1 px
    erosion. "No sky found" if under half the columns have sky at the top.
  - Geometry: the median skyline at 10°, the photo's bottom at −40°, and the tallest feature
    capped at 35°. The photo spans 180° and is mirrored over the other 180°; south = 0.25.
  - Built in a temporary folder next to the personal folder, then moved into place
    (`os.replace`); `landscapes.json` is rewritten atomically. Fixed file names.
  - The JPEG is re-encoded from the pixels, so no EXIF/GPS is carried over (tested with an EXIF
    block).
- Test photo: a slice of the CC0 "plain" over a drawn sky, plus fake GPS. Build 1.5 s; renders
  at noon, sunset and night look right; the preview dialog and Settings row were screenshotted.
- Tests (tests/test_photo_landscape.py): build/install/remove, mask (sky at the top, ground at the
  bottom, mirrored), EXIF dropped, refusals (no sky, too small, not an image, too large). 83 pass.
- Not shipped: the user's photos and the hand-installed "yard" from the previous step.

### Location privacy (1.5.4)

The user called this "very important". The code's default location had 4 decimals (~11 m).
- Default → `6.14, 1.22`: Lomé's public city-centre point, at the same ~1 km precision Caelum
  uses for every online lookup. Settings' fallback and the sky-drawing defaults now read
  DEFAULT_CONFIG instead of repeating numbers.
- Tests: the geoip sample is now Tokyo and the rounding example Paris.
- JOURNAL scrubbed of the old point, distances from it, and the link to the user's home.
- **Not removable:** the old values stay in the git history and in the released 1.0–1.5.3
  packages. Erasing them would mean rewriting public history (force-push, broken tags and
  releases), and copies already downloaded would remain. Not done; the user decides.
- Existing installs keep whatever location their config saved; the default only applies to new
  configs.

### Release 1.5.4 (2026-10-25)

The user asked to release 1.5.4: "Your own photo" landscapes and the location privacy fix. Version
bump in `__init__`, debian/changelog, metainfo (screenshots pinned to v1.5.4, not re-rendered: the
default views are unchanged). The privacy grep (now in the release routine) found only public
places, star positions and formula constants.

### Snap: say when an update is waiting (unreleased)

The user still got "cannot refresh: has running apps" and asked for a global fix ("Think Global").
snapd 2.77 holds automatic refreshes while the app runs: it downloads ahead, installs as soon as
the app's processes exit (logout, Ctrl+Q), and forces the update after 14 days. Only a manual
`snap refresh` fails. The Store allows `refresh-mode` only for daemons, and the sandbox can't
relaunch Caelum, so the fix is to tell the user.
- `caelum/core/snapstore.py`: `GET https://api.snapcraft.io/v2/snaps/info/<name>?fields=version,revision`
  with `Snap-Device-Series: 16`, the public endpoint snapd uses. `waiting()` compares the channel
  map with our revision (same architecture, `latest` track).
  - A snap can't see its tracked channel, so it is taken as the least risky channel at or past our
    revision. A stable user is never pointed at a beta; a beta user whose revision is also stable
    gets no notice, which is the accepted trade-off.
- `sandbox.snap_identity()`: (name, revision, arch) from the snap env; None for `--dangerous`
  builds (revision x1) and outside a snap. `net.get_bytes/get_json` take extra headers.
- Window: checks 90 s after start, then every 6 h (snap only, in a thread). The note reads
  "Caelum {v} is ready · it installs when Caelum closes (Ctrl+Q, or when you log out)"; the
  "installed · restart" note takes priority. fr/es/de/pt/it.
- Live: revision 11 → no notice (stable = 11); revision 9 → "1.5.3". Note checked in en/de at 960 px.
- README: snap updates and privacy (the request carries no location or personal data).
- Tests: tests/test_snapstore.py (channel choice, architecture/track, garbage, request,
  identity). 92 pass.

### Release 1.5.5 (2026-10-25)

The user asked to release 1.5.5: the snap's "update waiting" note. Version bump in `__init__`,
debian/changelog, metainfo (screenshots pinned to v1.5.5, not re-rendered). Privacy grep clean.
- The user tested beta ("beta works"). Snap rev 13 (1.5.5) promoted to stable; stable users go
  from 1.5.3 to 1.5.5 with the photo landscapes, the location fix and the update note.

### End of session (2026-10-25)

Released today: 1.5.0 → 1.5.5. The Snap Store's stable channel is 1.5.5 (rev 13); GitHub and the
PPA have 1.5.5. 1.5.0, 1.5.2 and 1.5.4 went to beta only and reached stable users through the next
release.

Rules agreed this session:
- Every change is global: shipped to all users through the app, never a machine-only setup.
  Security or privacy risks are raised before building.
- No precise location tied to the user in any public file. Coordinates have ≤ 2 decimals; test
  examples use neutral places. A privacy grep runs before every release.

**Next session: Windows package**, then the Android APK (Kivy milestone 1 is already done).
On Windows, the Linux-only parts must be replaced or turned off:
- wallpaper export (gsettings/portal);
- autostart (.desktop);
- the snap/flatpak sandbox code and the snap update note;
- XDG paths (→ `%APPDATA%`);
- the desktop-level transparent overlay window;
- the IIO / iio-sensor-proxy compass.

The packaging route (e.g. GTK3/PyGObject via MSYS2 plus an installer) is to be chosen with the
user first.

---

## Session 14 — Windows package (2026-10-25)

The user asked whether Caelum can go on the Microsoft Store: yes, as an MSIX (Microsoft signs and
hosts it for free) or an EXE/MSI (own code-signing certificate). Plan agreed: (1) PyInstaller
build of the GTK app from MSYS2, tested by hand; (2) MSIX for the Store plus a zip on GitHub
Releases; (3) built on GitHub Actions. This session: step 1, on the `windows` branch.

### Step 1: Windows code paths and a CI test build (unreleased)

- `caelum/gtk_ui/win32.py` (ctypes, Windows only):
  - **Sky behind the desktop icons**, as live-wallpaper apps do: Progman's message 0x052C creates
    the WorkerW between the wallpaper and the icons, and the sky becomes its child. On Windows 11
    24H2+ the icons (SHELLDLL_DefView) sit inside Progman: the sky becomes Progman's child, just
    below the icons. Click-through off, or no icon layer found → a bottom-most window over the
    icons that takes clicks. Either way: no taskbar button, and a click doesn't raise it.
  - On exit the user's own wallpaper is re-applied so the icon layer isn't left with the sky.
  - Wallpaper export → `SystemParametersInfoW` (background only; no lock-screen API for desktop
    apps). Autostart → the per-user `Run` registry key.
  - Folders: config in `%APPDATA%\caelum`, landscapes and cache in `%LOCALAPPDATA%`.
- Window: a tray icon (Settings, Clean mode, Quit), since the gear can't be clicked behind the
  icons. The Click-through switch moves the sky in front of or behind the icons at once.
- i18n: Windows has no LANG; the display language comes from `GetUserDefaultUILanguage`.
  New strings ("Start when you sign in", "Settings", "Quit Caelum") in fr/es/de/pt/it.
- Settings: the photo chooser also filters by pattern (the Windows dialog ignores MIME types);
  serial port placeholder `COM3`.
- Linux behaviour unchanged; the IIO and D-Bus compasses simply find nothing on Windows.
- Packaging: `packaging/windows/` (launcher, PyInstaller spec, build.sh), one folder (not one
  file: faster start, fewer antivirus false alarms). The launcher points OpenSSL at the bundled
  certificates and logs to `%LOCALAPPDATA%\caelum\caelum.log`. `caelum.exe --selftest <file>`
  checks GTK, Cairo and HTTPS (with a neutral place, Paris).
- `.github/workflows/windows.yml`: MSYS2 UCRT64, unit tests, build, self-test, 30 s launch with a
  screenshot; the zip and the checks are kept as run artifacts.
- Not tested yet on a real Windows desktop: the icon-layer placement is undocumented Windows
  behaviour and needs the user's test on Windows 10/11.
- First CI run (Windows Server 2025, build 26100 = 24H2 base): 92 tests pass, self-test ok (GTK
  3.24.52, cairo 1.18.6, HTTPS, 3 landscapes), Caelum ran 30 s with no error, zip 47 MB. But the
  screenshot showed the stock wallpaper, no sky. Likely cause: GTK draws RGBA windows as layered
  windows, which don't paint as a child of the icon layer. The sky window is now opaque on
  Windows (the sky is opaque by default anyway), the placement is logged to caelum.log, and the
  CI takes one screenshot behind the icons and one with click-through off.
- Second run: the placement log said both modes worked (24H2 Progman path; bottom-most), but the
  click-through-off screenshot showed the sky in a 200×200 corner only: the Win32 resize never
  reached GTK, which kept painting at its default size. Behind the icons nothing showed at all.
  Now GTK gets the screen size (set_default_size) before the first show and the Win32 call only
  moves the window. On 24H2 the sky child is layered (opaque), since 24H2's Progman is composited
  and draws only layered children. The log also gives GTK's own drawing size.
- Third run: GTK's size was right (1024×768) but no sky showed in either mode. Clearing the
  layered bit was the likely cause: GTK on Windows may paint through UpdateLayeredWindow, so that
  bit is GTK's. Kept now (and logged); the 24H2 path adds it only when GTK hasn't. A probe 10 s in
  logs which window is at the screen centre and the sky's parent chain.
