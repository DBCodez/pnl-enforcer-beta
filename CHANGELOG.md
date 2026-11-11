# PnL Enforcer Beta — Changelog

All notable updates, guardrail improvements, and broker adapter fixes are documented in this file.

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
