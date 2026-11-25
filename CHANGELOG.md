# PnL Enforcer Beta — Changelog

All notable updates, guardrail improvements, and broker adapter fixes are documented in this file.

---

## [v0.9.87.1] — 2026-11-24
### ⚡ Quick Summary
- **Thanksgiving / Black Friday Early-Close UI Polish (`1:00 PM` RTH / `5:00 PM` Extended Hours) & Card 4 Header Fix:** Updated Pre-Flight session greetings, `FLIGHT PLAN` tooltips, Card 3/4/5 session labels, HUD status tooltips, and transition log text to dynamically display **`1:00 PM ET`** RTH / **`5:00 PM ET`** Extended-Hours schedules on NYSE early-close days (including across Midnight ET overnight rollovers) and trimmed Card 4's title to `(Pre & After-Hours)` so it never clips.

### 🔍 Detailed Breakdown
- **Dynamic Early-Close & Holiday Schedule Copy (`format_preflight_session_greeting`, `build_preflight_card4_subtitle`, `build_preflight_card5_title`, `build_flight_plan_summary`, `refresh_active_rulebook_highlight`, `data_loop`):**
  - Displays `"⏸ Market Closed (NYSE Holiday)"` on NYSE holidays like Thanksgiving (`2026-11-26`), reflects `1:00 PM Early Close` pre-market/RTH copy and `5:00 PM ET` extended-hours close + `"🌙 Market Closed for Evening"` on early-close dates like Black Friday (`2026-11-27`), dynamically switches `build_flight_plan_summary()` and HUD tooltips between `4:00 PM` and `1:00 PM`, refreshes Card 3/4/5 and idle footer copy automatically across Midnight ET / session boundaries, and logs `"1:00 PM Early-Close Extended-Hours Transition"` in `data_loop`.
- **Card 4 Pre-Flight Title Fit (`make_card`):**
  - Shortened Card 4's header to **`▶  4. EXTENDED HOURS RULEBOOK (Pre & After-Hours)`** so `"rs)"` no longer clips before the `STANDBY` / `• ACTIVE NOW` pill.

---

## [v0.9.87] — 2026-11-24
### ⚡ Quick Summary
- **Anti-Wick Escalation Protection (`data_loop`, Schwab & Webull):** Closed a loophole where a poll that initially crossed only a Warning Alarm (`Warn 1`/`Warn 2`) or Open PnL Stop and dipped past a stricter threshold (`Open PnL Auto-Flatten` or `Daily Stop`) on the 0.2s verification fetch could fire the escalated flatten/lockout on a single unconfirmed reading. Escalated stops now run one bounded confirmation pass (with `0s` extra delay whenever equity NBBO book quotes already confirm) before touching working orders.
- **~0.7s Faster Schwab Flatten Preparation (`cancel_all_working_orders`) + Flatten Timing Telemetry:** Runs Schwab's `120h` and `58d WORKING` GTC order queries concurrently during emergency flattens so working orders cancel faster, and adds single-line `[PERF]` sub-step timing breakdowns (`peek`, `cancel`, `refetch`, `submit`) to pinpoint broker API latency.
- **Clearer Diagnostic Upload Limit Notice (`429`):** When the Safe Log / Bug Report server hits a Tester ID's daily upload cap (`HTTP 429`), the popup now clearly displays **`DAILY UPLOAD LIMIT REACHED`** instead of **`CONNECTION UNREACHABLE`**, while still saving a local copy and clipboard backup.

### 🔍 Detailed Breakdown
- **Escalation-Safe Anti-Wick Confirmation, Deferred Alarm Seed Preservation & Non-Grace Parity (`_eval_breach_state`, `evaluate_stop_decisions`, `data_loop`, `_call_adapter_fetch_account_data`):**
  - Unified breach candidate and confirmation math in `_eval_breach_state()` so Snapshot #1, Pass #1, and Pass #2 all evaluate non-grace `open_pnl` (`_launch_grace_syms` excluded) identically.
  - Added a bounded Pass #2 confirmation whenever Pass #1 newly crosses an escalated destructive stop (`LOCKDOWN` when Snapshot #1 did not breach Daily Floor, or `OPEN_PNL_FLATTEN` when Snapshot #1 only hit a Warning), added explicit fail-safe handling when a re-verify poll returns `None` or cached data (carrying breach state across `_deferred_breach_carry` so consecutive live polls still breach cleanly with zero infinite deferral), moved `WebullAdapter.fetch_account_data(pace_as_verify=True)` onto the faster `1.15s` verify slot (`WEBULL_POS_MIN_INTERVAL_SEC`) during re-verifies, and deferred Warning Alarm `triggered_alarms` seeding (`defer_alarm_seeds=True`) until actions actually execute so deferred polls never silently consume Warning 1/2 sirens.
- **Concurrent Schwab Cancel Lookups & Flatten `[PERF]` Breakdown (`SchwabAdapter.cancel_all_working_orders`, `flatten_equities`):**
  - Overlapping Schwab's `120h` and `58d WORKING` order fetches eliminates sequential wait time before canceling resting orders, and `flatten_equities()` now logs `peek_ms`, `cancel_ms`, `refetch_ms`, and `submit_ms` in `[PERF]`.
- **Rate-Limit Aware Diagnostic Telemetry (`_upload_sanitized_log_to_drive_detailed`, `show_telemetry_upload_result_dialog`):**
  - Preserves `_upload_sanitized_log_to_drive() -> bool` while returning `(ok, err_kind)` from `_upload_sanitized_log_to_drive_detailed()` so both Bug Reports and manual Safe Log uploads distinguish `"rate_limited"` (`429`) from `"unreachable"`.

---

## [v0.9.86] — 2026-11-24
### ⚡ Quick Summary
- **Public GitHub Repo as Primary Source (`main` & `beta`):** Switched **`Inspect Source ↗`**, web **`Open Full Changelog ↗`** links, `Launch_Enforcer.bat` fresh-install downloads (now including `enforcer.ico`), and background/manual update checks (`raw.githubusercontent.com`) to use the public **`DBCodez/pnl-enforcer-beta`** GitHub repository first—eliminating redundant Gist REST API lookups while keeping Secret Gists as automatic failover mirrors.

### 🔍 Detailed Breakdown
- **GitHub-First Web Links, Single-Request Update Check & Backup Gist Failover (`GITHUB_REPO_WEB_URL`, `get_changelog_web_url`, `get_source_diff_web_url`, `_fetch_remote_doc_bytes`, `_fetch_available_update_payload`, `_is_bat_beta_channel_text`, `_rewrite_bat_bytes_for_beta`, `Launch_Enforcer.bat`):**
  - Updated `CHANGELOG_WEB_URL` / `BETA_CHANGELOG_WEB_URL` (`blob/main/CHANGELOG.md` / `blob/beta/CHANGELOG.md`), `SOURCE_DIFF_WEB_URL` / `BETA_SOURCE_DIFF_WEB_URL` (repo root / `tree/beta`), and `src_diff_lbl`'s tooltip to point directly to `https://github.com/DBCodez/pnl-enforcer-beta`.
  - Updated `_fetch_available_update_payload()` to read the first `4 KB` of `raw.githubusercontent.com/.../enforcer.py` first (`1` lightweight request when up to date, ignoring HTML error pages missing `APP_VERSION`, and validating full downloads via `_validate_enforcer_source_bytes()` with automatic failover to the channel's Secret Gist mirror).
  - Updated `_is_bat_beta_channel_text()`, `_rewrite_bat_bytes_for_beta()`, and `relocate_desktop_install()` so Beta-channel launchers pointing to either `BETA_GITHUB_RAW_BASE` or `BETA_GIST_BUNDLE_ID` retain Beta channel identity cleanly across updates and Desktop relocations, and updated `Launch_Enforcer.bat` bootstrap downloads to pull from `main` on GitHub first with automatic Gist failover.

---

## [v0.9.85] — 2026-11-24
### ⚡ Quick Summary
- **10x Faster Mid-Day Relaunch Sync (`~0.5s` vs. `12s`) + Instant `~0.4s` HUD PnL Paint:** Relaunching after a break where trades executed off-session now checks the fast `36h` order window first instead of downloading 58 days of broker order history (`~4.8 MB`) upfront—escalating to `58d` only if an older multi-day GTC order filled while you were away—and paints your live Realized/Open/Net PnL onto the HUD in `~0.4s` without waiting on order-history catch-up.
- **Hardened `58d` Order-History Timeout, Single-Flight Lock & Tri-State W/L Retry (Schwab & Webull):** Extended `58d` order-history read timeouts (`12.0s` read timeout without slowing `4.5s` account/flatten calls), eliminated duplicate unlocked `/orders` dogpiles, prevented transient `/orders` blips from ever dropping off-session W/L counts, and removed duplicate `API authenticated` log lines on quick launch.
- **Optional 1-Click Desktop Tidy-Up & Shortcut Relocator (Shoutout to `T$MAC`!):** Running PnL Enforcer loose on your Windows Desktop now gently offers a one-time optional prompt to tuck all app/update files into `~\PnL_Enforcer` (or a folder you choose) and leave a single clean **`PnL Enforcer`** shortcut icon on your Desktop — or click **`Keep on Desktop`** and it will never ask again (while staying available anytime under `📜 Logs ▾ -> 📁 Move App off Desktop & Create Shortcut...`).

### 🔍 Detailed Breakdown
- **Smart `36h`-First Reconstruction With Tight Fee-Band Gate (`_reconcile_off_session_activity`, `_bg_preflight_broker_sync`, `on_account_switch`):**
  - Queries the `36h` window (`fast_recent_only=True`) first across `<30h` off-session gaps even when `abs(actual_off_delta) >= $0.01`, accepting `36h` immediately when Path A `_try_reconstruct(..., strict_36h_fees=True)` (including `trim_cands` boundary-overlap retry) matches live positions 100% and satisfies `-min(max_fee_tol, strict_neg_tol) <= fee_res <= +$0.02` (`strict_neg_tol = round(0.06 + 0.000035 * sell_notional + 0.00025 * sold_eq_shares + 0.80 * opt_contracts, 2)`), and escalating by replacing `36h` with `58d` (`strict_36h_fees=False`) whenever an older `>36h` GTC leg or two-leg GTC bracket leaves unexplained position or residual deltas (while returning `False` with zero state mutation when `allow_network=False`).
- **Immediate `~400ms` Poll #1 Live-Balance HUD Preview (`_paint_poll1_preview_if_valid`, `data_loop`):**
  - Schedules a read-only `update_gui()` preview (`evaluate_stop_decisions(..., suppress_mutations=True)`, `spark_snap=None`, guarded by `_poll_still_valid()` and matching `(poll_epoch, poll_broker, poll_acct, session_key)`) right after midnight rollover, `force_reanchor`, `pending_baseline_revert`, and `9:30 AM` / `4:00 PM` rulebook transitions settle on `was_poll_1_launch`, displaying live PnL immediately while order-history catch-up runs.
- **Per-Request `58d` Read Timeout, Lock-Timeout Guard & Tri-State Deferred W/L Retry (`SchwabAdapter._get_orders_window_cached`, `WebullAdapter._get_orders_window_cached`, `has_non_ignored_closing_fills_since`, `_off_session_pending_boundary`, `_stabilize_mid_fill_realized_and_equity`):**
  - Uses `httpx.Timeout(4.5, read=12.0)` (`SCHWAB_ORDERS_58D_READ_TIMEOUT_SEC`) per request on `58d` Schwab order queries without mutating shared client timeouts, raises single-flight `_orders_fetch_lock.acquire(timeout=13.0)` (`ORDERS_FETCH_LOCK_WAIT_SEC`) returning `None` cleanly on waiter timeout, logs sanitized `[WARN]` timings (`type(e).__name__` / HTTP status), and stamps a `2.0s` (`ORDERS_WINDOW_FAIL_COOLDOWN_SEC`) negative cooldown only from the fetching thread across both `SchwabAdapter` and `WebullAdapter`.
  - Converted `has_non_ignored_closing_fills_since()` to tri-state (`True` / `False` / `None` on `/orders` failure) in both adapters and added `_off_session_pending_boundary` (`OFF_SESSION_DEFER_MAX_RETRIES = 5`) so Poll #1 settles live equity/PnL/stops immediately while retrying `/orders` on subsequent polls (`preserve_live_equity=True`) instead of misclassifying transient `/orders` failures as `"0 closing fills"`.
- **Clean Pre-Flight Sync Abort & Atomic Auth Log Pop (`_flush_bg_auth_if_launched`, `_bg_preflight_broker_sync`):**
  - Checks `_bg_sync_abort()` before `58d` escalation and `has_non_ignored_closing_fills_since()`, and only calls `_enqueue_postlaunch_preflight_auth(*bg_p)` when `pf_timer_state.pop("bg_auth_pending", None)` returns a tuple.
- **Optional Desktop Tidy-Up, Adopt Mode & `$`-Safe Shortcut Relocator (`is_running_directly_on_desktop`, `_get_user_desktop_dirs`, `_resolve_tidy_target_dir`, `_is_verified_enforcer_app_file`, `_create_windows_lnk_shortcut`, `relocate_desktop_install`, `prompt_desktop_tidy_dialog`):**
  - Detects exact root-Desktop execution across standard `<USER_HOME>\Desktop`, OneDrive KFM Desktop, and `HKCU\...\User Shell Folders\Desktop` via `winreg.ExpandEnvironmentStrings` (`_expand_win_env_vars_percent_only`, avoiding `os.path.expandvars` `$VAR` expansion on usernames containing `$`), while returning `False` for subfolders on the Desktop.
  - Verifies strict PnL Enforcer content ownership before touching any file (leaving personal Desktop files untouched), preserves Beta vs. Main channel identity via mandatory `Launch_Enforcer.bat` verification, supports **Adopt Mode** (`dst_ver >= src_ver`) so an existing equal-or-newer folder install and its `.prev` rollback backup are never downgraded, creates an atomic `WindowStyle=7` `PnL Enforcer.lnk` shortcut via child-process env vars (`CREATE_NO_WINDOW`) before removing any Desktop files (zero-delete abort on failure), coordinates cleanly with background update/icon workers via `_desktop_tidy_in_progress`, and persists `"desktop_tidy_dismissed"` across launches without re-nagging.
- **Privacy Sanitizer `rev2`, Bug-Report Scrubbing & Updater Safety (`_redact_balance_figures`, `sanitize_user_report_text`, `sanitize_log_for_export`, `_sync_sanitized_log_archive`, `_cap_sanitized_log_for_upload`, `_upload_sanitized_log_to_drive`, `_is_git_repo_checkout`, `_is_valid_launcher_bat_bytes`):**
  - Extends balance redaction (`rev2`) to catch negative margin/debit balances (`Cash=$-...`, `Baseline anchored to: $-...`), automatically upgrades pre-`rev2` sanitized log archives on startup/export, scrubs user-entered bug-report descriptions & contact fields against accidental token/path/balance pastes, routes Safe Log & bug-report uploads through an edge-rate-limited Cloudflare relay (`BETA_TELEMETRY_WEBHOOK_URL`) capped cleanly at `2.2 MB` with a `PnL-Enforcer/<APP_VERSION>` `User-Agent`, validates `Launch_Enforcer.bat` / `enforcer.ico` payloads before overwriting on update, and skips automatic startup overwrites inside `.git` repository checkouts.

---

## [v0.9.84] — 2026-11-24
### ⚡ Quick Summary
- **Smarter Webull `401` / Gateway Resilience (Shoutout to `T$MAC`!):** Fixed upstream Webull `401 UNAUTHORIZED` gateway wobbles falsely triggering `"BROKER TOKEN EXPIRED — RESTART APP TO RE-LOGIN"`, kept `WebullAdapter` client rebuilds tightly time-boxed so a pending 2FA check can never freeze stop monitoring, and added clear `"WEBULL KEYS REJECTED — CHECK KEYS / PC CLOCK"` guidance only if `401`s persist ~30 seconds.
- **Calm Flap-Storm Audio Protection (Schwab & Webull):** When an unstable broker connection flaps repeatedly inside 60 seconds, Enforcer now speaks a single calm `"Broker connection is unstable. I'm watching it."` notice instead of repeating disconnect/restore voice prompts and chimes on every blip—while still keeping yellow HUD alerts live and breaking through with audio immediately if an outage stays down `>= 3` attempts (`~6s+`).
- **No More Secret Startup Broker Switching:** Removed automatic cross-broker fallback during startup (`run_startup_broker_connect`) and added automatic retry backoff (`1.5s`, `3.0s` for Webull; `1.5s` for Schwab) on transient startup blips so Enforcer never overwrites your active broker to the secondary broker or pops an unrequested OAuth browser login.
- **Time-Agnostic `PnL CURVE` (Pause While Flat) & Dropdown Click Polish:** Stopped `PnL CURVE` from appending duplicate 45-second points while 100% flat so idle gaps between trades never squish your active price action into the left edge, and eliminated a rare background `[TCL_ERR]` (`_on_top_button1`) when switching away from an open dropdown menu.
- **Revert to Original Daily Baseline (`Preferences & Audio`):** If you use **`↺ Re-Zero Baseline`** mid-day and later want your true full-day numbers back, a tucked-away **`↺ Revert to Original Daily Baseline...`** option inside `Preferences & Audio` restores today's original morning equity baseline, full-day high/low, W/L count, and stitched PnL curve safely—while protecting against surprise instant lockouts (`Restore & Call It a Day` option if already past your Daily Stop), rulebook reset bypasses, and swing-position PnL leaks.
- **Off-Session Qualifying Win `TiltStreak` Reset:** Closing Enforcer during an active Consecutive Loss streak and returning after closing an off-session qualifying win (`>= +Win Reset $`, with no subsequent qualifying losses) now automatically clears your old losing streak across restarts while keeping off-session losses penalty-free.

### 🔍 Detailed Breakdown
- **Broker-Aware Poll Auth Classifier & Webull Token Guard (`_classify_poll_auth_error`, `_format_disconnect_alarm_copy`, `_validate_webull_token_file`, `WebullAdapter.reconnect_session`, `is_disconnect_alarm_reason`):**
  - Classified Webull `401` / `unauthorized` / `invalid credentials` / `ERROR_CHECK_TOKEN_ENABLE` / `ERROR_INIT_TOKEN` / `sign` errors as `auth_transient` (never triggering Schwab OAuth `"BROKER TOKEN EXPIRED"`), while keeping Schwab `invalid_grant` / `unsupported_token_type` / `refresh_token` / `"token expired"` / `"token rejected"` / `"safety buffer"` immediately hard and giving bare Schwab `401` errors 1 silent `reconnect_session()` token-file reload before escalating at `>= 3` consecutive `401`s (removed bare `"expired"` substring matching).
  - Updated `data_loop()` to skip unnecessary Attempt #1 full SDK rebuilds on Webull `401`s (running full reinit at `att == 3 or att % 6 == 0`), updated `WebullAdapter.reconnect_session()` to pass `token_check_duration_seconds=8` & `token_check_interval_seconds=2` (`TypeError`-guarded for mocks) without carrying stale `old_tok` across full reinits, validated `~/conf/token.txt` line 3 (`NORMAL`) + expiry before light-path injection via `_validate_webull_token_file()`, and added `"AUTH/GATEWAY"` / `"KEYS REJECTED"` to `is_disconnect_alarm_reason()` so all auth/gateway alerts route through the calm 2-note disconnect loop and preempt cleanly under real risk sirens.
- **Paired Flap-Storm Audio Throttle (`_evaluate_disconnect_flap_start`, `_handle_disconnect_recovery`, `_maybe_expire_disconnect_flap_quiet`, `_is_disconnect_audio_suppressed`):**
  - Added a 60s sliding flap window (`>= 3` drops/60s -> quiet mode until `>= 30s` continuous stability—clearing drop history across all 30s+ healthy intervals—or `_bump_adapter_epoch()` reset), gated `sound_disconnect_alert_loop()`, Settings modal one-shot disconnect alerts, and restore speech/chimes behind paired `_disc_audio_announced` tracking so `"Connection restored"` is never spoken for an unannounced drop, and enforced an `att >= 3` prolongation breakthrough so multi-poll outages always alert audibly without touching risk sirens.
- **Transient Startup Retry & Primary-Broker Preservation (`_is_transient_startup_auth_error`, `connect_broker_adapter`, `run_startup_broker_connect`):**
  - Retries transient startup `authenticate()` failures with fresh adapter instances (`2` retries at `1.5s`, `3.0s` for Webull; `1` retry at `1.5s` for Schwab; never retrying `DeferredAuthRequired`, cancelled OAuth, or `force_wizard`), and removed silent cross-broker fallback in `run_startup_broker_connect()` so Pre-Flight always opens on the configured `active_broker` with zero unintended `save_config()` mutations.
- **Pause-While-Flat `PnL CURVE` & Synchronous-Flush Safe Unbind (`_record_pnl_curve_point`, `_compact_flat_pnl_curve_pts`, `_load_pnl_curve_for_session`, `_safe_unbind`):**
  - Gated the `45s` periodic sparkline checkpoint with `(not is_flat_now)` and deduplicated identical flat `force=True` restart commits so sitting flat for 30+ minutes never crowds prior trades into the leftmost pixels, while `_compact_flat_pnl_curve_pts()` collapses legacy trailing flat runs on reload (`len >= 2 -> 1`, interior identical runs `>= 3 -> (first, last)`).
  - Updated `_safe_unbind()` to defer `deletecommand(funcid)` via `after(500, ...)` instead of `after_idle(...)`, preventing synchronous `update_idletasks()` calls inside click handlers from deleting an already-snapshotted `top_ref` `<Button-1>` handler mid-dispatch.
- **Original Daily Baseline Archive & Safe Revert (`_baseline_archive`, `_manual_reanchor_pending`, `_archive_baseline_before_reanchor`, `_fold_segment_into_baseline_archive`, `_get_baseline_revert_block_reason`, `_apply_pending_baseline_revert`, `describe_active_floor`):**
  - Tracks manual `↺ Re-Zero Baseline` explicitly via `_manual_reanchor_pending` (so fresh morning startup anchoring never creates a phantom archive), captures immutable morning root state (`orig_start_equity`, `orig_anchor_cash_flow`, extremes, W/L, pre-reanchor `ignored_positions`, `active_shift`, and stitched curve) inside `data_loop()` (`save_session_state()` persists `"baseline_archive"` safely across restarts), and folds intermediate segments cleanly across multiple same-day re-anchors (clearing stale prior-segment `rb_reset_s0` / `rb_reset_seg_max` markers).
  - Enforces identical flat/lockout/cooldown/commit-today/tilt-streak/ignored-swing-unchanged gates across Preferences UI (`_sync_prefs_modal_state`), `save_and_launch()`, and `data_loop()` with transactional `(ignored_positions, anchor_cash_flow)` rollback on live drift past the stop, keeps `has_reset_at_open` / `has_reset_at_close` monotonic, pre-seeds crossed warning alarms, and evaluates counterfactual restored floors via `describe_active_floor(start_eq=..., hwm_eq=...)` offering **`Keep Current View`** vs **`Restore & Call It a Day`** (`done_for_today=True` paired with silent `"DONE_RESTORE"` lock via `_is_done_today_display_active()` so live backstops remain intact while avoiding surprise OS lockouts).
- **Chronological Off-Session `TiltStreak` Reset (`_reconcile_off_session_activity`):**
  - Reconstructs cleanly through pre-save `-2s` boundary-overlap fills (dropping stray pre-shutdown closing fills when strict end-position and fee checks verify an exact match), prunes expired `recent_loss_timestamps` in place (`consec_loss_window_mins`), and resets `recent_loss_timestamps` on reconstructed post-shutdown qualifying wins (`>= +consec_win_reset_dollars`) **only** when no subsequent qualifying loss (`abs(d_pnl) >= consec_loss_min_dollars`) occurred—preserving inferred net-delta fallback's strict anti-tamper invariant when per-trade order is unavailable—then persists immediately via `save_session_state()` and refreshes Pre-Flight lock dimming and HUD pills automatically.

---

## [v0.9.83] — 2026-11-23
### ⚡ Quick Summary
- **Live Card 5 Ratchet Ladder Preview (`RTH` & `Ext-Hours`):** Added an interactive step-and-trailing chart directly inside Card 5 that redraws as you type Tier 1–4 stops, highlights tightened/green floors & clamped steps cleanly, switches automatically between `Card 5 (RTH)` and `Card 4 (Ext-Hours)`, tracks your live `Rulebook High`, and collapses anytime with one click (`▾ Hide`).
- **Opt-In HUD `PnL CURVE` Sparkline Column:** Added **`PnL CURVE`** to `📊 HUD Columns` so you can monitor your intraday Net PnL curve with `$0` breakeven, `Session High`, and smart Anti-Pancake Stop scaling (pinning a subtle bottom marker when your Daily Stop is far away and revealing the true-scale Stop line as you approach or trail profit), persisting cleanly across mid-day restarts.
- **Reliable Repeat Disconnect Alerts & Risk-Siren Priority Protection:** Fixed an old `triggered_alarms` dedup entry from your first `CONNECTION LOST` recovery silently blocking the 2-note disconnect tone and yellow HUD alarm banner on later disconnects in the same session, and protected active high-priority Stop / Manual-Options risk sirens from ever being overwritten by a mid-siren API blip.
- **Rock-Steady Pre-Flight Columns, Zero-Glitch Dropdown Unbinds & Cleaner Logs:** Fixed Card 3's settings summary line nudging Pre-Flight columns when toggling **`🚨 Breach Sim: ON`** (preventing mid-word clipping like `Breach Si`), fixed a rare background `[TCL_ERR]` when clicking top-bar buttons while a dropdown is open, clarified warning-only anti-wick checks (`"No warning alarm triggered."`), and preserved full `(read timeout=...)` details in disconnect logs.

### 🔍 Detailed Breakdown
- **Card 5 Single-Canvas Ratchet Preview (`_preview_stop_at_peak`, `compute_ratchet_preview_model`, `ENABLE_RATCHET_PREVIEW`):**
  - Evaluates the exact piecewise `describe_active_floor()` / `_get_effective_rth_tier_stops()` step & T4/Ext trailing logic inside a screen-aware `96px` chart (`52px` compact fallback on `< 860px` screens, keeping Pre-Flight within `<= 785px` logical height on full displays and `<= 740px` on compact laptops), with tactile `RTH` / `EXT` / `▾ Hide` pills, zone-aware cursor switching (`hand2` / arrow / `crosshair`), step dollar callouts, bottom profit ticks, per-field last-valid keystroke memory, `[Clamped]` & `Alarms Only` tags, and an isolated `ratchet_prev_after_id` debounce.
- **Thread-Safe Intraday HUD Sparkline Column (`_record_pnl_curve_point`, `compute_sparkline_scale`, `_redraw_hud_sparkline_canvas`, `update_gui`, `"pnl_sparkline"`):**
  - Stores up to `160` min/max-and-boundary-preserving points per `(broker, account_id)` session under strict `_config_io_lock -> _pnl_curve_lock` ordering, renders calm slate `#94a3b8` pre-trade `$0.00` flatlines before green/red PnL develops, passes immutable `spark_snap` snapshots to Tkinter, mirrors Demo flash colors, and automatically hides the canvas whenever `"OFFLINE"` / `"RETRY #N"` / `"TOKEN EXPIRED"` alert text needs the cell.
- **Disconnect Dedup Reset, Atomic Priority Guard & Safe Deferred Replay (`_purge_disconnect_alarm_dedup`, `trigger_alarm`, `_flush_deferred_alarms`, `data_loop`):**
  - Added `_purge_disconnect_alarm_dedup()` on every live API recovery (alongside `is_repeatable_disconnect` re-arming when idle) so repeat disconnects in the same session always play `sound_disconnect_alert_loop` and illuminate the HUD alert button.
  - Serialized `trigger_alarm()`'s priority check and state transition under a single non-nested `_alarm_loop_lock` (and guarded `data_loop()`'s Attempt #3+ progress update with `is_disconnect_alarm_reason(last_alarm_reason)`) so transient disconnect/retry updates never silence or clear an active Stop / Manual-Options risk siren, and updated `_flush_deferred_alarms()` to prioritize risk alarms and stop only once `trigger_alarm()` returns `True`.
- **Fixed-Geometry Card 3 Summary, Event-Safe Tcl Unbind & Cleaner Diagnostics (`prefs_summary_frame`, `_refresh_card3_prefs_summary`, `_safe_unbind`, `_clip_log_detail`):**
  - Wrapped `lbl_prefs_summary` inside `prefs_summary_frame` (`pack_propagate(False)` with worst-case emoji height measured before freezing + `<Configure>` tracking), applied `uniform="pf_cols"` on `body_frame` columns after outer geometry locks, stepped down priority-ordered unclipped shorthand keeping **`🚨 Breach Sim`** and **`🔇 MUTED`** visible longest, and synced Card 3 across `Preferences & Audio`, `Post-Breach Popup`, and `_dismiss_hud_breach_preview()` via `_pf_prefs_summary_refresh_cb`.
  - Updated `_safe_unbind()` to match exact `"[funcid "` tokens and defer `widget.deletecommand(funcid)` via `after_idle`, added stale-popup (`self._win is not tw` / `nav_state["popup"] is not pop`) and exact widget-path prefix (`w == p or w.startswith(p + ".")`) guards, parameterized `wick_delay_s` (`0.2s`/`0.35s`) with `"No warning alarm triggered."` on warning-only flickers, and added `_clip_log_detail(msg, max_len=140)` for word-boundary error formatting.

---

## [v0.9.80] — 2026-11-20
### ⚡ Quick Summary
- **Smart Recovery & Bounce-Close Protection on Manual Options (`Options Auto-Flatten: OFF`, Shoutout to `T$MAC`!):** When an option trade dips past your Single-Trade Stop with Options Auto-Flatten OFF and then recovers cleanly back above your stop threshold (above `-$425` on a `-$500` stop) without averaging down, Enforcer now automatically clears the manual-options watch, silences repeat sirens, and skips the Penalty Box OS lock if you close for a win or small scratch — while still enforcing the lockout if you close near/past your stop or average down during the watch.
- **Rock-Solid `📜 Logs ▾` Dropdown Menus & `"⏳ Sending..."` Progress Feedback:** Fixed dropdown menus snapping shut whenever the 1-second `STREAK` countdown or Card 3 labels refreshed inside Settings, fixed a cross-version Python `< 3.13` unbind hazard that could drop Settings drag/click listeners after closing a dropdown, and added an instant `⏳ Sending...` indicator right on `📜 Logs ▾` while uploading Safe Logs.
- **Instant Manual-Options Alerts (Zero `HTTP 429` Burst) & Clearer Early Warnings:** Eliminated the 8-second equity polling delay and Webull `HTTP 429` bursts when breaching an Open PnL / Tilt stop while holding options only, and renamed cryptic `Hit -$400 (Tier 1)` / `Hit $0 (Tier 2)` HUD pills to **`Net -$400 Warn · No Stop`** so early heads-ups never look like surprise stops.

### 🔍 Detailed Breakdown
- **Manual-Options `OPEN_PNL` Recovery Disarm, Averaging-Down Guard & Accurate Lockout Copy (`_compute_open_pnl_recovery_threshold`, `_is_manual_options_alarm_reason`, `_purge_manual_options_deferred_alarms`, `_format_manual_options_alarm_reason`, `_enter_halt_breach_watch`, `_handle_pending_halt_breach`, `get_full_idle_button_text`):**
  - Tagged unarmed / outside-RTH manual-options `OPEN_PNL` watches with `manual_options_only=True`, `pre_watch_flat_realized`, and `saw_increase=False` (safe `.get()` defaults for restored pre-`v0.9.80` sessions), updating HUD status pills & hover cards to display **`MANUAL OPTIONS WATCH`** instead of `"⏸ HALT ... EXIT QUEUED"`.
  - Runs recovery disarm strictly after `DAILY` upgrade evaluation and `unauthorized` averaging-down detection on the watched option position(s)' own `open_pnl` (or `min(open_pnl, watched_open_pnl)`) against `_compute_open_pnl_recovery_threshold()` (`-open_max + clamp(0.15 * open_max, $25, $100)`, i.e. `-$425.00` on a `-$500` stop): clean recovery disarms `pending_halt_breach`, purges queued `"MANUAL OPTIONS EXIT"` alarms from `_deferred_alarms`, clears active manual-options sirens without touching other alarms, and re-arms the Single-Trade Stop cleanly. If contracts are added mid-watch (`saw_increase=True`), repeat 30s nagging still pauses while recovered/green while the deferred Penalty Box lock remains enforced on close.
  - On flat close of an un-increased `manual_options_only` watch, compares `closed_delta = _round_cents(net_pnl - pre_watch_flat_realized)` against the recovery threshold (skipping `start_cooldown_lock` for wins/scratches while still locking real losses), sets `deferred_from_halt=bool(hb.get("halted_with_working_exit"))` on `OPEN_PNL` / `CONSEC_LOSS` locks so manual-options lockouts show normal Penalty Box copy instead of `"POST-HALT COOLDOWN"`, and avoids duplicating `" — CHECK OPTIONS MANUALLY!"` while preserving it on repeatable `"OPTIONS MARKET CLOSED"` notices.
- **Zero-Burst Manual-Options Fast Path & Cache-Miss Pacing (`_prev_snapshot_has_no_equities`, `trigger_open_pnl_flatten`, `trigger_consec_loss_cooldown`, `WebullAdapter`, `SchwabAdapter`):**
  - Added `_prev_snapshot_has_no_equities()` fast path across both manual-options branches of `trigger_open_pnl_flatten()` and `trigger_consec_loss_cooldown()`, entering `_enter_halt_breach_watch(..., seed_from_prev_snapshot=True)` immediately (`0s` siren delay, `0` `/account/position` HTTP calls) before sweeping working non-option orders via `cancel_all_working_orders(..., cancel_options=False)`.
  - Reused `< 0.45s` empty equity snapshots on `peek_pos` inside `flatten_equities()` (`cache_empty_ok=True`), stamped `_last_pos_call_ts` / `_next_pos_slot_ts` on unpaced `WebullAdapter.get_open_equity_positions()` / `get_open_option_positions()` pre-submit cache misses (preserving `0ms` emergency pre-submit latency while spacing follow-up `pace_for_verify=True` / `data_loop` calls), and honored active `_rate_limit_until` backoffs on `SchwabAdapter.get_open_equity_positions()` / `get_open_option_positions()` `pace_for_verify=True` verification reads for two-way parity.
- **Safe Single-Handler Unbind, Descendant Event Filtering & Upload Progress (`_safe_unbind`, `DarkDropdownMenu`, `_open_version_picker`, `_close_ver_popup`, `send_today_safe_log_now`):**
  - Added `_safe_unbind(widget, seq, funcid)` (fixing CPython `< 3.13` `Misc.unbind(seq, funcid)` stripping sibling `add='+'` listeners like `_on_pf_configure` / `_on_pf_button1` on testers running Python 3.12), filtered top-level `<Configure>` (exact outer geometry diff) and `<Unmap>` (`ev.widget is top`), debounced `overrideredirect` `<FocusOut>` against `focus_displayof() is None`, added live `hud_root` outside-click dismissal, and disabled `btn_logs_menu` with `"⏳ Sending..."` (restored in both `_finish` and `except`) during manual Safe Log uploads.
- **Plain-English Warning Alarm Copy (`_humanize_alarm_reason`, `format_alarm_button_text`, `trigger_alarm`):**
  - Added `_humanize_alarm_reason()` preserving `triggered_alarms` keys and `[ALARM] Triggered:` log prefixes while displaying `ACKNOWLEDGE ALARM (Net -$400 Warn · No Stop)` / `Net $0 Pullback Warn · Tier N` / `Ext Net -$X Warn · No Stop` on the HUD and spoken alerts.

---

## [v0.9.79] — 2026-11-20
### ⚡ Quick Summary
- **Live Pre-Launch `FLIGHT PLAN` Strip & 2-Column Hover Card:** A plain-English status strip (`FLIGHT PLAN (RTH)` / `(Ext-Hours)` / `(Alarms Only)` / `(Done Today)` / `(DEMO $25K)`) now updates in real time right above the launch button as you tweak stops, alarms, options mode, or presets — plus a hover-or-click `ⓘ Full plan` card showing a clean two-column rulebook summary (`Early Alerts`, `Daily Stop`, `Options Mode`, `Hold-Off Rule`, `Trade & Tilt`, clamped `Profit Lock` / `Profit Ratchet` floors, and `9:30 AM Bell` behavior).
- **`Start Automatically with Windows` (`OFF` by Default) & Cold-Boot `--startup` Resilience:** Optional toggle in **`⚙ Preferences & Audio... -> SYSTEM & TELEMETRY`** (`Win Boot: ON` in Card 3) that launches PnL Enforcer automatically on Windows login via `pythonw.exe ... --startup` — waiting patiently for boot Wi-Fi, protecting your saved 7-day Schwab token from captive-portal HTML or `<14h` boot refresh wipes, and deferring interactive browser logins until Pre-Flight is on screen.
- **Zero Duplicate `36h` Order Fetch on Launch & Cleaner `[CONFIG]` Telemetry (Schwab & Webull):** Extending Pre-Flight's verified flat zero-delta `36h` order cache window to `60s` across launch (`HUD Poll #1`) avoids redundant broker `/orders` calls when reviewing settings for `>8s` (while invalidating instantly on any `$0.01` balance or position change), and fixes negative tier stops in `[CONFIG]` logs (`-$1,000` / `-$500` + `WinBoot=ON/OFF`).

### 🔍 Detailed Breakdown
- **Live Pre-Launch Flight Plan Strip, Dynamic Tooltip Card & Floor Clamping (`build_flight_plan_summary`, `elide_flight_plan_headline`, `_redraw_flight_plan_canvas`, `_populate_rich_tooltip_card`, `_normalize_tooltip_paragraphs_global`, `_get_effective_rth_tier_stops`, `attach_tooltip`):**
  - Renders `cv_flight_plan` (`tk.Canvas`) with a colored `FLIGHT PLAN` prefix tag, clause-boundary elided headline (`elide_flight_plan_headline`), click-or-hover instant card display (`_show_tooltip_now_fn`), High-DPI overlap prevention against `"ⓘ Full plan"`, DPI-measured two-column `• Key | Value` grid alignment with `"---"` dividers and `("IMPORTANT:", "WARNING:", "CAUTION:")` / `!` warning styling, and `_get_effective_rth_tier_stops()` / `-stop_mag` floor clamping for RTH tiers and Extended-Hours Profit Lock.
- **Windows Boot Auto-Start (`HKCU\...\Run`) & Cold-Boot `--startup` Hardening (`DEFAULT_CONFIG["start_with_windows"]`, `build_windows_startup_command`, `read_windows_startup_status`, `sync_windows_startup_registry`, `DeferredAuthRequired`, `run_startup_broker_connect`, `SchwabAdapter.authenticate`, `WebullAdapter.authenticate`, `_spawn_updated_enforcer`):**
  - Registers `PnLEnforcerBeta` (`pythonw.exe` + `--startup`, forwarding `--startup` across self-updates and respecting Task Manager `StartupApproved\Run` status), retries pending boot network connections via `Case 3a` (`6x3s`) and `Case 3b` (`22x4s`) background reconnect without modal error popups or unwanted broker switches, preserves saved Schwab tokens against captive-portal `JSONDecodeError` or `<14h` silent boot expiry checks, and suppresses foreground stealing during silent `--startup` boots.
- **`60s` Post-Reconcile Launch Order Cache & `[CONFIG]` Sign Fix (`SchwabAdapter.fetch_filled_orders_since`, `WebullAdapter.fetch_filled_orders_since`, `format_config_summary`):**
  - Uses `eff_ord_ttl = 60.0` (with instant `$0.01` equity/holding signature invalidation via `_compute_orders_cache_inv_sig`) on both `SchwabAdapter` and `WebullAdapter` when `_off_session_reconciled and fast_recent_only` is active across the Pre-Flight to `HUD Poll #1` handoff, and formats negative `t2_max_loss` / `t3_max_loss` values cleanly via `_fp_fmt_signed()` alongside `WinBoot=ON/OFF`.

---

## [v0.9.78] — 2026-11-19
### ⚡ Quick Summary
- **Live HUD Data-Freshness LED & Hover Feed Status (Schwab, Webull & Demo):** Added a subtle real-time freshness dot directly inside the HUD center status pill (**`● GREEN`** when live, **`○ SYNCING`** hollow ring on startup or wake-from-sleep resync, **`● AMBER`** with compact age timer on Retry #1 or aging feed, and **`● RED`** on disconnects/stalls) plus live-ticking hover tooltip status (`Broker Feed LIVE · synced X.Xs ago · Poll: Ns`).
- **Faster Pre-Flight Launch & Instant `0ms` Cold HUD Metrics:** Eliminated duplicate blocking broker `/orders` queries across Pre-Flight sync, fee-drift checks, and `data_loop()` Poll #1 using a shared single-flight `/orders` cache (`8s` TTL), a conservative `36h -> 58d` GTC escalation fast-path for untouched `$0.00`-drift launches, and pure-math `0ms` HUD column seeding under calm neutral `#262a2e` tiles while Poll #1 finishes live verification.
- **Post-Breach Recovery Pin Retirement & Pre-Sync Lock Cleanup (`InvWithRed` Follow-Up):** Retiring an intraday bounce-fill trigger pin after a later flat round-trip close now cleanly allows Daily Stop re-arming even when keeping the same floor, and speculative pre-sync Daily Stop locks clear reliably once genuine live Poll #1 off-session catch-up settles above the active floor.

### 🔍 Detailed Breakdown
- **HUD Freshness LED, Sleep/Wake Detection & Compact Bottom-Bar Sizing (`_get_capsule_led_photo`, `HudCapsulePill`, `_get_feed_health_state`, `_apply_hud_status_pill_state`, `_refresh_open_tip_feed`, `_sync_hud_bottom_bar_layout`):**
  - Renders crisp anti-aliased status LEDs (`GREEN` `#22c55e`, `AMBER` `#f59e0b`, `RED` `#ef4444`, hollow `SYNCING` `#7dd3fc`, `DEMO` `#38bdf8`) inside `HudCapsulePill` with live wall-vs-monotonic wake-from-sleep detection (`|dw - dm| > 5.0s`), `2`-poll degrade hysteresis, dynamic tooltip color/text refreshes, and pill width measurements including active compact age suffixes (`<= 3` cols).
- **Single-Flight `/orders` Window Cache, `36h -> 58d` GTC Escalation & Deferred Auth Queue (`_compute_orders_cache_inv_sig`, `SchwabAdapter`, `WebullAdapter`, `_reconcile_off_session_activity`, `_is_untouched_fee_drift_candidate`, `_apply_postlaunch_preflight_auth`, `_seed_hud_columns_from_known_state`):**
  - Coalesces concurrent `/orders` fetches across both `SchwabAdapter` (`max_results=3000` with `3,000`-order `[WARN]` & `[PERF]` telemetry) and `WebullAdapter` behind `_orders_fetch_lock` (`6.0s` timeout), keyed by `(account_id, _snapshot_gen, window)` plus active SDK client identity, cache-dict identity, snapshot epoch delta, and `_compute_orders_cache_inv_sig()` (covering both open holdings and settled equity changes while holding ignored swing positions), and isolates `reconnect_session()` / mid-launch trades cleanly across `_raw_orders_window_cache`, `_filled_since_cache`, and `_filled_today_cache`.
  - Gates `has_any_filled_orders_today()` prefetches behind `_is_untouched_fee_drift_candidate()`, escalates any `$0.01+` delta, open position, older save, or non-empty `36h` fill set cleanly to `58d` on both background workers and Poll #1 (`allow_network=False` returns `False` instead of advancing `_reconciled_through_epoch` on incomplete `36h` batches), hands off deferred `verify_accounts_live()` auth atomically across `pf.destroy()` via `_enqueue_postlaunch_preflight_auth()`, and populates flat HUD tiles at `0ms` beneath neutral `#262a2e` backgrounds without touching lock or W/L state.
- **Post-Breach Trigger Pin Retirement & Pre-Sync Lock Deferral (`_retire_stale_breach_trigger_pin`, `_breach_pin_retired`, `_recheck_presync_save_lock_after_sync`, `_stabilize_mid_fill_realized_and_equity`, `save_and_launch`):**
  - Persists `breach_pin_retired` and `lock_from_presync_save` inside `config["account_sessions"]`, excludes explicitly retired recovery pins and speculative pre-sync locks from `save_and_launch()`'s fallback unchanged-floor lock clause, and defers Poll #1 off-session/pre-sync evaluation via `_launch_live_sync_deferred` whenever Poll #1 receives a rate-limited cached snapshot (`is_reverify=True`).

---

## [v0.9.77] — 2026-11-19
### ⚡ Quick Summary
- **One-Click `↺ Undo Edits` in Pre-Flight & Settings:** Clicked **`Standard Full Risk`**, **`50% Low Energy`**, or **`Restore Defaults`** while dialing in custom today settings? A clean contextual **`↺ Undo Edits`** button now appears right beside **`Save as Default`** whenever anything on screen differs from when you opened the window — snapping every checkbox, dollar threshold, HUD column, and preference back in one click without saving a thing.
- **Clearer `"Loaded — Not Saved Yet"` Preset & Defaults Status Copy:** Clicking **`Standard Full Risk`**, **`50% Low Energy`**, or **`Restore Defaults`** now explicitly confirms the preset is **loaded, not saved yet** (with a calm hint pointing to **`↺ Undo Edits`** whenever changes exist), removing any guesswork before you hit `SAVE`.

### 🔍 Detailed Breakdown
- **Pre-Flight Deferred-State Snapshot, Dirty Detection & Contextual Undo (`show_preflight_window`, `undo_preflight_edits`, `_refresh_undo_edits_btn`, `apply_half_risk_preset`, `apply_standard_full_preset`, `restore_factory_defaults`):**
  - Captures an in-memory window-open baseline of all deferred Pre-Flight controls (dollar thresholds, rulebook toggles, HUD column selection, poll interval, TTS voice, and audio toggles — strictly excluding immediate-persist controls like Privacy Mode, Mute All Audio, Debug Console, Auto-Share Logs, Broker/Account switches, Commit/Done Today locks, and ignored pre-existing holdings).
  - Keeps the top `PRESETS:` row unchanged and displays **`↺ Undo Edits`** (compacting automatically to **`↺ Undo`** beside **`🧪 DEMO`** so Demo Mode stays unclipped at high DPI scaling) directly after **`Save as Default`** only when unsaved edits exist outside `In Trade` / `Commit Today` tamper locks, while respecting active Loss-Streak tamper locks and avoiding waiver pop-ups during undo.

---

## [v0.9.76] — 2026-11-19
### ⚡ Quick Summary
- **Clean Launch Past Startup `HTTP 429` Rate Limits (Webull & Schwab):** Cached snapshots replayed during an `HTTP 429` backoff no longer bypass baseline initialization or evaluate guardrails while an anchor or Force Re-Anchor is pending — eliminating the startup `'NoneType' and 'float'` `TypeError` alarm loop and pacing cleanly until the first live snapshot arrives (shoutout to **`T$MAC`** for the Safe Log catch!).
- **Single Post-Lock Watchdog on Briefing Upgrades & Safe One-Shot Handoffs (`v0.9.75` Hardening):** Upgrading a `Penalty Box` or `Tilt Streak` cooldown to a `Daily Breach OS Lock` during the 15-second briefing screen now defers the post-lock watchdog until Windows actually locks (no duplicate Stage 1 sweep/callout), closes pre-worker duration races, and prevents persistent locks and `0-min` one-shot locks from overwriting or canceling each other.

### 🔍 Detailed Breakdown
- **Unanchored-Cache Gate, `max_equity` Guard & Paced `429` Backoff Recovery (`data_loop`, `evaluate_stop_decisions`):**
  - Clears any stale `_data_loop_wake_event` on entry to `data_loop()` and initializes `poll_ad = None` / `snap_was_cached = False` at the top of `while True:` before `try:` so early pre-fetch exceptions can never raise `UnboundLocalError` in the sleep block.
  - Added an explicit gate right after the Midnight ET rollover check (`data_loop()`): whenever `snap_was_cached` is `True` and `force_reanchor`, `start_equity is None`, `start_equity <= 0.0`, or `max_equity is None` holds, cached replays never anchor or evaluate while a re-anchor is pending — pacing directly to `poll_ad._rate_limit_until` (logged once per episode) until a live snapshot arrives, and pacing mid-session cached `429` waits cleanly at the bottom of the loop.
  - Added defensive `max_equity` / `daily_max_equity` fallback normalization (`eff_max_eq` / `eff_dmax_eq`) inside `evaluate_stop_decisions()` and a live-poll `if max_equity is None and start_equity is not None: max_equity = start_equity` guard across both `WebullAdapter` and `SchwabAdapter`.
- **Sequence-Tied Lock Engagement & Persistent / One-Shot Isolation (`_cooldown_worker_seq`, `_cooldown_lock_engaged_seq`, `_cooldown_flat_at_start`, `start_cooldown_lock`, `trigger_lockdown`, `PenaltyBoxBriefingOverlay`):**
  - Replaced single-flag assumptions with sequence-tied `_cooldown_worker_seq`, `_cooldown_lock_engaged_seq`, and `_cooldown_flat_at_start` (`&= bool(was_flat_at_lock_start)` on upgrade): upgrades during the 15s briefing update `cooldown_label`, `cooldown_end_time`, and live countdown callbacks (`lock_end_fn` / `label_prefix_fn`) while deferring `_run_post_lock_watchdog()` until `cooldown_worker()` engages `LockWorkStation()`.
  - Protected `cooldown_worker()`'s startup `cooldown_end_time = max(cooldown_end_time, now_w + duration_sec)` against pre-worker upgrades, and hardened the persistent ↔ `dl_mins == 0` one-shot boundary so active persistent locks fold Daily Breaches into `"DAILY BREACH OS LOCK"` without downgrading to one-shot while persistent locks cleanly supersede an active one-shot briefing.

---

## [v0.9.75] — 2026-11-19
### ⚡ Quick Summary
- **Accurate Win/Loss & Tilt-Streak Math Across Broker Fee Settlements (Schwab & Webull):** Post-close fee or commission adjustments while flat no longer leak into the next trade's PnL delta (preventing winning resets from being misread as scratches or losses), while any rapid round-trip opened and closed completely between polls still counts accurately toward your Tilt Streak.
- **Zero `HTTP 429` Collisions on `Done for Today` / Flatten & Quieter Rate-Limit Holds (Webull & Schwab):** Serialized Webull `/account/position` requests across live polling, flatten verification, and post-lock watchdogs, reused the final verified flat check's paired options read so `Done for Today` / `Panic` never fire an extra position burst, and held brief `HTTP 429` backoffs cleanly without flashing false `RETRYING API` reconnects.
- **Armed Options Order Sweep on All Breach Triggers During RTH & Resilient Audio Sirens:** Single-Trade Stops, Consecutive Loss Cooldowns, and Daily Stop Lockdowns now cancel resting option orders and sweep any sub-second option fills whenever `Options Auto-Flatten (BETA)` is armed during Regular Trading Hours (`9:30 AM – 4:00 PM ET`), and live HUD sirens now pause and resume cleanly when `⚙ SETTINGS` comes to the foreground instead of silencing permanently after one beep.

### 🔍 Detailed Breakdown
- **Flat-State Realized Baseline Sync & Sub-Poll Round-Trip Guard (`_classify_round_trip_delta`, `log_position_transitions`, `_stabilize_mid_fill_realized_and_equity`, `restore_account_session`, `evaluate_stop_decisions`):**
  - Extracted W/L and `TiltStreak` scoring into `_classify_round_trip_delta(delta, cfg=None)` and tracked `_last_round_trip_close_ts` / `_pending_subpoll_consec_reason`.
  - Inside `_stabilize_mid_fill_realized_and_equity()` (`is_flat` and `was_flat_before`, non-demo), post-close equity drifts within `90s` of a round-trip close log `[POS_SETTLE]` and sync `prev_flat_realized_pnl` cleanly; larger non-recent flat drifts (`drift <= -consec_loss_min_dollars` or `>= max(consec_loss_min_dollars, consec_win_reset_dollars)`) are scored as `(Sub-poll flat round-trip)` via `_classify_round_trip_delta()` before syncing, while preserving Demo Sandbox `_trig_tilt_loss()` and ignored-position deadband handling.
- **Unified Webull Position Slot Pacer, Paired Post-Flatten Options Verify & Two-Way `HTTP 429` Hold (`WebullAdapter._reserve_pos_slot`, `flatten_equities`, `_verify_post_flatten_unarmed_options`, `data_loop`):**
  - Replaced `WebullAdapter.fetch_account_data()`'s unlocked `2.10s` check and `_pace_position_verify_call()`'s single-pass sleep with `_reserve_pos_slot(own_gap=..., owner=...)` under `_pos_pace_lock`, stamping `_last_pos_call_ts` at claim time and re-checking `_rate_limit_until` every `<= 0.25s`.
  - Updated `flatten_equities()`'s `_mark_flatten_flat(save_paired_opts=True)` to snapshot fresh (`< 1.0s`) paired `_last_open_opt` readings onto `adapter._post_flatten_opt_verify` right before `invalidate_cached_snapshots()`, letting `_verify_post_flatten_unarmed_options()` consume verified `< 2.0s` readings for the active `account_id` without a redundant `/account/position` or `/accounts` call (falling back to live polling if stale, mismatched, or inferred post-timeout via order coverage).
  - Updated `data_loop()` to hold active `< 20s` `HTTP 429` rate-limit windows (`_rate_limit_until`) without incrementing `consecutive_api_failures` or calling `reconnect_session()` on both `SchwabAdapter` and `WebullAdapter`, escalating normally if continuous `429`s reach `>= 20s`.
- **RTH Armed-Options Breach Coverage (`trigger_open_pnl_flatten`, `trigger_consec_loss_cooldown`, `trigger_lockdown`):**
  - Evaluated `rth_now = is_market_hours()` once per trigger and passed `include_options=bool(opt_armed and rth_now)` directly to `flatten_equities()` (matching `activate_done_for_today` and `trigger_manual_panic_flatten`), keeping all unarmed/off-RTH siren & halt-watch guards intact and logging `bool(has_options or opt_exec_now)` to `_enter_halt_breach_watch()`.
- **Siren Loop Foreground-Focus Survival & Non-Blocking Startup Grace Tone (`sound_alarm_loop`, `sound_disconnect_alert_loop`, `trigger_alarm`, `play_startup_grace_chime`):**
  - Updated `sound_alarm_loop()` and `sound_disconnect_alert_loop()` to pause cleanly (`time.sleep(0.20); continue`) instead of terminating the loop thread while `_settings_suppresses_alarms()` is `True`, added `_alarm_loop_gen` under `_alarm_loop_lock` so overlapping alarm triggers never double-cadence, and moved `play_startup_grace_chime()` to a daemon thread so `data_loop()` never blocks `140ms` on startup grace.

---

## [v0.9.74] — 2026-11-17
### ⚡ Quick Summary
- **Manual Overrides Always Clear Startup Grace (`🔒 Done Today` & `🚨 HOLD 2s: FLATTEN`):** Ensured explicit manual overrides immediately clear any startup breach grace before saving session state or canceling working orders — even if an initial position read momentarily returns empty or `data_loop` polls mid-scale-out at the same instant.
- **Timestamp-Safe OCO Partial-Fill Exit Coverage (Schwab & Webull):** Tightened OCO bracket coverage math during partial fills so a partially filled leg can never stack onto a `~100ms`-lagging sibling leg's remaining quantity (nor over-sell on a stale position snapshot), and fixed a numeric `remain_quantity = 0` check on Webull open orders.

### 🔍 Detailed Breakdown
- **Immediate Startup Grace Clearance on Manual Overrides (`_clear_launch_grace_state`, `activate_done_for_today`, `trigger_manual_panic_flatten`, `flatten_equities`, `evaluate_stop_decisions`):**
  - Added `_clear_launch_grace_state()` (clearing `_launch_grace_pending = False`, `_launch_grace_syms`, `_launch_grace_ref_opnl`, and `_launch_grace_ref_net`) invoked at entry of `activate_done_for_today()` (prior to `save_session_state()`), inside `trigger_manual_panic_flatten()`, and at the start of `flatten_equities()` whenever `manual_panic or done_for_today` so transient `None` `peek_pos` reads or follow-up `POST_BREACH_FLATTEN` sweeps never skip graced working orders or shares.
  - Added early `done_for_today or _manual_flatten_in_flight` guards in `is_launch_grace_position()` and `evaluate_stop_decisions()`'s scale-out branch so concurrent background polls cannot re-insert cleared grace keys.
- **Timestamp-Verified OCO Partial-Fill Coverage Cap & Webull `0`-Remaining Fix (`SchwabAdapter.get_recent_exit_order_coverage`, `WebullAdapter.get_recent_exit_order_coverage`):**
  - Tracks per-OCO-group `init_max`, `work_max`, `filled_all`, and post-`cutoff_epoch` `filled_recent` (via `orderActivityCollection[].executionLegs[].time` on Schwab and `filled_time` / `update_time` on Webull): caps `grp_working = min(work_max, max(0.0, init_max - filled_all))` and `grp_filled_rec = min(filled_recent, init_max)` whenever fill timestamps are present, preventing both sibling-lag coverage overstatement on updated snapshots and accidental over-selling on stale snapshots. *(Note: on Webull, a fully filled OCO leg drops off the open-orders list, leaving at most the broker's ~100ms sibling-cancel propagation window before the next sweep.)*
  - Replaced Webull's falsy `or` chain on `remain_quantity` with explicit `is not None` checks so numeric `0` remaining never falls through to original `quantity`, and added Suite `Test 29` in `test_enforcer.py`.

---

## [v0.9.73] — 2026-11-17
### ⚡ Quick Summary
- **Off-Session Trade Catch-Up & Zero-Penalty Startup (Schwab & Webull):** Closed Enforcer for part of the day and took trades while it was off? Re-opening now automatically scans your broker fills while closed to catch up your **`TRADES (W/L)`**, **`SESSION HIGH`**, and **`SESSION LOW`** — and **never** penalizes you on launch (no surprise Windows OS lock, no instant position dump, and a calm **`• GRACE`** hold on any already-open trade until you close it, add size, flip, or lose past your post-launch stop backstop).
- **Compact `2–3` Column HUD Bottom-Bar Polish:** On smaller `2`- and `3`-column HUDs, the **`● ARMED`** status pill and **`🔔 DISMISS ALARM`** button now stay full-width and legible instead of shrinking to `"• ARM..."`, consolidating the emergency exit button cleanly to **`🚨 FLAT 2s`**.
- **Bounce-Fill Daily Stop Readout & Lockout Fix (Shoutout to `InvWithRed`!):** If a trade dips past your Daily Stop mid-candle and catches a fast bounce while the market exit fills (so your closed day PnL settles above your stop), the crimson HUD banner and review popup now show both numbers clearly (**`Triggered at -$574.84 Net · Filled at -$329.48`**), and saving Settings without raising your Daily Stop past that trigger keeps your lockout active as intended. Huge thanks to **`InvWithRed`** for catching and reporting this!
- **Faster Schwab & Webull OCO/Bracket Order Cancels + Clean Startup Polish:** Replaced slow 58-day unfiltered Schwab cancel lookups with a fast 2-step sweep, added full OCO/bracket child-order cancel & exit-coverage handling on both Schwab and Webull, fixed `"Restore Defaults"` un-minimizing the debug console or touching ignored swing positions, and eliminated `[TCL_ERR]` popup timer noise in logs.

### 🔍 Detailed Breakdown
- **Off-Session Multi-Trade Broker Reconstruction & Zero-Penalty Startup (`reconstruct_off_session_trades`, `_reconcile_off_session_activity`, `evaluate_stop_decisions`, `is_launch_grace_position`):**
  - Added incremental chronological fill reconstruction across `SchwabAdapter.fetch_filled_orders_since()` (`100x` option multiplier, multi-leg flagging) and `WebullAdapter.fetch_filled_orders_since()` (`list_today_orders` / `list_order_history` pagination, UTC `Z` & epoch ms normalization) tracked via per-order cumulative `reconciled_order_qty` and `reconciled_through_epoch` in `config["account_sessions"]`, with UI-thread `allow_network=False` prefetching in Pre-Flight so account switches never block Tkinter.
  - Enforces a strict end-quantity gate against live `pos_details` and a tight fee-residual cap (`max($3, N * $1.50)` equities / `max($5, contracts * $2.25)` options, never flipping trade W/L sign) before booking per-round-trip `win_trades` / `loss_trades`, `daily_max_equity`, and `daily_min_equity`; falls back cleanly to single net-delta flat reconciliation (deferring mid-trade open-position W/L until flat so partial scale-outs never double-count) and never feeds off-session losses into `recent_loss_timestamps` or ratchets `max_equity` to an already-retraced off-session peak.
  - Added `breach_source = "OFF_SESSION"` + `_launch_grace_syms` (with OCC option whitespace normalization across Schwab & Webull) so launching past Daily Stop or Open PnL Stop suppresses immediate OS Lock / App Kill / auto-flatten on pre-existing shares while arming a post-launch drawdown safety backstop (`open_max_loss` when Single-Trade Stop is ON, else `50%` of base Daily Stop) and immediately flattening any scale-in, direction flip, or newly opened symbol. *(Rollback note: rolling back to `v0.9.72` while holding an open `"OFF_SESSION"`-locked position will treat `is_locked_down` as standard Post-Breach Force-Flatten.)*
- **Bounce-Fill Daily Stop Telemetry & Settings Save Lockout Guard (`last_breach_trigger_net_pnl`, `show_daily_breach_return_notice`, `save_and_launch`):**
  - Captures and persists `breach_trigger_net_pnl` across both direct and deferred halt/manual-option Daily Stop breaches, rendering `Triggered at -$X Net · Filled at -$Y` on `_get_hud_breach_banner_text()` whenever settled equity bounces above the stop floor.
  - Fixed `show_daily_breach_return_notice()` so live bounce-fill breaches (`ref_eq > act_fl`) display real trigger & settled PnL instead of falling into the `is_sim` preview branch, and hardened `save_and_launch()` so `is_locked_down` stays active until the active floor is loosened below `min(ref_eq, start_equity + last_breach_trigger_net_pnl)` (or `Re-Zero Baseline` is used; legacy lockouts without a saved trigger require loosening the floor or Re-Zeroing).
- **2-Step Schwab Order Cancel, Recursive OCO Traversal & OCO Exit-Coverage Parity (`SchwabAdapter`, `WebullAdapter`):**
  - Split `SchwabAdapter.cancel_all_working_orders()` into a fast `120h` unfiltered sweep plus a thread-bounded (`2.2s` join, without mutating shared client timeouts) `58d` `status=Order.Status.WORKING` GTC sweep, setting `last_coverage_lookup_failed = True` + `[WARN]` if Step 2 times out.
  - Added recursive `childOrderStrategies` OCO traversal on Schwab and `combo_id` sub-order unwrapping on Webull: verified `400`/`404` OCO sibling cascade-cancels against `get_order()` (Schwab) and a post-loop `_fetch_all_open_orders_webull()` recheck (Webull) before clearing `last_cancel_failed_syms`, and took `max(rem_q)` per OCO group inside both `SchwabAdapter.get_recent_exit_order_coverage()` and `WebullAdapter.get_recent_exit_order_coverage()` so 2-leg OCO brackets never double-count exit coverage.
- **Compact HUD Bottom Bar, `Restore Defaults` Guards, Tcl `after` Cleanup & Config Write Guard (`is_compact_hud`, `_wrapped_misc_destroy`, `_config_loaded_once`):**
  - Added `is_compact_hud()` (`<= 3` columns): dynamic `HudCapsulePill` / `GlassStadiumButton` sizing, `"🚨 FLAT 2s"` idle panic label (preserving active hold progress and `"✓ FLATTENED"` result banners across column rebuilds), full `"🔔 DISMISS ALARM"` text, and hidden `🧪 PAD` button on `<= 3` columns so status/alarm pills never clip.
  - Guarded `Restore Defaults` with `_ignore_prepos_guard` so `ignored_positions` (`F2` swing exemptions) are untouched and gated `set_debug_console_visible()` on actual state transitions + `_IS_MAIN_PROCESS` so hidden/minimized consoles never pop forward.
  - Wrapped `tk.Misc.destroy` to cancel doomed `_tclCommands` `after` timers before `deletecommand`, preserved/restored `tk._default_root` + `master=pf` `StringVar` bindings in `show_preflight_window()`, added `_config_loaded_once` (`try/finally` in `load_config()`) so uninitialized diagnostic imports can never overwrite an existing `~/enforcer_config.json`, and expanded `test_enforcer.py` to 28 verification suites.

---

## [v0.9.72] — 2026-11-17 (All New Since v0.9.59.3)
### ⚡ Quick Summary — Everything New Since v0.9.59.3
- **Walk Away Green (`🔒 Done Today` in Card 3):** Call your session done anytime — cancels working daytrade orders, flattens open tracked equities right now (even if `Alarms Only` is ON), and auto-flattens any impulse re-entry until Midnight ET, with a 5-second cooling-off check if you try to unlock early.
- **Freeze Your Rules (`🔒 Commit Today` in Card 3):** Optional 1-click commitment that freezes your stops, presets, baseline, and broker/account switching until Midnight ET so mid-session tilt can't widen limits or turn off protection.
- **Post-Breach Force-Flatten Mode:** Once your Daily Stop is breached (with Auto-Flatten ON), the HUD turns crimson (`🚨 DAILY STOP BREACHED`) and any new revenge trade is automatically flattened for the rest of the day until you explicitly raise limits or re-zero.
- **2-Second Emergency Exit (`🚨 HOLD 2s: FLATTEN` on HUD):** Press and hold for 2 seconds on the HUD bottom bar to cancel working orders and flatten tracked equities immediately (overrides `Alarms Only` and `Auto-Flatten: OFF`, cancels cleanly if released early, and warns you if unarmed options are still open).
- **`$25,000` Paper Demo Sandbox (`BROKER: -> 🧪 DEMO`):** Rehearse Single-Trade Stops, Daily Stops, Profit Ratchets, Tilt Streaks, and LULD Halts anytime with zero real orders and Windows OS locks disabled — complete with a live **Demo Simulator Pad**, 1-click **`↺ Reset Demo ($25k)`**, and 100% isolation from your live account baselines.
- **Calm LULD Halt Handling & Post-Halt Cooldown:** Halted stocks with no broken rules show a calm `⏸ HALT` HUD notice with zero orders or sirens; if a stop breaches during a halt, Enforcer queues your exit, holds off locking Windows until shares actually fill flat, sweeps any new trades opened mid-halt, and announces `POST-HALT COOLDOWN` once flat.
- **Live `Trade API` Permission Check & App Kill-Switch Guarantee:** Card 3 checks upfront whether your broker key can route orders (`✓ Verified`, `⚠️ Blocked / Read-Only`, or `• Unconfirmed`), and enabling Thinkorswim / Webull Desktop `Kill Apps` confirms the Triple / 15-Second + live option flat guarantee.
- **Freely Movable Live HUD + Settings, Saved Window Positions & Silent Mode Cues:** Drag, hover, or close the live HUD while `⚙ SETTINGS` is open; Pre-Flight & Settings now remember the monitor/position where you last placed them (just like the HUD); Silent Mode glows warm amber (`🔇 MUTED ·` / `🔇 SETTINGS`) so muted audio is never missed; Release Notes open in clean **`⚡ Summaries Only: ON`** view by default; and `✦ Quick Tour` adds a `✦ What's New` spotlight tab.
- **Execution & Broker Hardening (Schwab & Webull):** Broker-verified partial-fill exit coverage (preventing duplicate sells or early flat checks during halts/API lag), fractional-share support, per-ticker `W/L` & tilt-streak scoring across multi-position holds, off-session `W/L` reconciliation, atomic `.tmp`/`.bak` config protection, NYSE `1:00 PM ET` early-close calendar awareness through 2028, and calmer trader-to-trader dialog & tooltip copy.
- **Built With Fellow Traders (Shoutout to `T$MAC` & `InvWithRed`!):** Huge thanks to beta testers **`T$MAC`** and **`InvWithRed`** for live session testing, sharp feedback, and Safe Log reports helping shape these upgrades — spot anything off or have an idea? Hit **`🐞 Report Bug`** anytime!

### 🔍 Detailed Breakdown (v0.9.60 – v0.9.72)
- *(Consolidates all experimental `beta` channel iterations `v0.9.60` through `v0.9.72` since the `v0.9.59.3` stable release.)*
- **Session Discipline Locks, 5s Cooling-Off Unlock & Post-Breach Force-Flatten (`activate_done_for_today`, `unlock_done_for_today`, `activate_commit_for_today`, `is_locked_down`, `evaluate_stop_decisions`):**
  - Persists `done_for_today` (`done_for_today_date`), `committed_for_today` (`committed_date`), and `is_locked_down` (`breach_date`) per `(broker, account_id)` inside `config["account_sessions"]` until `00:00 Midnight ET`, surviving 9:30 AM / 4:00 PM rulebook switches and app restarts while isolating `DEMO` commits strictly to `_demo_memory_session` in RAM.
  - Added `_prompt_done_for_today_dialog()` with fail-safe error cleanup (`_build_done_for_today_dialog` + `_restore_pf_modal_focus`), `disabledforeground` support in `GlassStadiumButton.__init__`, a 5-second cooling-off countdown (`🔓 Unlock Anyway (5s)` -> `🔓 Unlock Anyway`), `<Return>`-to-stay-locked keyboard safety, and truthful post-unlock `Alarms Only` / `Auto-Flatten OFF` status warnings.
  - Routes `Done Today` straggler shares through a dedicated `"DONE_TODAY"` halt-watch type without triggering Card 2 OS Lock or App Kill, and triggers `POST_BREACH_FLATTEN` with responsive `2–9` column crimson HUD banners (`_sync_hud_breach_banner`) whenever `is_post_breach_force_flatten_active()` detects a new tracked entry after a Daily Stop breach.
- **2s Manual Panic Flatten, 3-State Post-Flatten Options Guard & Broker-Verified Exit Coverage (`PanicFlattenHoldController`, `trigger_manual_panic_flatten`, `_verify_post_flatten_unarmed_options`, `get_recent_exit_order_coverage`, `flatten_equities`):**
  - Added `PanicFlattenHoldController` (`PANIC_FLATTEN_HOLD_SEC = 2.0`, `SM_SWAPBUTTON`-aware `GetAsyncKeyState` primary-button check, `0.25s` UI-stall delta clamp, `_manual_flatten_in_flight` + `_manual_flatten_state_lock` concurrency guards) passing `manual_panic=True` to `flatten_equities()` so open equities liquidate even when `alarms_only_mode=True` or `enable_auto_flatten=False`.
  - Added paced uncached `_verify_post_flatten_unarmed_options()` (`FLAT` -> `"✓ FLATTENED"`, `OPTIONS_OPEN` -> `"⚠️ OPTIONS OPEN"` + repeatable `"CLOSE OPTIONS MANUALLY"` siren without ever auto-flattening options when unarmed, `OPTIONS_UNVERIFIED` -> `"⚠️ VERIFY OPTIONS"`), plus `_prompt_kill_app_confirm_dialog()` and 3-attempt uncached equity + option flat verification before `terminate_selected_apps()` or `LockWorkStation()`.
  - Added `get_recent_exit_order_coverage()` across `SchwabAdapter` (UTC `Z` timestamp normalization, `max(1800s, elapsed + 120s)` halt lookback, multi-lot summing) and `WebullAdapter` (`list_today_orders` / `list_order_history` / `get_order_detail` with `last_coverage_lookup_failed`), starting-size partial-fill math (`unreflected_f_q` / `uncovered_q`), 15s Extended-Hours `GTC_EXT` limit chasing, 15s `_pending_flatten_cids` replica-bounce retention across `reconnect_session()`, `58-day` Schwab working-order cancel lookback + Webull 100-row pagination (canceling opening `BUY_TO_OPEN`/`SELL_TO_OPEN` option orders while preserving protective `SELL_TO_CLOSE`/`BUY_TO_CLOSE` orders when Options Auto-Flatten is OFF), and `format_order_qty_str()`.
- **LULD Halt Watch, Multi-Monitor Penalty Box Overlay & `$25K` Demo Sandbox (`_enter_halt_breach_watch`, `PenaltyBoxBriefingOverlay`, `DemoBrokerAdapter`, `reset_demo_sandbox_state`, `open_demo_simulator_pad`):**
  - Separated calm `NON_BREACH_HALT_NOTICE` (`⏸ HALT` pill, zero orders/sirens) from `Halt + Breach` (preserving RTH `MARKET` queue priority, suppressing OS Lock until flat, sweeping unauthorized mid-halt entries, and announcing `POST-HALT COOLDOWN — HALT ENDED & POSITION FLAT` via `deferred_from_halt=True` and a `45s` PowerShell SAPI timeout).
  - Hardened `PenaltyBoxBriefingOverlay` with `win.maxsize(16000, 16000)` for full-height portrait monitors, distinct `is_demo_preview` vs. `10 SEC` `DRY_RUN` badges, top-right `✕ Exit Preview (Esc)` + `100ms` `Esc` poll + backdrop click-to-dismiss + `try/finally` early-abort cleanup, and zero-flash HUD `-topmost` restoration (`_restore_hud_after_overlay`).
  - Added `DemoBrokerAdapter` (`$25,000` paper account, `100%` isolated from `enforcer_config.json` live sessions, `"DEMO"` stripped back to `"SCHWAB"`/`"WEBULL"` on disk for `v0.9.59.3` rollback compatibility), `_is_breach_epoch_superseded()` + `_in_flight_poll_lock` race guards, scenario-specific headroom checks (`_prepare_for_demo_scenario`), cross-monitor Demo Pad re-docking (`_dock_demo_pad_near_hud`), emerald `✓ Reset to $25,000 Flat!` confirmation, and full-banner click-to-reset on Demo HUD breach banners.
- **3-State `Trade API` Probe, Fractional Shares, Multi-Position `W/L` & Off-Session Reconciliation (`check_trading_permission_preview`, `log_position_transitions`, `_reconcile_off_session_flat_delta`):**
  - Added `_classify_preview_order_result()` (`1-share DAY Limit BUY of SPY @ $1.00`, Webull v3 `category: US_EQUITY` headers, `_pace_position_verify_call()` `1.15s` pacer + `HTTP 429` -> `"UNCONFIRMED"`, Schwab/Webull 401 reconnect retry, `orderValidationResult.rejects` inspection, 120s TTL cache, and account/balance scrubbing).
  - Added fractional-share formatting/liquidation (`:+g`, whole-share step-down in Extended Hours, sub-1-share `mark_uncloseable_fractional_sym`), immediate per-ticker `W/L` & tilt-streak scoring while other positions remain open, two-way `has_non_ignored_closing_fills_since()` (`58-day` GTC lookback + `_utc_to_eastern_naive()` post-`00:00 UTC` date parity) for off-session flat delta `W/L` reconciliation, equity-based profit ratchet leash math (`max_equity - floor_equity`), atomic `.tmp`/`.bak`/`.corrupt_<ts>` config saves, NYSE `1:00 PM ET` early-close calendar through `2028`, and tightened `_check_version_switch_guardrails()` across persisted `"loss_timestamps"`.
- **Non-Modal Live Settings, Saved Window Positions, `HudDragController`, Silent Mode & Release Notes Polish (`get_saved_preflight_position`, `_settings_suppresses_alarms`, `HudDragController`, `_insert_formatted_changelog`):**
  - Removed root `pf.grab_set()` so the live HUD stays draggable, hoverable, and `✕`-closeable while `⚙ SETTINGS` is open (keeping modal grabs strictly on child confirmation/waiver dialogs and foreground alarm suppression via `_settings_suppresses_alarms()`), and persisted outer-frame Pre-Flight/Settings coordinates (`preflight_x`, `preflight_y`) clamped via `get_monitor_work_area()`.
  - Added `HudDragController` + `_heal_win32_stuck_mouse_button_state()` for focus-steal phantom-drag immunity, `reserve_texts` zero-shift button widths across dynamic Pre-Flight pills, `HudCapsulePill.configure()` custom option stripping, front-anchored warm-amber Silent Mode cues (`🔇 MUTED ·`, `🔇 SETTINGS`, `🔇 Audio Muted · Prefs...`), 4-tab `✦ Quick Tour` (`LAYOUT_TOUR_VERSION = "0.9.72"`), default-collapsed `Detailed Breakdown` (`⚡ Summaries Only: ON`) in Release Notes, refreshed `README.md` / `LICENSE.txt` / trader-to-trader copy, and 24-suite mock-broker + static AST class/wrapper keyword verification (`test_enforcer.py`).

---

## [v0.9.59.3] — 2026-11-16
### ⚡ Quick Summary
- **Ignored-Position Penny-Flicker Elimination & Proportional `$ TO STOP` Color Fix (Shoutout to `InvWithRed`!):** Fixed an edge case where accounts holding open **Ignored Pre-Existing Positions** (e.g., long-term shares + LEAPS) could see flat `REALIZED PnL` / `NET PnL` alternate between `$0.00` and `-$0.01` with zero daytrades taken, AND replaced the hardcoded `<= $500` orange warning threshold on **`$ TO STOP`** with proportional `1/3` leash coloring so Daily Stops `<= $500` (such as `-$450.00`) stay calm slate (`#2c3e50`) at `$0.00` PnL until `<= 33.3%` (`$150.00`) of cushion remains—special shoutout to beta tester **`InvWithRed`** for catching both and sending over the screenshot + clean log! *(Tip: if your `SESSION LOW` saved `-$0.01` earlier, clicking `↺ Re-Zero Baseline` once when flat clears it cleanly.)*

### 🔍 Detailed Breakdown
- **Single-Round Algebraic Cancellation & Two-Step IEEE-754 Cent Cleanup (`_round_cents`, `SchwabAdapter`, `WebullAdapter`, `_apply_ignored_positions_to_snapshot`):**
  - Removed premature cent rounding on `raw_adj_eq` inside `SchwabAdapter.fetch_account_data()` and `WebullAdapter.fetch_account_data()` before `_apply_ignored_positions_to_snapshot()` so `(qty * lp * mult) - qty * (lp - ref_price) * mult` cancels live quote ticks algebraically prior to rounding, and added `_round_cents(val)` (`round(round(float(val), 6), 2)`) across ignored-impact neutralization and un-ignore `delta_base` updates so exact half-cent (`x.xx5`) baselines never flip by `±$0.01`.
- **Adapter-Reported Flat Rounding Deadband & Scratch-Trade W/L Protection (`get_flat_rounding_tolerance`, `_stabilize_mid_fill_realized_and_equity`, `log_position_transitions`):**
  - Added two-way `get_flat_rounding_tolerance()` (`SchwabAdapter`: `$0.02` on `currentBalances` equity/option buckets or `min($0.05, floor((N+1)*0.5)/100)` fallback; `WebullAdapter`: `$0.00` on `cash + pos` / `$0.01` on `raw_adj_eq` fallback) plus throttled balance-free `[SESSION]` residual-shift telemetry.
  - When continuously flat with active open ignored positions, `_stabilize_mid_fill_realized_and_equity()` holds `current_eq` steady at `last_flat_equity` within `±tol` without mutating `last_flat_equity` or `daily_min_equity` (preventing random walk while allowing any `> tol` fee or tracked trade exit to snap through immediately), and `log_position_transitions()` treats closed round-trips with `abs(delta) <= tol` as flat scratches.
- **Thread-Safe Clean-Frame `Re-Zero Baseline` & Proportional HUD Colors (`_ignored_positions_lock`, `get_last_true_live_eq`, `_compute_leash_metrics`, `_compute_dist_and_giveback_bgs`):**
  - Protected `ignored_positions` reads/mutations with `_ignored_positions_lock` and anchored `force_reanchor` on the `data_loop()` thread against unrounded `get_last_true_live_eq()` after resetting `anchor_cash_flow` and `reanchor_ignored_positions_to_live()`.
  - Replaced hardcoded `$500` / `-$250` / `-$500` HUD warning thresholds on `$ TO STOP` and `FROM HIGH` with proportional thresholds (`<= 1/3` of active leash on `$ TO STOP`; `-1/6` orange / `-1/3` red of base Daily Stop on `FROM HIGH`).

---

## [v0.9.59.2] — 2026-11-16
### ⚡ Quick Summary
- **Webull `HTTP 429` Rate-Limit Pacing & False Post-Lock Straggler Alarm Fix (Shoutout to `T$MAC`!):** Fixed a burst rate-limit edge case where Webull returning `HTTP 429` right after a successful auto-flatten could replay a cached pre-flatten snapshot and cause the 15-second Post-Lock Watchdog to mistake a `None` rate-limit response for open shares (*"Warning, straggler shares detected"* / `POST-LOCK FLATTEN FAILED`) even though the account was already 100% flat—special shoutout to beta tester **`T$MAC`** for stumbling into this one live and sending over the log that nailed it!

### 🔍 Detailed Breakdown
- **Zero-Delay Pre-Submit Reads, Paced Verification & Hold-Only Rate-Limit Snapshots (`WebullAdapter`, `SchwabAdapter`, `flatten_equities`, `data_loop`):**
  - Pre-submit emergency flatten reads retain `0ms` pacing so order cancellation and exit submission are never delayed, while post-submit verification, `0.8s` settlement double-confirms, and Post-Lock Watchdog checks pace `get_account_position` calls cleanly (`WEBULL_POS_MIN_INTERVAL_SEC = 1.15s`, paired option cache reuse, `25s` Webull verification window) and stamp `_last_pos_call_ts` inside `finally:`.
  - Added generation-guarded `invalidate_cached_snapshots()` across order submission and flat confirmation so stale pre-flatten snapshots cannot survive or repopulate after an exit order, and marked `HTTP 429` fallback snapshots as HUD **hold-only** (`last_snapshot_was_cached`) so stale cached ticks never re-confirm anti-wick spikes or re-fire stop/lockout actions.
- **3-State Flatten Outcome & Single-Instance Post-Lock Watchdog (`_run_post_lock_watchdog`, `_post_lock_wd_state`):**
  - Deduplicated Post-Lock Watchdog threads per `(broker, account_id)` across lock upgrades (`Upgraded active lock`) so concurrent watchdogs never collide on broker position endpoints.
  - Separated API rate-limit `None` responses from real straggler positions (`len > 0`): `_run_post_lock_watchdog()` now retries `None` up to `3x` (`2.6s` backoff, clearing the `2.5s` `429` window) and preserves the active lock quietly without false *"straggler shares detected"* voice callouts or sirens whenever `0` shares were already confirmed prior to lock.

---

## [v0.9.59.1] — 2026-11-16
### ⚡ Quick Summary
- **Optional `SESSION LOW` HUD Column (`📊 HUD Columns`):** Added an opt-in **`SESSION LOW`** metric column (right below `SESSION HIGH`) that tracks your lowest closed (flat) realized PnL trough of the day in a calm muted slate-rose tone (`#6e2c2c` when below `$0.00`, `#2c3e50` at `$0.00`)—including automatic mid-day log backfill from today's closed round-trip trades if you update mid-session.
- **Mid-Session Newly-Ignored Position Drift Cap (`Ignored` Positions):** Fixed an edge case where marking a newly opened position (e.g., an ETF share lot bought while Enforcer was closed) as **Ignored** mid-day could absorb off-session realized daytrade PnL into that ignored ticker's offset.

### 🔍 Detailed Breakdown
- **`SESSION LOW` Tracking, Per-Account Persistence & Mid-Day Backfill (`HUD_COLUMN_CATALOG`, `daily_min_equity`, `restore_account_session`, `backfill_min_pnl_from_today_log`):**
  - Tracks per-account `daily_min_equity` across all confirmed flat transitions in `_stabilize_mid_fill_realized_and_equity()` (mirroring `SESSION HIGH` on the closed-realized curve while filtering transient cross-endpoint cash desyncs), preserves `daily_min_equity` across 9:30 AM and 4:00 PM rulebook switches, shifts cleanly on un-ignore `delta_base` adjustments, and resets on `↺ Re-Zero Baseline` or new trading days.
  - When upgrading mid-day with an active session that predates `daily_min_equity`, `backfill_min_pnl_from_today_log()` reconstructs today's flat realized trough from `[POS_CHANGE] ... (CLOSED FLAT)` log entries scoped strictly to the active broker and starting baseline segment.
- **Tightened Newly-Ignored Fee/Mark Drift Cap (`_apply_preexisting_selection` & `_apply_ignored_positions_to_snapshot`):**
  - Capped newly-ignored mid-session drift absorption strictly to entry fees and penny rounding (`min($25.00, max($2.00, contracts * $1.00 + 0.05% notional))`), cleared stale preview equity across account restores, and gated live-trim drift absorption off `first_poll_of_launch` so off-session realized PnL is never masked inside `locked_impact`.

---

## [v0.9.59] — 2026-11-16
### ⚡ Quick Summary
- **1-Click Update Rollback & Crash-Safe Startup Recovery (`enforcer.py.prev`, `📜 Logs ▾`, `View Release Notes`, `Launch_Enforcer.bat`):** Before installing any future update, PnL Enforcer now validates and saves a verified local backup (`enforcer.py.prev` and `CHANGELOG.md.prev`) in your app folder—giving you **1-click version rollback** from **`📜 Logs ▾ -> ↺ Restore Previous Version`**, **`View Release Notes`**, or the Pre-Flight footer **`↺ Rollback`** link while keeping 100% of your saved settings, API tokens, and today's session baseline intact, pausing repeat startup prompts for the reverted version (`skipped_update_version`), enforcing full anti-tamper guardrails against lock/trade bypass, and offering automatic native Windows crash-recovery rollback if a future update ever fails to launch.

### 🔍 Detailed Breakdown
- **Verified `.prev` Backup Rotation, Two-Phase Boot Confirmation & Crash-Safe Recovery (`_install_update_payload`, `get_rollback_backup_info`, `check_rollback_allowed`, `execute_version_rollback`, `prompt_version_rollback_dialog`, `_offer_crash_boot_rollback`, `check_for_updates_manual`):**
  - `_install_update_payload()` validates UTF-8 integrity, entrypoint markers (`def data_loop`, `if __name__ == "__main__":`), `APP_VERSION`, and `compile()` syntax on incoming updates before touching disk; atomically backs up your working `enforcer.py -> enforcer.py.prev` and `CHANGELOG.md -> CHANGELOG.md.prev` (preserving any existing known-good `.prev` whenever `.enforcer_boot_pending.json` is still present); and clears `.enforcer_boot_pending.json` only after Pre-Flight opens (`_clear_boot_pending_marker()`).
  - Added rollback controls in **`📜 Logs ▾`** (`↺ Restore Previous Version (vX.Y.Z)...` when `.prev` exists, or `↺ Version Rollback: Armed` before your first update, plus background-threaded **`🔄 Check for Updates Now...`**), **`View Release Notes`** (`↺ Restore vX.Y.Z` / `↺ Rollback: Armed ✓` with modal grab restoration), and the Pre-Flight footer (`↺ Rollback (vX.Y.Z)`), with `(st_mtime_ns, st_size)` memoization on `get_rollback_backup_info()`.
  - Enforced `_check_version_switch_guardrails()` to block rollback while the live HUD is open, during active Penalty Box / OS cooldown timers, while Daily Stop Breach Lockout or a rolling Consecutive Loss Streak is active today, or while any non-ignored live position is open—while allowing rollback when flat and unlocked even if the broker adapter is offline.
  - Added 2-layer crash-safe startup recovery via in-process `_offer_crash_boot_rollback()` (native Win32 `MessageBoxW`, preserving `enforcer_config.json` on disk even before `load_config()` runs) and a pure-stdlib pre-launch guard in `Launch_Enforcer.bat`.

---

## [v0.9.58] — 2026-11-14
### ⚡ Quick Summary
- **Prior-Day Safe Log Attachment Fix & Preview Sync (Bug Report Modal):** Fixed an issue where checking *"Include yesterday's sanitized log"* updated the cloud upload without including the prior-day file in the live preview, attached badge, fallback exports, or upload filename.
- **Benign Post-Destroy Timer Cleanup:** Eliminated harmless orphaned `after` timer tracebacks in the background console when closing the Schwab OAuth login dialog or short-lived modals.

### 🔍 Detailed Breakdown
- **Full Two-Day Safe Log Parity (`open_bug_report_dialog` & `_prepare_sanitized_log`):**
  - Toggling the prior-day checkbox now immediately updates the green `✓ Attached:` badge and feeds the combined log into *"Preview Attached Log"*, *"Copy Safe Log & Open Backup Web Form"*, and local fallback exports (`~/enforcer_log_sanitized.txt`, `~/Downloads/enforcer_log_sanitized.txt`, and clipboard).
  - Dual-log Bug Report uploads now include both dates in the uploaded filename (`BUG_REPORT_<today>_PLUS_<prior_date>_sanitized.txt`), list both files in the report header (`Attached Logs : Today (...) + Prior Day (...)`) and confirmation popup, and trim Today's log (up to `450,000` chars) before appending the prior-day block under the `900,000`-char upload cap so the prior-day section is never truncated off.
- **Schwab OAuth Timer & `bgerror` Hardening (`prompt_schwab_oauth_url_dialog` & `_install_tcl_bgerror_hook`):**
  - `poll_clipboard()` now tracks its scheduled `after()` handle in `clip_after_state` and cancels it cleanly across Submit, Cancel, and window close (`WM_DELETE_WINDOW`).
  - `_install_tcl_bgerror_hook()` now suppresses benign orphaned `invalid command name ... ("after" script)` callbacks while continuing to log real Tcl/Tk background errors to `[TCL_ERR]`.

---

## [v0.9.57] — 2026-11-14
### ⚡ Quick Summary
- **Pixel-Aligned `[Click to Expand]` / `[Click to Collapse]` Release Notes Headers:** Replaced character-count space padding with a DPI-aware pixel tab stop on Release Notes version headers so merged version ranges (`v0.9.46 – v0.9.53`, `v0.9.43 & v0.9.44`) and single-version headers align `[Click to Expand]` / `[Click to Collapse]` to the exact same column.

### 🔍 Detailed Breakdown
- **Release Notes Header Tab Stop Alignment (`_insert_formatted_changelog`, `_format_ver_hdr_line`):**
  - Configured a pixel tab stop (`tabs=(ver_tab_px,)`) on the `ver_hdr` tag measured via `tkinter.font.Font` in proportional `Arial 11 bold` and formatted `_format_ver_hdr_line()` with `\t` so all version header hints line up at the exact same pixel X coordinate across both collapsed (`▶`) and expanded (`▼`) states.

---

## [v0.9.56] — 2026-11-14
### ⚡ Quick Summary
- **Built-In In-App `🐞 Report Bug` Dialog with Auto-Attached Safe Log:** Clicking **`🐞 Report Bug`** now opens an in-app bug report modal with an optional contact field (persisted locally), a required description box, and automatic attachment of today's balance-redacted Safe Log (plus a **`🔍 Preview Safe Log`** button, optional prior-day Safe Log checkbox, and an **`Open Tally Web Form ↗`** fallback link).
- **Live Numeric Entry Filtering, 3-State `Stop Level ($)` Highlighting & Field-Specific Validation:** Pre-Flight numeric boxes now restrict invalid characters and multiple signs while typing, support `+`/`-` key sign-toggling and full double-click selection (including `-`), highlight Tier 2/3 **`Stop Level ($)`** boxes in rose-red (`< $0`), slate-blue (`$0`), or emerald green (`> $0`), and name the exact field in validation popups.
- **`Mute All Sounds & Voice Callouts (Silent Mode)` & Clearer Rulebook Switch Setting:** Added a master **`Mute All Sounds & Voice Callouts (Silent Mode — Work Calls / Quiet Room)`** checkbox inside **`⚙ Preferences & Audio...`** to silence all sirens, warning alarms, chimes, and TTS voice callouts during calls/meetings, and renamed the rulebook switch toggle to **`Reset Profit Ratchets at 9:30 AM & 4:00 PM Session Switch (Start at Base Tier 1)`** with a clear inline explanation.
- **Streamlined `✦ Quick Tour`, Non-Blocking Spotlight Pulse & Tcl `[TCL_ERR]` Logging:** Redesigned **`✦ Quick Tour`** into structured overview/controls/checklist tabs with an on-demand **`✦ Highlight Controls`** button (clicking anywhere stops the pulse immediately), fixed a `<Button-1>` event propagation error when closing Pre-Flight on launch, and routed C-level Tcl `bgerror` messages into `enforcer_log.txt` under `[TCL_ERR]`.

### 🔍 Detailed Breakdown
- **In-App Bug Report & Safe Log Attachment (`open_bug_report_dialog`, `_build_bug_report_header`, `_prepare_sanitized_log`, `_upload_sanitized_log_to_drive`, `show_telemetry_upload_result_dialog`, `bug_report_contact`):**
  - Replaced the external-only Tally browser jump in `report_bug_action()` with a dark-glass `open_bug_report_dialog()` modal that auto-attaches today's redacted Safe Log (and optionally the most recent prior-day Safe Log), prepends an environment + redacted config + description header (`_build_bug_report_header()`), and persists the optional Reddit/Discord/email field (`bug_report_contact`) locally.
  - Extended `_upload_sanitized_log_to_drive()` with optional `extra_fields` (`report_type`, `contact`, `description`) and preserved `Open Tally Web Form ↗` plus local/clipboard fallback when offline.
- **Numeric Entry Validation & 3-State Signed Stop Coloring (`_attach_numeric_entry_behavior`, `_validate_preflight_numeric_inputs`, `_apply_dynamic_stop_box_style`, `_signed_stop_visual_state`, `_refresh_dynamic_stop_box_colors`, `save_and_launch`):**
  - Added live keystroke validation (`_attach_numeric_entry_behavior`), `+`/`-` sign-toggling (`_on_key_minus`), and full-text double-click selection (`_on_double_click`) across Pre-Flight numeric inputs, plus field-specific error alerts in `_validate_preflight_numeric_inputs()`.
  - Updated `_apply_dynamic_stop_box_style()` and `_signed_stop_visual_state()` so Tier 2 and Tier 3 `Stop Level ($)` boxes reflect rose-red (`< $0`), slate-blue (`$0`), or emerald green (`> $0`).
- **Master Silent Mode & Session Behavior Clarity (`mute_all_audio`, `open_preferences_audio_dialog`, `format_config_summary`):**
  - Added `mute_all_audio` across all siren, warning alarm, chime, and speech paths (plus `SILENT MODE ACTIVE` status badge, live Card 3 summary indicator, and `SilentMode=ON/OFF` in `[CONFIG]` logs) inside `open_preferences_audio_dialog()`.
  - Clarified **`Reset Profit Ratchets at 9:30 AM & 4:00 PM Session Switch (Start at Base Tier 1)`** wording, hint text, and tooltip so users clearly see why Pre-Market peaks don't pre-trigger RTH profit tiers while full-day HUD totals remain intact.
- **Quick Tour, Non-Blocking Control Pulse & Tcl Error Hook (`show_layout_tour_dialog`, `pulse_relocated_controls`, `_stop_control_pulse`, `GlassStadiumButton._on_click`, `_install_tcl_bgerror_hook`, `_install_global_error_hooks`):**
  - Updated `show_layout_tour_dialog()` with fixed geometry across `Overview`, `Where Controls Live`, and `60-Second Checklist` tabs and added non-blocking `✦ Highlight Controls` spotlight pulsing (`pulse_relocated_controls()`, `_stop_control_pulse()`).
  - Updated `GlassStadiumButton._on_click()` to stop pulsing before action callbacks, guard destroyed widgets in `_after_menu_close()`, and `return "break"` to prevent `<Button-1>` event bubbling onto a destroyed Pre-Flight window (`_on_pf_button1` / `_cancel_pf_timers`), and installed `_install_tcl_bgerror_hook()` to capture C-level Tcl background errors in `enforcer_log.txt` as `[TCL_ERR]`.

---

## [v0.9.55] — 2026-11-14
### ⚡ Quick Summary
- **Monotonic Profit Ratchet Floor Clamping & Pre-Flight Inverted Stop Warning:** RTH Tiers 2–4 and Extended-Hours Profit Lock now enforce monotonic floor clamping so unlocking a higher profit tier can never loosen your Daily Stop below `Starting Max Loss ($)` or a lower enabled tier, and Pre-Flight warns you before launch if a Tier 2/3 `Stop Level ($)` is entered lower than an earlier tier.
- **Observation / `Alarms Only` Daily Breach Latch & Clean Tier 2/3 Startup:** Breaching the Daily Floor in `Alarms Only` Mode now latches cleanly so it sounds and logs once instead of re-checking every 2-second poll, and Tier 2/3 `$0` pullback warnings only pre-seed at launch once their unlock profit threshold has been reached (eliminating false `[REARM]` log entries).
- **Attempt `#1` Stale Socket Auto-Refresh (Schwab & Webull):** Refreshes the broker HTTP session immediately on Attempt `#1` of a read timeout so stale idle keep-alive sockets recover cleanly without tripping a 2-poll `CONNECTION LOST` alert.

### 🔍 Detailed Breakdown
- **Monotonic Profit Ratchet Floor Protection (`_get_effective_rth_tier_stops`, `describe_active_floor`, `data_loop`, `save_and_launch`):**
  - Added `_get_effective_rth_tier_stops()` and applied consistent floor clamping across `describe_active_floor()` and `data_loop()` (covering RTH Tiers 2–4 and Extended-Hours Profit Lock) so an inverted `Stop Level ($)` or wide trailing offset never drops the active floor below `Starting Max Loss ($)` or a prior unlocked tier.
  - Updated `[RATCHET]` log and emerald HUD banner messaging to display `FLOOR HELD AT ... (clamped; configured Tier N stop ... is below prior floor)` whenever clamping holds the prior floor.
  - Added a Pre-Flight confirmation prompt in `save_and_launch()` when an enabled Tier 2 or Tier 3 `Stop Level ($)` is below the preceding tier, clarifying that `Stop Level ($)` represents the Daily Net PnL stop level (e.g., `-250`, `0`, or `+100`) rather than a trailing offset.
- **Observation Mode Daily Breach Latch & Tier 2/3 `$0` Pre-Seed Fix (`trigger_lockdown`, `data_loop`):**
  - Latched `is_locked_down = True` and `daily_breach_settings_prompted = False` inside `trigger_lockdown()` when `Alarms Only Mode` is ON (or all daily enforcement toggles are OFF), preventing repeated `0.2s` anti-wick broker re-fetches and `[GUARDRAIL]` log spam on every subsequent poll while still preserving recovery auto-rearm (`RECOVERY_BUFFER_DOLLARS`).
  - Guarded `first_poll_of_launch` pre-seeding of `"Hit $0 (Tier 2)"` and `"Hit $0 (Tier 3)"` in `data_loop()` so those pullback alerts are only pre-seeded when the corresponding tier is already unlocked (`max_realized_profit >= t2_trig` / `t3_trig` with a negative effective stop).
- **Attempt `#1` Stale Keep-Alive Socket Refresh (`data_loop` — Schwab & Webull):**
  - Called `active_adapter.reconnect_session()` immediately on `consecutive_api_failures == 1` (non-token-expiration errors) so stale `httpx` / `requests` keep-alive connections after idle periods are flushed before Attempt `#2` runs, eliminating false 2-poll `CONNECTION LOST` alerts.

---

## [v0.9.54] — 2026-11-13
### ⚡ Quick Summary
- **One-Click `Inspect Source ↗` Links & `Check for Updates on Startup` Toggle:** Added an **`Inspect Source ↗`** button to the **Update Available** dialog, the **Release Notes** viewer, and the Pre-Flight footer (`Inspect Source ↗`) that opens the GitHub Gist source bundle in your browser, plus a **`Check for Updates on Startup`** checkbox (enabled by default) inside **`⚙ Preferences & Audio...`** for users who prefer to manage updates manually.
- **Background Update Modal & Full-File Verification Fixes:** Fixed a `NameError` (`hide_all_tooltips`) when opening the **Update Available** modal over the Pre-Flight window, verified full-file syntax (`compile()`) and end-of-file markers on 900 KB+ update payloads, and prioritized the user's primary `PATH` `pythonw.exe` in `Launch_Enforcer.bat`.

### 🔍 Detailed Breakdown
- **Source Code Inspection & Update Preferences (`get_source_diff_web_url`, `show_update_available_dialog`, `show_release_notes_dialog`, `open_preferences_modal`):**
  - Added `SOURCE_DIFF_WEB_URL` and `BETA_SOURCE_DIFF_WEB_URL` pointing to the GitHub Gist bundle for the active channel, wired to **`Inspect Source ↗`** buttons in the Update Available and Release Notes headers plus **`Inspect Source ↗`** in the Pre-Flight footer.
  - Added a **`Check for Updates on Startup`** toggle (`check_updates_on_startup`, default `True`) in Section 3 (`SYSTEM & TELEMETRY`) of **`⚙ Preferences & Audio...`** that persists immediately on toggle and skips startup update checks when unchecked.
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
