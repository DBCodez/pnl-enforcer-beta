# PnL Enforcer Beta — Changelog

All notable updates, guardrail improvements, and broker adapter fixes are documented in this file.

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

