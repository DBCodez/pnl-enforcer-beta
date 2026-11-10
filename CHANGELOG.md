# PnL Enforcer Beta — Changelog

All notable updates, guardrail improvements, and broker adapter fixes are documented in this file.

---

## [v0.9.26] — 2026-11-10
### Added & Changed
- **Optional Small 3-Column (Compact) HUD & Live Hover-Over Status Tooltip:**
  - Added a **`Small 3-Col (Compact)`** preset button alongside **`Standard 5-Col`** in **`📊 HUD Columns`** (`open_hud_columns_dialog`), with dynamic active cyan highlight tracking (`refresh_hud_preset_highlight`) and fixed button widths (`auto_width=False`) so switching modes never shifts or stretches the Pre-Flight window.
  - Lowered the minimum HUD width clamp from `800px` to `480px` (`max(480, len(active_cols) * 160)`), shrinking the 3-column HUD footprint by 40% (`480x88` vs. `800x88`) while keeping **`⚙ SETTINGS`** and **`✕`** anchored on the right.
  - When in Compact HUD mode (`<= 4` columns), the middle status capsule displays concise labels (`● ARMED`, `● ALARMS ONLY`, `MUTE ALARM`, `🔒 LOCKED: Xs`, `★ FLOOR RAISED ★`) and provides a dark-slate hover-over tooltip card (`attach_hud_mute_tooltip`) showing the full armed configuration summary, active Rulebook & poll interval, and active alarm or cooldown details.

---

## [v0.9.25] — 2026-11-09
### Fixed
- **HUD Warning Alarm & Upside Ratchet Banner High-Contrast Readability (`trigger_alarm` / `HudCapsulePill`):**
  - Fixed a color-parsing bug where `trigger_alarm()` passed `bg="yellow"` (a 6-character named color) to `_hex_to_rgb_tuple()`, causing it to fall back to the dark-slate `#141820` fill with `fg="black"` text. Active warning alarms now render with a bright warning-gold capsule fill (`#eab308`), `#fef08a` border highlight, and crisp dark `#090d16` text, and named colors are normalized via `_normalize_color_hex6()`.
  - Updated all 6 steps of `trigger_upside_tier_glow()` to use `#ffffff` white text over the `#10452c` emerald capsule.

---

## [v0.9.24] — 2026-11-08
### Added & Changed
- **Custom Borderless Dark-Slate Dropdown Menus (`DarkDropdownMenu`):**
  - Replaced native Win32 `tk.Menu` popups across all 5 dropdowns (`BROKER`, `ACCOUNT`, `📜 Logs ▾`, `Voice`, and `Audio Cue`) with a custom borderless `tk.Toplevel` dropdown (`DarkDropdownMenu`) featuring a crisp `1px` `#334155` dark-slate border, `#141820` fill, and `#1e293b` row hover highlight (eliminating Windows' thick white system menu border).
  - Multi-monitor safe downward positioning (`+{x}+{y}`) and window-relative tooltip bounds so menus and tooltips never flip upward on secondary monitors.
- **HUD Left Capsule Defaulted to `W/L`:**
  - Defaulted the HUD bottom-left capsule to **`W/L`** (`W: X (%) | L: Y (%)`) on startup (clicking cycles through `W/L -> FLAT: $... -> BASE: $...`).
- **Regular Trading Hours Rulebook Switch Aligned to `9:30 AM – 4:00 PM ET` (`is_rth()`):**
  - Aligned the Regular Hours Rulebook switch (`is_rth()`), Card 3's *Start Fresh on Rulebook Switch (`9:30 AM & 4:00 PM`)*, Card 4's subtitle (*Active before `9:30 AM` and after `4:00 PM ET`*), and Card 5's header (*`5. REGULAR HOURS RULEBOOK (9:30 AM – 4:00 PM)`*) to the standard `9:30 AM ET` US market open.

---

## [v0.9.23] — 2026-11-06
### Added
- **Modern `6px` Rounded-Rectangle (Squircle) Button Engine (`_render_glass_pill_image` / `_get_glass_pill_photo` / `GlassStadiumButton`):**
  - Built a cached `PIL` / SDF anti-aliased button renderer featuring:
    - **Crisp `6px` Rounded-Rectangle Geometry (`corner_radius=6`):** All clickable buttons, dropdowns, and the unified `BROKER / ACCOUNT` bar use a modern `6px` rounded-rectangle radius, while non-clickable status badges (`● ACTIVE NOW`, `STANDBY`, and HUD `FLAT:` / `ARMED:` readouts) retain full stadium capsules (`height // 2`).
    - **One-Way Top-Down Micro-Fade:** Replaces dark-center tube gradients with a smooth, continuous one-way top-to-bottom linear fade (`#1c212b` top edge fading smoothly downward to `#141820` bottom).
    - **Razor-Sharp `1px` Top Catch-Light Border:** Removes fuzzy edge blur in favor of a tack-sharp `1px` anti-aliased border where the top horizontal edge is `25%` brighter than the sides and bottom.
- **Custom Dark-Glass Checkboxes (`GlassCheckbutton` / `make_glass_checkbutton`):**
  - Replaced legacy Windows sunken square checkboxes across Pre-Flight and all setup dialogs with a custom `tk.Label`-backed dark-glass checkbox widget (`GlassCheckbutton` + `_get_glass_checkbox_photo`) featuring an anti-aliased `18x18` rounded dark-glass icon, glowing emerald/amber/coral border with a vector `✓` checkmark when checked, and zero Windows `selectcolor` white boxes or relief borders.
- **Pre-Flight Top Bar — Single Un-Nested `BROKER / ACCOUNT` Bar, Unified Neutral Utility Buttons & Segmented Presets:**
  - Un-nested the top-left **`BROKER / ACCOUNT`** container into **one unified dark-slate `6px` rounded bar** (`#1c212b -> #141820` top-down fade + `#2e3746` `1px` border) where **`BROKER: SCHWAB ▾   ● ACCOUNT: Schwab Account ... ▾`** and the glowing emerald status orb (**`●`** `_get_glow_dot_photo`) sit directly on the surface without inner outlines at rest.
  - Unified all secondary utility buttons (**`🔑 API Keys`**, **`📊 HUD Columns (5)`**, **`📜 Logs ▾`**, **`Restore Defaults`**, **`Save as Default`**, and Card 3's **`Voice / Cue`** dropdowns and **`🔊 Test`**) onto a cohesive neutral dark-slate surface (`#1c212b -> #141820` with `#2e3746` border brightening to `#475569` on hover), with a subtle muted rose border (`#5c2836`) on **`🐞 Report Bug`**.
  - Reserved saturated color fills strictly for the active preset (**`✓ Standard Full Risk`** in deep steel-blue `#163052 -> #0f213a` with `#38bdf8` border, or **`✓ 50% Low Energy`** in deep emerald `#144332 -> #0d2e22` with `#10b981` border) and the primary **`🚀 SAVE & LAUNCH ENFORCER >>`** button (`#14532d -> #0d3b20` top-to-bottom fade with a crisp `1px` `#10b981` border).
- **Pre-Flight Bottom Action Bar & HUD Controls:**
  - Upgraded HUD **`⚙ SETTINGS`** and **`✕`** to `6px` rounded rectangles with crisp `1px` borders while preserving full stadium capsules on the left badge and **`ARMED:`** and honoring the **`🔒 IN TRADE`** tamper lock.
- **Calm Left-Accent Card Borders, Crisp `Arial` / `Consolas` Typography & Live Telemetry Strip (Cards 1–5):**
  - Replaced 4-sided neon box borders around Cards 1–5 with calm `1px` dark-slate card perimeters (`#243040`) paired with a single glowing left vertical accent bar (`NeonBarCanvas`), dark-glass numeric entry boxes, and crisp integer-aligned `Arial` / `Consolas` GDI ClearType typography.
  - Added geometric **`▶  `** prefixes to Cards 1–5 numbered headers, crisp `1px` (`#222d3d`) horizontal section dividers across Cards 1–5 (including between Base Tier 1 and Profit Ratchet Tiers in Card 5), **`▸ `** prefixes on Tiers 2–4, and an SDF **`● ACTIVE NOW` / `STANDBY`** rulebook badge (`RulebookPillBadge`).
  - Upgraded Card 3's live telemetry row into a multi-color inline strip: Baseline dollar value in soft cyan (`#7dd3fc`), Token time remaining in emerald (`#4ade80`, or amber `#fbbf24` when `< 1.5d`), **`W:`** count/percentage in emerald (`#58d68d`), and **`L:`** count/percentage in soft coral (`#e07a7a`).
  - Styled Card 3's **`Voice / Cue`** dropdowns as quiet, flat dark-glass selector boxes (`#0e141d` fill, `#283546` border) so they never compete visually with the risk inputs.
- **Expanded, Un-Truncated API Keys Setup Wizard & Unified Modal Popups:**
  - Upgraded the **Schwab & Webull API Credential Setup Wizard** (`show_broker_setup_wizard`) with complete, un-truncated multi-line step-by-step instructions (including the full Step 5 browser approval + clipboard auto-detection walkthrough), cyan step badges (`1.`–`5.`), color-highlighted pill badges (`Accounts and Trading Production`, `https://127.0.0.1` with a one-click **`📋 Copy`** button, `Ready for Use`), a header **`🌐 Open ... Developer Portal ↗`** button, and frosted-glass action pills.
  - Upgraded **`Customize HUD Columns & Order`**, **`Release Notes`**, **`Update Available`**, **`Schwab OAuth`**, and **`Liability Waiver`** modals to match the frosted-glass aesthetic.
  - Hover tooltips on all dropdown menus now immediately cancel and disappear before opening the dropdown menu so tooltips never linger behind open menus.

---

## [v0.9.22] — 2026-11-06
### Added
- **Windows Kernel Single-Instance Guard (`_ensure_single_instance_or_exit`):**
  - Acquires an OS-level named mutex (`Local\PnLEnforcerBeta_SingleInstance_Mutex`) at startup so two instances of PnL Enforcer can never run simultaneously on top of each other, preventing duplicate flatten orders and double-logged `[POS_CHANGE]` / `W/L` trade counts. If a user launches the app while an instance is already open, Enforcer logs a `[GUARDRAIL]` block, displays an always-on-top alert dialog, and exits cleanly.

---

## [v0.9.21] — 2026-11-06
### Fixed
- **US Eastern Market Time Synchronization (`get_eastern_now()`):**
  - Anchored `is_rth()` (`9:25 AM – 4:00 PM ET`), `is_market_hours()` (`9:30 AM – 4:00 PM ET`), `is_after_hours()` (`>= 4:00 PM ET`), and `get_today_str()` directly to US Eastern Time (`America/New_York`, with built-in zero-dependency `EST`/`EDT` Daylight Saving Time handling) instead of local computer clock time. Traders in Pacific (`PT`), Mountain (`MT`), Central (`CT`), or international timezones now automatically switch between Extended Hours (`Card 4`) and Regular Hours (`Card 5`) at exact US market hours.
- **Webull Partial-Fill Balance & Position Settlement Sync (`WebullAdapter.fetch_account_data`):**
  - Eliminated 1-poll transient `Realized` / `Net` PnL spikes on Webull when scaling in or out of an open position by querying positions before account balance, performing an automatic `0.25s` settlement re-sync whenever share quantity changes mid-trade, and requiring a `0.35s` anti-wick confirmation whenever a breach candidate coincides with a share-quantity change.
- **Zero-Delay Gist API Update Discovery (`check_for_updates_cli`):**
  - Queries the un-cached GitHub Gist API (`api.github.com/gists/...`) to resolve the exact commit-pinned `raw_url` before falling back to CDN raw URLs, plus runs an automatic startup update check inside `enforcer.py` so updates are detected immediately regardless of how the app is launched.

---

## [v0.9.20] — 2026-11-06
### Added
- **Two-Stage Post-Lock Straggler Watchdog (`2.0s` + `15.0s`) with Verbal Confirmations:**
  - **Stage 1 (`T + 2.0s`):** Performs the initial post-lock flat check against `get_open_equity_positions()`. When `0` open equity shares are confirmed (`HTTP 200`), logs the Stage 1 pass and announces via TTS: *"Initial flat check passed."*
  - **Stage 2 (`T + 15.0s`):** Runs a second delayed verification sweep `15.0s` after the OS lock engages (while the lock remains active) to catch late ECN fills, unhalt prints, or hanging cancel-and-replace orders. When `0` open equity shares are confirmed, logs the Stage 2 pass and announces via TTS: *"15 second sweep clear, account confirmed flat."*
  - **Emergency Straggler Sweep:** If straggler shares are detected on either the `2.0s` or `15.0s` sweep, Enforcer immediately announces *"Warning, straggler shares detected, flattening now"*, executes an emergency `flatten_equities()` sweep, and if unable to confirm flat, aborts the OS lock and sounds the emergency siren.
- **Selectable Windows OneCore TTS Voices (`Zira`, `Mark`, `David`):**
  - Added a voice selector in Card 3 (`Zira (Female)`, `Mark (Male)`, `David (Male)`) backed by the Windows OneCore speech registry (`HKLM\SOFTWARE\Microsoft\Speech_OneCore\Voices`) so all installed Windows voices can be selected and previewed via **`🔊 Test`**.
- **Native Windows Dark Mode Title Bars (`apply_dark_title_bar`):**
  - Applied `DwmSetWindowAttribute` (`DWMWA_USE_IMMERSIVE_DARK_MODE`, attributes `20` and `19`) to the Pre-Flight window and all pop-up dialogs (API Keys, HUD Columns, Release Notes, Schwab OAuth, and Update Available).
- **Pre-Flight Card Accent Bars & Dynamic `[● ACTIVE NOW]` / `[STANDBY]` Rulebook Highlight:**
  - Added `4px` left-edge colored accent strips across Cards 1–5 (`#3498db` Steel Blue for Card 1, `#f39c12` Amber for Card 2, `#2ecc71` Emerald for Card 3, and dynamic session-aware coloring for Cards 4 & 5).
  - Cards 4 (`Extended Hours`) and 5 (`Regular Hours 9:25 AM – 4:00 PM ET`) now dynamically highlight whichever rulebook is currently governing the HUD with a bright **`● ACTIVE NOW`** emerald badge and border while placing the inactive rulebook in **`STANDBY`**.
  - Top-bar **`Standard Full Risk`** and **`50% Low Energy`** preset buttons now display an active **`✓`** indicator and bright border highlight whenever the current dollar fields match that preset.
- **HUD Visual Upgrade — Status Bar Pill Styling & Dynamic `$ TO STOP` Leash Bar:**
  - Styled the HUD bottom bar with rounded stadium capsules (`FLAT` / `BASE` / `W/L` and `ARMED: SCHWAB + ...`) and high-contrast warm gold status text (`#ffca58` on `#282c31`).
  - Added a `10px` glowing neon progress bar along the bottom edge of the **`$ TO STOP`** column that visualizes remaining distance to the active stop (`> 50%` Emerald `#00e676`, `25%–50%` Amber `#ffab00`, `< 25%` Crimson `#ff1744`).
- **90-Day Sanitized Log Archive & Automatic Retroactive Backfill (`_sync_sanitized_log_archive`):**
  - Automatically maintains balance-redacted copies of all 90-day archived logs inside `~/enforcer_logs/sanitized/enforcer_log_YYYY-MM-DD_sanitized.txt` (including retroactively generating sanitized copies for all existing archived logs on startup) and adds **`🔒 Open Safe Archived Logs (90-Day Redacted)`** to the **`📜 Logs ▾`** menu.
- **`Alarms Only Mode` Master Toggle & Formatted Release Notes Viewer:**
  - Added an **`Alarms Only Mode`** checkbox in Card 2 that greys out all automated flatten, app-kill, and Windows OS lock options across Cards 1 & 2 (preserving saved checkmarks when unchecked) and runs Enforcer in 100% passive observation/siren mode.
  - Upgraded the in-app **Release Notes** and **Update Available** dialogs with rich-text Markdown typography, color-coded version banner pills, and clean hierarchy.

---

## [v0.9.15] — 2026-11-04
### Added
- **3-Layer Flat Confirmation & Post-Lock Watchdog (Schwab & Webull Parity):**
  - **Layer 1 — Explicit `HTTP 200` Flat Verification:** `SchwabAdapter.get_open_equity_positions()` and `WebullAdapter.get_open_equity_positions()` now return `None` (instead of an empty list `[]`) on any non-`200` HTTP status or network exception, preventing transient API hiccups from falsely reporting 0 open shares.
  - **Layer 2 — 0.8s Pre-Lock Settlement Double-Confirmation:** `flatten_equities()` now waits `0.8s` after detecting `0` open equity shares and queries the broker API a second time before declaring the account flat or engaging the Windows OS lock (catching any in-flight partial fills and giving Thinkorswim / Webull Desktop time to play local fill chimes before locking).
  - **Layer 3 — 2.0s Post-Lock Watchdog Sweep (`_run_post_lock_watchdog`):** Automatically queries the broker API `2.0s` after Windows OS lock engages (`PENALTY BOX LOCK`, `DAILY BREACH OS LOCK`, or one-shot OS lock) to triple-confirm `0` open equity shares remain. If any straggler shares are detected, it immediately initiates an emergency flatten sweep and, if unable to confirm flat, aborts the OS lock and sounds the emergency siren.
- **Pre-Flight Footer Version Badge & Release Notes Viewer (`show_release_notes_dialog`):**
  - Added a subtle **`Version v0.9.15 · View Release Notes`** link in the Pre-Flight bottom bar to open an in-app scrollable Changelog viewer (with a direct link to the web Changelog).

---

## [v0.9.14] — 2026-11-04
### Changed
- **Unified "Daily Stop" Terminology Across Pre-Flight & HUD:**
  - Renamed Card 1 to **`1. SINGLE-TRADE STOP (Open PnL)`** and Card 2 to **`2. DAILY STOP ACTIONS (Max Loss & Profit Lock)`** (`Auto-Flatten Equities on Max Loss / Profit Stop`, `Lock Windows OS on Max Loss / Profit Stop`).
  - Renamed the HUD column headers from `TERMINATE LVL` / `$ TO TERMINATE` to **`DAILY STOP`** and **`$ TO STOP`** (preserving internal config keys for seamless backwards compatibility).
- **Signed (`-` / `0` / `+`) RTH Tier 2 & Tier 3 Stop Ratchets (`Stop Level ($)`):**
  - RTH Tiers 2 and 3 (`Fixed Stop Ratchet ($0 Siren)`) now accept negative, zero, or positive PnL stop levels (e.g. `-1000` or `-500` for a tightened loss stop, `0` for breakeven, or `+250` for a locked-in profit stop before Tier 4's trailing stop activates), with automatic one-time migration for existing saved configs.
- **Pre-Flight Visual Polish & Consolidated `📜 Logs ▾` Menu:**
  - Highlighted primary Max Loss labels (`Max Open Loss ($):` and `Starting Max Loss ($):`) in coral red (`#eb7067`) and trailing profit locks in emerald green (`#58d68d`), while displaying all loss/warning alarm inputs as negative values (`-250`, `-500`, `-1500`) with automatic sign normalization.
  - Consolidated `View Log`, `Export Safe Log (Balances Redacted)`, and `Open Archived Logs (90-Day History)` into a single **`📜 Logs ▾`** dropdown menu in the Pre-Flight top bar.

---

## [v0.9.13] — 2026-11-03
### Added
- **Custom Application & Taskbar Icon (`enforcer.ico`):**
  - Added multi-resolution Windows `.ico` badge (`16×16` through `256×256`) for Desktop shortcuts, Pre-Flight/HUD window titlebars, and the Windows Taskbar (`SetCurrentProcessExplicitAppUserModelID`).
  - Automatic `enforcer.ico` asset sync during startup version checks.

---

## [v0.9.12] — 2026-11-03
### Added
- **GUI "Update Available" Pop-Up Dialog (`show_update_available_dialog`):**
  - Replaced the terminal-only `Y/N` update prompt with a dark-themed, always-on-top GUI pop-up whenever a newer release is detected on startup.
  - Displays a live scrollable preview of `CHANGELOG.md` right inside the dialog, a clickable **`Open Full Changelog ↗`** button, and one-click **`Skip for Now`** or **`Install vX.Y.Z & Launch >>`** buttons.
- **Launcher Banner Cleanup (`Launch_Enforcer.bat`):** Replaced the UTF-8 em-dash (`—`) in `Launch_Enforcer.bat` with ASCII `--` to prevent `ΓÇö` encoding artifacts in Windows `cmd.exe`.

---

## [v0.9.11] — 2026-11-03
### Added
- **One-Click `🐞 Report Bug` Button (Pre-Flight Top Bar):**
  - Automatically generates `enforcer_log_sanitized.txt` (in `~` and `~/Downloads`) with all account balances redacted, copies the sanitized text to the Windows clipboard, opens Windows Explorer with `enforcer_log_sanitized.txt` pre-highlighted (`explorer /select,`) for instant drag-and-drop upload, and launches the Tally.so Bug Report portal (`https://tally.so/r/Z98y4V`).

---

## [v0.9.10] — 2026-11-03
### Fixed
- **Webull OpenAPI SDK Auto-Installer (`Launch_Enforcer.bat` & `enforcer.py`):**
  - Fixed a package name list bug in `Launch_Enforcer.bat` where deprecated split package names (`webull-openapi-core`, `webull-openapi-trade`, `webull-openapi-data`) caused `pip install` to abort before installing `webull-openapi-python-sdk`.
  - Added missing runtime dependencies (`six`, `jmespath`, `protobuf`, `paho-mqtt`) alongside `--no-deps --ignore-requires-python webull-openapi-python-sdk` so the Webull SDK installs cleanly out-of-the-box on all Python versions (including Python 3.13, 3.14, and 3.15).
  - Added self-healing SDK auto-installation inside both `SchwabAdapter.authenticate()` and `WebullAdapter.authenticate()` in `enforcer.py` so missing broker packages are installed automatically even if launched from an older `.bat` file.

---

## [v0.9.9] — 2026-11-02
### Changed
- **Structured Multi-Paragraph Hover Tooltips (`attach_tooltip`):**
  - Added automatic paragraph normalization (`_normalize_tooltip_paragraphs`) so soft mid-sentence `\n` breaks never collide with Tkinter word-wrapping (`wraplength=420`) to create jagged 2-word orphan lines.
  - Styled tooltip title headers (`...:`) in bold light-blue (`#aed6f1`), highlighted `• IMPORTANT:` callouts in warm amber (`#f5cba7`), and added clean vertical spacing between paragraphs, examples, and bullet points.

---

## [v0.9.8] — 2026-11-02
### Changed
- **Unified Rulebook & Termination Floor Terminology (Cards 2, 4, & 5):**
  - Renamed Card 5 from *"5. REGULAR HOURS TIERED RISK"* to **`5. REGULAR HOURS RULEBOOK (9:25 AM – 4:00 PM)`** so it pairs directly with **`4. EXTENDED HOURS RULEBOOK (Pre-Market & After-Hours)`** and Card 3's *"Start Fresh on Rulebook Switch"* toggle.
  - Standardized the initial loss floor label in both Rulebooks to **`Starting Max Loss (-$):`** (replacing *"EH Max Loss Floor"* in Card 4 and *"Hard Termination"* in Card 5 so Base Tier 1 doesn't appear to be the only hard termination level).
  - Updated **Card 2 (`2. FLOOR BREACH ACTIONS (Max Loss & Profit Locks)`)** and all hover tooltips across Cards 2, 4, and 5 to make it explicit that unlocking a Profit Ratchet Tier (Tier 2/3) or Trailing Profit Lock (Tier 4 / Extended-Hours Profit Lock) replaces your active Termination Floor, and breaching that ratcheted/trailed floor triggers the exact same Card 2 actions (Auto-Flatten Equities, Kill Apps, and Windows OS Lock for the configured duration).

---

## [v0.9.7] — 2026-11-02
### Changed
- **Pre-Flight UI & Layout Polish:**
  - Restyled the sanitized log export button into a compact, dark-slate **`🔒 Safe Log`** utility button in the top bar (removing the oversized Windows multi-codepoint emoji gap and bright green CTA collision).
  - Enforced uniform grid column alignment across Cards 4 and 5 (`make_dual_field_row`) so single-field rows (`EH Max Loss Floor (-$)` and `Hard Termination (-$)`) align vertically with dual-field input columns above and below them.
  - Added subtle `1px` horizontal section dividers below every card header subtitle, indented the Card 1 `└─ Penalty Box OS Lock` checkbox widget under its parent toggle, right-aligned the `NEW FLOOR / TRAIL` table header in Card 5, and trimmed verbose parenthetical text on Card 3 checkboxes.

---

## [v0.9.6] — 2026-11-02
### Added
- **One-Click "🛡️ Export Sanitized Log" Button (Pre-Flight Top Bar):**
  - Generates a share-safe copy of today's session log (`~/enforcer_log_sanitized.txt`), automatically copies the sanitized text to the Windows clipboard, and opens it in Notepad for inspection.
  - Redacts all total account equity/balance figures (`Baseline anchored to: $[REDACTED]`, `Start=$[REDACTED]`, `LastFlat=$[REDACTED]`, `TotalAccountValue=$[REDACTED]`, etc.) while keeping 100% of relative PnL (`Realized`, `Open`, `Net`, `High`, `SessionHighPnL`) and guardrail events intact for bug reports.
- **Automatic Privacy Scrubbing in Local Session Logs (`enforcer_log.txt`):**
  - Masks the user's Windows home folder path (`C:\Users\<Username>`) as `~` across all log headers and events so real names are never written to disk while preserving full account baseline details in the user's local log.
  - Masks brokerage order IDs (`orderId` / `client_order_id`) to their last 4 characters (`...1234`) in both `SchwabAdapter` and `WebullAdapter`.
  - Added central regex sanitization inside `log_event()` to strip any accidental `/accounts/<hash>` URL segments, Bearer tokens, or OAuth query parameters from raw HTTP exception strings.

---

## [v0.9.5] — 2026-11-02
### Added
- **Extended Hours Rulebook (Pre-Market & After-Hours):** Renamed Pre-Flight Card 4 and all associated HUD tooltips, banners, and audit log entries from "Pre-Market" to **Extended Hours** to reflect that Card 4 governs both Pre-Market (`Before 9:25 AM ET`) and After-Hours (`After 4:00 PM ET`).
- **4:00 PM RTH -> After-Hours Transition Guard:**
  - Automatically recalibrates the active Rulebook High-Water Mark (HWM) to current flat equity at `4:00 PM ET` when *"Start Fresh on Rulebook Switch (9:25 AM & 4:00 PM)"* is enabled (while preserving full-day `SESSION HIGH`), preventing an earlier intraday RTH profit peak from prematurely triggering an After-Hours trailing stop.
  - Pre-arms flat alarm states across the 4:00 PM transition so finishing RTH flat below an Extended-Hours threshold never fires a false siren or OS lockout at `4:00:01 PM`.
  - Persists `has_reset_at_close` in `enforcer_config.json` so closing the app during RTH and reopening in After-Hours transitions cleanly.
- **Launcher Version Check & One-Step Updater (`Launch_Enforcer.bat`):**
  - Checks `APP_VERSION` against the latest GitHub `main` release on startup (with a non-blocking 3-second timeout).
  - Prompts `Download and install vX.X.X now? (Y/N)` when a newer version is available and updates `enforcer.py`, `CHANGELOG.md`, `README.md`, and `LICENSE.txt` atomically without touching user settings or broker tokens in `C:\Users\<Username>\`.
- **Version Tracking (`APP_VERSION`):** Added version display (`v0.9.5`) to the Pre-Flight window title bar, HUD window title, and daily session log header.

---

## [v0.9.4] — 2026-10-30
### Added
- **90-Day Daily Session Log Archive (`~/enforcer_logs`):**
  - Automatically archives the previous day's `enforcer_log.txt` into `C:\Users\<Username>\enforcer_logs\enforcer_log_YYYY-MM-DD.txt` before starting a new daily log and prunes archives older than 90 days.
  - Right-clicking the **📂 View Log** button in Pre-Flight opens the 90-day archive folder in Windows Explorer.
- **Zero-Delay Dual-Snapshot Anti-Wick Confirmation:**
  - Compares live NBBO quote midpoint AND the broker's account position snapshot simultaneously on breach candidates: fires immediately (`0.0s` delay) when confirmed by both, or runs a fast `0.2s` re-verification poll when only a single trade print spiked.
- **NBBO Bid/Ask Price Clamping:** Clamps extended-hours and illiquid last-trade price ticks inside live `[Bid, Ask]` bounds (when spread is valid) to eliminate false unrealized PnL spikes from stale prints.
- **Per-Minute Lockout Voice Countdown:** Announces remaining minutes every whole minute (`"3 minutes remaining until unlock"`, `"2 minutes..."`, `"1 minute..."`) plus the `"30 seconds remaining"` warning.

---

## [v0.9.3] — 2026-10-29
### Added
- **Schwab 7-Day Token Renewal GUI Popup:** Replaced the terminal-only console prompt with a dedicated dark-themed OAuth renewal window (clickable **"1. Open Schwab Login Page"** button + redirect URL paste box) and added a **"🔄 Renew Token"** button in the API Keys wizard.
- **Interactive Hover Tooltips:** Added dark-themed hover explanation cards across all Pre-Flight controls, checkboxes, and risk fields.
- **Individual Alarm & Tier Checkboxes:** Added inline checkboxes to enable/disable individual Warning Alarms, Extended-Hours Profit Lock, and RTH Tiers 2/3/4 independently.
- **Built-In Audio Preview Tester:** Added a **Preview Audio Cue** dropdown + **🔊 Test** button in Card 3 to test sirens, chimes, and voice cues at current speaker volume.
- **Liability Waiver Audit Logging:** Added SHA-256 waiver integrity verification and timestamp logging on every session startup.

---

## [v0.9.2] — 2026-10-28
### Added
- **Customizable HUD Columns:** Added **📊 HUD Columns** selector dialog supporting up to 8 toggleable & reorderable metrics (`REALIZED PnL`, `OPEN PnL`, `NET PnL`, `TERMINATE LVL`, `$ TO TERMINATE`, `SESSION HIGH`, `FROM HIGH`, and `TRADES (W/L)` with win-rate percentage).
- **Upside Tier Chime & Emerald HUD Glow:** Plays a 4-note ascending chime and flashes the HUD status bar emerald green for 3 seconds whenever a closed winning trade unlocks a higher profit floor tier.
- **Spoken TTS Lockout Voice Cues:** Added Windows SAPI speech synthesis announcements on Penalty Box and Daily Floor lockouts.

---

## [v0.9.1] — Initial Closed Beta
### Added
- **Dual-Broker Architecture:** Full two-way parity between Charles Schwab (`schwab-py`) and Webull (`webull-openapi-python-sdk`) with independent per-account daily baselines.
- **Single-Trade Circuit Breaker (Open PnL Stop):** Automated equity liquidation (`MARKET` order in RTH `9:30–16:00 ET`; marketable `GTC_EXT` limit order in Extended Hours) and optional Penalty Box OS Cooldown Lock.
- **Tiered Daily Floor Ratchet:** Extended-Hours rulebook and 4-tier RTH profit ratcheting (`Tier 1 -> Tier 2 -> Tier 3 -> Tier 4 Trailing`) with automated platform kill-switch (`Thinkorswim` / `Webull Desktop`) and persistent Windows OS lockout.
- **Zero-Config Windows Launcher (`Launch_Enforcer.bat`):** Auto-detects or installs Python 3.12 via `winget` and installs required broker SDKs automatically.

