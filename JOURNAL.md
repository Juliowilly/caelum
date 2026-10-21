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
