# PnL Enforcer Beta — Changelog

All notable updates, guardrail improvements, and broker adapter fixes are documented in this file.

---

## [v0.9.54] — 2026-11-13
### ⚡ Quick Summary
- **One-Click `Inspect Source / Diff ↗` Links:** Added an **`Inspect Source / Diff ↗`** button to the **Update Available** dialog, the **Release Notes** viewer, and the Pre-Flight footer (`Inspect Source ↗`) that opens the GitHub Gist `/revisions` diff page in your browser so security-conscious users can inspect the full source code and exact line-by-line changes before or after any update.
- **Background Update Modal & Full-File Verification Fixes:** Fixed a `NameError` (`hide_all_tooltips`) when opening the **Update Available** modal over the Pre-Flight window, verified full-file syntax (`compile()`) and end-of-file markers on 900 KB+ update payloads, and prioritized the user's primary `PATH` `pythonw.exe` in `Launch_Enforcer.bat`.

### 🔍 Detailed Breakdown
- **Source Code & Revision Diff Inspection (`get_source_diff_web_url`, `show_update_available_dialog`, `show_release_notes_dialog`):**
  - Added `SOURCE_DIFF_WEB_URL` and `BETA_SOURCE_DIFF_WEB_URL` pointing to the GitHub Gist `/revisions` side-by-side diff view for the active channel, wired to **`Inspect Source / Diff ↗`** buttons in the Update Available and Release Notes headers plus **`Inspect Source ↗`** in the Pre-Flight footer.
- **Updater & Launcher Hardening (`hide_all_tooltips`, `_fetch_available_update_payload`, `Launch_Enforcer.bat`):**
  - Added a module-level `hide_all_tooltips()` dispatcher wired to `show_preflight_window()` so opening `show_update_available_dialog(parent=parent_pf)` from `start_background_update_check()` never raises `NameError` or falls back to `input()`.
  - Guarded the CLI `input()` fallback in `show_update_available_dialog()` so it only runs when `parent is None` and `sys.stdin.isatty()` is `True`.
  - Increased the raw-stream fallback timeout in `_fetch_available_update_payload()` from `3s` to `8s` and verified both `'if __name__ == "__main__":'` and `compile(rem_txt, "enforcer.py", "exec")` before accepting downloaded updates.
  - Updated `Launch_Enforcer.bat` fast-path to check `where pythonw` on `PATH` first before scanning `%LocalAppData%\Programs\Python\Python3*` so multi-Python systems always launch with the primary `PATH` interpreter.

---

## [v0.9.46 – v0.9.53] — 2026-11-13
### ⚡ Quick Summary
- **All-Monitor 15-Second Penalty Box Briefing Screen:** Whenever a Penalty Box or Daily OS Lockout triggers (and during the **10-Second Dry-Run Lockout Test**), Enforcer now displays a full-screen **Penalty Box Briefing Card** across every connected monitor showing the exact breach trigger, live broker order-cancel & 100% flat-verification checklist, and a **15-second** countdown (counted as the first 15 seconds of your total lockout duration) before engaging the Windows OS Lock—or locking Windows immediately if clicked or bypassed.
- **Pre-Flight Settings Overhaul, Quick Layout Tour & Spotlight Pulse:** Grouped set-and-forget preferences inside Card 3's **`⚙ Preferences & Audio...`** modal, added a warm, low-noise **`✦ Quick Tour`** guide (automatically showing a *"What Moved"* map for existing users or a *60-Second Quick Start* for new users, with a ~6.8s sky-blue spotlight pulse on relocated controls), and added a top-bar **`👁 Privacy: OFF / ON`** screenshot toggle that masks account numbers & balances (`*******************` / `********** (Saved)`).
- **Instant Fast-Path Startup, Persistent Multi-Monitor HUD Position & Windowless Launch:** The floating HUD now remembers the exact monitor and screen coordinates where you last dragged it across restarts (`hud_x`, `hud_y`), `Launch_Enforcer.bat` hands off to `pythonw.exe` in ~15ms with zero background command prompt window (plus a live **`Show Background Debug Terminal`** toggle in **`⚙ Preferences & Audio...`**), and Pre-Flight opens on screen immediately using cached account metadata while running live balance sync and update checks asynchronously in the background.
- **Friendly Feature-Notice Popups & Tracked-Daytrade Tooltip Clarity:** Enabling **`Penalty Box OS Lock Cooldown`**, **`Lock Windows OS on Max Loss / Profit Stop`**, **`Enable Open PnL Auto-Flatten`**, or **`Auto-Flatten Equities on Max Loss / Profit Stop`** now opens a friendly *"How It Works & How to Test Safely"* walkthrough dialog with a **`Got It ✓`** confirmation, and Card 1/2 tooltips explicitly state that Auto-Flatten, App Kill-Switch, and OS Lock flat-verification strictly target tracked intraday positions while leaving Ignored swing positions untouched.
- **Exact Ignored Swing Portfolio PnL Isolation, Locked In-Trade `Realized PnL` & Cash-Flow Neutralization:** Pre-existing swing/ETF portfolios marked **`🛡️ IGNORE`** recognize `"COLLECTIVE_INVESTMENT"` ETFs (`SPY`, `QQQ`, etc.) and 4-decimal quote marks, `Realized PnL` stays 100% locked at closed-trade `settled_realized_pnl` while entering, scaling into, or holding an open trade until shares/contracts are partially or fully closed, and large diagnostic log uploads use a 30s timeout with JSON status verification — **huge shoutout to `/u/InvWithRed` for putting Enforcer through its paces today, sending detailed logs, and helping track down every one of these real-world edge cases!**
- **Moved API Setup, Tilt Filter, Alarms Only & Dynamic Profit-Lock Coloring:** Moved API key setup & 7-day token renewal into the **`BROKER:`** dropdown (plus clickable **`Token: X.Xd ↻`** readout in Card 3), tucked Card 1's micro-scratch filter behind **`⚙ Filter`**, promoted **`🔔 Alarms Only`** to a global caution-amber toggle beside the launch button, unified crimson styling across **`Max Open Loss ($)`** and **`Starting Max Loss ($)`**, and dynamically colored **`Trail Peak By ($)`** / **`Stop Level ($)`** boxes green only when the initial stop locks in green (`> $0`) and slate-blue when `<= $0`.
- **Active Profit Tier HUD Tag, LULD Halt Protection & Early-Unlock Re-Lock:** The HUD `DAILY STOP` column shows the live tier (`(T1)`–`(T4)`, `(EXT)`, `(EXT LOCK)`), preserves working RTH `MARKET` exit orders during halts (`HALT WATCH` defers App Kill/OS Lock until 100% flat), re-locks early screen unlocks within `0.20s` with exact remaining-time speech, and uses a gentle 2-tone disconnect chime.

### 🔍 Detailed Breakdown
- **All-Monitor Penalty Box Briefing Overlay (`PenaltyBoxBriefingOverlay`, `get_all_monitor_bounds`, `start_cooldown_lock`):**
  - Enumerates all physical monitors via Win32 `EnumDisplayMonitors` / `GetMonitorInfoW` (`get_all_monitor_bounds`) and renders a full-screen dark-slate Penalty Box card on every connected display during Open PnL Stop, Consecutive Loss Cooldown, Daily Rulebook Lockdown, and the 10-Second Dry-Run Lockout Test.
  - Displays live 2-stage enforcement progress (`Stage A`: working-order cancellation & broker 100% flat verification; `Stage B`: 15-second transition countdown to Windows OS Lock, counted as the first 15 seconds of the total lockout duration so a 2-minute lock transitions to Windows OS Lock with `1:45` remaining) and engages `LockWorkStation()` immediately if any mouse click, key press, close attempt, or focus switch is detected.
- **Pre-Flight UI, Quick Layout Tour, Privacy Mode & Dynamic Input Polish:**
  - Added **`✦ Quick Tour`** (`show_layout_tour_dialog` & `pulse_relocated_controls`) in the bottom-right footer (and once on first launch after layout updates), with locked window geometry when switching between *"What Moved"* and *"60-Second Quick Start"* and a 9-cycle sky-blue spotlight glow across all relocated controls.
  - Added friendly confirmation walkthroughs (`show_os_lock_feature_notice` & `show_auto_flatten_feature_notice`) when enabling **`Penalty Box OS Lock Cooldown`**, **`Lock Windows OS on Max Loss / Profit Stop`**, **`Enable Open PnL Auto-Flatten (Equities)`**, or **`Auto-Flatten Equities on Max Loss / Profit Stop`** (pointing users to the **10-Second Dry-Run OS Lockout Test**, **`🔔 Alarms Only`**, and **1-Share Live Testing**), and clarified Card 1 & Card 2 tooltips regarding tracked intraday vs. Ignored swing positions.
  - Moved Session Behavior, Audio/Voice Cues (`🔊 Test`), Poll Interval (with validation), Auto-Share Safe Logs, and **`Show Background Debug Terminal`** behind Card 3's **`⚙ Preferences & Audio...`** modal (`3. TODAY'S SESSION & BASELINE`), preserving focus/grab across nested confirmation popups.
  - Added persistent HUD screen coordinates (`hud_x`, `hud_y`, `get_saved_hud_position`) saved on drag and app close and clamped to the target monitor's work area on launch, updated `Launch_Enforcer.bat` + `set_debug_console_visible` so normal launches hand off to `pythonw.exe` in ~15ms while allowing instant live terminal toggling in Preferences (with the console `✕` Close button disabled via `SC_CLOSE`), and added cached account fast-startup (`cached_accounts`, `verify_accounts_live`, `start_background_update_check`) so the Pre-Flight window opens immediately without blocking on initial network/update checks.
  - Added dynamic stop-box coloring (`_refresh_dynamic_stop_box_colors`) in Cards 4 and 5 so **`Trail Peak By ($)`** and **`Stop Level ($)`** highlight emerald green only when the resulting initial stop is strictly `> $0` (`At Profit > Trail Peak By` or `Stop Level > 0`) and switch to neutral slate-blue when `<= $0`.
  - Added top-bar **`👁 Privacy: OFF / ON`** pill (with zero top-bar layout shift) to mask account labels in the top bar/dropdown and baseline dollar balances in Card 3 for safe screenshots, locked Pre-Flight window geometry when toggling **`Include Options in Auto-Flatten`**, and cleared `GlassStadiumButton` hover highlights when opening modal dialogs.
  - Added welcoming **`✨ Help Improve Enforcer — Auto-Share Safe Logs`** CTA in **`📜 Logs ▾`**, cleared background hover tooltips on modal open, and upgraded the Auto-Share Safe Logs modal, 10s Dry-Run Lockout modal, Consecutive Loss Cooldown notice, Broker API Setup Wizards, and Release Notes version picker to a calm sky-slate visual hierarchy.
  - Added API setup/token renewal directly to the **`BROKER:`** dropdown + clickable Card 3 **`Token: X.Xd ↻`** status, moved Tilt **`Min Loss` / `Win Reset`** behind Card 1's **`⚙ Filter`** pill, moved **`🔔 Alarms Only: OFF / ON`** into the bottom launch bar (with a caution-amber **`SAVE & LAUNCH (ALARMS ONLY)`** state), and unified crimson styling across **`Max Open Loss ($)`** (Card 1) and **`Starting Max Loss ($)`** (Cards 4 & 5) with uniform `At Profit → Stop / Trail` rows.
- **Ignored Swing Portfolio Isolation, In-Trade `Realized PnL` Lock & Cash-Flow Fixes (Schwab & Webull):**
  - Special thanks to **`/u/InvWithRed`** for putting Enforcer through its paces across live swing/ETF + intraday option sessions and sharing detailed diagnostic logs to help uncover and verify these edge cases:
  - Fixed `Realized PnL` drift on accounts holding large **`🛡️ IGNORED`** swing/ETF portfolios: `SchwabAdapter.fetch_account_data` now recognizes `"COLLECTIVE_INVESTMENT"` ETFs (`SPY`, `QQQ`, etc.) alongside `"EQUITY"`, preserves 4-decimal `lp` quote precision (`SchwabAdapter` & `WebullAdapter`), and neutralizes ignored holdings' intraday impact across live ticks, scale-ins, trims, and exits in `_apply_ignored_positions_to_snapshot`.
  - Locked `Realized PnL` (`_stabilize_mid_fill_realized_and_equity`) at closed-trade `settled_realized_pnl` whenever entering, scaling into, or holding an open trade (`not any_closed_or_reduced`), so option entry commissions or sub-second broker balance/mark differences never move `Realized PnL` until shares or contracts are partially or fully closed, and increased the diagnostic log webhook timeout (`_upload_sanitized_log_to_drive`) to 30s with JSON response status verification.
  - Added `_maybe_absorb_untouched_flat_fee_drift` + `has_any_filled_orders_today` (`SchwabAdapter` & `WebullAdapter`) with `_launch_fee_drift_checked` startup-only gating so overnight broker clearing/regulatory fee adjustments posted to a flat account with 0 filled orders today automatically align `start_equity` and `last_flat_equity` to `$0.00` PnL on first launch (and never re-trigger after a 9:30 AM or 4:00 PM rulebook switch), and updated `sanitize_log_for_export` to redact fee-drift baseline log lines.
  - Persisted intraday `anchor_cash_flow` per session across relaunches to neutralize same-day deposits and withdrawals (without double-counting or tripping when overnight pending deposits settle) and synced Webull equity/market-value marks during fast moves and scale-ins.
  - Fixed `DarkDropdownMenu` popup rendering (`BROKER`, `ACCOUNT`, `Logs`, `Voices`), deduplicated rapid-hover tooltips, and eliminated primary-monitor popup flash on modal dialogs.
- **Rulebook Ratchets, Halt Watch & Lockout Hardening:**
  - Added tier-aware HUD column headers/tooltips, tier-specific Post-Breach Review instructions, and first-poll `[RATCHET]` notifications on mid-session resume.
  - Added LULD halt working-order preservation + 2-poll stale-replica filter + passive `⏳ HALT WATCH` deferral, instant early-unlock detection with exact remaining time TTS callouts, queued non-overlapping speech, calm 2-tone (`660 Hz -> 440 Hz`) disconnect alerts, seamless file-backed Schwab token re-binding & in-place `token_invalid` self-healing after manual 7-day token renewals, and automatic Beta Channel changelog routing.

---

## [v0.9.45] — 2026-11-12
### ⚡ Quick Summary
- **Webull Fast Timeout Recovery (`reconnect_session`):** Eliminated redundant blocking `TradeClient` initializer HTTP calls on routine network read timeouts so Webull reconnects recover on the very next poll without cascading timeouts or interrupting active token state.
- **Guaranteed `[SESSION] Restored ... baseline from memory` Audit Log:** Ensured `load_config(log_restore=True)` always logs the restored session baseline (`Start`, `LastFlat`, `SessionHighPnL`, `W/L`) on mid-day launches even after the startup liability waiver check loads config early.

### 🔍 Detailed Breakdown
- **Lightweight Webull Timeout Reconnect (`WebullAdapter.reconnect_session`):**
  - Because `webull-openapi-python-sdk` already opens a fresh `requests.Session()` per HTTP call, routine network read timeouts no longer invoke `TradeClient(new_api)` (which previously fired extra blocking `ClientInitializer` HTTP calls during a network stall and assigned `self.api_client = new_api` before initialization completed).
  - Instead, routine timeouts refresh `_connect_timeout = 3.5` / `_read_timeout = 4.5` and verify/reload the local `~/conf/token.txt` token in-place with zero extra network calls, reserving a full `TradeClient` rebuild strictly for authentication/token errors (`401`/`403`/`unauthorized`/`token`/`expired`/`sign`) with an atomic client swap after initialization succeeds.
- **Unconditional Mid-Day Baseline Restore Logging (`load_config`):**
  - Updated `load_config(log_restore=True)` so `[SESSION] Restored <BROKER> baseline from memory: Start=$... | LastFlat=$... | SessionHighPnL=... | W: ... | L: ...` is always written to `enforcer_log.txt` when `log_restore=True`, even when `show_liability_waiver()` previously populated `start_equity` via `load_config(log_restore=False)`.

---

## [v0.9.43 & v0.9.44] — 2026-11-12
### ⚡ Quick Summary
- **In-Trade Settings Access (`IN TRADE` Mode):** Open Pre-Flight Settings anytime during an active daytrade to customize **HUD Columns**, adjust **Audio / Voice / Poll Interval**, or export **Logs** — while all enforcement and rulebook settings across **Cards 1, 2, 4, and 5** stay tamper-locked until your position is flat.
- **Live Background Enforcement & Real-Time Auto-Unlock:** Broker polling and stop enforcement continue uninterrupted while Settings is open, automatically unlocking all cards the instant your trade closes flat (or closing Settings if a stop triggers).
- **10-Second Dry-Run OS Lockout & Hardened Cooldown Protection:** Added **`Full 10s Dry-Run Lockout`** to the Card 3 `Voice / Cue` **`Test`** dropdown so you can test the siren, voice cues, Windows lock screen, and unlock chime while flat — and locked HUD/Pre-Flight close & settings buttons with a `0.35s` re-lock cadence during active lockouts.
- **Updated Liability Waiver & License (`v2026.11.12`):** Refreshed `LICENSE.txt` and the startup Assumption of Risk waiver with a high-legibility 5-section layout covering Equities, Options (Siren-Only default + opt-in BETA RTH Auto-Flatten), Ignored Swing Positions, `Alarms Only Mode`, and Post-Breach `DISARMED` mode.

### 🔍 Detailed Breakdown
- **In-Trade Settings Access & Enforcement Tamper-Lock (`is_in_trade_tamper_locked`, `refresh_smart_dimming`, `save_and_launch`):**
  - **HUD `IN TRADE` Settings Button:** While an active daytrade is open (`not is_flat`), the HUD Settings button transitions to an amber **`IN TRADE`** button (`state="normal"`), while the HUD **`✕`** Close button stays locked (`state="disabled"`).
  - **Cards 1, 2, 4, and 5 Locked (`IN TRADE — LOCKED` / `ACTIVE (LOCKED)` / `STANDBY (LOCKED)`):** All checkboxes and dollar/minute entry fields in Cards 1, 2, 4, and 5 are disabled while in a trade, with high-contrast amber/slate styling (`disabledforeground`) on armed guardrails so active stops remain easy to read.
  - **Card 3 & Top/Bottom Bar Protection:** Broker/Account switching, `API Keys`, Risk Presets (`Standard Full Risk` / `50% Low Energy`), `Restore Defaults`, `Save as Default`, `↺ Re-Zero Baseline` (`In Trade`), `Start Fresh on Rulebook Switch`, and `Ignore Pre-Existing Positions on Launch` are locked while in a trade. Opening **`Positions`** while in a trade opens in **`IN TRADE · READ-ONLY VIEW`** so an active daytrade cannot be switched to `IGNORE` mid-trade.
  - **Editable Utility Controls (`SAVE HUD & AUDIO >>`):** `HUD Columns`, `Logs ▾`, `Report Bug`, Release Notes, Voice/Audio cues, Upside Chime, API Poll Interval, and Auto-Share Safe Logs remain unlocked and savable while in a trade.
- **Live Background Enforcement & Real-Time State Transitions (`data_loop`, `_close_active_settings_window_on_breach`, `_tick_preflight_streak`):**
  - `data_loop()` continues polling the broker API while Settings is open (only pausing during an explicit broker/account reconfiguration wizard when flat).
  - If an Open PnL Stop, Consecutive Loss Cooldown, or Daily Stop triggers while Settings is open, `_close_active_settings_window_on_breach()` closes the Settings modal on the UI thread immediately so flatten/lockout execution is unobstructed.
  - `_tick_preflight_streak()` monitors `is_in_trade_tamper_locked()` at `200ms` intervals and automatically unlocks (or locks) Cards 1, 2, 4, and 5 in real time if a trade closes (or a working entry fills) while Settings is open.
- **Liability Waiver & License Terminology Update (`WAIVER_VERSION = "2026.11.12"`, `LICENSE.txt`):**
  - Updated `LICENSE.txt` and `show_liability_waiver()` to reflect all current functionality and risk disclosures, upgraded the startup waiver modal to the high-legibility 5-section badge layout, and bumped `WAIVER_VERSION` to `"2026.11.12"` so users acknowledge and log the updated SHA-256 hash once on update.
- **Penny-Exact Fill Neutralization on Ignored Position Trims & Exits (`_apply_ignored_positions_to_snapshot`, `_apply_preexisting_selection`):**
  - When an ignored position changes quantity (scale-in, partial trim, or full exit to `0`) on a poll where no tracked daytrade position changed quantity, `locked_impact` is anchored directly against `(raw_adj_eq - tot_open_pnl) - last_flat_equity` so any difference between the actual broker fill price and the prior poll's `last_seen_price` is 100% absorbed into `locked_impact` with `$0.00` drift on daytrade `Realized PnL`.
- **10-Second Dry-Run OS Lockout, Hardened Lockout Protection & Expanded Log Telemetry (`play_selected_test_audio`, `start_cooldown_lock`, `format_config_summary`, `init_daily_log`):**
  - Added **`Full 10s Dry-Run Lockout`** to the Card 3 `Voice / Cue` **`Test`** dropdown (with a confirmation dialog while flat) so traders can test the full siren, voice announcement, 10-second `LockWorkStation()` screen lock, and 3-tone unlock chime sequence without placing orders or affecting session stats.
  - Tightened the `LockWorkStation()` re-lock loop to `0.35s` and locked the HUD `✕` Close / `⚙ SETTINGS` buttons (and Pre-Flight close/launch during dry-runs) whenever an OS lockout cooldown is active so a lockout cannot be aborted during the Windows PIN-unlock transition window.
  - Isolated SAPI `.Speak()` from the `System.Speech` fallback in `speak_async()` so Windows desktop-switch audio transitions never re-trigger the sentence a second time.
  - Expanded `[CONFIG]` log lines to include `ResetSwitch`, `EH_Lock`, `T2`, `T3`, and `T4` profit ratchet thresholds, and stamped the OS build (`Win10`/`Win11`) and Python version in the daily session log header.

---

## [v0.9.42] — 2026-11-11
### ⚡ Quick Summary
- **🙌 Community Shoutout (`/u/InvWithRed`):** Huge thanks to Reddit beta tester **`/u/InvWithRed`** for catching the pre-existing swing/long-term position edge case and prompting the upgrades and position-scaling fixes in this release!
- **Ignore Pre-Existing Positions on Launch (`Swing / Hold` vs. `Daytrade` Filter):** New Card 3 setting (ON by default) that isolates pre-existing swing or long-term holdings at launch so they have `$0.00` impact on daytrade `Realized PnL`, `Open PnL`, `Net PnL`, and `Daily Stop` (across price swings, adds, trims, or closes), never lock `⚙ SETTINGS` / `✕` Close as `🔒 IN TRADE`, and are never auto-flattened or canceled.
- **Smart Mid-Day Re-Launch Detection (`⚡ NEW POSITION(S) FOUND TODAY`):** If you close the app briefly mid-day, enter a new intraday position, and re-open the app, Enforcer automatically detects and prompts only for the newly opened position (defaulting it to `⚡ TRACK AS DAYTRADE` while keeping your earlier morning swing positions `🛡️ IGNORED`).
- **Exact Partial Scale-Out Realized PnL Fix:** Fixed a key-name lookup in `_stabilize_mid_fill_realized_and_equity` (`"avg"` vs. `"avg_price"`) so partial trims/scale-outs on active daytrades credit realized PnL immediately without waiting until the final share is closed.

### 🔍 Detailed Breakdown
- **Pre-Existing Swing / Long-Term Position Isolation (`_apply_ignored_positions_to_snapshot`, `SchwabAdapter`, `WebullAdapter` — prompted by `/u/InvWithRed`):**
  - Added **`Ignore Pre-Existing Positions on Launch`** (`ignore_preexisting_positions`, default `True`) in **Card 3 (`3. SESSION & SYSTEM`)** alongside a live **`🛡️ Ignored (N) ▸` / `⚡ Tracked (N) ▸`** pill button.
  - **Morning Launch Prompt (`▶ 🛡️ PRE-EXISTING POSITIONS DETECTED IN ACCOUNT`):** When launching into an account with open positions for the first time today, prompts a per-ticker review modal where pre-existing holdings default to **`🛡️ IGNORE (Swing / Hold)`** (with 1-click toggle to **`⚡ TRACK AS DAYTRADE`**).
  - **Mid-Day Re-Launch Prompt (`▶ ⚡ NEW POSITION(S) FOUND TODAY — DAYTRADE OR SWING?`):** When today's session already exists (`had_saved == True`) and a brand-new position is found on re-launch, lists the new position at the top with a **`⚡ NEW POSITION TODAY`** badge defaulting to **`⚡ TRACK AS DAYTRADE`**, while keeping earlier morning holdings on **`🛡️ ALREADY IGNORED (SWING)`** (plus a 1-click **`Track New & Ignore Swings (Default)`** button).
  - **Zero-Impact Accounting & Execution Guardrails:** Ignored tickers are neutralized in `SchwabAdapter` and `WebullAdapter` across unrealized price moves, share/contract additions, partial trims, and full closes (`$0.00` daytrade PnL impact), excluded from `is_flat` / `🔒 IN TRADE` locks, and skipped during both `cancel_all_open_orders` and equity/option `flatten_equities`.
- **Partial Scale-Out Realized PnL Stabilization (`_stabilize_mid_fill_realized_and_equity`):**
  - Updated the scale-out average-cost lookup in `_stabilize_mid_fill_realized_and_equity` to read `"avg"` from `prev_pos_details`, ensuring partial trims on active daytrades update `Realized PnL` and `last_flat_equity` on the exact poll the trim occurs.

---

## [v0.9.41] — 2026-11-11
### ⚡ Quick Summary
- **Post-Daily-Breach Auto-Open Settings & Disarmed Protection:** Automatically opens Pre-Flight Settings after a Daily Stop lockout finishes with a friendly reminder to raise your Daily Max Loss or Re-Zero Baseline — or keep trading as-is with your old Daily Stop held in `DAY STOP: BREACHED (DISARMED)` mode so new entries never immediately stop you out.
- **Clear `BREACHED` HUD Display (`$ TO STOP` & Status Pill):** Replaced negative numbers like `$-449.91` in the `$ TO STOP` column with a two-line `BREACHED` / `-$449.91 OVER` readout and updated the HUD status pill to show `DAY STOP: BREACHED` when trading past a breached Daily Stop.
- **Loss Streak Reset on Daily Breach & Active Card 1 Guardrails:** Resets the Consecutive Loss Streak (`0/X`) when a Daily Breach Lockout occurs and keeps Card 1 (`Open PnL Auto-Flatten` & `Consecutive Loss Cooldown`) active even when the Daily Stop is disarmed.
- **Wider Default Release Notes & Update Prompt Windows:** Expanded both the Release Notes viewer and Update Available dialog to `1040 x 690` (resizable) so full summaries fit comfortably without scrolling.

### 🔍 Detailed Breakdown
- **Post-Daily-Breach Return Workflow (`_prompt_daily_breach_settings_on_unlock`, `show_daily_breach_return_notice`, `save_and_launch`):**
  - When a Daily Stop OS Lock countdown finishes (or a Daily Breach siren is muted), Pre-Flight Settings opens automatically with a dark-glass notice (`Review & Edit Limits ✓`, `↺ Arm Re-Zero Baseline ($0.00)`, or `Keep As-Is (Close Settings)`).
  - If you close Settings or click Save without raising your Daily Stop below your current Net PnL, the Daily Stop remains in `BREACHED (DISARMED)` mode (`is_locked_down = True`) so entering a new trade will not immediately flatten/lock you on a small tick, while Card 1 (`Open PnL Stop` & `Consecutive Loss Cooldown`) stays 100% active.
  - Automatically re-arms the Daily Stop if you raise your Daily Max Loss below your current balance, check `↺ Re-Zero Baseline`, or recover while flat above `floor + $150` buffer.
- **HUD `$ TO STOP` & Status Pill Clarity (`format_dist_to_stop_hud`, `get_medium_idle_button_text`, `get_full_idle_button_text`):**
  - Displays `BREACHED` on line 1 and `-$X.XX OVER` (or `+$X.XX BUF` inside the recovery buffer) on line 2 of the `$ TO STOP` column on a crimson (`#b03a2e`) background.
  - Updates the HUD status pill to `DAY STOP: BREACHED` (4-col) / `DAY STOP: BREACHED (DISARMED)` (5-col) / `⚠️ DAY BREACHED` (3-col).
- **Wider Release Notes & Update Dialogs (`show_release_notes_dialog`, `show_update_available_dialog`):**
  - Default window size increased to `1040 x 690` (`minsize(780, 500)`) and centered over Pre-Flight Settings.

---

## [v0.9.40] — 2026-11-11
### ⚡ Quick Summary
- **Consecutive Loss Cooldown ("Tilt Streak Stop") & Anti-Tilt Tamper Lock:** New opt-in Card 1 guardrail that flattens open positions and triggers a Penalty Box OS Lock after `X` consecutive losses (`>= -Min Loss $`) within `Y` minutes — with a friendly heads-up popup on arming and automatic tamper-locking (`🔒 STREAK X/Y — LOCKED`) whenever an active loss streak (`>= 1`) is underway.
- **Independent `Min Loss ($)` & `Win Reset ($)` Scratch Filters:** Separate user-settable thresholds in Card 1 (`Min Loss ($)` default `-$25`, `Win Reset ($)` default `+$10`) so tiny micro-scratch losses are ignored AND tiny `$0.30` scratch "wins" cannot wipe out an active loss streak.
- **Live `LOSS STREAK` HUD Column & Smooth 200ms Countdown Timer:** Added a 9th customizable HUD column (`LOSS STREAK`, e.g. `3 / 5` + live `RST 06:42` countdown), plus live 200ms-synced countdowns in the HUD `ARMED:` pill, bottom-left `STREAK:` badge, and Pre-Flight Card 3 telemetry strip.
- **Interactive Collapsible & Version-Jumping Release Notes Viewer:** Click any release banner or `Detailed Breakdown` header to collapse/expand it, jump directly to any version (`Release: ▾`, `▲ Newer`, `▼ Older`), or toggle `⚡ Summaries Only` / `Collapse All Releases`.
- **Fast Connection-Loss Detection & Live Auto-Reconnect Engine:** Enforces `4.5s` socket timeouts across both Schwab and Webull, alerts immediately on connection drops (`OFFLINE` / `RETRY #N`), rebuilds stale HTTP sessions automatically (`reconnect_session()`), and announces when back online.
- **Mid-Fill Cash/Position Desync & False Alarm Prevention (`WebullAdapter` & `data_loop`):** Eliminated false warning/floor alarms during multi-lot entries, adds, and scale-outs when broker cash balances update 150–350ms ahead of the positions endpoint.
- **Pre-Flight Card 1 & Card 3 UI Tidy-Up:** Renamed Card 1 to `1. TRADE & TILT STOPS`, moved `↺ Re-Zero Baseline` into Card 3's header, and paired `API Poll Interval` + `Auto-Share Safe Logs` on one row.

### 🔍 Detailed Breakdown
- **Consecutive Loss Cooldown / "Tilt Streak Stop" (`enable_consec_loss_cooldown`, `trigger_consec_loss_cooldown`):**
  - Added an opt-in **`Consecutive Loss Cooldown`** guardrail inside **Card 1 (`1. TRADE & TILT STOPS (Intraday Penalty Box)`)** (`enable_consec_loss_cooldown`, default `False`).
  - **4 User-Adjustable Parameters:**
    - **`[ X ] Losses` (`consec_loss_count`, default `3`):** Number of consecutive completed losing round-trip trades required to trigger the cooldown.
    - **`In (Mins)` (`consec_loss_window_mins`, default `15`):** Rolling time window (`Y` minutes) within which the `X` consecutive qualifying losses must occur.
    - **`Min Loss ($)` (`consec_loss_min_dollars`, default `-25`):** User-defined micro-scratch loss filter. Losses smaller than `-Min Loss ($)` (e.g. scratching out for `-$5` when `Min Loss ($)` is `-$25`) are ignored and never penalized toward the consecutive loss streak.
    - **`Win Reset ($)` (`consec_win_reset_dollars`, default `10`):** Independent user-defined minimum winning trade required to reset an active loss streak early (e.g. `+$10` means a `+$0.30` scratch green trade still counts in `W/L` but does **not** wipe out a `4/5` streak, while a `+$10+` win resets the streak to `0/5`). Both `Min Loss ($)` and `Win Reset ($)` participate automatically in **`Standard Full Risk`** (`-25` / `10`) and **`50% Low Energy`** (`-12` / `5`) presets.
  - **Friendly Arming Popup & Anti-Tilt Tamper Lock (`show_tilt_cooldown_lock_notice`, `is_tilt_streak_tamper_locked`):**
    - Clicking to enable **`Consecutive Loss Cooldown`** displays a friendly dark-glass reminder popup (`show_tilt_cooldown_lock_notice`) explaining upfront that the streak settings lock automatically during an active loss streak.
    - Displays a **`🛡️ Locks on active streak`** badge in Card 1's header when `Streak` is `0/X`.
    - As soon as an active loss streak is underway (`cur_s > 0`, e.g. `1/5`–`4/5`), the Card 1 header badge switches to **`🔒 STREAK X/Y (MM:SS) — LOCKED`** (counting down live) and disables modifying the Consecutive Loss Cooldown toggle, `Losses` count, `Min Loss ($)`, `Win Reset ($)`, `In (Mins)`, Penalty Box OS Lock Cooldown, `Alarms Only Mode`, `↺ Re-Zero Baseline`, or risk presets until the streak resets via a qualifying win (`>= +Win Reset $`) or the rolling countdown expires (`00:00`).
  - **Streak Reset & Enforcement Mechanics:**
    - Closing a qualifying winning trade (`delta >= abs(Win Reset $)`), letting timestamps age past `consec_loss_window_mins`, serving a Penalty Box cooldown, or re-anchoring the baseline (when `Streak == 0`) resets the rolling loss streak (`recent_loss_timestamps`) back to `0` (with explicit `[POS_CHANGE]` audit notes for qualifying win-resets, micro-scratch wins, and `$0.00` flat scratches).
    - When the `X`th consecutive qualifying loss closes within `Y` minutes, Enforcer cancels any working orders, confirms 100% flat (`flatten_equities`), and starts the shared Card 1 **Penalty Box OS Lock Cooldown** (`TILT STREAK LOCK`) with dedicated verbal announcement (`"Consecutive loss cooldown triggered. Locked out for X minutes."`).
- **4-Way Live Loss Streak & Smooth 200ms Reset Timer Telemetry (`get_loss_streak_status`, `_tick_loss_streak_hud`, `_tick_preflight_streak`):**
  - **High-Precision 200ms Countdown Sync:** Upgraded both the HUD countdown ticker (`_tick_loss_streak_hud`) and the Pre-Flight Settings countdown ticker (`_tick_preflight_streak`) to poll `time.time()` at `200ms` resolution while a streak is active and only redraw widgets when the formatted string changes — eliminating 1-second timer phase drift and background-thread overwrite jitter.
  - **Optional `LOSS STREAK` HUD Column (`loss_streak`):** Displays `3 / 5` on line 1 and `RST 06:42` (`CLEAR` when `0 / 5`) on line 2 with dynamic caution amber (`#d35400`) and final-warning crimson (`#b03a2e` when 1 loss away from lockout) backgrounds.
  - **HUD Bottom `ARMED:` Status Pill & Hover Tooltip:** Dynamically updates `TILT STOP (3/5 · 06:42)` on the bottom bar (`TILT(3/5 06:42)` in 4-column HUD mode) even when the `LOSS STREAK` column is not enabled, and shows both the next-loss drop timer (`-1`), full-reset timer (`0/X`), and `🔒 Tamper-Locked` status when hovering the status pill.
  - **HUD Bottom-Left Clickable Capsule (`STREAK:`):** Added `STREAK: 3/5 (06:42)` to the bottom-left capsule click cycle (`W/L -> STREAK -> FLAT -> BASE`).
  - **Pre-Flight Card 3 Live Telemetry Strip:** Displays `Streak: 3/5 (06:42)` inline next to `W:` and `L:` in Card 3 and ticks down live every second while the Pre-Flight window is open.
- **Interactive Collapsible & Version-Jumping Release Notes Viewer (`_insert_formatted_changelog` & `_build_changelog_nav_bar`):**
  - **Clickable Collapsible Sections:** Every green version header (`▼ v0.9.40 — 2026-11-11  [Click to Collapse]`) and every `▼ 🔍 DETAILED BREAKDOWN  [Click to Hide Details]` header can be clicked to collapse or expand in place (`elide=True`).
  - **Top Release Navigation Bar:** Added a `Release:` scrollable version-picker dropdown, **`▲ Newer`** / **`▼ Older`** version-skip buttons, a 1-click **`⚡ Summaries Only`** toggle (hides all detailed breakdowns across every version so only Quick Summaries remain), and a **`▶ Collapse All Releases`** / **`▼ Expand All Releases`** toggle.
- **Fast Connection-Loss Detection & Live Auto-Reconnect (`SchwabAdapter`, `WebullAdapter`, `data_loop`):**
  - Configured explicit `4.5s` HTTP socket timeouts on both `SchwabAdapter` (`self.client.set_timeout(4.5)`) and `WebullAdapter` (`connect_timeout=3.5, timeout=4.5`) so dropped internet connections fail fast instead of hanging the HUD polling thread.
  - Preserves `~/schwab_token.json` on startup if `get_account_numbers()` encounters a network/DNS/socket timeout while offline (only deleting the token file on true OAuth/token rejection).
  - Shows an immediate amber retry notice on the first failed poll (`⚠️ CONNECTION HICCUP — RETRYING BROKER API (ATTEMPT #1)...`), transitions to `OFFLINE` / `RETRY #N` with siren + verbal alert (`"Warning. Connection lost. Attempting to reconnect automatically."`) on poll #2+, rebuilds stale HTTP client sessions via `reconnect_session()`, updates the live `ATTEMPT #N` counter on every poll, and announces `"Connection restored. Enforcer is back online."` with an emerald glow upon recovery.
- **3-Layer Mid-Fill Cash/Position Desync & False Alarm Prevention (`WebullAdapter.fetch_account_data`, `_stabilize_mid_fill_realized_and_equity`, `data_loop`):**
  - **Layer 1 (`WebullAdapter.fetch_account_data`):** Removed the `0.25s` inter-endpoint sleep between `_call_get_positions()` and `_call_get_balance()` (which was creating a 250ms window where rapid multi-lot fills updated `cash_bal` after positions were already snapshotted) and added `total_raw_pos_mkt_val` cross-checking against `raw_eq + (total_pos_mkt_val - total_raw_pos_mkt_val)` whenever `cash_bal + total_pos_mkt_val` diverges by `> $15.00` during an in-flight fill (matching `SchwabAdapter`).
  - **Layer 2 (`_stabilize_mid_fill_realized_and_equity`):** Rejects 1-to-2 poll `Realized PnL` spikes caused by broker endpoints settling cash 150–350ms before `/positions` reflects newly bought/added/sold shares — covering pre-position cash deductions while flat (`0 -> 0` before shares appear), mid-entry/scale-in fills (`0 -> +Q` or `+Q1 -> +Q2` where zero shares were sold), and mid-scale-out cash double-counting (`+Q1 -> +Q2` where sale proceeds for the next lot land in cash before `/positions` decrements quantity, preventing false `[REARM]` and warning alarms).
  - **Layer 3 (`data_loop` Anti-Wick Verification):** Extended the `0.2s–0.35s` anti-wick re-verification check to also cover flat floor breaches (`is_flat=True`) and un-triggered warning alarms (`warn_breach_cand`) whenever share quantities just changed (`qty_just_changed`) or the NBBO book does not confirm the spike.
- **Pre-Flight Card 1 & Card 3 UI Tidy-Up:**
  - Renamed Card 1 to **`▶  1. TRADE & TILT STOPS (Intraday Penalty Box)`** with shared **`└─ Penalty Box OS Lock Cooldown`** duration.
  - Replaced the standalone *Re-Zero Today's Starting Baseline* checkbox row in Card 3 with a compact toggleable **`↺ Re-Zero Baseline`** (`✓ Re-Zero Armed`) stadium pill button in the top-right header of Card 3 (`c3_hdr_row`).
  - Consolidated **`API Poll Interval (s)`** and **`Auto-Share Safe Logs (Beta Opt-In)`** onto a single bottom row in Card 3, reclaiming two vertical rows in the left column.

---

## [v0.9.31] — 2026-11-10
### ⚡ Quick Summary
- **1-Click Safe Log Upload (`📤 Send Today's Safe Log Now`):** Upload today's balance-redacted diagnostic log directly from the `📜 Logs ▾` menu in Pre-Flight.
- **Opt-In Daily Auto-Share (`Auto-Share Safe Logs`):** Strictly opt-in (`False` by default) background uploader that shares yesterday's balance-redacted log on startup after explicit user consent.
- **Anonymous 6-Char Tester ID:** Tags uploaded beta logs with a random 6-character hex ID (`anonymous_tester_id`) with zero personal or account balance data.

### 🔍 Detailed Breakdown
- **Google Drive Beta Telemetry Uploader (`_upload_sanitized_log_to_drive` & `_maybe_upload_prior_day_sanitized_log`):**
  - **Anonymous 6-Character Tester ID (`anonymous_tester_id`):** Automatically generates and persists a random 6-character hex identifier (`uuid.uuid4().hex[:6]`) in `~/enforcer_config.json` on startup so balance-redacted diagnostic logs from the same beta tester share a consistent anonymous prefix without collecting any personal or identifiable data.
  - **1-Click Manual Safe Log Upload (`📤 Send Today's Safe Log Now`):** Added at the top of the **`📜 Logs ▾`** menu in Pre-Flight to scrub today's session log in memory (`sanitize_log_for_export`) and upload it asynchronously in a background daemon thread with a dark-glass status popup on completion.
  - **Strictly Opt-In Daily Auto-Share (`Auto-Share Daily Safe Logs (Beta Opt-In)`):** Added a synchronized checkable toggle in both **`📜 Logs ▾`** and **Card 3 (`3. SESSION & SYSTEM SETTINGS`)** (`auto_share_sanitized_logs`, `False` by default). Enabling it displays a dark-glass confirmation modal with a **`Preview Safe Log`** button (opening the latest sanitized log in Notepad), **`Enable Auto-Share`**, and **`Cancel`**.
  - **Non-Blocking Startup Auto-Uploader:** When opted in, checks `~/enforcer_logs/sanitized/` on startup for the most recent prior-day redacted log (`YYYY-MM-DD < today`) and uploads it once in a background daemon thread (`last_uploaded_sanitized_log`), handling Google Apps Script `HTTP 302`/`405` `googleusercontent.com` redirects cleanly and failing silently if offline.

---

## [v0.9.30] — 2026-11-10
### ⚡ Quick Summary
- **Options BETA Waiver Readability Upgrade:** Restyled the Options Auto-Flatten BETA risk waiver modal with numbered coral badges, bold amber headers, horizontal dividers, and highlighted key terms.

### 🔍 Detailed Breakdown
- **Options Auto-Flatten BETA Waiver Readability & Typography (`show_options_flatten_beta_waiver`):**
  - Replaced the flat `Arial 9` wall-of-text label inside the Options Auto-Flatten BETA Risk Waiver modal with a structured, high-legibility 5-section layout (`Arial 10` / `10 bold` / `Consolas 10 bold`) featuring distinct coral section numbers (`1.`–`5.`), bold amber section headers, generous line and paragraph spacing, `1px` `#222d3d` horizontal section dividers, and inline badge highlights on key warning terms (`experimental BETA feature`, `BUY_TO_CLOSE / SELL_TO_CLOSE`, `WIDE BID-ASK SPREADS`, `SEVERE SLIPPAGE`, `Regular Trading Hours (9:30 AM – 4:00 PM ET)`) while preserving the full waiver text and SHA-256 verification hash unchanged.

---

## [v0.9.29] — 2026-11-10
### ⚡ Quick Summary
- **Experimental BETA Options Auto-Flatten Toggle:** Opt-in Card 2 toggle (`OFF` by default) to include open option contracts in RTH Market order liquidations (`9:30 AM – 4:00 PM ET`).
- **Mandatory Options Risk Waiver & SHA-256 Audit:** Requires explicit waiver acceptance warning of option bid-ask spread slippage and single-leg spread unwinding before arming.
- **Short-Legs-First Dual-Broker Execution:** Both `SchwabAdapter` and `WebullAdapter` close short option legs (`BUY_TO_CLOSE`) before long option legs (`SELL_TO_CLOSE`) to prevent margin rejections.

### 🔍 Detailed Breakdown
- **Experimental BETA Options Auto-Flatten Toggle & Cryptographic Risk Waiver (`enable_flatten_options`, OFF by Default):**
  - Added an opt-in **`└─ Include Options in Auto-Flatten (BETA — RTH Market Orders)`** toggle inside **Card 2 (`2. DAILY STOP ACTIONS`)** of the Pre-Flight window (`enable_flatten_options`, default `False`). By default, option contracts remain **Siren-Only**.
  - **Mandatory BETA Options Risk Waiver & Audit Log (`show_options_flatten_beta_waiver`):** Enabling the toggle displays a dedicated modal assumption-of-risk dialog explicitly warning that Options Auto-Flattening is **BETA**, detailing wide bid-ask spread slippage on unpriced Market orders (`BUY_TO_CLOSE` / `SELL_TO_CLOSE`), single-leg liquidation mechanics on multi-leg option spreads, Regular Trading Hours (`9:30 AM – 4:00 PM ET`) restrictions, and broker API/fill limitations. Acceptance requires checking an explicit acknowledgment box and is logged to `enforcer_log.txt` (`[WAIVER]`) and persisted in `enforcer_config.json` with a timestamp, version tag (`2026.11.10-BETA`), and SHA-256 hash (`options_waiver_sha256`), verified automatically at startup alongside the main Welcome Waiver.
  - **Two-Way Broker Parity (`SchwabAdapter` & `WebullAdapter`):**
    - Added `get_open_option_positions()` and `submit_option_liquidation_batch()` across both `SchwabAdapter` (`schwab.orders.options.option_buy_to_close_market` / `option_sell_to_close_market`) and `WebullAdapter` (`order_v3.place_order` single-leg `OPTION` `MARKET` orders with `BUY_TO_CLOSE` / `SELL_TO_CLOSE`, plus `_parse_option_contract_meta()` supporting OCC symbols and `legs` payloads).
    - **Short-Legs-First Execution (`qty < 0` before `qty > 0`):** Both adapters sort and submit `BUY_TO_CLOSE` orders on short option contracts before `SELL_TO_CLOSE` orders on long option contracts to prevent broker "naked short option" margin rejections when unwinding spreads or covered positions.
  - **Anti-Wick Re-Verification & Flat-Before-Lock Safeguards:**
    - Enforces the `0.2s` anti-wick re-verification poll (`not has_options` excluded from the 0s fast-path) before triggering any breach while holding options.
    - Both `flatten_equities()` and the `2s`/`15s` post-lock watchdog (`_run_post_lock_watchdog()`) double-confirm that 100% of open equities AND option contracts are flat before allowing any Windows OS Lock or trading app termination. If options are held outside RTH (`9:30 AM – 4:00 PM ET`) or fail to close, Enforcer holds off on OS Lock / App Kill and sounds the continuous manual intervention siren.
  - **HUD & Config Telemetry:** Updated `format_config_summary()` (`OptFlat=ON(BETA)` / `OptFlat=OFF`) and the HUD `ARMED:` status pill (`+ OPT(BETA)`) to clearly indicate when BETA Options Auto-Flatten is armed.

---

## [v0.9.28] — 2026-11-10
### ⚡ Quick Summary
- **Webull `HTTP 429` Rate-Limit Prevention:** Cut Webull position-query calls in half on trade transitions and added `2.10s` spacing + `2.5s` `429` backoff with last-known-good caching across both brokers.
- **Enhanced Log Path & Header Scrubbing:** Masks JSON-escaped Windows user paths (`C:\\Users\\...`) as `~` and redacts SDK auth headers (`x-access-token`, `x-signature`).

### 🔍 Detailed Breakdown
- **Webull Rate-Limit (`HTTP 429`) Prevention, Backoff & Broker Parity (`WebullAdapter` & `SchwabAdapter`):**
  - Removed the redundant second `_call_get_positions()` call inside `WebullAdapter.fetch_account_data()` when share quantities change (`probe_qty_map != prev_q_map`), keeping the `0.25s` settlement pause before `_call_get_balance()` while cutting `/trading/assets/positions/list` requests in half during entries, scale-outs, and exits.
  - Added a `2.10s` minimum inter-request spacing guard on Webull's `/trading/assets/positions/list` endpoint so `2s` polling jitter never trips Webull's per-endpoint burst limiter.
  - Added `2.5s` `HTTP 429` rate-limit backoff, throttled `[WARN]` logging (at most once per 30s), per-account last-known-good snapshot caching (`<= 15s`), and cached open-equity fallback (`<= 10s`) during `get_open_equity_positions()` across both `WebullAdapter` and `SchwabAdapter`.
  - Prevented `TradeClient` from resetting `webull.core` logger levels to `DEBUG`/`INFO` or creating `webull_trade_sdk.log` in the working directory, removed the redundant `DataClient` startup initialization, and explicitly pinned Webull's token storage to `~/conf`.
- **Log Scrubber Hardening (`_mask_user_path` & `_scrub_log_line`):**
  - Extended `_mask_user_path()` to mask JSON-escaped double and quadruple backslash Windows user paths (`C:\\Users\\...` and `C:\\\\Users\\\\...`) as `~`.
  - Extended `_scrub_log_line()` to redact JSON-serialized SDK auth headers (`x-access-token`, `x-signature`, `x-app-key`, `authorization`).
  - Added `Cols=N` to `format_config_summary()` so `[CONFIG]` log lines record the active HUD column count.

---

## [v0.9.27] — 2026-11-10
### ⚡ Quick Summary
- **Aligned `$ TO STOP` Digits & `5px` Leash Bar:** Centered `$ TO STOP` numbers on the exact same baseline as all other HUD columns with a sleek `5px` bottom progress bar.
- **Tapered `6–8` Column HUD Widths:** Kept 6, 7, and 8-column HUD layouts compact (`840px` / `900px` / `960px`) and added a concise `4-Col` status summary.

### 🔍 Detailed Breakdown
- **HUD `$ TO STOP` Vertical Baseline Alignment & `5px` Leash Bar (`rebuild_hud_columns` / `_redraw_hud_leash_canvas`):**
  - Aligned `$ TO STOP`'s dollar readout (`val_lbl`) to the exact same full `36px` vertical height and dead-center baseline (`y = 25..61`) as all other HUD columns while placing the `5px` glowing leash bar (`hud_leash_bar`) along the bottom `5px` (`y = 56..61`) with zero digit overlap and zero gap above the bottom bar.
- **Tapered Multi-Column HUD Widths (`6–8` Columns) & Tiered `ARMED:` Status Pill (`compute_hud_width` / `get_medium_idle_button_text`):**
  - Tapered column width scaling when adding `6`, `7`, or `8` columns (`6 cols = 840px`, `7 cols = 900px`, `8 cols = 960px` instead of `960 / 1,120 / 1,280`) while preserving `480px` (`3-Col Small`) and `800px` (`5-Col Standard`).
  - Added a medium-detailed status summary for `4-Column` mode (`ARMED: SCHWAB + OPEN (-$250/2m) + DAY FLAT + LOCK (5m)`).

---

## [v0.9.26] — 2026-11-10
### ⚡ Quick Summary
- **Small 3-Column (Compact) HUD Mode:** New 1-click `Small 3-Col (Compact)` preset (`480x88` footprint — 40% narrower than standard 5-column mode).
- **Live Hover-Over HUD Status Tooltip:** Hovering the HUD status pill reveals a dark-slate card with full armed stops, active Rulebook, and alarm/lockout details.

### 🔍 Detailed Breakdown
- **Optional Small 3-Column (Compact) HUD & Live Hover-Over Status Tooltip:**
  - Added a **`Small 3-Col (Compact)`** preset button alongside **`Standard 5-Col`** in **`📊 HUD Columns`** (`open_hud_columns_dialog`), with dynamic active cyan highlight tracking (`refresh_hud_preset_highlight`) and fixed button widths (`auto_width=False`) so switching modes never shifts or stretches the Pre-Flight window.
  - Lowered the minimum HUD width clamp from `800px` to `480px` (`max(480, len(active_cols) * 160)`), shrinking the 3-column HUD footprint by 40% (`480x88` vs. `800x88`) while keeping **`⚙ SETTINGS`** and **`✕`** anchored on the right.
  - When in Compact HUD mode (`<= 3` columns), the middle status capsule displays concise labels (`● ARMED`, `● ALARMS ONLY`, `MUTE ALARM`, `🔒 LOCKED: Xs`, `★ FLOOR RAISED ★`) and provides a dark-slate hover-over tooltip card (`attach_hud_mute_tooltip`) showing the full armed configuration summary, active Rulebook & poll interval, and active alarm or cooldown details.

---

## [v0.9.25] — 2026-11-09
### ⚡ Quick Summary
- **High-Contrast HUD Alarm & Ratchet Banners:** Fixed warning alarm pill rendering so active sirens display a bright warning-gold capsule (`#eab308`) with dark `#090d16` text.

### 🔍 Detailed Breakdown
- **HUD Warning Alarm & Upside Ratchet Banner High-Contrast Readability (`trigger_alarm` / `HudCapsulePill`):**
  - Fixed a color-parsing bug where `trigger_alarm()` passed `bg="yellow"` (a 6-character named color) to `_hex_to_rgb_tuple()`, causing it to fall back to the dark-slate `#141820` fill with `fg="black"` text. Active warning alarms now render with a bright warning-gold capsule fill (`#eab308`), `#fef08a` border highlight, and crisp dark `#090d16` text, and named colors are normalized via `_normalize_color_hex6()`.
  - Updated all 6 steps of `trigger_upside_tier_glow()` to use `#ffffff` white text over the `#10452c` emerald capsule.

---

## [v0.9.24] — 2026-11-08
### ⚡ Quick Summary
- **Custom Dark-Slate Dropdown Menus:** Replaced Windows system white-bordered menus with custom borderless dark-slate dropdowns (`DarkDropdownMenu`) across all 5 selectors.
- **9:30 AM ET RTH Switch & `W/L` Badge Default:** Aligned the Regular Hours Rulebook switch to `9:30 AM ET` and defaulted the HUD bottom-left badge to `W/L`.

### 🔍 Detailed Breakdown
- **Custom Borderless Dark-Slate Dropdown Menus (`DarkDropdownMenu`):**
  - Replaced native Win32 `tk.Menu` popups across all 5 dropdowns (`BROKER`, `ACCOUNT`, `📜 Logs ▾`, `Voice`, and `Audio Cue`) with a custom borderless `tk.Toplevel` dropdown (`DarkDropdownMenu`) featuring a crisp `1px` `#334155` dark-slate border, `#141820` fill, and `#1e293b` row hover highlight (eliminating Windows' thick white system menu border).
  - Multi-monitor safe downward positioning (`+{x}+{y}`) and window-relative tooltip bounds so menus and tooltips never flip upward on secondary monitors.
- **HUD Left Capsule Defaulted to `W/L`:**
  - Defaulted the HUD bottom-left capsule to **`W/L`** (`W: X (%) | L: Y (%)`) on startup (clicking cycles through `W/L -> FLAT: $... -> BASE: $...`).
- **Regular Trading Hours Rulebook Switch Aligned to `9:30 AM – 4:00 PM ET` (`is_rth()`):**
  - Aligned the Regular Hours Rulebook switch (`is_rth()`), Card 3's *Start Fresh on Rulebook Switch (`9:30 AM & 4:00 PM`)*, Card 4's subtitle (*Active before `9:30 AM` and after `4:00 PM ET`*), and Card 5's header (*`5. REGULAR HOURS RULEBOOK (9:30 AM – 4:00 PM)`*) to the standard `9:30 AM ET` US market open.

---

## [v0.9.23] — 2026-11-06
### ⚡ Quick Summary
- **Frosted Dark-Glass UI Overhaul:** Added anti-aliased `6px` squircle buttons (`GlassStadiumButton`), custom vector checkboxes (`GlassCheckbutton`), and single left-accent card bars (`NeonBarCanvas`).
- **Unified Top Bar & Multi-Color Card 3 Telemetry:** Combined Broker + Account into one sleek top bar and added color-coded Baseline, Token expiry, and `W/L` telemetry in Card 3.

### 🔍 Detailed Breakdown
- **Modern `6px` Rounded-Rectangle (Squircle) Button Engine (`_render_glass_pill_image` / `_get_glass_pill_photo` / `GlassStadiumButton`):**
  - Built a cached `PIL` / SDF anti-aliased button renderer featuring `6px` rounded-rectangle geometry (`corner_radius=6`), one-way top-down micro-fades (`#1c212b -> #141820`), and razor-sharp `1px` top catch-light borders.
- **Custom Dark-Glass Checkboxes (`GlassCheckbutton` / `make_glass_checkbutton`):**
  - Replaced legacy Windows sunken square checkboxes across Pre-Flight and all setup dialogs with a custom `tk.Label`-backed dark-glass checkbox widget (`GlassCheckbutton` + `_get_glass_checkbox_photo`) featuring an anti-aliased `18x18` rounded dark-glass icon and vector `✓` checkmark.
- **Pre-Flight Top Bar, Calm Left-Accent Cards & Setup Wizard:**
  - Un-nested the top-left **`BROKER / ACCOUNT`** container into one unified dark-slate `6px` rounded bar with a glowing emerald status orb (`●`).
  - Upgraded Card 3's live telemetry row into a multi-color inline strip (`Baseline`, `Token`, `W:`, `L:`) and expanded the **Schwab & Webull API Credential Setup Wizard** with un-truncated step-by-step instructions and one-click `📋 Copy` badges.

---

## [v0.9.22] — 2026-11-06
### ⚡ Quick Summary
- **Single-Instance Kernel Guard:** Prevents launching a second copy of PnL Enforcer simultaneously so duplicate flatten orders or double-counted trades can never occur.

### 🔍 Detailed Breakdown
- **Windows Kernel Single-Instance Guard (`_ensure_single_instance_or_exit`):**
  - Acquires an OS-level named mutex (`Local\PnLEnforcerBeta_SingleInstance_Mutex`) at startup so two instances of PnL Enforcer can never run simultaneously on top of each other, preventing duplicate flatten orders and double-logged `[POS_CHANGE]` / `W/L` trade counts. If a user launches the app while an instance is already open, Enforcer logs a `[GUARDRAIL]` block, displays an always-on-top alert dialog, and exits cleanly.

---

## [v0.9.21] — 2026-11-06
### ⚡ Quick Summary
- **US Eastern Time (`EST`/`EDT`) Auto-Sync:** Syncs all market-hour transitions (`9:30 AM` & `4:00 PM ET`) to New York time regardless of your PC's local timezone.
- **Webull Scale-In/Out Settlement Sync:** Eliminates 1-poll transient PnL spikes on Webull during partial fills.
- **Instant GitHub Gist Update Discovery:** Resolves commit-pinned raw URLs via the GitHub Gist API for zero-delay update checks.

### 🔍 Detailed Breakdown
- **US Eastern Market Time Synchronization (`get_eastern_now()`):**
  - Anchored `is_rth()`, `is_market_hours()`, `is_after_hours()`, and `get_today_str()` directly to US Eastern Time (`America/New_York`, with built-in zero-dependency `EST`/`EDT` Daylight Saving Time handling) instead of local computer clock time.
- **Webull Partial-Fill Balance & Position Settlement Sync (`WebullAdapter.fetch_account_data`):**
  - Eliminated 1-poll transient `Realized` / `Net` PnL spikes on Webull when scaling in or out of an open position by querying positions before account balance, performing an automatic `0.25s` settlement re-sync whenever share quantity changes mid-trade, and requiring a `0.35s` anti-wick confirmation whenever a breach candidate coincides with a share-quantity change.
- **Zero-Delay Gist API Update Discovery (`check_for_updates_cli`):**
  - Queries the un-cached GitHub Gist API (`api.github.com/gists/...`) to resolve the exact commit-pinned `raw_url` before falling back to CDN raw URLs.

---

## [v0.9.20] — 2026-11-06
### ⚡ Quick Summary
- **Two-Stage Post-Lock Straggler Watchdog (`2s` + `15s`):** Verifies 0 open shares at `T+2s` and `T+15s` after Windows OS lock engages, sweeping any late straggler fills automatically.
- **Selectable TTS Voices & Dark Title Bars:** Added `Zira`, `Mark`, and `David` voice selection, native Windows dark title bars, `$ TO STOP` neon leash bar, and `Alarms Only Mode`.

### 🔍 Detailed Breakdown
- **Two-Stage Post-Lock Straggler Watchdog (`2.0s` + `15.0s`) with Verbal Confirmations:**
  - **Stage 1 (`T + 2.0s`):** Performs the initial post-lock flat check against `get_open_equity_positions()` and announces *"Initial flat check passed."*
  - **Stage 2 (`T + 15.0s`):** Runs a second delayed verification sweep `15.0s` after the OS lock engages to catch late ECN fills or unhalt prints and announces *"15 second sweep clear, account confirmed flat."*
  - **Emergency Straggler Sweep:** If straggler shares are detected on either sweep, Enforcer announces *"Warning, straggler shares detected, flattening now"*, executes an emergency `flatten_equities()` sweep, and if unable to confirm flat, aborts the OS lock and sounds the emergency siren.
- **Selectable Windows OneCore TTS Voices, Dark Mode Title Bars & `Alarms Only Mode`:**
  - Added a voice selector in Card 3 (`Zira`, `Mark`, `David`), applied `DWMWA_USE_IMMERSIVE_DARK_MODE` to all windows, added the glowing `$ TO STOP` progress bar, retroactive 90-day sanitized log archiving (`~/enforcer_logs/sanitized/`), and the `Alarms Only Mode` master observation toggle in Card 2.

---

## [v0.9.15] — 2026-11-04
### ⚡ Quick Summary
- **3-Layer Flat Confirmation:** Requires explicit `HTTP 200` position verification, a `0.8s` pre-lock double-confirm, and a `2.0s` post-lock watchdog before and after locking Windows.
- **In-App Release Notes Viewer:** Added `View Release Notes` link in the Pre-Flight footer.

### 🔍 Detailed Breakdown
- **3-Layer Flat Confirmation & Post-Lock Watchdog (Schwab & Webull Parity):**
  - **Layer 1 — Explicit `HTTP 200` Flat Verification:** Both broker adapters return `None` (instead of `[]`) on any non-`200` HTTP status or network exception.
  - **Layer 2 — 0.8s Pre-Lock Settlement Double-Confirmation:** `flatten_equities()` waits `0.8s` after detecting `0` open equity shares and re-queries the broker API before declaring the account flat.
  - **Layer 3 — 2.0s Post-Lock Watchdog Sweep (`_run_post_lock_watchdog`):** Queries the broker API `2.0s` after Windows OS lock engages to triple-confirm `0` open shares remain.
- **Pre-Flight Footer Version Badge & Release Notes Viewer (`show_release_notes_dialog`):**
  - Added a clickable **`View Release Notes`** link in the Pre-Flight bottom bar.

---

## [v0.9.14] — 2026-11-04
### ⚡ Quick Summary
- **Signed (`-` / `0` / `+`) RTH Profit Ratchet Stops:** Tiers 2 & 3 now support negative (tightened loss stop), zero (`$0` breakeven), or positive (`+$250` locked profit) stop levels.
- **Unified "Daily Stop" Labels & `📜 Logs ▾` Menu:** Renamed HUD columns to `DAILY STOP` and `$ TO STOP` and grouped log tools into `📜 Logs ▾`.

### 🔍 Detailed Breakdown
- **Unified "Daily Stop" Terminology & Signed Tier 2/3 Ratchets:**
  - Renamed HUD column headers to **`DAILY STOP`** and **`$ TO STOP`** and enabled signed (`-` / `0` / `+`) stop levels in RTH Tiers 2 and 3 with automatic config migration.
  - Consolidated `View Log`, `Export Safe Log`, and `Open Archived Logs` into the **`📜 Logs ▾`** dropdown menu.

---

## [v0.9.10 – v0.9.13] — 2026-11-03
### ⚡ Quick Summary
- **Custom `.ico` Badge & GUI Update Dialog (`v0.9.12–v0.9.13`):** Added the custom `enforcer.ico` taskbar icon and dark-themed "Update Available" GUI popup with live Changelog preview.
- **1-Click `🐞 Report Bug` & Webull SDK Auto-Installer (`v0.9.10–v0.9.11`):** Added 1-click sanitized log export + Tally bug report launcher and self-healing Webull SDK installation on Python 3.12–3.15.

### 🔍 Detailed Breakdown
- **Application Icon (`enforcer.ico`) & GUI Update Popup (`show_update_available_dialog`):**
  - Added multi-resolution Windows `.ico` badge (`16×16` through `256×256`) and replaced the console `Y/N` update prompt with a dark-glass GUI modal previewing `CHANGELOG.md`.
- **One-Click `🐞 Report Bug` & Self-Healing Broker SDK Installer:**
  - Generates `enforcer_log_sanitized.txt`, copies it to the clipboard, highlights the file in Explorer, and opens the bug report form. Self-heals missing `schwab-py` or `webull-openapi-python-sdk` dependencies on launch.

---

## [v0.9.5 – v0.9.9] — 2026-11-02
### ⚡ Quick Summary
- **Share-Safe Sanitized Logs (`v0.9.6`):** Redacts all account balances (`$[REDACTED]`), Windows usernames (`~`), and order IDs (`...1234`) while keeping PnL and guardrail events intact.
- **Extended-Hours Rulebook & 4:00 PM Transition Guard (`v0.9.5`):** Recalibrates rulebook High-Water Mark at `9:30 AM` and `4:00 PM ET` transitions and adds automatic startup version checks.

### 🔍 Detailed Breakdown
- **Privacy Scrubbing (`enforcer_log.txt` & `enforcer_log_sanitized.txt`):**
  - Masks `USER_HOME` paths as `~`, masks order IDs to last 4 digits, strips `/accounts/<hash>` URL segments and OAuth tokens, and redacts all total equity figures in exported safe logs.
- **Extended Hours Rulebook, 4:00 PM Transition Guard & Structured Tooltips:**
  - Recalibrates active Rulebook HWM at `4:00 PM ET` while preserving full-day `SESSION HIGH`, and normalizes multi-paragraph hover tooltips (`attach_tooltip`).

---

## [v0.9.1 – v0.9.4] — Initial Closed Beta
### ⚡ Quick Summary
- **Dual-Broker Guardrail Engine (`Schwab` & `Webull`):** Real-time PnL monitoring, Single-Trade Open PnL Stop, 4-Tier RTH Profit Ratchet, Extended-Hours Rulebook, and persistent Windows OS Lockout.
- **Anti-Wick Confirmation & 90-Day Log Archive:** Dual-snapshot NBBO anti-wick verification, customizable 8-column HUD, spoken TTS countdowns, and 90-day daily log archiving.

### 🔍 Detailed Breakdown
- **Core Architecture (`v0.9.1 – v0.9.4`):**
  - Full two-way parity between Charles Schwab (`schwab-py`) and Webull (`webull-openapi-python-sdk`) with independent per-account daily baselines in `~/enforcer_config.json`.
  - Automated equity liquidation (`MARKET` in RTH `9:30–16:00 ET`; marketable `GTC_EXT` limit in Extended Hours), NBBO bid/ask clamping, `0.2s` anti-wick verification, 90-day log archiving (`~/enforcer_logs`), Schwab 7-day OAuth GUI renewal popup, and spoken TTS lockout countdowns.
