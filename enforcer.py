"""
PnL Enforcer (Closed Beta) — Dual-Broker Edition (Charles Schwab & Webull)
MIT License & Trading Risk Disclaimer — Provided "AS IS" without warranty of any kind.
Not financial advice; no guarantee of loss prevention; not affiliated with Schwab or Webull.
See LICENSE.txt for full terms, limitation of liability, and indemnification.
"""

import os
import sys
import re
import uuid
import json
import hashlib
import ctypes
import time
import builtins
import webbrowser
import threading
import tkinter as tk
from tkinter import messagebox
import winsound
import logging
import warnings
import subprocess
from datetime import datetime, time as dt_time

# Suppress harmless Tkinter Variable.__del__ RuntimeError when Python's
# cyclic garbage collector runs on the background API polling thread
# after the Pre-Flight or HUD Columns dialog has been closed.
_orig_tk_var_del = getattr(tk.Variable, "__del__", None)
if _orig_tk_var_del is not None:
    def _safe_tk_var_del(self):
        try:
            _orig_tk_var_del(self)
        except Exception:
            pass

    tk.Variable.__del__ = _safe_tk_var_del

# ==========================================
# 1. DYNAMIC USER PATHS (NO HARDCODED KEYS)
# ==========================================
USER_HOME = os.path.expanduser("~")
# Keep working directory in USER_HOME so Webull SDK stores conf/token.txt
# safely in C:\Users\<Username>\conf\ instead of inside the repo folder.
try:
    os.chdir(USER_HOME)
except Exception:
    pass

SCHWAB_TOKEN_PATH = os.path.join(USER_HOME, "schwab_token.json")
CONFIG_PATH = os.path.join(USER_HOME, "enforcer_config.json")
LOG_PATH = os.path.join(USER_HOME, "enforcer_log.txt")
CALLBACK_URL = "https://127.0.0.1"

logging.basicConfig(level=logging.INFO)
logging.getLogger("webull").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ==========================================
# 2. DEFAULT CONFIGURATION
# ==========================================
WAIVER_VERSION = "2026.10.29"

DEFAULT_CONFIG = {
    "waiver_accepted": False,
    "waiver_accepted_version": "",
    "waiver_accepted_at": "",
    "waiver_sha256": "",
    "active_broker": "SCHWAB",
    "brokers": {
        "SCHWAB": {
            "app_key": "",
            "app_secret": "",
            "selected_account_id": ""
        },
        "WEBULL": {
            "app_key": "",
            "app_secret": "",
            "selected_account_id": ""
        }
    },
    "account_sessions": {},
    "user_defaults": {},
    "enable_auto_flatten": False,
    "enable_kill_tos": False,
    "enable_kill_webull": False,
    "enable_lock_os": False,
    "daily_lock_mins": 15.0,
    "enable_open_flatten": False,
    "open_max_loss": 500.0,
    "enable_open_cooldown": False,
    "open_cooldown_mins": 1.0,
    "enable_voice_cues": True,
    "enable_upside_chime": True,
    "hud_columns": [
        "realized_pnl",
        "open_pnl",
        "terminate_lvl",
        "dist_to_term",
        "session_high",
    ],
    "reset_at_925": True,
    "poll_interval": 2,
    "enable_pm_warn_1": True,
    "enable_pm_warn_2": True,
    "enable_pm_lock": True,
    "pm_warn_1": 500.0,
    "pm_warn_2": 1000.0,
    "pm_max_loss": 1500.0,
    "pm_lock_trigger": 500.0,
    "pm_trail_cushion": 500.0,
    "enable_t1_warn_1": True,
    "enable_t1_warn_2": True,
    "enable_t2": True,
    "enable_t3": True,
    "enable_t4": True,
    "t1_warn_1": 1000.0,
    "t1_warn_2": 1500.0,
    "t1_max_loss": 2000.0,
    "t2_trigger": 250.0,
    "t2_max_loss": 1000.0,
    "t3_trigger": 500.0,
    "t3_max_loss": 500.0,
    "t4_trigger": 1000.0,
    "t4_trail": 500.0,
    "session_date": "",
    "saved_start_equity": None,
    "saved_max_equity": None,
    "saved_daily_max_equity": None,
    "saved_last_flat_equity": None,
    "saved_has_reset_at_open": False,
    "saved_win_trades": 0,
    "saved_loss_trades": 0,
    "saved_account_id": ""
}

HUD_COLUMN_CATALOG = [
    ("realized_pnl", "REALIZED PnL", "Closed (flat) PnL for the day"),
    ("open_pnl", "OPEN PnL", "Live unrealized PnL on open positions"),
    ("net_pnl", "NET PnL", "Total daily PnL (Realized + Open)"),
    ("terminate_lvl", "TERMINATE LVL", "Active Pre-Market or RTH lockout floor"),
    ("dist_to_term", "$ TO TERMINATE", "Remaining dollar cushion above floor"),
    ("session_high", "SESSION HIGH", "Highest flat realized PnL of the day"),
    ("from_high", "FROM HIGH", "Current drawdown/giveback from Session High"),
    ("trades_wl", "TRADES (W/L)", "Completed round-trip Wins & Losses (%)"),
]
HUD_COL_HEADERS = {col_id: hdr for col_id, hdr, _ in HUD_COLUMN_CATALOG}
DEFAULT_HUD_COLUMNS = [
    "realized_pnl",
    "open_pnl",
    "terminate_lvl",
    "dist_to_term",
    "session_high",
]

HALF_RISK_DOLLARS = {
    "open_max_loss": 250.0,
    "pm_warn_1": 250.0,
    "pm_warn_2": 500.0,
    "pm_max_loss": 750.0,
    "pm_lock_trigger": 250.0,
    "pm_trail_cushion": 250.0,
    "t1_warn_1": 500.0,
    "t1_warn_2": 750.0,
    "t1_max_loss": 1000.0,
    "t2_trigger": 125.0,
    "t2_max_loss": 500.0,
    "t3_trigger": 250.0,
    "t3_max_loss": 250.0,
    "t4_trigger": 500.0,
    "t4_trail": 250.0
}

config = json.loads(json.dumps(DEFAULT_CONFIG))

# ==========================================
# 3. GLOBAL TRACKERS & STATE
# ==========================================
start_equity = None
max_equity = None
daily_max_equity = None
last_flat_equity = None
has_reset_at_open = False
is_locked_down = False
force_reanchor = False
current_is_flat = True
first_poll_of_launch = True

alarm_active = False
cooldown_active = False
cooldown_end_time = 0.0
cooldown_label = "COOL-DOWN LOCK"
cooldown_30s_announced = False
current_upside_tier = 1
last_rth_mode = None
win_trades = 0
loss_trades = 0
prev_flat_realized_pnl = 0.0
triggered_alarms = {}
ALARM_COOLDOWN_SEC = 180
RECOVERY_BUFFER_DOLLARS = 150.0

settings_win_open = False
log_lock = threading.Lock()
prev_pos_snapshot = {}
active_adapter = None


def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


def get_session_key(broker_name, account_id):
    if not broker_name or not account_id:
        return ""
    return f"{broker_name}_{account_id}"


def format_dollar(val):
    rounded = round(val, 2)
    if rounded > 0:
        return f"+${rounded:,.2f}"
    elif rounded < 0:
        return f"-${abs(rounded):,.2f}"
    return "$0.00"


def get_active_hud_columns(cfg=None):
    raw_cols = (cfg or config).get("hud_columns") or DEFAULT_HUD_COLUMNS
    valid = [c for c in raw_cols if c in HUD_COL_HEADERS]
    return valid if valid else list(DEFAULT_HUD_COLUMNS)


def format_trades_wl_multiline(wins, losses):
    total = int(wins) + int(losses)
    if total <= 0:
        return "W: 0 (0.0%)\nL: 0 (0.0%)"
    w_pct = (wins / total) * 100.0
    l_pct = (losses / total) * 100.0
    return f"W: {wins} ({w_pct:.1f}%)\nL: {losses} ({l_pct:.1f}%)"


def format_trades_wl_inline(wins, losses):
    total = int(wins) + int(losses)
    if total <= 0:
        return "W: 0 (0.0%) | L: 0 (0.0%)"
    w_pct = (wins / total) * 100.0
    l_pct = (losses / total) * 100.0
    return f"W: {wins} ({w_pct:.1f}%) | L: {losses} ({l_pct:.1f}%)"


def backfill_trades_from_today_log(target_broker=None):
    """If today's log has completed round-trip trades and win/loss counters
    are at 0 (e.g. upgrading mid-day), reconstructs W/L from today's log
    for the specified broker without cross-contaminating other brokers."""
    if not os.path.exists(LOG_PATH):
        return 0, 0, 0.0
    today_str = get_today_str()
    w_cnt = 0
    l_cnt = 0
    prev_real = 0.0
    curr_log_broker = target_broker or "SCHWAB"
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            first = f.readline()
            if today_str not in first:
                return 0, 0, 0.0
            for line in f:
                if "SCHWAB API authenticated" in line or "Broker=SCHWAB" in line:
                    curr_log_broker = "SCHWAB"
                elif "WEBULL API authenticated" in line or "Broker=WEBULL" in line:
                    curr_log_broker = "WEBULL"

                if "Baseline anchored to:" in line:
                    if target_broker is None or f"({target_broker})" in line:
                        w_cnt = 0
                        l_cnt = 0
                        prev_real = 0.0
                elif (
                    (target_broker is None or curr_log_broker == target_broker)
                    and "[POS_CHANGE]" in line
                    and ("(CLOSED FLAT)" in line or "Re-entry Avg:" in line)
                ):
                    m = re.search(
                        r"Realized:\s*([+-]?)\$(\d[\d,]*\.\d{2})", line
                    )
                    if m:
                        sign = -1.0 if m.group(1) == "-" else 1.0
                        val = sign * float(m.group(2).replace(",", ""))
                        delta = round(val - prev_real, 2)
                        if delta > 0.0:
                            w_cnt += 1
                        elif delta < 0.0:
                            l_cnt += 1
                        prev_real = val
    except Exception:
        pass
    return w_cnt, l_cnt, prev_real


# --- ACTION-ONLY DAILY EVENT LOGGER ---
def init_daily_log():
    today_str = get_today_str()
    header_line = f"=== ENFORCER SESSION LOG | DATE: {today_str} ===\n"
    needs_wipe = True

    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                first_line = f.readline()
                if today_str in first_line:
                    needs_wipe = False
        except Exception:
            needs_wipe = True

    try:
        if needs_wipe:
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.write(header_line)
                f.write(f"Log File Path: {LOG_PATH}\n" + "=" * 50 + "\n")
            log_event("SESSION", "Initialized fresh daily log file.")
        else:
            log_event("SESSION", "--- APPLICATION LAUNCHED / RESUMED ---")
    except Exception as e:
        print(f"Could not initialize log file: {e}")


def log_event(category, message):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{category:<10}] {message}"
    print(line)
    with log_lock:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"Log write error: {e}")


def _custom_showwarning(message, category, filename, lineno, file=None, line=None):
    short_file = os.path.basename(str(filename)) if filename else "unknown"
    cat_name = getattr(category, "__name__", str(category))
    msg_clean = str(message).strip().replace("\n", " ")
    log_event("PY_WARN", f"{cat_name} ({short_file}:{lineno}): {msg_clean}")


warnings.showwarning = _custom_showwarning


class _EnforcerFileLogHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self._in_emit = False

    def emit(self, record):
        if self._in_emit:
            return
        try:
            self._in_emit = True
            msg = record.getMessage().strip().replace("\n", " ")
            if msg:
                log_event("LIB_WARN", f"{record.name} ({record.levelname}): {msg}")
        except Exception:
            pass
        finally:
            self._in_emit = False


logging.getLogger().addHandler(_EnforcerFileLogHandler())


def format_config_summary(cfg):
    broker = cfg.get("active_broker", "SCHWAB")
    cd_str = (
        f"ON({cfg.get('open_cooldown_mins', 1):g}m)"
        if cfg.get("enable_open_cooldown") else "OFF"
    )
    dl_mins = cfg.get("daily_lock_mins", 15.0)
    dl_str = (
        f"ON({dl_mins:g}m)" if dl_mins > 0 else "ON(Once)"
    ) if cfg.get("enable_lock_os") else "OFF"

    return (
        f"Broker={broker} | Poll={cfg.get('poll_interval')}s | "
        f"OpenStop={'ON' if cfg.get('enable_open_flatten') else 'OFF'}"
        f"(-${cfg.get('open_max_loss', 0):,.0f}, CoolDown={cd_str}) | "
        f"DayFlat={'ON' if cfg.get('enable_auto_flatten') else 'OFF'} | "
        f"KillTOS={'ON' if cfg.get('enable_kill_tos') else 'OFF'} | "
        f"KillWB={'ON' if cfg.get('enable_kill_webull') else 'OFF'} | "
        f"LockOS={dl_str} | "
        f"Voice={'ON' if cfg.get('enable_voice_cues', True) else 'OFF'} | "
        f"UpChime={'ON' if cfg.get('enable_upside_chime', True) else 'OFF'} | "
        f"PM_Max=-${cfg.get('pm_max_loss', 0):,.0f} | "
        f"T1_Max=-${cfg.get('t1_max_loss', 0):,.0f}"
    )


def restore_account_session(broker_name, account_id, log_restore=False):
    """Restores today's saved baseline for a specific broker + account_id.
    Returns True if a valid baseline for today was found, False otherwise."""
    global start_equity, max_equity, daily_max_equity
    global last_flat_equity, has_reset_at_open
    global win_trades, loss_trades, prev_flat_realized_pnl
    global current_upside_tier, first_poll_of_launch

    today_str = get_today_str()
    s_key = get_session_key(broker_name, account_id)
    acct_sessions = config.get("account_sessions", {})

    if s_key and s_key in acct_sessions:
        s_data = acct_sessions[s_key]
        s_start = s_data.get("start_equity")
        if (
            s_data.get("session_date") == today_str
            and s_start is not None
            and float(s_start) > 0.0
        ):
            start_equity = float(s_start)
            max_equity = float(s_data.get("max_equity") or start_equity)
            daily_max_equity = float(
                s_data.get("daily_max_equity") or max_equity
            )
            last_flat_equity = float(
                s_data.get("last_flat_equity") or start_equity
            )
            has_reset_at_open = bool(
                s_data.get("has_reset_at_open", False)
            )
            win_trades = int(s_data.get("win_trades", 0) or 0)
            loss_trades = int(s_data.get("loss_trades", 0) or 0)
            prev_flat_realized_pnl = round(last_flat_equity - start_equity, 2)
            if win_trades == 0 and loss_trades == 0:
                bw, bl, _ = backfill_trades_from_today_log(broker_name)
                if bw > 0 or bl > 0:
                    win_trades, loss_trades = bw, bl
            current_upside_tier = compute_upside_tier(
                is_rth(), round(max_equity - start_equity, 2), config
            )
            first_poll_of_launch = True
            if log_restore:
                log_event(
                    "SESSION",
                    f"Restored {broker_name} baseline from memory: "
                    f"Start=${start_equity:,.2f} | "
                    f"LastFlat=${last_flat_equity:,.2f} | "
                    f"SessionHighPnL={format_dollar(daily_max_equity - start_equity)} | "
                    f"{format_trades_wl_inline(win_trades, loss_trades)}"
                )
            return True

    # Backward-compatible check for legacy top-level saved session fields
    saved_start = config.get("saved_start_equity")
    if (
        config.get("session_date") == today_str
        and saved_start is not None
        and float(saved_start) > 0.0
        and config.get("saved_account_id") == account_id
        and account_id != ""
    ):
        start_equity = float(saved_start)
        max_equity = float(config.get("saved_max_equity") or start_equity)
        daily_max_equity = float(
            config.get("saved_daily_max_equity") or max_equity
        )
        last_flat_equity = float(
            config.get("saved_last_flat_equity") or start_equity
        )
        has_reset_at_open = bool(config.get("saved_has_reset_at_open", False))
        win_trades = int(config.get("saved_win_trades", 0) or 0)
        loss_trades = int(config.get("saved_loss_trades", 0) or 0)
        prev_flat_realized_pnl = round(last_flat_equity - start_equity, 2)
        if win_trades == 0 and loss_trades == 0:
            bw, bl, _ = backfill_trades_from_today_log(broker_name)
            if bw > 0 or bl > 0:
                win_trades, loss_trades = bw, bl
        current_upside_tier = compute_upside_tier(
            is_rth(), round(max_equity - start_equity, 2), config
        )
        first_poll_of_launch = True
        if log_restore:
            log_event(
                "SESSION",
                f"Restored {broker_name} baseline from memory: "
                f"Start=${start_equity:,.2f} | "
                f"LastFlat=${last_flat_equity:,.2f} | "
                f"SessionHighPnL={format_dollar(daily_max_equity - start_equity)} | "
                f"{format_trades_wl_inline(win_trades, loss_trades)}"
            )
        return True

    start_equity = None
    max_equity = None
    daily_max_equity = None
    last_flat_equity = None
    has_reset_at_open = False
    win_trades = 0
    loss_trades = 0
    prev_flat_realized_pnl = 0.0
    current_upside_tier = 1
    first_poll_of_launch = True
    return False


def load_config(log_restore=False):
    global config
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                saved_brokers = saved.pop("brokers", {})
                saved_sessions = saved.pop("account_sessions", {})
                saved_user_defs = saved.pop("user_defaults", {})
                config.update(saved)
                for b_name in ("SCHWAB", "WEBULL"):
                    if b_name in saved_brokers:
                        config["brokers"][b_name].update(saved_brokers[b_name])
                if isinstance(saved_sessions, dict):
                    config["account_sessions"].update(saved_sessions)
                if isinstance(saved_user_defs, dict):
                    config["user_defaults"] = saved_user_defs
        except Exception as e:
            print(f"Could not load saved config: {e}")

    active_b = config.get("active_broker", "SCHWAB")
    sel_acct = (
        config["brokers"].get(active_b, {}).get("selected_account_id", "")
    )
    if start_equity is None and sel_acct:
        restore_account_session(active_b, sel_acct, log_restore=log_restore)


def save_config(new_cfg):
    global config
    config = json.loads(json.dumps(new_cfg))
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config file: {e}")


def save_session_state():
    today_str = get_today_str()
    active_b = (
        active_adapter.name
        if active_adapter is not None
        else config.get("active_broker", "SCHWAB")
    )
    sel_acct = (
        active_adapter.account_id
        if active_adapter is not None and active_adapter.account_id
        else config["brokers"].get(active_b, {}).get("selected_account_id", "")
    )
    s_key = get_session_key(active_b, sel_acct)

    if "account_sessions" not in config or not isinstance(
        config["account_sessions"], dict
    ):
        config["account_sessions"] = {}

    new_entry = {
        "session_date": today_str,
        "start_equity": start_equity,
        "max_equity": max_equity,
        "daily_max_equity": daily_max_equity,
        "last_flat_equity": last_flat_equity,
        "has_reset_at_open": has_reset_at_open,
        "win_trades": win_trades,
        "loss_trades": loss_trades,
    }

    old_entry = config["account_sessions"].get(s_key)
    changed = (
        old_entry != new_entry
        or config.get("session_date") != today_str
        or config.get("saved_start_equity") != start_equity
        or config.get("saved_max_equity") != max_equity
        or config.get("saved_daily_max_equity") != daily_max_equity
        or config.get("saved_last_flat_equity") != last_flat_equity
        or config.get("saved_has_reset_at_open") != has_reset_at_open
        or config.get("saved_win_trades") != win_trades
        or config.get("saved_loss_trades") != loss_trades
        or config.get("saved_account_id") != sel_acct
    )
    if changed:
        if s_key:
            config["account_sessions"][s_key] = new_entry
        config["session_date"] = today_str
        config["saved_start_equity"] = start_equity
        config["saved_max_equity"] = max_equity
        config["saved_daily_max_equity"] = daily_max_equity
        config["saved_last_flat_equity"] = last_flat_equity
        config["saved_has_reset_at_open"] = has_reset_at_open
        config["saved_win_trades"] = win_trades
        config["saved_loss_trades"] = loss_trades
        config["saved_account_id"] = sel_acct
        save_config(config)


def is_rth():
    now = datetime.now().time()
    return dt_time(9, 25) <= now <= dt_time(16, 0)


def is_market_hours():
    now = datetime.now().time()
    return dt_time(9, 30) <= now < dt_time(16, 0)


def calc_ext_limit_price(ref_price, is_sell=True):
    """Calculates a marketable extended-hours limit price just past
    the current Bid/Ask without triggering broker price-collar rejections."""
    if ref_price < 1.0:
        offset = min(max(ref_price * 0.02, 0.005), 0.02)
        raw = (ref_price - offset) if is_sell else (ref_price + offset)
        return round(max(0.0001, raw), 4)
    elif ref_price < 3.0:
        offset = 0.03
    elif ref_price < 10.0:
        offset = 0.05
    else:
        offset = min(ref_price * 0.01, 0.15)

    offset = min(offset, ref_price * 0.025)
    raw = (ref_price - offset) if is_sell else (ref_price + offset)
    return round(max(0.01, raw), 2)


def format_limit_price_str(price_val):
    """Formats a limit price float as a clean string (2 decimals for >= $1.00,
    up to 4 decimals for sub-$1.00 stocks) so schwab-py and Webull SDKs
    never emit float deprecation warnings or float precision artifacts."""
    p = float(price_val)
    if p < 1.0:
        s = f"{p:.4f}".rstrip("0").rstrip(".")
        if "." not in s:
            return f"{p:.2f}"
        dec_part = s.split(".")[1]
        if len(dec_part) < 2:
            return f"{p:.2f}"
        return s
    return f"{p:.2f}"


def sanitize_equity_live_price(raw_last, bid=None, ask=None, mark=None, net_qty=0):
    """Protects equity open PnL valuation against off-exchange FINRA TRF / dark-pool
    sub-penny prints and single-order wicks that fall outside the live NBBO
    [bid, ask] spread."""
    def _pos_f(v):
        try:
            f = float(v)
            return f if f > 0.0 else None
        except Exception:
            return None

    lp = _pos_f(raw_last)
    b = _pos_f(bid)
    a = _pos_f(ask)
    m = _pos_f(mark)

    if lp is None:
        lp = m or b or a
    if lp is None:
        return None

    if b is not None and a is not None and b <= a:
        if lp < b:
            return b
        if lp > a:
            return a
        return lp

    if net_qty > 0 and b is not None and lp < b:
        return b
    if net_qty < 0 and a is not None and lp > a:
        return a

    return lp


# ==========================================
# 4. DUAL-BROKER ADAPTER ENGINE (SCHWAB & WEBULL)
# ==========================================
def get_schwab_token_remaining_hours():
    """Returns remaining lifetime (in hours) of the 7-day Schwab Refresh Token,
    or None if the token file does not exist or lacks creation_timestamp."""
    if not os.path.exists(SCHWAB_TOKEN_PATH):
        return None
    try:
        with open(SCHWAB_TOKEN_PATH, "r", encoding="utf-8") as f:
            tok_data = json.load(f)
        created_ts = tok_data.get("creation_timestamp")
        if created_ts is not None:
            expires_ts = float(created_ts) + (7 * 86400)
            return (expires_ts - time.time()) / 3600.0
    except Exception:
        pass
    return None


def prompt_schwab_oauth_url_dialog(auth_url=""):
    """Displays an always-on-top GUI popup with clickable link, clear numbered
    instructions, and clipboard auto-detection for the Schwab 7-day OAuth URL."""
    result = {"url": ""}
    login_url = auth_url or "https://api.schwabapi.com"
    parent = getattr(tk, "_default_root", None)
    is_standalone = parent is None

    dlg = tk.Tk() if is_standalone else tk.Toplevel(parent)
    if not is_standalone:
        dlg.grab_set()

    dlg.title("Schwab 7-Day Security Login — Step-by-Step")
    dlg.config(bg="#141414", padx=24, pady=18)
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)

    tk.Label(
        dlg,
        text="🔐 SCHWAB 7-DAY SECURITY LOGIN (STEP-BY-STEP)",
        font=("Arial", 12, "bold"),
        fg="#5dade2",
        bg="#141414",
        anchor="w"
    ).pack(fill="x", pady=(0, 8))

    steps_frame = tk.Frame(
        dlg, bg="#1e1e1e", bd=1, relief="solid", padx=16, pady=12
    )
    steps_frame.pack(fill="x", pady=(0, 12))

    tk.Label(
        steps_frame,
        text=(
            "STEP 1: Log into your Charles Schwab account in the browser window that just opened\n"
            "        and approve account access. (If your browser didn't open, click the link below):"
        ),
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1e1e1e",
        justify="left",
        anchor="w"
    ).pack(fill="x", pady=(0, 4))

    link_lbl = tk.Label(
        steps_frame,
        text="🌐 Click Here to Open / Re-Open the Charles Schwab Login Page in Your Browser",
        font=("Arial", 10, "bold underline"),
        fg="#5dade2",
        bg="#1e1e1e",
        cursor="hand2",
        anchor="w"
    )
    link_lbl.pack(fill="x", padx=18, pady=(0, 10))
    link_lbl.bind("<Button-1>", lambda _e: webbrowser.open(login_url))

    tk.Label(
        steps_frame,
        text=(
            "STEP 2: After clicking Approve on Schwab's site, your browser will redirect to a blank\n"
            "        \"This site can't be reached (127.0.0.1)\" page. This is 100% normal!\n\n"
            "STEP 3: Copy the ENTIRE URL from the top of your browser's address bar\n"
            "        (it starts with  https://127.0.0.1/?code=... ) and paste it below:"
        ),
        font=("Arial", 10),
        fg="#dddddd",
        bg="#1e1e1e",
        justify="left",
        anchor="w"
    ).pack(fill="x")

    tk.Label(
        dlg,
        text="Redirected Browser URL (https://127.0.0.1/?code=...):",
        font=("Arial", 10, "bold"),
        fg="#ffffff",
        bg="#141414",
        anchor="w"
    ).pack(fill="x", pady=(2, 4))

    url_entry = tk.Entry(
        dlg,
        font=("Consolas", 10, "bold"),
        width=74,
        bg="#2a2a2a",
        fg="#ffffff",
        insertbackground="white",
        bd=1,
        relief="solid"
    )
    url_entry.pack(fill="x", pady=(0, 6))
    url_entry.focus_set()

    status_lbl = tk.Label(
        dlg,
        text="⏳ Waiting for https://127.0.0.1/?code=... URL (auto-fills as soon as you copy it in your browser)...",
        font=("Arial", 9, "bold"),
        fg="#f5b041",
        bg="#141414",
        anchor="w"
    )
    status_lbl.pack(fill="x", pady=(0, 10))

    def is_valid_redirect(text):
        t = (text or "").strip()
        return t.startswith("https://127.0.0.1") and "code=" in t

    def paste_from_clipboard():
        try:
            clip = dlg.clipboard_get().strip()
        except Exception:
            clip = ""
        if clip:
            url_entry.delete(0, "end")
            url_entry.insert(0, clip)
            if is_valid_redirect(clip):
                status_lbl.config(
                    text="✓ Valid Schwab redirect URL pasted! Click 'Complete Schwab Login >>' below.",
                    fg="#58d68d"
                )
            else:
                status_lbl.config(
                    text="⚠️ Pasted text does not start with https://127.0.0.1/?code=... — check your browser address bar.",
                    fg="#eb7067"
                )

    def poll_clipboard():
        if not dlg.winfo_exists():
            return
        curr = url_entry.get().strip()
        if not is_valid_redirect(curr):
            try:
                clip = dlg.clipboard_get().strip()
                if is_valid_redirect(clip):
                    url_entry.delete(0, "end")
                    url_entry.insert(0, clip)
                    status_lbl.config(
                        text="✓ Redirect URL auto-detected from your clipboard! Click 'Complete Schwab Login >>' below.",
                        fg="#58d68d"
                    )
            except Exception:
                pass
        dlg.after(450, poll_clipboard)

    dlg.after(450, poll_clipboard)

    def submit_url(event=None):
        val = url_entry.get().strip()
        if not is_valid_redirect(val):
            messagebox.showwarning(
                "Invalid Redirect URL",
                "Please copy and paste the FULL redirect URL from your browser's address bar.\n\n"
                "It must start with:\nhttps://127.0.0.1/?code=...",
                parent=dlg
            )
            return
        result["url"] = val
        dlg.destroy()

    url_entry.bind("<Return>", submit_url)

    btn_row = tk.Frame(dlg, bg="#141414", pady=6)
    btn_row.pack(fill="x")

    tk.Button(
        btn_row,
        text="Cancel",
        font=("Arial", 10, "bold"),
        bg="#333333",
        fg="white",
        padx=14,
        pady=6,
        command=dlg.destroy
    ).pack(side="left")

    tk.Button(
        btn_row,
        text="📋 Paste from Clipboard",
        font=("Arial", 10, "bold"),
        bg="#1f538d",
        fg="white",
        padx=16,
        pady=6,
        command=paste_from_clipboard
    ).pack(side="left", padx=10)

    tk.Button(
        btn_row,
        text="Complete Schwab Login >>",
        font=("Arial", 10, "bold"),
        bg="#1e8449",
        fg="white",
        padx=20,
        pady=6,
        command=submit_url
    ).pack(side="right")

    if is_standalone:
        dlg.mainloop()
    else:
        parent.wait_window(dlg)

    if not result["url"]:
        raise RuntimeError(
            "Schwab browser login was cancelled before pasting the redirect URL."
        )
    return result["url"]


class SchwabAdapter:
    name = "SCHWAB"

    def __init__(self, app_key, app_secret):
        self.app_key = app_key.strip()
        self.app_secret = app_secret.strip()
        self.client = None
        self.account_id = None
        self.accounts = []
        self.last_error = ""

    def authenticate(self):
        from schwab.auth import client_from_manual_flow, client_from_token_file
        try:
            if os.path.exists(SCHWAB_TOKEN_PATH):
                rem_hrs = get_schwab_token_remaining_hours()
                if rem_hrs is not None and rem_hrs < 14.0:
                    raise RuntimeError(
                        f"Schwab 7-day token has {max(0.0, rem_hrs):.1f}h remaining "
                        f"(<14h safety buffer) — refreshing proactively before session"
                    )
                self.client = client_from_token_file(
                    SCHWAB_TOKEN_PATH, self.app_key, self.app_secret
                )
                resp = self.client.get_account_numbers()
                if resp.status_code == 200:
                    self._parse_accounts(resp.json())
                    return True
        except Exception as e:
            log_event(
                "SESSION",
                f"Saved Schwab token expired or invalid ({e}). "
                f"Starting fresh OAuth flow..."
            )
            if os.path.exists(SCHWAB_TOKEN_PATH):
                try:
                    os.remove(SCHWAB_TOKEN_PATH)
                except Exception:
                    pass

        print("\n=======================================================")
        print("  SCHWAB OAUTH LOGIN — OPENING BROWSER & PASTE DIALOG")
        print("=======================================================\n")

        opened = {"done": False, "url": ""}

        def try_open_url(text):
            match = re.search(
                r"(https://api\.schwabapi\.com/v1/oauth/authorize\S+)",
                str(text)
            )
            if match:
                opened["url"] = match.group(1)
                if not opened["done"]:
                    opened["done"] = True
                    webbrowser.open(opened["url"])

        class BrowserLogHandler(logging.Handler):
            def emit(self, record):
                try_open_url(record.getMessage())

        handler = BrowserLogHandler()
        logging.getLogger().addHandler(handler)
        orig_print = builtins.print
        orig_input = builtins.input

        def hooked_print(*args, **kwargs):
            orig_print(*args, **kwargs)
            try_open_url(" ".join(str(a) for a in args))

        def hooked_input(prompt=""):
            if prompt:
                orig_print(prompt)
                try_open_url(prompt)
            return prompt_schwab_oauth_url_dialog(opened.get("url", ""))

        builtins.print = hooked_print
        builtins.input = hooked_input
        try:
            self.client = client_from_manual_flow(
                self.app_key, self.app_secret, CALLBACK_URL, SCHWAB_TOKEN_PATH
            )
        finally:
            builtins.print = orig_print
            builtins.input = orig_input
            logging.getLogger().removeHandler(handler)

        resp = self.client.get_account_numbers()
        if resp.status_code == 200:
            self._parse_accounts(resp.json())
            return True
        raise RuntimeError(
            f"Schwab get_account_numbers failed: HTTP {resp.status_code}"
        )

    def _parse_accounts(self, acct_list):
        self.accounts = []
        for item in acct_list:
            acc_num = str(item.get("accountNumber", ""))
            h_val = str(item.get("hashValue", ""))
            masked = f"...{acc_num[-4:]}" if len(acc_num) >= 4 else acc_num
            self.accounts.append({
                "id": h_val,
                "label": f"Schwab Account {masked}"
            })
        if self.accounts and not self.account_id:
            self.account_id = self.accounts[0]["id"]

    def cancel_all_working_orders(self):
        try:
            today_start = datetime.combine(datetime.now().date(), dt_time(0, 0))
            orders_resp = self.client.get_orders_for_account(
                self.account_id, from_entered_datetime=today_start
            )
        except TypeError:
            orders_resp = self.client.get_orders_for_account(self.account_id)

        if orders_resp.status_code == 200:
            active_statuses = [
                "WORKING", "QUEUED", "PENDING_ACTIVATION", "ACCEPTED"
            ]
            cancelled_any = False
            for order in orders_resp.json():
                status = order.get("status")
                if status in active_statuses:
                    order_id = order.get("orderId")
                    log_event(
                        "FLATTEN",
                        f"Canceling Schwab order ID: {order_id} ({status})"
                    )
                    c_resp = self.client.cancel_order(self.account_id, order_id)
                    log_event(
                        "FLATTEN",
                        f"Cancel response {order_id}: HTTP {c_resp.status_code}"
                    )
                    cancelled_any = True
            if cancelled_any:
                time.sleep(0.6)
            else:
                log_event("FLATTEN", "No working orders found to cancel.")
        else:
            log_event(
                "ERROR",
                f"Failed to query working orders: HTTP {orders_resp.status_code}"
            )

    def get_open_equity_positions(self):
        """Returns ONLY Equity positions for Auto-Flatten (Never Options)."""
        resp = self.client.get_account(
            self.account_id, fields=self.client.Account.Fields.POSITIONS
        )
        open_eq = []
        if resp.status_code == 200:
            sec_acc = resp.json().get("securitiesAccount", {})
            for pos in sec_acc.get("positions", []):
                inst = pos.get("instrument", {})
                if inst.get("assetType") == "EQUITY":
                    qty = (
                        pos.get("longQuantity", 0)
                        - pos.get("shortQuantity", 0)
                    )
                    if qty != 0:
                        open_eq.append((inst["symbol"], qty))
        else:
            log_event(
                "ERROR",
                f"get_open_equity_positions HTTP {resp.status_code}"
            )
        return open_eq

    def submit_liquidation_batch(self, open_positions):
        from schwab.orders.common import Session, Duration
        from schwab.orders.equities import (
            equity_sell_market,
            equity_buy_to_cover_market,
            equity_sell_limit,
            equity_buy_to_cover_limit
        )
        if not open_positions:
            return

        use_market = is_market_hours()
        quotes_data = {}

        if not use_market:
            symbols = [sym for sym, _ in open_positions]
            try:
                q_resp = self.client.get_quotes(symbols)
                if q_resp.status_code == 200:
                    quotes_data = q_resp.json()
            except Exception as e:
                log_event("ERROR", f"Quote lookup error during flatten: {e}")

        for symbol, qty in open_positions:
            if use_market:
                if qty > 0:
                    log_event(
                        "ORDER_OUT",
                        f"Submitting RTH DAY Market Sell: {int(qty)} {symbol}"
                    )
                    spec = equity_sell_market(symbol, int(qty)).build()
                    r = self.client.place_order(self.account_id, spec)
                    log_event(
                        "ORDER_RESP", f"Market Sell {symbol} -> HTTP {r.status_code}"
                    )
                elif qty < 0:
                    abs_q = int(abs(qty))
                    log_event(
                        "ORDER_OUT",
                        f"Submitting RTH DAY Buy-to-Cover: {abs_q} {symbol}"
                    )
                    spec = equity_buy_to_cover_market(symbol, abs_q).build()
                    r = self.client.place_order(self.account_id, spec)
                    log_event(
                        "ORDER_RESP",
                        f"Buy-to-Cover {symbol} -> HTTP {r.status_code}"
                    )
            else:
                q_info = quotes_data.get(symbol, {}).get("quote", {})
                if qty > 0:
                    bid = (
                        q_info.get("bidPrice")
                        or q_info.get("lastPrice")
                        or q_info.get("mark")
                    )
                    if not bid or bid <= 0:
                        log_event("ERROR", f"No valid bid found for {symbol}!")
                        continue
                    lim_price = calc_ext_limit_price(float(bid), is_sell=True)
                    lim_price_str = format_limit_price_str(lim_price)
                    log_event(
                        "ORDER_OUT",
                        f"Submitting EXT GTC_EXT Limit Sell: {int(qty)} {symbol} "
                        f"@ ${lim_price_str} (Live Bid: ${bid})"
                    )
                    spec = (
                        equity_sell_limit(symbol, int(qty), lim_price_str)
                        .set_session(Session.SEAMLESS)
                        .set_duration(Duration.GOOD_TILL_CANCEL)
                        .build()
                    )
                    r = self.client.place_order(self.account_id, spec)
                    log_event(
                        "ORDER_RESP",
                        f"GTC_EXT Limit Sell {symbol} -> HTTP {r.status_code}"
                    )
                elif qty < 0:
                    abs_q = int(abs(qty))
                    ask = (
                        q_info.get("askPrice")
                        or q_info.get("lastPrice")
                        or q_info.get("mark")
                    )
                    if not ask or ask <= 0:
                        log_event("ERROR", f"No valid ask found for {symbol}!")
                        continue
                    lim_price = calc_ext_limit_price(float(ask), is_sell=False)
                    lim_price_str = format_limit_price_str(lim_price)
                    log_event(
                        "ORDER_OUT",
                        f"Submitting EXT GTC_EXT Limit Cover: {abs_q} {symbol} "
                        f"@ ${lim_price_str} (Live Ask: ${ask})"
                    )
                    spec = (
                        equity_buy_to_cover_limit(symbol, abs_q, lim_price_str)
                        .set_session(Session.SEAMLESS)
                        .set_duration(Duration.GOOD_TILL_CANCEL)
                        .build()
                    )
                    r = self.client.place_order(self.account_id, spec)
                    log_event(
                        "ORDER_RESP",
                        f"GTC_EXT Limit Cover {symbol} -> HTTP {r.status_code}"
                    )

    def fetch_account_data(self):
        """Returns (adj_eq, is_flat, open_pnl, pos_details, has_options)
        tracking BOTH Equities (1x) and Options (100x)."""
        try:
            resp = self.client.get_account(
                self.account_id, fields=self.client.Account.Fields.POSITIONS
            )
            if resp.status_code == 200:
                self.last_error = ""
                data = resp.json().get("securitiesAccount", {})
                balances = data.get("currentBalances", {})
                raw_eq = float(balances.get("liquidationValue", 0))

                positions = data.get("positions", [])
                open_assets = []
                has_options = False
                for pos in positions:
                    a_type = pos.get("instrument", {}).get("assetType")
                    if a_type in ("EQUITY", "OPTION"):
                        net_q = (
                            pos.get("longQuantity", 0)
                            - pos.get("shortQuantity", 0)
                        )
                        if net_q != 0:
                            if a_type == "OPTION":
                                has_options = True
                            open_assets.append((pos, net_q, a_type))

                if not open_assets:
                    return raw_eq, True, 0.0, {}, False

                symbols = [
                    p[0]["instrument"]["symbol"] for p in open_assets
                ]
                adj_eq = raw_eq
                total_open_pnl = 0.0
                pos_details = {}

                try:
                    q_resp = self.client.get_quotes(symbols)
                    q_data = (
                        q_resp.json() if q_resp.status_code == 200 else {}
                    )
                except Exception as qe:
                    log_event("ERROR", f"Live quote fetch error: {qe}")
                    q_data = {}

                for pos, net_q, a_type in open_assets:
                    sym = pos["instrument"]["symbol"]
                    mult = 100.0 if a_type == "OPTION" else 1.0
                    acct_mkt_val = float(pos.get("marketValue", 0.0))
                    avg_price = float(
                        pos.get("averageLongPrice")
                        or pos.get("averageShortPrice")
                        or pos.get("averagePrice")
                        or 0.0
                    )

                    quote_info = q_data.get(sym, {}).get("quote", {})
                    if a_type == "OPTION":
                        live_price = (
                            quote_info.get("mark")
                            or quote_info.get("lastPrice")
                            or quote_info.get("bidPrice")
                        )
                    else:
                        live_price = sanitize_equity_live_price(
                            raw_last=quote_info.get("lastPrice"),
                            bid=quote_info.get("bidPrice"),
                            ask=quote_info.get("askPrice"),
                            mark=quote_info.get("mark"),
                            net_qty=net_q
                        )

                    if live_price is not None and float(live_price) > 0:
                        lp = float(live_price)
                        live_mkt_val = net_q * lp * mult
                        adj_eq += (live_mkt_val - acct_mkt_val)
                    else:
                        lp = (
                            abs(acct_mkt_val / (net_q * mult))
                            if net_q != 0 else avg_price
                        )

                    pos_open_pnl = (
                        (lp - avg_price) * net_q * mult
                        if avg_price > 0 else 0.0
                    )
                    total_open_pnl += pos_open_pnl
                    tag = f"{sym} (OPT)" if a_type == "OPTION" else sym
                    pos_details[tag] = {
                        "qty": int(net_q),
                        "avg": round(avg_price, 4),
                        "last": round(lp, 4),
                        "open_pnl": round(pos_open_pnl, 2),
                        "asset_type": a_type
                    }

                return (
                    adj_eq,
                    False,
                    round(total_open_pnl, 2),
                    pos_details,
                    has_options
                )
            else:
                self.last_error = f"HTTP {resp.status_code}"
                log_event(
                    "ERROR", f"Schwab get_account returned HTTP {resp.status_code}"
                )
        except Exception as e:
            self.last_error = str(e)
            log_event("ERROR", f"Schwab account fetch exception: {e}")
        return None, True, 0.0, {}, False


class WebullAdapter:
    name = "WEBULL"

    def __init__(self, app_key, app_secret):
        self.app_key = app_key.strip()
        self.app_secret = app_secret.strip()
        self.api_client = None
        self.trade_client = None
        self.data_client = None
        self.account_id = None
        self.accounts = []
        self._logged_accounts = set()
        self.last_error = ""

    def authenticate(self):
        logging.getLogger("webull").setLevel(logging.ERROR)
        from webull.core.client import ApiClient
        from webull.trade.trade_client import TradeClient
        self.api_client = ApiClient(self.app_key, self.app_secret, "us")
        self.api_client.add_endpoint("us", "api.webull.com")
        self.trade_client = TradeClient(self.api_client)
        try:
            from webull.data.data_client import DataClient
            self.data_client = DataClient(self.api_client)
        except Exception:
            self.data_client = None

        res = self._call_get_account_list()
        if res.status_code == 200:
            payload = res.json()
            raw_list = (
                payload if isinstance(payload, list)
                else payload.get("data", payload.get("accounts", []))
            )
            self.accounts = []
            for item in raw_list:
                aid = str(
                    item.get("account_id")
                    or item.get("sec_account_id")
                    or item.get("id")
                    or ""
                )
                atype = (
                    item.get("account_type")
                    or item.get("account_class")
                    or item.get("type")
                    or "TRADING"
                )
                anum = str(item.get("account_number") or aid)
                masked = f"...{anum[-4:]}" if len(anum) >= 4 else anum
                if aid:
                    self.accounts.append({
                        "id": aid,
                        "label": f"Webull {atype} ({masked})"
                    })
            if self.accounts and not self.account_id:
                self.account_id = self.accounts[0]["id"]
            return True
        raise RuntimeError(
            f"Webull authentication failed (HTTP {res.status_code}): {res.text}"
        )

    def _call_get_account_list(self):
        if hasattr(self.trade_client, "account_v2"):
            return self.trade_client.account_v2.get_account_list()
        return self.trade_client.get_account_list()

    def _call_get_balance(self):
        if hasattr(self.trade_client, "account_v2"):
            return self.trade_client.account_v2.get_account_balance(
                self.account_id
            )
        return self.trade_client.get_account_balance(self.account_id)

    def _call_get_positions(self):
        if hasattr(self.trade_client, "account_v2"):
            return self.trade_client.account_v2.get_account_position(
                self.account_id
            )
        return self.trade_client.get_account_position(self.account_id)

    def cancel_all_working_orders(self):
        try:
            res = None
            if hasattr(self.trade_client, "order_v3") and hasattr(
                self.trade_client.order_v3, "get_order_open"
            ):
                res = self.trade_client.order_v3.get_order_open(
                    account_id=self.account_id
                )
            elif hasattr(self.trade_client, "order_v2") and hasattr(
                self.trade_client.order_v2, "get_order_open"
            ):
                res = self.trade_client.order_v2.get_order_open(
                    account_id=self.account_id
                )
            elif hasattr(self.trade_client, "get_open_orders"):
                res = self.trade_client.get_open_orders(self.account_id)

            if res is not None and res.status_code == 200:
                payload = res.json()
                orders = (
                    payload if isinstance(payload, list)
                    else payload.get("data", payload.get("orders", []))
                )
                cancelled_any = False
                for o in orders:
                    cid = (
                        o.get("client_order_id")
                        or o.get("order_id")
                    )
                    if cid:
                        log_event(
                            "FLATTEN", f"Canceling Webull order ID: {cid}"
                        )
                        if hasattr(self.trade_client, "order_v3"):
                            c_res = self.trade_client.order_v3.cancel_order(
                                self.account_id, cid
                            )
                        else:
                            c_res = self.trade_client.cancel_order(
                                self.account_id, cid
                            )
                        log_event(
                            "FLATTEN",
                            f"Cancel response {cid}: HTTP {c_resp_code(c_res)}"
                        )
                        cancelled_any = True
                if cancelled_any:
                    time.sleep(0.6)
                else:
                    log_event("FLATTEN", "No working Webull orders to cancel.")
        except Exception as e:
            log_event("ERROR", f"Webull cancel working orders exception: {e}")

    def get_open_equity_positions(self):
        """Returns (symbol, qty, last_price) for EQUITIES ONLY."""
        res = self._call_get_positions()
        open_eq = []
        if res.status_code == 200:
            payload = res.json()
            pos_list = (
                payload if isinstance(payload, list)
                else payload.get("data", payload.get("positions", []))
            )
            for p in pos_list:
                itype = str(
                    p.get("instrument_type")
                    or p.get("asset_type")
                    or "EQUITY"
                ).upper()
                if "OPT" in itype:
                    continue
                qty = float(p.get("quantity") or p.get("position") or 0)
                if qty != 0:
                    sym = (
                        p.get("symbol")
                        or p.get("ticker", {}).get("symbol")
                        or ""
                    )
                    lp = float(
                        p.get("last_price")
                        or p.get("market_price")
                        or p.get("cost_price")
                        or 0.0
                    )
                    if sym:
                        open_eq.append((sym, qty, lp))
        return open_eq

    def submit_liquidation_batch(self, open_positions):
        if not open_positions:
            return
        use_market = is_market_hours()
        for item in open_positions:
            symbol = item[0]
            qty = item[1]
            ref_lp = item[2] if len(item) > 2 else 0.0
            side = "SELL" if qty > 0 else "BUY"
            abs_q = int(abs(qty))
            client_oid = uuid.uuid4().hex[:24]

            if use_market:
                log_event(
                    "ORDER_OUT",
                    f"Submitting Webull RTH Market {side}: {abs_q} {symbol}"
                )
                order_item = {
                    "client_order_id": client_oid,
                    "symbol": symbol,
                    "instrument_type": "EQUITY",
                    "market": "US",
                    "order_type": "MARKET",
                    "side": side,
                    "quantity": str(abs_q),
                    "time_in_force": "DAY",
                    "support_trading_session": "CORE",
                    "entrust_type": "QTY"
                }
            else:
                if ref_lp <= 0:
                    log_event(
                        "ERROR",
                        f"No valid reference price found for {symbol} on Webull!"
                    )
                    continue
                lim_price = calc_ext_limit_price(
                    float(ref_lp), is_sell=(qty > 0)
                )
                lim_price_str = format_limit_price_str(lim_price)
                log_event(
                    "ORDER_OUT",
                    f"Submitting Webull EXT Limit {side}: {abs_q} {symbol} "
                    f"@ ${lim_price_str} (Ref Last: ${ref_lp})"
                )
                order_item = {
                    "client_order_id": client_oid,
                    "symbol": symbol,
                    "instrument_type": "EQUITY",
                    "market": "US",
                    "order_type": "LIMIT",
                    "limit_price": lim_price_str,
                    "side": side,
                    "quantity": str(abs_q),
                    "time_in_force": "DAY",
                    "support_trading_session": "ALL",
                    "extended_hours_trading": True,
                    "entrust_type": "QTY"
                }

            try:
                if hasattr(self.trade_client, "order_v3"):
                    r = self.trade_client.order_v3.place_order(
                        self.account_id, [order_item]
                    )
                else:
                    r = self.trade_client.place_order(
                        self.account_id, order_item
                    )
                log_event(
                    "ORDER_RESP",
                    f"Webull {side} {symbol} -> HTTP {r.status_code}"
                )
            except Exception as e:
                log_event("ERROR", f"Webull place_order exception: {e}")

    @staticmethod
    def _extract_webull_equity_and_cash(b_data):
        """Extracts Total Account Value (Net Liquidation) and Cash Balance
        from Webull's balance payload without ever mistaking Market Value
        of positions for Total Account Value."""
        def to_f(val):
            try:
                return float(val) if val is not None and val != "" else None
            except Exception:
                return None

        # 1. Check direct top-level net liquidation fields
        for k in (
            "total_net_liquidation_value",
            "net_liquidation_value",
            "total_net_liquidation",
            "net_liquidation",
            "total_asset",
            "total_value",
            "account_value"
        ):
            v = to_f(b_data.get(k))
            if v is not None and v > 0:
                cash = to_f(
                    b_data.get("total_cash_balance")
                    or b_data.get("cash_balance")
                    or b_data.get("total_cash")
                )
                return v, cash

        # 2. Check inside account_currency_assets (USD)
        assets = b_data.get("account_currency_assets")
        if isinstance(assets, list) and assets:
            for item in assets:
                for k in (
                    "net_liquidation_value",
                    "total_net_liquidation_value",
                    "net_liquidation",
                    "total_asset"
                ):
                    v = to_f(item.get(k))
                    if v is not None and v > 0:
                        cash = to_f(
                            item.get("cash_balance")
                            or item.get("total_cash_balance")
                            or item.get("total_cash")
                        )
                        return v, cash

        # 3. Fallback: Sum Cash Balance + Market Value
        cash = to_f(
            b_data.get("total_cash_balance")
            or b_data.get("cash_balance")
            or b_data.get("total_cash")
        )
        mkt = to_f(
            b_data.get("total_market_value")
            or b_data.get("market_value")
        ) or 0.0
        if cash is not None:
            return cash + mkt, cash

        if isinstance(assets, list) and assets:
            for item in assets:
                c_sub = to_f(
                    item.get("cash_balance")
                    or item.get("total_cash_balance")
                    or item.get("settled_cash")
                )
                m_sub = to_f(
                    item.get("market_value")
                    or item.get("total_market_value")
                ) or 0.0
                if c_sub is not None:
                    return c_sub + m_sub, c_sub

        return 0.0, None

    def fetch_account_data(self):
        """Returns (adj_eq, is_flat, open_pnl, pos_details, has_options)
        for Webull accounts."""
        try:
            b_res = self._call_get_balance()
            if b_res.status_code != 200:
                self.last_error = (
                    f"HTTP {b_res.status_code}: {getattr(b_res, 'text', '')[:80]}"
                )
                log_event(
                    "ERROR",
                    f"Webull get_account_balance HTTP {b_res.status_code}"
                )
                return None, True, 0.0, {}, False

            b_json = b_res.json()
            b_data = (
                b_json.get("data", b_json)
                if isinstance(b_json, dict) else {}
            )

            raw_eq, cash_bal = self._extract_webull_equity_and_cash(b_data)
            if self.account_id not in self._logged_accounts:
                self._logged_accounts.add(self.account_id)
                log_event(
                    "SESSION",
                    f"Webull Balance Parsed -> TotalAccountValue=${raw_eq:,.2f} "
                    f"(Cash=${cash_bal if cash_bal is not None else 0.0:,.2f})"
                )

            p_res = self._call_get_positions()
            if p_res.status_code != 200:
                self.last_error = (
                    f"HTTP {p_res.status_code}: {getattr(p_res, 'text', '')[:80]}"
                )
                log_event(
                    "ERROR",
                    f"Webull get_account_position HTTP {p_res.status_code}"
                )
                return None, True, 0.0, {}, False

            p_json = p_res.json()
            pos_list = (
                p_json if isinstance(p_json, list)
                else p_json.get("data", p_json.get("positions", []))
            )

            total_open_pnl = 0.0
            total_pos_mkt_val = 0.0
            pos_details = {}
            has_options = False

            for p in pos_list:
                qty = float(p.get("quantity") or p.get("position") or 0)
                if qty == 0:
                    continue
                itype = str(
                    p.get("instrument_type")
                    or p.get("asset_type")
                    or "EQUITY"
                ).upper()
                is_opt = "OPT" in itype
                if is_opt:
                    has_options = True
                mult = 100.0 if is_opt else 1.0

                sym = (
                    p.get("symbol")
                    or p.get("ticker", {}).get("symbol")
                    or "UNKNOWN"
                )
                avg_price = float(
                    p.get("cost_price")
                    or p.get("avg_price")
                    or p.get("average_price")
                    or 0.0
                )
                raw_lp = float(
                    p.get("last_price")
                    or p.get("market_price")
                    or avg_price
                )
                if not is_opt:
                    san_lp = sanitize_equity_live_price(
                        raw_last=raw_lp,
                        bid=p.get("bid_price") or p.get("bid"),
                        ask=p.get("ask_price") or p.get("ask"),
                        mark=p.get("market_price"),
                        net_qty=qty
                    )
                    lp = float(san_lp) if san_lp is not None else raw_lp
                else:
                    lp = raw_lp

                if abs(lp - raw_lp) > 0.0001:
                    pos_mkt_val = qty * lp * mult
                    pos_open_pnl = (
                        (lp - avg_price) * qty * mult
                        if avg_price > 0 else 0.0
                    )
                else:
                    pos_mkt_val = float(
                        p.get("market_value") or (qty * lp * mult)
                    )
                    if "unrealized_profit_loss" in p and p.get(
                        "unrealized_profit_loss"
                    ) is not None:
                        pos_open_pnl = float(p["unrealized_profit_loss"])
                    else:
                        pos_open_pnl = (
                            (lp - avg_price) * qty * mult
                            if avg_price > 0 else 0.0
                        )
                total_pos_mkt_val += pos_mkt_val

                total_open_pnl += pos_open_pnl
                tag = f"{sym} (OPT)" if is_opt else sym
                pos_details[tag] = {
                    "qty": int(qty),
                    "avg": round(avg_price, 4),
                    "last": round(lp, 4),
                    "open_pnl": round(pos_open_pnl, 2),
                    "asset_type": "OPTION" if is_opt else "EQUITY"
                }

            is_flat = (len(pos_details) == 0)

            if cash_bal is not None and cash_bal > 0:
                adj_eq = round(cash_bal + total_pos_mkt_val, 2)
            else:
                adj_eq = round(raw_eq, 2)

            self.last_error = ""
            return (
                adj_eq,
                is_flat,
                round(total_open_pnl, 2),
                pos_details,
                has_options
            )
        except Exception as e:
            self.last_error = str(e)
            log_event("ERROR", f"Webull account fetch exception: {e}")
            return None, True, 0.0, {}, False


def c_resp_code(res):
    return getattr(res, "status_code", "OK")


# ==========================================
# 5. FIRST-TIME WAIVER & BROKER SETUP WIZARD
# ==========================================
def show_liability_waiver():
    load_config()
    waiver_text = (
        "1. NO WARRANTY, LIMITATION OF LIABILITY & INDEMNIFICATION:\n"
        "   This software is an experimental beta tool provided strictly 'AS IS' without warranty of any kind.\n"
        "   In no event shall the authors or contributors be liable for any direct or indirect trading losses,\n"
        "   slippage, missed fills, API outages, rate limits, rejected orders, or unexpected software behavior.\n"
        "   By using this software, you agree to indemnify and hold harmless the authors from any claims or losses.\n\n"
        "2. NOT FINANCIAL ADVICE & NO GUARANTEE OF LOSS PREVENTION:\n"
        "   This tool is a self-directed mechanical utility, NOT a registered investment advisor, broker-dealer,\n"
        "   or fiduciary. It DOES NOT and CANNOT guarantee that losses will be capped at your configured limits.\n"
        "   Market gaps, illiquid spreads, halts, API latency, or order rejections can cause actual account losses\n"
        "   to significantly exceed your configured thresholds.\n\n"
        "3. NO BROKER AFFILIATION & API TERMS RISK:\n"
        "   This project is an independent third-party tool and is NOT affiliated with, endorsed by, or sponsored\n"
        "   by Charles Schwab, Thinkorswim, or Webull. Automated API polling and liquidation orders are subject\n"
        "   to your broker's terms of service and rate limits.\n\n"
        "4. EQUITIES vs. OPTIONS BEHAVIOR:\n"
        "   • Equities (Stocks) are tracked for HUD display, Alarms, AND automated Market/Limit flatten orders.\n"
        "   • Options contracts are tracked for HUD PnL display and Warning Sirens ONLY. Because option\n"
        "     bid-ask spreads can widen dramatically, this software will NEVER auto-flatten option contracts.\n"
        "     If a guardrail breaches while holding options, you must manually flatten your options.\n\n"
        "5. SAFE TESTING RECOMMENDATION:\n"
        "   Always test first in Observation Mode (all enforcement checkboxes unchecked) or with 1 share\n"
        "   to verify your API connection and PnL calculations before trading live size."
    )
    expected_sha = hashlib.sha256(waiver_text.encode("utf-8")).hexdigest()

    if (
        config.get("waiver_accepted", False)
        and config.get("waiver_accepted_version") == WAIVER_VERSION
        and config.get("waiver_sha256") == expected_sha
    ):
        acc_at = config.get("waiver_accepted_at", "Unknown")
        log_event(
            "WAIVER",
            f"Liability Waiver v{WAIVER_VERSION} verified "
            f"(Accepted at: {acc_at} | SHA256: {expected_sha[:12]}...)"
        )
        return True

    accepted = {"ok": False}
    w = tk.Tk()
    w.title(f"PnL Enforcer Beta — Legal Disclaimer & Assumption of Risk (v{WAIVER_VERSION})")
    w.config(bg="#141414", padx=28, pady=22)
    w.resizable(False, False)
    w.attributes("-topmost", True)

    tk.Label(
        w,
        text=f"⚠️ EXPERIMENTAL BETA SOFTWARE — ASSUMPTION OF RISK (v{WAIVER_VERSION})",
        font=("Arial", 12, "bold"),
        fg="#f5b041",
        bg="#141414",
        anchor="w"
    ).pack(fill="x", pady=(0, 12))

    msg_box = tk.Label(
        w,
        text=waiver_text,
        font=("Arial", 9),
        fg="#e0e0e0",
        bg="#1e1e1e",
        justify="left",
        anchor="w",
        padx=16,
        pady=14,
        bd=1,
        relief="solid"
    )
    msg_box.pack(fill="x", pady=(0, 14))

    var_agree = tk.BooleanVar(value=False)
    tk.Checkbutton(
        w,
        text=(
            "I have read this disclaimer and LICENSE.txt, understand that losses cannot be guaranteed, "
            "and assume 100% sole responsibility for my account."
        ),
        variable=var_agree,
        font=("Arial", 9, "bold"),
        fg="#58d68d",
        bg="#141414",
        selectcolor="#2a2a2a",
        activebackground="#141414",
        activeforeground="#58d68d"
    ).pack(anchor="w", pady=(0, 14))

    btn_row = tk.Frame(w, bg="#141414")
    btn_row.pack(fill="x")

    def on_accept():
        if not var_agree.get():
            messagebox.showwarning(
                "Confirmation Required",
                "Please check the box confirming you understand and assume all risk.",
                parent=w
            )
            return
        accepted_ts = datetime.now().isoformat(timespec="seconds")
        config["waiver_accepted"] = True
        config["waiver_accepted_version"] = WAIVER_VERSION
        config["waiver_accepted_at"] = accepted_ts
        config["waiver_sha256"] = expected_sha
        save_config(config)
        log_event(
            "WAIVER",
            f"User accepted Liability Waiver v{WAIVER_VERSION} "
            f"(Accepted at: {accepted_ts} | SHA256: {expected_sha[:12]}...)"
        )
        accepted["ok"] = True
        w.destroy()

    tk.Button(
        btn_row,
        text="Decline & Exit",
        font=("Arial", 10, "bold"),
        bg="#922b21",
        fg="white",
        padx=16,
        pady=6,
        command=w.destroy
    ).pack(side="left")

    tk.Button(
        btn_row,
        text="I Understand & Assume All Risk >>",
        font=("Arial", 10, "bold"),
        bg="#1e8449",
        fg="white",
        padx=20,
        pady=6,
        command=on_accept
    ).pack(side="right")

    w.mainloop()
    return accepted["ok"]


def show_broker_setup_wizard(broker_name, parent=None):
    """Step-by-step tailored guide & API Key setup dialog for Schwab or Webull."""
    load_config()
    saved_ok = {"status": False}

    wiz = tk.Tk() if parent is None else tk.Toplevel(parent)
    if parent is not None:
        wiz.grab_set()

    wiz.title(f"PnL Enforcer — {broker_name} API Setup Wizard")
    wiz.config(bg="#141414", padx=26, pady=20)
    wiz.resizable(False, False)
    wiz.attributes("-topmost", True)

    tk.Label(
        wiz,
        text=f"🔑 {broker_name} API CREDENTIAL SETUP",
        font=("Arial", 12, "bold"),
        fg="#5dade2",
        bg="#141414",
        anchor="w"
    ).pack(fill="x", pady=(0, 8))

    if broker_name == "SCHWAB":
        guide_txt = (
            "HOW TO GET YOUR SCHWAB API KEYS (One-Time Setup):\n"
            "1. Log in at https://developer.schwab.com and create a free Individual Developer account.\n"
            "2. Click 'Apps' -> 'Create App' and select 'Accounts and Trading Production'.\n"
            "3. Set the Callback URL to exactly:   https://127.0.0.1\n"
            "4. Once your App status is 'Ready for Use', paste your App Key & Secret below.\n"
            "5. When you click Save & Connect, your browser will open to log into Schwab.\n"
            "   After approving, copy the full https://127.0.0.1/?code=... URL from your browser\n"
            "   address bar — our popup window will auto-detect it from your clipboard!"
        )
        portal_url = "https://developer.schwab.com"
    else:
        guide_txt = (
            "HOW TO GET YOUR WEBULL OPENAPI KEYS (One-Time Setup):\n"
            "1. Go to https://developer.webull.com (or Webull Web -> Account Management -> OpenAPI).\n"
            "2. Apply for a Retail Trading API Key (often approved within minutes).\n"
            "3. Generate your App Key and App Secret in the Webull portal and paste them below.\n"
            "4. ⚠️ IMPORTANT MOBILE 2FA STEP: On your first connection attempt, check your\n"
            "   Webull Mobile App / SMS! Webull may push a notification asking you to enter\n"
            "   a texted 2FA verification code (unless 2FA is disabled in your OpenAPI portal)."
        )
        portal_url = "https://developer.webull.com"

    guide_lbl = tk.Label(
        wiz,
        text=guide_txt,
        font=("Arial", 10),
        fg="#dddddd",
        bg="#1e1e1e",
        justify="left",
        anchor="w",
        padx=16,
        pady=12,
        bd=1,
        relief="solid"
    )
    guide_lbl.pack(fill="x", pady=(0, 8))

    link_row = tk.Frame(wiz, bg="#141414")
    link_row.pack(fill="x", pady=(0, 12))
    tk.Button(
        link_row,
        text=f"🌐 Open {portal_url} in Browser",
        font=("Arial", 9, "bold"),
        bg="#1f538d",
        fg="white",
        padx=12,
        pady=4,
        command=lambda: webbrowser.open(portal_url)
    ).pack(side="left", padx=(0, 12))
    portal_link = tk.Label(
        link_row,
        text=f"{portal_url} (Click to launch)",
        font=("Arial", 9, "bold underline"),
        fg="#5dade2",
        bg="#141414",
        cursor="hand2"
    )
    portal_link.pack(side="left")
    portal_link.bind("<Button-1>", lambda _e: webbrowser.open(portal_url))

    b_cfg = config.get("brokers", {}).get(broker_name, {})
    var_key = tk.StringVar(value=b_cfg.get("app_key", ""))
    var_sec = tk.StringVar(value=b_cfg.get("app_secret", ""))

    form = tk.Frame(wiz, bg="#141414")
    form.pack(fill="x", pady=6)

    tk.Label(
        form,
        text=f"{broker_name} App Key:",
        font=("Arial", 10, "bold"),
        fg="white",
        bg="#141414",
        width=20,
        anchor="w"
    ).grid(row=0, column=0, pady=6, sticky="w")
    tk.Entry(
        form,
        textvariable=var_key,
        font=("Arial", 10, "bold"),
        width=48,
        bg="#2a2a2a",
        fg="white",
        insertbackground="white"
    ).grid(row=0, column=1, pady=6, padx=8)

    tk.Label(
        form,
        text=f"{broker_name} App Secret:",
        font=("Arial", 10, "bold"),
        fg="white",
        bg="#141414",
        width=20,
        anchor="w"
    ).grid(row=1, column=0, pady=6, sticky="w")
    tk.Entry(
        form,
        textvariable=var_sec,
        font=("Arial", 10, "bold"),
        width=48,
        bg="#2a2a2a",
        fg="white",
        insertbackground="white",
        show="*"
    ).grid(row=1, column=1, pady=6, padx=8)

    def save_keys(force_token_renew=False):
        k = var_key.get().strip()
        s = var_sec.get().strip()
        if not k or not s:
            messagebox.showwarning(
                "Missing Credentials",
                f"Please paste both your {broker_name} App Key and App Secret.",
                parent=wiz
            )
            return
        if force_token_renew and broker_name == "SCHWAB":
            if os.path.exists(SCHWAB_TOKEN_PATH):
                try:
                    os.remove(SCHWAB_TOKEN_PATH)
                    log_event("SESSION", "User requested manual 7-day Schwab token renewal.")
                except Exception:
                    pass
        config["brokers"][broker_name]["app_key"] = k
        config["brokers"][broker_name]["app_secret"] = s
        config["active_broker"] = broker_name
        save_config(config)
        saved_ok["status"] = True
        wiz.destroy()

    if broker_name == "SCHWAB":
        rem_h = get_schwab_token_remaining_hours()
        if rem_h is not None and rem_h > 0:
            tok_info = f"Current 7-Day Schwab Token Status: {rem_h / 24.0:.1f} days ({rem_h:.0f}h) remaining."
            tok_col = "#58d68d" if rem_h >= 24.0 else "#f5b041"
        elif os.path.exists(SCHWAB_TOKEN_PATH):
            tok_info = "Current 7-Day Schwab Token Status: Expired — will prompt browser login on connect."
            tok_col = "#eb7067"
        else:
            tok_info = "Current 7-Day Schwab Token Status: Not yet authenticated."
            tok_col = "#aaaaaa"
        tk.Label(
            wiz,
            text=tok_info,
            font=("Arial", 9, "bold"),
            fg=tok_col,
            bg="#141414",
            anchor="w"
        ).pack(fill="x", pady=(4, 2))

    btn_bar = tk.Frame(wiz, bg="#141414", pady=12)
    btn_bar.pack(fill="x")

    tk.Button(
        btn_bar,
        text="Cancel",
        font=("Arial", 10, "bold"),
        bg="#333333",
        fg="white",
        padx=14,
        pady=6,
        command=wiz.destroy
    ).pack(side="left")

    tk.Button(
        btn_bar,
        text=f"Save & Connect {broker_name} >>",
        font=("Arial", 10, "bold"),
        bg="#1e8449",
        fg="white",
        padx=20,
        pady=6,
        command=lambda: save_keys(force_token_renew=False)
    ).pack(side="right")

    if broker_name == "SCHWAB" and os.path.exists(SCHWAB_TOKEN_PATH):
        tk.Button(
            btn_bar,
            text="🔄 Renew 7-Day Token Now",
            font=("Arial", 10, "bold"),
            bg="#1f538d",
            fg="white",
            padx=14,
            pady=6,
            command=lambda: save_keys(force_token_renew=True)
        ).pack(side="right", padx=(0, 10))

    if parent is None:
        wiz.mainloop()
    else:
        parent.wait_window(wiz)
    return saved_ok["status"]


def connect_broker_adapter(broker_name, parent=None, force_wizard=False):
    """Ensures credentials exist for broker_name, authenticates, and
    returns an initialized SchwabAdapter or WebullAdapter."""
    load_config()
    b_cfg = config.get("brokers", {}).get(broker_name, {})
    if force_wizard or not b_cfg.get("app_key") or not b_cfg.get("app_secret"):
        ok = show_broker_setup_wizard(broker_name, parent=parent)
        if not ok:
            return None
        load_config()
        b_cfg = config["brokers"][broker_name]

    try:
        if broker_name == "SCHWAB":
            adapter = SchwabAdapter(b_cfg["app_key"], b_cfg["app_secret"])
        else:
            adapter = WebullAdapter(b_cfg["app_key"], b_cfg["app_secret"])

        adapter.authenticate()
        saved_acct = b_cfg.get("selected_account_id", "")
        valid_ids = [a["id"] for a in adapter.accounts]
        if saved_acct in valid_ids:
            adapter.account_id = saved_acct
        elif valid_ids:
            adapter.account_id = valid_ids[0]
            config["brokers"][broker_name]["selected_account_id"] = valid_ids[0]
            save_config(config)

        log_event(
            "SESSION",
            f"{broker_name} API authenticated ({len(adapter.accounts)} account(s) found)."
        )
        return adapter
    except Exception as e:
        log_event("ERROR", f"{broker_name} connection error: {e}")
        extra_hint = (
            "\n\n⚠️ NOTE FOR WEBULL USERS:\n"
            "1. Check your Webull mobile app / SMS! Webull may send a 2FA code prompt "
            "the first time your API keys are used.\n"
            "2. Once you approve the 2FA code (or disable API 2FA in Webull portal), "
            "click 'No' to open Pre-Flight settings or 'Yes' to re-enter keys."
            if broker_name == "WEBULL" else ""
        )
        retry = messagebox.askyesno(
            f"{broker_name} Connection Error",
            f"Could not authenticate with {broker_name}:\n\n{e}{extra_hint}\n\n"
            f"Would you like to re-enter your {broker_name} API keys?",
            parent=parent
        )
        if retry:
            return connect_broker_adapter(
                broker_name, parent=parent, force_wizard=True
            )
        return None


# ==========================================
# 6. ALARM, COOL-DOWN & FLATTEN ORCHESTRATION
# ==========================================
def get_idle_button_text():
    b_name = config.get("active_broker", "SCHWAB")
    active_modes = [b_name]
    if config.get("enable_open_flatten", False):
        oml = config.get("open_max_loss", 500.0)
        if config.get("enable_open_cooldown", False):
            cd_m = config.get("open_cooldown_mins", 1.0)
            active_modes.append(f"OPEN STOP (-${oml:,.0f} + {cd_m:g}m LOCK)")
        else:
            active_modes.append(f"OPEN STOP (-${oml:,.0f})")
    if config.get("enable_auto_flatten", False):
        active_modes.append("DAY FLATTEN")
    if config.get("enable_kill_tos", False):
        active_modes.append("KILL TOS")
    if config.get("enable_kill_webull", False):
        active_modes.append("KILL WEBULL")
    if config.get("enable_lock_os", False):
        dl_m = config.get("daily_lock_mins", 15.0)
        active_modes.append(
            f"LOCK OS ({dl_m:g}m)" if dl_m > 0 else "LOCK OS (1x)"
        )

    if len(active_modes) == 1:
        return f"[{b_name}] MODE: ALARM ONLY (OBSERVATION)"
    return "ARMED: " + " + ".join(active_modes)


def sound_alarm_loop():
    global alarm_active
    while alarm_active and not cooldown_active:
        for _ in range(10):
            if not alarm_active or cooldown_active:
                break
            winsound.Beep(2600, 220)
            time.sleep(0.04)
        time.sleep(0.25)


def trigger_alarm(reason, ui_button, context_str=""):
    global alarm_active, triggered_alarms
    if reason in triggered_alarms:
        return

    triggered_alarms[reason] = time.time()
    extra = f" | {context_str}" if context_str else ""

    if cooldown_active:
        log_event(
            "ALARM",
            f"Suppressed siren during OS Cool-Down Lock: {reason}{extra}"
        )
        return

    log_event("ALARM", f"Triggered: {reason}{extra}")
    alarm_active = True
    btn_txt = f"ACKNOWLEDGE ALARM ({reason})"
    ui_button.after(
        0,
        lambda: ui_button.config(
            text=btn_txt, bg="yellow", fg="black", state="normal"
        )
    )
    threading.Thread(target=sound_alarm_loop, daemon=True).start()


def check_alarm_rearm(reason, current_val, threshold_val):
    if reason in triggered_alarms:
        elapsed = time.time() - triggered_alarms[reason]
        if (
            current_val >= (threshold_val + RECOVERY_BUFFER_DOLLARS)
            and elapsed >= ALARM_COOLDOWN_SEC
        ):
            del triggered_alarms[reason]
            log_event(
                "REARM",
                f"Alarm re-armed after recovery & cooldown: {reason}"
            )


def mute_alarm(ui_button):
    global alarm_active
    alarm_active = False
    log_event("ALARM", "User acknowledged and muted siren.")
    if not cooldown_active:
        ui_button.config(
            text=get_idle_button_text(),
            bg="#333333",
            fg="white",
            state="disabled"
        )


def play_unlock_chimes():
    """Plays 3 pleasant ascending musical chimes (C5 -> E5 -> G5)
    when the OS Cool-Down Lock timer expires."""
    try:
        for freq, dur in ((523, 180), (659, 180), (784, 320)):
            winsound.Beep(freq, dur)
            time.sleep(0.06)
    except Exception:
        pass


def speak_async(text, force=False):
    """Speaks text asynchronously using Windows built-in SAPI speech synthesizer."""
    if not force and not config.get("enable_voice_cues", True):
        return
    try:
        safe_text = str(text).replace("'", "")
        ps_cmd = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Speak('{safe_text}')"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def play_upside_tier_chime():
    """Plays a crisp 4-note ascending D-major arpeggio (D5 -> F#5 -> A5 -> D6)
    when a higher profit tier is unlocked while 100% flat."""
    def _chime_worker():
        try:
            for freq, dur in ((587, 110), (740, 110), (880, 110), (1175, 240)):
                winsound.Beep(freq, dur)
                time.sleep(0.03)
        except Exception:
            pass

    threading.Thread(target=_chime_worker, daemon=True).start()


def compute_upside_tier(rth_now, max_realized_profit, cfg):
    """Returns the current upside profit tier (1=Base, 2/3/4=Unlocked Tiers)."""
    if not rth_now:
        if cfg.get("enable_pm_lock", True) and max_realized_profit >= cfg["pm_lock_trigger"]:
            return 2
        return 1
    if cfg.get("enable_t4", True) and max_realized_profit >= cfg["t4_trigger"]:
        return 4
    if cfg.get("enable_t3", True) and max_realized_profit >= cfg["t3_trigger"]:
        return 3
    if cfg.get("enable_t2", True) and max_realized_profit >= cfg["t2_trigger"]:
        return 2
    return 1


def trigger_upside_tier_glow(ui_button, banner_text, log_msg):
    """Logs the tier ratchet and, if enabled, plays the upside chime and pulses
    the bottom HUD status bar with a 3-second emerald glow."""
    log_event("RATCHET", log_msg)
    if not config.get("enable_upside_chime", True):
        return
    if alarm_active or cooldown_active or ui_button is None:
        return

    play_upside_tier_chime()

    # 6 steps x 500ms = 3.0 seconds total
    glow_steps = [
        ("#00e676", "#000000"),
        ("#2ecc71", "#000000"),
        ("#27ae60", "#ffffff"),
        ("#1e8449", "#ffffff"),
        ("#196f3d", "#ffffff"),
        ("#145a32", "#ffffff"),
    ]

    def _step(idx=0):
        if alarm_active or cooldown_active:
            return
        if idx < len(glow_steps):
            bg_c, fg_c = glow_steps[idx]
            ui_button.config(
                text=banner_text, bg=bg_c, fg=fg_c, state="disabled"
            )
            ui_button.after(500, lambda: _step(idx + 1))
        else:
            if not alarm_active and not cooldown_active:
                ui_button.config(
                    text=get_idle_button_text(),
                    bg="#333333",
                    fg="white",
                    state="disabled"
                )

    ui_button.after(0, lambda: _step(0))


def _format_lock_voice_msg(duration_mins, label_prefix, upgraded=False):
    mins_val = float(duration_mins)
    dur_words = "1 minute" if mins_val == 1.0 else f"{mins_val:g} minutes"
    is_daily = "DAILY" in str(label_prefix).upper()
    if upgraded:
        reason_words = "Upgraded to daily floor breach" if is_daily else "Lockout extended"
    else:
        reason_words = "Daily floor breached" if is_daily else "Open P and L stop triggered"
    return f"{reason_words}. Locked out for {dur_words}."


def start_cooldown_lock(duration_mins, ui_button, label_prefix="COOL-DOWN LOCK"):
    global cooldown_active, cooldown_end_time, cooldown_label, cooldown_30s_announced, alarm_active
    duration_sec = max(5, int(round(float(duration_mins) * 60)))
    new_end_time = time.time() + duration_sec

    if cooldown_active:
        if new_end_time > cooldown_end_time:
            cooldown_end_time = new_end_time
            cooldown_label = label_prefix
            cooldown_30s_announced = (duration_sec <= 35)
            log_event(
                "COOLDOWN",
                f"Upgraded active lock to {label_prefix} for {duration_sec}s "
                f"({duration_mins:g} min). Siren muted."
            )
            speak_async(_format_lock_voice_msg(duration_mins, label_prefix, upgraded=True))
        return

    cooldown_active = True
    cooldown_end_time = new_end_time
    cooldown_label = label_prefix
    cooldown_30s_announced = (duration_sec <= 35)
    alarm_active = False

    def cooldown_worker():
        global cooldown_active, cooldown_end_time, cooldown_label, cooldown_30s_announced, alarm_active
        log_event(
            "COOLDOWN",
            f"Persistent {cooldown_label} started for {duration_sec}s "
            f"({duration_mins:g} min). Siren muted."
        )
        speak_async(_format_lock_voice_msg(duration_mins, cooldown_label, upgraded=False))
        while time.time() < cooldown_end_time:
            alarm_active = False
            rem = int(round(cooldown_end_time - time.time()))
            if not cooldown_30s_announced and 0 < rem <= 30:
                cooldown_30s_announced = True
                speak_async("30 seconds remaining until unlock.")
            txt = (
                f"{cooldown_label} ACTIVE: {rem}s REMAINING "
                f"(DO NOT REVENGE TRADE)"
            )
            ui_button.after(
                0,
                lambda t=txt: ui_button.config(
                    text=t, bg="#922b21", fg="white", state="disabled"
                )
            )
            ctypes.windll.user32.LockWorkStation()
            time.sleep(1.5)

        cooldown_active = False
        alarm_active = False
        log_event(
            "COOLDOWN",
            f"{cooldown_label} timer expired. Workstation unlocked."
        )
        ui_button.after(
            0,
            lambda: ui_button.config(
                text=get_idle_button_text(),
                bg="#333333",
                fg="white",
                state="disabled"
            )
        )
        play_unlock_chimes()

    threading.Thread(target=cooldown_worker, daemon=True).start()


def flatten_equities(adapter, force_flatten=False):
    """Cancels working orders, submits RTH Market or EXT Limit liquidations
    for EQUITIES ONLY, and verifies 0 equity shares remain."""
    should_exec = force_flatten or config.get("enable_auto_flatten", False)
    try:
        if should_exec:
            log_event("FLATTEN", "Starting emergency equity flatten sequence...")
            adapter.cancel_all_working_orders()

            open_pos = adapter.get_open_equity_positions()
            if not open_pos:
                log_event("FLATTEN", "No open equity shares to flatten.")
                return True

            log_event("FLATTEN", f"Equity positions to liquidate: {open_pos}")
            adapter.submit_liquidation_batch(open_pos)
        else:
            open_pos = adapter.get_open_equity_positions()
            if not open_pos:
                return True
            log_event(
                "WARNING",
                f"Auto-Flatten is OFF, but equity shares remain open: {open_pos}"
            )
            return False

        log_event("FLATTEN", "Polling broker API to verify 0 open equity shares...")
        start_wait = time.time()
        polls = 0
        while time.time() - start_wait < 15:
            time.sleep(2)
            polls += 1
            rem_pos = adapter.get_open_equity_positions()
            elapsed = time.time() - start_wait
            if not rem_pos:
                log_event(
                    "FLATTEN",
                    f"SUCCESS: Confirmed 0 equity shares in {elapsed:.1f}s."
                )
                return True

            log_event(
                "FLATTEN",
                f"Check #{polls} ({elapsed:.1f}s): Equities still open: {rem_pos}"
            )

            if should_exec and polls % 2 == 0:
                log_event(
                    "FLATTEN",
                    "Equities still open after 4s — canceling & sweeping..."
                )
                adapter.cancel_all_working_orders()
                rem_pos = adapter.get_open_equity_positions()
                if not rem_pos:
                    log_event(
                        "FLATTEN",
                        f"SUCCESS: Confirmed 0 equity shares after cancel "
                        f"({time.time() - start_wait:.1f}s)."
                    )
                    return True
                adapter.submit_liquidation_batch(rem_pos)

        log_event(
            "CRITICAL",
            "Equity flatten 15s timeout reached! Shares still open!"
        )
        return False

    except Exception as e:
        log_event("ERROR", f"Flatten execution exception: {e}")
        return False


def trigger_open_pnl_flatten(
    adapter, reason, ui_button, has_options=False, context_str=""
):
    global alarm_active
    cd_on = config.get("enable_open_cooldown", False)

    if has_options:
        opt_reason = f"{reason} — MANUAL OPTIONS EXIT REQUIRED!"
        trigger_alarm(opt_reason, ui_button, context_str)
        log_event(
            "GUARDRAIL",
            f"Open PnL Stop breached with OPTIONS open ({context_str}). "
            f"Flattening any equities; waiting for manual options exit."
        )
        flatten_equities(adapter, force_flatten=True)
        return

    if not cd_on:
        trigger_alarm(reason, ui_button, context_str)
    else:
        alarm_active = False

    log_event(
        "GUARDRAIL",
        f"OPEN PnL AUTO-FLATTEN INITIATED: {reason} | {context_str}"
    )
    eq_flat = flatten_equities(adapter, force_flatten=True)
    if eq_flat:
        log_event("GUARDRAIL", "Open PnL equity bailout confirmed 100% flat.")
        if cd_on:
            alarm_active = False
            cd_mins = config.get("open_cooldown_mins", 1.0)
            start_cooldown_lock(
                cd_mins, ui_button, label_prefix="PENALTY BOX LOCK"
            )
    else:
        log_event(
            "CRITICAL",
            "Open PnL flatten timed out — Cool-Down Lock ABORTED! "
            "Check platform manually!"
        )
        trigger_alarm(reason, ui_button, context_str)


def terminate_selected_apps():
    if config.get("enable_kill_tos", False):
        log_event(
            "LOCKDOWN",
            "Confirmed flat. Terminating Thinkorswim (thinkorswim.exe)..."
        )
        subprocess.run(
            ["taskkill", "/f", "/im", "thinkorswim.exe", "/t"],
            capture_output=True
        )
    if config.get("enable_kill_webull", False):
        log_event(
            "LOCKDOWN",
            "Confirmed flat. Terminating Webull Desktop..."
        )
        for exe_name in ("Webull Desktop.exe", "WebullDesktop.exe"):
            subprocess.run(
                ["taskkill", "/f", "/im", exe_name, "/t"],
                capture_output=True
            )


def trigger_lockdown(
    adapter, reason, ui_button, has_options=False, context_str=""
):
    global is_locked_down, alarm_active
    if is_locked_down:
        return

    flat_on = config.get("enable_auto_flatten", False)
    kill_tos = config.get("enable_kill_tos", False)
    kill_wb = config.get("enable_kill_webull", False)
    lock_on = config.get("enable_lock_os", False)

    if not flat_on and not kill_tos and not kill_wb and not lock_on:
        trigger_alarm(reason, ui_button, context_str)
        log_event(
            "GUARDRAIL",
            f"Daily floor breached ({reason}), but all enforcement toggles "
            f"are OFF (Observation Mode)."
        )
        return

    log_event(
        "LOCKDOWN",
        f"DAILY TERMINATION BREACHED: {reason} | {context_str}"
    )

    eq_flat = flatten_equities(adapter)

    if has_options:
        trigger_alarm(
            f"{reason} (CLOSE OPTIONS MANUALLY!)", ui_button, context_str
        )
        log_event(
            "CRITICAL",
            "OPTIONS ARE STILL OPEN! Holding off on App Kill / OS Lock "
            "until options are manually flattened!"
        )
        return

    if not eq_flat:
        log_event(
            "CRITICAL",
            "OS ACTIONS ABORTED: Equity shares still open! Manual action needed!"
        )
        trigger_alarm(reason, ui_button, context_str)
        return

    is_locked_down = True
    if not lock_on:
        trigger_alarm(reason, ui_button, context_str)

    terminate_selected_apps()

    if lock_on:
        alarm_active = False
        dl_mins = float(config.get("daily_lock_mins", 15.0))
        if dl_mins > 0:
            log_event(
                "LOCKDOWN",
                f"Confirmed flat. Starting persistent Daily OS Lock "
                f"for {dl_mins:g} mins..."
            )
            start_cooldown_lock(
                dl_mins, ui_button, label_prefix="DAILY BREACH OS LOCK"
            )
        else:
            log_event(
                "LOCKDOWN",
                "Confirmed flat. Muting siren and locking Windows once..."
            )
            ctypes.windll.user32.LockWorkStation()


# ==========================================
# 7. MAIN POLLING LOOP
# ==========================================
def log_position_transitions(
    pos_details, realized_pnl, open_pnl, net_pnl, session_high_pnl
):
    global prev_pos_snapshot, win_trades, loss_trades, prev_flat_realized_pnl
    curr_sig_map = {
        s: (d["qty"], round(float(d.get("avg", 0.0)), 4))
        for s, d in pos_details.items()
    }
    prev_sig_map = {
        s: (d["qty"], round(float(d.get("avg", 0.0)), 4))
        for s, d in prev_pos_snapshot.items()
    }

    if curr_sig_map == prev_sig_map:
        return

    all_syms = sorted(set(curr_sig_map.keys()) | set(prev_sig_map.keys()))
    changes = []
    completed_round_trip = False
    for sym in all_syms:
        old_q, old_avg = prev_sig_map.get(sym, (0, 0.0))
        new_q, new_avg = curr_sig_map.get(sym, (0, 0.0))
        if old_q != new_q:
            if new_q != 0:
                info = pos_details[sym]
                changes.append(
                    f"{sym}: {old_q:+d} -> {new_q:+d} "
                    f"(Avg: ${info['avg']:.4f}, Last: ${info['last']:.4f})"
                )
            else:
                changes.append(f"{sym}: {old_q:+d} -> 0 (CLOSED FLAT)")
                completed_round_trip = True
        elif new_q != 0 and abs(new_avg - old_avg) >= 0.0001:
            info = pos_details[sym]
            changes.append(
                f"{sym}: {old_q:+d} -> 0 -> {new_q:+d} "
                f"(Re-entry Avg: ${old_avg:.4f} -> ${info['avg']:.4f}, "
                f"Last: ${info['last']:.4f})"
            )
            completed_round_trip = True

    if not changes:
        return

    if completed_round_trip and (len(pos_details) == 0 or any("Re-entry Avg:" in c for c in changes)):
        delta = round(realized_pnl - prev_flat_realized_pnl, 2)
        if delta > 0.0:
            win_trades += 1
        elif delta < 0.0:
            loss_trades += 1
        prev_flat_realized_pnl = realized_pnl
        save_session_state()

    prev_pos_snapshot = pos_details.copy()
    change_str = ", ".join(changes)
    log_event(
        "POS_CHANGE",
        f"{change_str} | Realized: {format_dollar(realized_pnl)} | "
        f"Open: {format_dollar(open_pnl)} | "
        f"Net: {format_dollar(net_pnl)} | "
        f"High: {format_dollar(session_high_pnl)}"
    )


def data_loop(ui_labels, mute_btn, settings_btn, close_btn, root):
    global start_equity, max_equity, daily_max_equity, last_flat_equity
    global has_reset_at_open, is_locked_down, force_reanchor
    global triggered_alarms, prev_pos_snapshot, current_is_flat
    global active_adapter, first_poll_of_launch
    global current_upside_tier, last_rth_mode
    global win_trades, loss_trades, prev_flat_realized_pnl

    consecutive_api_failures = 0
    api_disconnect_alerted = False

    while True:
        poll_sec = max(1, int(config.get("poll_interval", 2)))
        try:
            if active_adapter is None or settings_win_open:
                time.sleep(0.5)
                continue

            current_eq, is_flat, live_open_pnl, pos_details, has_options = (
                active_adapter.fetch_account_data()
            )

            if current_eq is not None and current_eq > 0:
                if consecutive_api_failures > 0 or api_disconnect_alerted:
                    consecutive_api_failures = 0
                    if api_disconnect_alerted:
                        api_disconnect_alerted = False
                        log_event("SESSION", "Broker API connection restored.")
                        if not alarm_active and not cooldown_active:
                            mute_btn.after(
                                0,
                                lambda: mute_btn.config(
                                    text=get_idle_button_text(),
                                    bg="#333333",
                                    fg="white",
                                    state="disabled"
                                )
                            )
                current_is_flat = is_flat

                if (
                    start_equity is None
                    or start_equity <= 0.0
                    or force_reanchor
                ):
                    start_equity = current_eq
                    max_equity = current_eq
                    daily_max_equity = current_eq
                    last_flat_equity = current_eq
                    has_reset_at_open = is_rth()
                    force_reanchor = False
                    is_locked_down = False
                    win_trades = 0
                    loss_trades = 0
                    prev_flat_realized_pnl = 0.0
                    triggered_alarms.clear()
                    prev_pos_snapshot = {}
                    save_session_state()
                    log_event(
                        "SESSION",
                        f"Baseline anchored to: ${start_equity:,.2f} "
                        f"({active_adapter.name})"
                    )

                if daily_max_equity is None:
                    daily_max_equity = max(start_equity, max_equity)

                reset_925 = config.get("reset_at_925", True)
                if reset_925 and is_rth() and not has_reset_at_open:
                    old_hwm = max_equity - start_equity
                    max_equity = max(start_equity, last_flat_equity)
                    new_hwm = max_equity - start_equity
                    has_reset_at_open = True
                    is_locked_down = False
                    triggered_alarms.clear()
                    first_poll_of_launch = True
                    save_session_state()
                    log_event(
                        "SESSION",
                        f"9:25 AM RTH Transition: Rulebook HWM recalibrated "
                        f"from {format_dollar(old_hwm)} to "
                        f"{format_dollar(new_hwm)} (Session High preserved at "
                        f"{format_dollar(daily_max_equity - start_equity)})."
                    )

                if is_flat:
                    last_flat_equity = current_eq
                    if current_eq > max_equity:
                        max_equity = current_eq
                    if current_eq > daily_max_equity:
                        daily_max_equity = current_eq
                    save_session_state()
                    realized_pnl = round(last_flat_equity - start_equity, 2)
                    open_pnl = 0.0
                    for k in list(triggered_alarms.keys()):
                        if k.startswith("Open PnL -"):
                            del triggered_alarms[k]
                else:
                    open_pnl = live_open_pnl
                    realized_pnl = round(
                        (current_eq - start_equity) - open_pnl, 2
                    )

                net_pnl = round(current_eq - start_equity, 2)
                max_realized_profit = round(max_equity - start_equity, 2)
                session_high_pnl = round(
                    daily_max_equity - start_equity, 2
                )

                open_flat_on = config.get("enable_open_flatten", False)
                open_max = config.get("open_max_loss", 500.0)

                pm_w1 = config["pm_warn_1"]
                pm_w2 = config["pm_warn_2"]
                pm_max = config["pm_max_loss"]
                pm_trig = config["pm_lock_trigger"]
                pm_trail = config["pm_trail_cushion"]
                pm_w1_on = config.get("enable_pm_warn_1", True) and (pm_w1 > 0)
                pm_w2_on = config.get("enable_pm_warn_2", True) and (pm_w2 > 0)
                pm_lock_on = config.get("enable_pm_lock", True)

                t1_w1 = config["t1_warn_1"]
                t1_w2 = config["t1_warn_2"]
                t1_max = config["t1_max_loss"]
                t2_trig = config["t2_trigger"]
                t2_max = config["t2_max_loss"]
                t3_trig = config["t3_trigger"]
                t3_max = config["t3_max_loss"]
                t4_trig = config["t4_trigger"]
                t4_trail = config["t4_trail"]
                t1_w1_on = config.get("enable_t1_warn_1", True) and (t1_w1 > 0)
                t1_w2_on = config.get("enable_t1_warn_2", True) and (t1_w2 > 0)
                t2_on = config.get("enable_t2", True)
                t3_on = config.get("enable_t3", True)
                t4_on = config.get("enable_t4", True)

                rth_now = is_rth()

                # Anti-Wick Verification: if an open position's live quote
                # appears to breach either the Daily Floor or Open PnL Stop,
                # re-poll once after 1.2s before logging or firing enforcement
                # so transient single-order wicks cannot cause a false flatten.
                active_floor_now = (
                    (
                        max_equity - pm_trail
                        if (pm_lock_on and max_realized_profit >= pm_trig)
                        else start_equity - pm_max
                    )
                    if not rth_now
                    else (
                        max_equity - t4_trail
                        if (t4_on and max_realized_profit >= t4_trig)
                        else start_equity - t3_max
                        if (t3_on and max_realized_profit >= t3_trig)
                        else start_equity - t2_max
                        if (t2_on and max_realized_profit >= t2_trig)
                        else start_equity - t1_max
                    )
                )
                floor_breach_cand = (
                    not is_locked_down and current_eq <= active_floor_now
                )
                open_breach_cand = (
                    open_flat_on and not is_flat and open_pnl <= -open_max
                )
                if (
                    not first_poll_of_launch
                    and not is_flat
                    and (floor_breach_cand or open_breach_cand)
                ):
                    spike_ctx = (
                        f"Realized={format_dollar(realized_pnl)}, "
                        f"Open={format_dollar(open_pnl)}, "
                        f"Net={format_dollar(net_pnl)}"
                    )
                    time.sleep(1.2)
                    v_eq, v_flat, v_open, v_pos, v_opt = (
                        active_adapter.fetch_account_data()
                    )
                    if v_eq is not None and v_eq > 0:
                        current_eq = v_eq
                        is_flat = v_flat
                        current_is_flat = v_flat
                        live_open_pnl = v_open
                        pos_details = v_pos
                        has_options = v_opt
                        if is_flat:
                            last_flat_equity = current_eq
                            if current_eq > max_equity:
                                max_equity = current_eq
                            if current_eq > daily_max_equity:
                                daily_max_equity = current_eq
                            save_session_state()
                            realized_pnl = round(
                                last_flat_equity - start_equity, 2
                            )
                            open_pnl = 0.0
                        else:
                            open_pnl = live_open_pnl
                            realized_pnl = round(
                                (current_eq - start_equity) - open_pnl, 2
                            )
                        net_pnl = round(current_eq - start_equity, 2)
                        max_realized_profit = round(
                            max_equity - start_equity, 2
                        )
                        session_high_pnl = round(
                            daily_max_equity - start_equity, 2
                        )
                        v_ctx = (
                            f"Realized={format_dollar(realized_pnl)}, "
                            f"Open={format_dollar(open_pnl)}, "
                            f"Net={format_dollar(net_pnl)}"
                        )
                        still_floor = (
                            not is_locked_down
                            and current_eq <= active_floor_now
                        )
                        still_open = (
                            open_flat_on
                            and not is_flat
                            and open_pnl <= -open_max
                        )
                        if not still_floor and not still_open:
                            log_event(
                                "GUARDRAIL",
                                f"Filtered transient single-order wick "
                                f"(Spike: {spike_ctx} -> Re-verified 1.2s later: "
                                f"{v_ctx}). No flatten triggered."
                            )
                        else:
                            log_event(
                                "GUARDRAIL",
                                f"Breach confirmed after 1.2s anti-wick check "
                                f"(Initial: {spike_ctx} -> Verified: {v_ctx})."
                            )

                log_position_transitions(
                    pos_details,
                    realized_pnl,
                    open_pnl,
                    net_pnl,
                    session_high_pnl
                )

                # Prevent immediate siren blast or flat re-lock on startup,
                # at the 9:25 AM transition, or right after saving Settings
                if first_poll_of_launch or last_rth_mode != rth_now:
                    last_rth_mode = rth_now
                    current_upside_tier = compute_upside_tier(
                        rth_now, max_realized_profit, config
                    )

                if first_poll_of_launch and is_flat:
                    first_poll_of_launch = False
                    if pm_w1_on and net_pnl <= -pm_w1:
                        triggered_alarms[f"Pre-market -${pm_w1:,.0f} Warn 1"] = time.time()
                    if pm_w2_on and net_pnl <= -pm_w2:
                        triggered_alarms[f"Pre-market -${pm_w2:,.0f} Warn 2"] = time.time()
                    if (t2_on or t3_on) and current_eq <= start_equity:
                        triggered_alarms["Hit $0 (Tier 2)"] = time.time()
                        triggered_alarms["Hit $0 (Tier 3)"] = time.time()
                    if t1_w1_on and current_eq <= (start_equity - t1_w1):
                        triggered_alarms[f"Hit -${t1_w1:,.0f} (Tier 1)"] = time.time()
                    if t1_w2_on and current_eq <= (start_equity - t1_w2):
                        triggered_alarms[f"Hit -${t1_w2:,.0f} (Tier 1)"] = time.time()
                    active_floor = (
                        (max_equity - pm_trail if (pm_lock_on and max_realized_profit >= pm_trig) else start_equity - pm_max)
                        if not is_rth() else
                        (max_equity - t4_trail if (t4_on and max_realized_profit >= t4_trig) else
                         start_equity - t3_max if (t3_on and max_realized_profit >= t3_trig) else
                         start_equity - t2_max if (t2_on and max_realized_profit >= t2_trig) else
                         start_equity - t1_max)
                    )
                    if current_eq <= active_floor:
                        is_locked_down = True
                else:
                    first_poll_of_launch = False

                ctx = (
                    f"Realized={format_dollar(realized_pnl)}, "
                    f"Open={format_dollar(open_pnl)}, "
                    f"Net={format_dollar(net_pnl)}"
                )

                if not is_rth():
                    r_pm_max = f"Pre-market -${pm_max:,.0f} Breach"
                    r_pm_w2 = f"Pre-market -${pm_w2:,.0f} Warn 2"
                    r_pm_w1 = f"Pre-market -${pm_w1:,.0f} Warn 1"
                    r_pm_tr = "Pre-market Trailing Floor Breach"

                    check_alarm_rearm(r_pm_max, net_pnl, -pm_max)
                    if pm_w2_on:
                        check_alarm_rearm(r_pm_w2, net_pnl, -pm_w2)
                    if pm_w1_on:
                        check_alarm_rearm(r_pm_w1, net_pnl, -pm_w1)

                    if pm_lock_on and max_realized_profit >= pm_trig:
                        floor_equity = max_equity - pm_trail
                        check_alarm_rearm(
                            r_pm_tr, current_eq, floor_equity
                        )
                    else:
                        floor_equity = start_equity - pm_max

                    if (
                        not is_locked_down
                        and pm_lock_on
                        and max_realized_profit >= pm_trig
                        and current_eq <= floor_equity
                    ):
                        trigger_lockdown(
                            active_adapter, r_pm_tr, mute_btn, has_options, ctx
                        )
                    elif not is_locked_down and net_pnl <= -pm_max:
                        triggered_alarms.setdefault(r_pm_w1, time.time())
                        triggered_alarms.setdefault(r_pm_w2, time.time())
                        trigger_lockdown(
                            active_adapter, r_pm_max, mute_btn, has_options, ctx
                        )
                    elif (
                        open_flat_on
                        and not is_flat
                        and open_pnl <= -open_max
                    ):
                        if pm_w2_on and net_pnl <= -pm_w2:
                            triggered_alarms.setdefault(r_pm_w2, time.time())
                        if pm_w1_on and net_pnl <= -pm_w1:
                            triggered_alarms.setdefault(r_pm_w1, time.time())
                        r_open = f"Open PnL -${open_max:,.0f} Stop"
                        trigger_open_pnl_flatten(
                            active_adapter, r_open, mute_btn, has_options, ctx
                        )
                    elif pm_w2_on and net_pnl <= -pm_w2:
                        triggered_alarms.setdefault(r_pm_w1, time.time())
                        trigger_alarm(r_pm_w2, mute_btn, ctx)
                    elif pm_w1_on and net_pnl <= -pm_w1:
                        trigger_alarm(r_pm_w1, mute_btn, ctx)

                else:
                    if t4_on and max_realized_profit >= t4_trig:
                        floor_equity = max_equity - t4_trail
                        if not is_locked_down and current_eq <= floor_equity:
                            msg = f"Breached ${t4_trail:,.0f} Trailing Floor"
                            trigger_lockdown(
                                active_adapter, msg, mute_btn, has_options, ctx
                            )
                        elif (
                            open_flat_on
                            and not is_flat
                            and open_pnl <= -open_max
                        ):
                            r_open = f"Open PnL -${open_max:,.0f} Stop"
                            trigger_open_pnl_flatten(
                                active_adapter,
                                r_open,
                                mute_btn,
                                has_options,
                                ctx
                            )

                    elif t3_on and max_realized_profit >= t3_trig:
                        floor_equity = start_equity - t3_max
                        r_t3 = "Hit $0 (Tier 3)"
                        check_alarm_rearm(r_t3, current_eq, start_equity)
                        if not is_locked_down and current_eq <= floor_equity:
                            msg = f"Breached Tier 3 Floor (-${t3_max:,.0f})"
                            trigger_lockdown(
                                active_adapter, msg, mute_btn, has_options, ctx
                            )
                        elif (
                            open_flat_on
                            and not is_flat
                            and open_pnl <= -open_max
                        ):
                            if current_eq <= start_equity:
                                triggered_alarms.setdefault(r_t3, time.time())
                            r_open = f"Open PnL -${open_max:,.0f} Stop"
                            trigger_open_pnl_flatten(
                                active_adapter,
                                r_open,
                                mute_btn,
                                has_options,
                                ctx
                            )
                        elif current_eq <= start_equity:
                            trigger_alarm(r_t3, mute_btn, ctx)

                    elif t2_on and max_realized_profit >= t2_trig:
                        floor_equity = start_equity - t2_max
                        r_t2 = "Hit $0 (Tier 2)"
                        check_alarm_rearm(r_t2, current_eq, start_equity)
                        if not is_locked_down and current_eq <= floor_equity:
                            msg = f"Breached Tier 2 Floor (-${t2_max:,.0f})"
                            trigger_lockdown(
                                active_adapter, msg, mute_btn, has_options, ctx
                            )
                        elif (
                            open_flat_on
                            and not is_flat
                            and open_pnl <= -open_max
                        ):
                            if current_eq <= start_equity:
                                triggered_alarms.setdefault(r_t2, time.time())
                            r_open = f"Open PnL -${open_max:,.0f} Stop"
                            trigger_open_pnl_flatten(
                                active_adapter,
                                r_open,
                                mute_btn,
                                has_options,
                                ctx
                            )
                        elif current_eq <= start_equity:
                            trigger_alarm(r_t2, mute_btn, ctx)

                    else:
                        floor_equity = start_equity - t1_max
                        r_t1_w2 = f"Hit -${t1_w2:,.0f} (Tier 1)"
                        r_t1_w1 = f"Hit -${t1_w1:,.0f} (Tier 1)"

                        if t1_w2_on:
                            check_alarm_rearm(
                                r_t1_w2, current_eq, start_equity - t1_w2
                            )
                        if t1_w1_on:
                            check_alarm_rearm(
                                r_t1_w1, current_eq, start_equity - t1_w1
                            )

                        if not is_locked_down and current_eq <= floor_equity:
                            msg = f"Breached Tier 1 Floor (-${t1_max:,.0f})"
                            trigger_lockdown(
                                active_adapter, msg, mute_btn, has_options, ctx
                            )
                        elif (
                            open_flat_on
                            and not is_flat
                            and open_pnl <= -open_max
                        ):
                            if t1_w2_on and current_eq <= (start_equity - t1_w2):
                                triggered_alarms.setdefault(
                                    r_t1_w2, time.time()
                                )
                            if t1_w1_on and current_eq <= (start_equity - t1_w1):
                                triggered_alarms.setdefault(
                                    r_t1_w1, time.time()
                                )
                            r_open = f"Open PnL -${open_max:,.0f} Stop"
                            trigger_open_pnl_flatten(
                                active_adapter,
                                r_open,
                                mute_btn,
                                has_options,
                                ctx
                            )
                        elif t1_w2_on and current_eq <= (start_equity - t1_w2):
                            triggered_alarms.setdefault(
                                r_t1_w1, time.time()
                            )
                            trigger_alarm(r_t1_w2, mute_btn, ctx)
                        elif t1_w1_on and current_eq <= (start_equity - t1_w1):
                            trigger_alarm(r_t1_w1, mute_btn, ctx)

                terminate_pnl_level = round(floor_equity - start_equity, 2)
                distance_to_terminate = round(current_eq - floor_equity, 2)

                new_upside_tier = compute_upside_tier(
                    rth_now, max_realized_profit, config
                )
                if is_flat and new_upside_tier > current_upside_tier:
                    current_upside_tier = new_upside_tier
                    fl_str = format_dollar(terminate_pnl_level)
                    if not rth_now:
                        banner_txt = (
                            f"★ PM PROFIT LOCK UNLOCKED — "
                            f"FLOOR RAISED TO {fl_str} ★"
                        )
                        log_txt = (
                            f"Pre-Market Profit Lock unlocked at "
                            f"{format_dollar(max_realized_profit)} — "
                            f"Floor raised to {fl_str}"
                        )
                    else:
                        banner_txt = (
                            f"★ TIER {new_upside_tier} UNLOCKED — "
                            f"DAILY FLOOR RAISED TO {fl_str} ★"
                        )
                        log_txt = (
                            f"RTH Tier {new_upside_tier} unlocked at "
                            f"{format_dollar(max_realized_profit)} — "
                            f"Daily Floor raised to {fl_str}"
                        )
                    trigger_upside_tier_glow(mute_btn, banner_txt, log_txt)

                c1_bg = (
                    "#1e8449" if realized_pnl > 0
                    else ("#b03a2e" if realized_pnl < 0 else "#2c3e50")
                )
                c2_bg = (
                    "#1e8449" if open_pnl > 0
                    else ("#b03a2e" if open_pnl < 0 else "#2c3e50")
                )
                net_bg = (
                    "#1e8449" if net_pnl > 0
                    else ("#b03a2e" if net_pnl < 0 else "#2c3e50")
                )
                c3_bg = "#1e8449" if terminate_pnl_level > 0 else "#1f538d"
                c4_bg = (
                    "#b03a2e" if distance_to_terminate <= 0
                    else ("#d35400" if distance_to_terminate <= 500 else "#2c3e50")
                )
                c5_bg = "#1e8449" if session_high_pnl > 0 else "#2c3e50"

                giveback_val = (
                    round(net_pnl - session_high_pnl, 2)
                    if session_high_pnl > 0 else 0.0
                )
                fh_bg = (
                    "#1e8449" if (session_high_pnl > 0 and giveback_val >= 0)
                    else (
                        "#b03a2e" if giveback_val <= -500
                        else ("#d35400" if giveback_val <= -250 else "#2c3e50")
                    )
                )
                wl_bg = "#2c3e50"

                all_col_values = {
                    "realized_pnl": (format_dollar(realized_pnl), c1_bg),
                    "open_pnl": (format_dollar(open_pnl), c2_bg),
                    "net_pnl": (format_dollar(net_pnl), net_bg),
                    "terminate_lvl": (format_dollar(terminate_pnl_level), c3_bg),
                    "dist_to_term": (f"${distance_to_terminate:,.2f}", c4_bg),
                    "session_high": (format_dollar(session_high_pnl), c5_bg),
                    "from_high": (format_dollar(giveback_val), fh_bg),
                    "trades_wl": (
                        format_trades_wl_multiline(win_trades, loss_trades),
                        wl_bg
                    ),
                }
                active_cols = get_active_hud_columns(config)
                col_data = [
                    all_col_values.get(cid, ("---", "#2c3e50"))
                    for cid in active_cols
                ]

                root.after(
                    0,
                    lambda d=col_data, f=is_flat: update_gui(
                        ui_labels, d, f, settings_btn, close_btn
                    )
                )
            else:
                consecutive_api_failures += 1
                err_lower = getattr(active_adapter, "last_error", "").lower()
                is_tok_exp = any(
                    k in err_lower
                    for k in (
                        "invalid_grant",
                        "unsupported_token_type",
                        "expired",
                        "unauthorized",
                        "http 401",
                    )
                )
                if is_tok_exp or consecutive_api_failures >= 3:
                    current_is_flat = True
                    lbl_1 = "TOKEN" if is_tok_exp else "API"
                    lbl_2 = "EXPIRED" if is_tok_exp else "LOST"
                    n_cols = max(1, len(get_active_hud_columns(config)))
                    err_cols = []
                    for idx in range(n_cols):
                        if idx == 0:
                            err_cols.append((lbl_1, "#7b241c"))
                        elif idx == 1:
                            err_cols.append((lbl_2, "#7b241c"))
                        else:
                            err_cols.append(("---", "#444444"))
                    root.after(
                        0,
                        lambda d=err_cols: update_gui(
                            ui_labels, d, True, settings_btn, close_btn
                        )
                    )
                    if not api_disconnect_alerted:
                        api_disconnect_alerted = True
                        r_msg = (
                            "BROKER TOKEN EXPIRED — RESTART APP TO RE-LOGIN"
                            if is_tok_exp
                            else "BROKER API DISCONNECTED — CHECK CONNECTION"
                        )
                        v_msg = (
                            "Warning. Broker token expired. Please restart Enforcer to log in."
                            if is_tok_exp
                            else "Warning. Broker A P I connection lost."
                        )
                        speak_async(v_msg)
                        trigger_alarm(
                            r_msg,
                            mute_btn,
                            getattr(active_adapter, "last_error", "")[:80],
                        )

        except Exception as e:
            log_event("ERROR", f"Main data_loop error: {e}")

        time.sleep(poll_sec)


# ==========================================
# 8. SPACIOUS WIDESCREEN PRE-FLIGHT WINDOW
# ==========================================
def show_preflight_window(parent=None, mute_btn=None):
    global settings_win_open, triggered_alarms
    global force_reanchor, is_locked_down, current_is_flat
    global active_adapter, start_equity

    if parent is not None:
        if settings_win_open:
            return False
        if not current_is_flat:
            log_event(
                "GUARDRAIL",
                "BLOCKED: Attempted to open Settings while in a position!"
            )
            return False

    load_config()
    launched = {"status": False}

    if parent is None:
        pf = tk.Tk()
    else:
        settings_win_open = True
        pf = tk.Toplevel(parent)
        pf.grab_set()

    pf.title("PnL Enforcer — Pre-Flight & Risk Rulebook")
    pf.config(bg="#121212", padx=26, pady=18)
    pf.resizable(False, False)
    pf.attributes("-topmost", True)

    def on_close():
        global settings_win_open, first_poll_of_launch
        first_poll_of_launch = True
        settings_win_open = False
        pf.destroy()

    pf.protocol("WM_DELETE_WINDOW", on_close)

    def attach_tooltip(widget, text):
        """Attaches a clean dark-themed hover tooltip card to any widget."""
        tip_state = {"win": None, "after_id": None}

        def show_tip():
            tip_state["after_id"] = None
            if tip_state["win"] is not None or not widget.winfo_exists():
                return
            try:
                tw = tk.Toplevel(pf)
                tw.wm_overrideredirect(True)
                tw.attributes("-topmost", True)
                tw.config(bg="#5dade2", padx=1, pady=1)
                lbl = tk.Label(
                    tw,
                    text=text,
                    font=("Arial", 9),
                    fg="#f2f2f2",
                    bg="#1b2631",
                    justify="left",
                    wraplength=360,
                    padx=10,
                    pady=7
                )
                lbl.pack()
                tw.update_idletasks()
                tip_w = tw.winfo_reqwidth()
                tip_h = tw.winfo_reqheight()
                scr_w = tw.winfo_screenwidth()
                scr_h = tw.winfo_screenheight()
                x = widget.winfo_rootx() + 16
                y = widget.winfo_rooty() + widget.winfo_height() + 6
                if x + tip_w + 12 > scr_w:
                    x = max(10, scr_w - tip_w - 16)
                if y + tip_h + 12 > scr_h:
                    y = max(10, widget.winfo_rooty() - tip_h - 6)
                tw.wm_geometry(f"+{x}+{y}")
                tip_state["win"] = tw
            except Exception:
                pass

        def hide_tip(_event=None):
            if tip_state["after_id"] is not None:
                try:
                    widget.after_cancel(tip_state["after_id"])
                except Exception:
                    pass
                tip_state["after_id"] = None
            if tip_state["win"] is not None:
                try:
                    tip_state["win"].destroy()
                except Exception:
                    pass
                tip_state["win"] = None

        def schedule_tip(_event=None):
            hide_tip()
            try:
                tip_state["after_id"] = widget.after(320, show_tip)
            except Exception:
                pass

        widget.bind("<Enter>", schedule_tip, add="+")
        widget.bind("<Leave>", hide_tip, add="+")
        widget.bind("<ButtonPress>", hide_tip, add="+")
        widget.bind("<Destroy>", hide_tip, add="+")

    # --- STATE VARIABLES ---
    var_broker = tk.StringVar(value=config.get("active_broker", "SCHWAB"))
    var_account_label = tk.StringVar(value="")
    account_label_to_id = {}
    base_sub_lbl = None

    var_open_flat = tk.BooleanVar(
        value=config.get("enable_open_flatten", False)
    )
    var_open_cd = tk.BooleanVar(
        value=config.get("enable_open_cooldown", False)
    )
    var_cd_mins = tk.StringVar(
        value=f"{config.get('open_cooldown_mins', 1.0):g}"
    )

    var_flatten = tk.BooleanVar(value=config["enable_auto_flatten"])
    var_kill_tos = tk.BooleanVar(value=config.get("enable_kill_tos", False))
    var_kill_wb = tk.BooleanVar(value=config.get("enable_kill_webull", False))
    var_lock_os = tk.BooleanVar(value=config["enable_lock_os"])
    var_daily_lock_mins = tk.StringVar(
        value=f"{config.get('daily_lock_mins', 15.0):g}"
    )

    var_reset925 = tk.BooleanVar(value=config["reset_at_925"])
    var_reanchor = tk.BooleanVar(value=False)
    var_voice_cues = tk.BooleanVar(
        value=config.get("enable_voice_cues", True)
    )
    var_upside_chime = tk.BooleanVar(
        value=config.get("enable_upside_chime", True)
    )
    var_audio_test = tk.StringVar(value="Warning Siren (Short Preview)")
    selected_hud_columns = list(get_active_hud_columns(config))
    var_poll = tk.StringVar(value=str(int(config["poll_interval"])))

    var_pm_w1_on = tk.BooleanVar(
        value=config.get("enable_pm_warn_1", True)
    )
    var_pm_w2_on = tk.BooleanVar(
        value=config.get("enable_pm_warn_2", True)
    )
    var_pm_lock_on = tk.BooleanVar(
        value=config.get("enable_pm_lock", True)
    )
    var_t1_w1_on = tk.BooleanVar(
        value=config.get("enable_t1_warn_1", True)
    )
    var_t1_w2_on = tk.BooleanVar(
        value=config.get("enable_t1_warn_2", True)
    )
    var_t2_on = tk.BooleanVar(value=config.get("enable_t2", True))
    var_t3_on = tk.BooleanVar(value=config.get("enable_t3", True))
    var_t4_on = tk.BooleanVar(value=config.get("enable_t4", True))

    dollar_keys = [
        "open_max_loss",
        "pm_warn_1", "pm_warn_2", "pm_max_loss",
        "pm_lock_trigger", "pm_trail_cushion",
        "t1_warn_1", "t1_warn_2", "t1_max_loss",
        "t2_trigger", "t2_max_loss",
        "t3_trigger", "t3_max_loss",
        "t4_trigger", "t4_trail"
    ]
    dollar_vars = {
        k: tk.StringVar(value=f"{config.get(k, DEFAULT_CONFIG[k]):.0f}")
        for k in dollar_keys
    }

    def refresh_baseline_preview():
        """Updates the Active Baseline label in Card 3 to match the
        currently selected Broker + Account."""
        global start_equity, force_reanchor
        if base_sub_lbl is None:
            return
        if active_adapter is None or not active_adapter.account_id:
            base_sub_lbl.config(
                text="No broker connected — click API Keys or select broker above."
            )
            return

        b_name = active_adapter.name
        acct_id = active_adapter.account_id
        had_saved = restore_account_session(b_name, acct_id, log_restore=False)
        tok_suffix = ""
        if b_name == "SCHWAB":
            rem_h = get_schwab_token_remaining_hours()
            if rem_h is not None and rem_h > 0:
                tok_suffix = f" | Token: {rem_h / 24.0:.1f}d left"
        wl_suffix = f" | {format_trades_wl_inline(win_trades, loss_trades)}"

        if had_saved and start_equity is not None and start_equity > 0:
            force_reanchor = False
            base_sub_lbl.config(
                text=f"Active Baseline ({b_name}): ${start_equity:,.2f} (Preserved){tok_suffix}{wl_suffix}"
            )
        else:
            eq, _, _, _, _ = active_adapter.fetch_account_data()
            if eq is not None and eq > 0:
                start_equity = eq
                force_reanchor = True
                base_sub_lbl.config(
                    text=f"Active Baseline ({b_name}): ${start_equity:,.2f} (Live equity){tok_suffix}{wl_suffix}"
                )
            else:
                base_sub_lbl.config(
                    text=f"Active Baseline ({b_name}): Will anchor on first API poll.{tok_suffix}{wl_suffix}"
                )

    # --- TOP BAR: BROKER & ACCOUNT SELECTOR + PRESETS ---
    top_bar = tk.Frame(
        pf, bg="#1c1c1c", bd=1, relief="solid", padx=16, pady=10
    )
    top_bar.pack(fill="x", pady=(0, 14))

    tk.Label(
        top_bar,
        text="BROKER:",
        font=("Arial", 10, "bold"),
        fg="#5dade2",
        bg="#1c1c1c"
    ).pack(side="left", padx=(0, 6))

    broker_menu = tk.OptionMenu(top_bar, var_broker, "SCHWAB", "WEBULL")
    broker_menu.config(
        font=("Arial", 10, "bold"),
        bg="#2a2a2a",
        fg="white",
        activebackground="#1f538d",
        activeforeground="white",
        highlightthickness=0,
        bd=1,
        relief="solid"
    )
    broker_menu["menu"].config(
        font=("Arial", 10, "bold"), bg="#2a2a2a", fg="white"
    )
    broker_menu.pack(side="left", padx=(0, 10))

    tk.Label(
        top_bar,
        text="ACCOUNT:",
        font=("Arial", 10, "bold"),
        fg="#5dade2",
        bg="#1c1c1c"
    ).pack(side="left", padx=(4, 6))

    acct_menu = tk.OptionMenu(top_bar, var_account_label, "Loading...")
    acct_menu.config(
        font=("Arial", 10, "bold"),
        bg="#2a2a2a",
        fg="white",
        activebackground="#1f538d",
        activeforeground="white",
        highlightthickness=0,
        bd=1,
        relief="solid",
        padx=12
    )
    acct_menu["menu"].config(
        font=("Arial", 10, "bold"), bg="#2a2a2a", fg="white"
    )
    acct_menu.pack(side="left", padx=(0, 8))
    attach_tooltip(
        broker_menu,
        "Select which broker API to monitor (Charles Schwab / Thinkorswim or Webull).\n"
        "Each broker and account tracks its own separate daily baseline and session history."
    )
    attach_tooltip(
        acct_menu,
        "Choose which sub-account to monitor under the active broker.\n"
        "Switching accounts preserves each account's independent starting equity and PnL."
    )

    def on_account_select(chosen_lbl):
        var_account_label.set(chosen_lbl)
        if active_adapter is not None:
            chosen_id = account_label_to_id.get(chosen_lbl)
            if chosen_id and chosen_id != active_adapter.account_id:
                active_adapter.account_id = chosen_id
                config["brokers"][active_adapter.name]["selected_account_id"] = chosen_id
                refresh_baseline_preview()

    def populate_account_dropdown():
        account_label_to_id.clear()
        menu = acct_menu["menu"]
        menu.delete(0, "end")
        if active_adapter and active_adapter.accounts:
            selected_lbl = active_adapter.accounts[0]["label"]
            for acc in active_adapter.accounts:
                lbl = acc["label"]
                aid = acc["id"]
                account_label_to_id[lbl] = aid
                menu.add_command(
                    label=lbl,
                    command=lambda v=lbl: on_account_select(v)
                )
                if aid == active_adapter.account_id:
                    selected_lbl = lbl
            var_account_label.set(selected_lbl)
        else:
            var_account_label.set("No Account Connected")

    def on_broker_change(*_):
        global active_adapter
        chosen = var_broker.get()
        if active_adapter is None or active_adapter.name != chosen:
            new_ad = connect_broker_adapter(chosen, parent=pf, force_wizard=False)
            if new_ad is not None:
                active_adapter = new_ad
                config["active_broker"] = chosen
                populate_account_dropdown()
                refresh_baseline_preview()
            else:
                if active_adapter is not None:
                    var_broker.set(active_adapter.name)

    def edit_api_keys():
        global active_adapter
        chosen = var_broker.get()
        new_ad = connect_broker_adapter(chosen, parent=pf, force_wizard=True)
        if new_ad is not None:
            active_adapter = new_ad
            config["active_broker"] = chosen
            populate_account_dropdown()
            refresh_baseline_preview()

    btn_api_keys = tk.Button(
        top_bar,
        text="🔑 API Keys",
        font=("Arial", 9, "bold"),
        bg="#333333",
        fg="white",
        padx=9,
        pady=3,
        command=edit_api_keys
    )
    btn_api_keys.pack(side="left", padx=(0, 6))
    attach_tooltip(
        btn_api_keys,
        "Open the API Credential Setup Wizard to enter or update your App Key & Secret,\n"
        "or to re-authenticate your 7-day Schwab security token."
    )

    def open_hud_columns_dialog():
        dlg = tk.Toplevel(pf)
        dlg.title("Customize HUD Columns & Order")
        dlg.config(bg="#161616", padx=22, pady=16)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.grab_set()

        tk.Label(
            dlg,
            text="📊 CUSTOMIZE HUD COLUMNS & DISPLAY ORDER",
            font=("Arial", 11, "bold"),
            fg="#5dade2",
            bg="#161616",
            anchor="w"
        ).pack(fill="x")
        tk.Label(
            dlg,
            text="Check the columns you want on your HUD and use ▲ / ▼ to arrange their left-to-right order.",
            font=("Arial", 9),
            fg="#aaaaaa",
            bg="#161616",
            anchor="w"
        ).pack(fill="x", pady=(2, 10))

        all_ids = [cid for cid, _, _ in HUD_COLUMN_CATALOG]
        ordered_ids = list(selected_hud_columns) + [
            cid for cid in all_ids if cid not in selected_hud_columns
        ]
        checked_vars = {
            cid: tk.BooleanVar(value=(cid in selected_hud_columns))
            for cid in all_ids
        }
        desc_map = {cid: (hdr, desc) for cid, hdr, desc in HUD_COLUMN_CATALOG}

        list_frame = tk.Frame(dlg, bg="#1f1f1f", bd=1, relief="solid", padx=12, pady=8)
        list_frame.pack(fill="both", expand=True)

        def render_rows():
            for w in list_frame.winfo_children():
                w.destroy()
            for idx, cid in enumerate(ordered_ids):
                hdr, desc = desc_map[cid]
                row = tk.Frame(list_frame, bg="#1f1f1f", pady=3)
                row.pack(fill="x")

                tk.Checkbutton(
                    row,
                    text=f"{idx + 1}. {hdr}",
                    variable=checked_vars[cid],
                    font=("Arial", 10, "bold"),
                    fg="#ffffff",
                    bg="#1f1f1f",
                    selectcolor="#2a2a2a",
                    activebackground="#1f1f1f",
                    activeforeground="#ffffff",
                    width=18,
                    anchor="w"
                ).pack(side="left")

                tk.Label(
                    row,
                    text=desc,
                    font=("Arial", 9),
                    fg="#999999",
                    bg="#1f1f1f",
                    anchor="w",
                    width=42
                ).pack(side="left", padx=(6, 10))

                def move_up(i=idx):
                    if i > 0:
                        ordered_ids[i - 1], ordered_ids[i] = (
                            ordered_ids[i],
                            ordered_ids[i - 1],
                        )
                        render_rows()

                def move_down(i=idx):
                    if i < len(ordered_ids) - 1:
                        ordered_ids[i + 1], ordered_ids[i] = (
                            ordered_ids[i],
                            ordered_ids[i + 1],
                        )
                        render_rows()

                tk.Button(
                    row,
                    text="▼",
                    font=("Arial", 8, "bold"),
                    bg="#2e2e2e",
                    fg="white",
                    width=3,
                    command=move_down
                ).pack(side="right", padx=2)
                tk.Button(
                    row,
                    text="▲",
                    font=("Arial", 8, "bold"),
                    bg="#2e2e2e",
                    fg="white",
                    width=3,
                    command=move_up
                ).pack(side="right", padx=2)

        render_rows()

        def reset_standard_5():
            ordered_ids.clear()
            ordered_ids.extend(
                list(DEFAULT_HUD_COLUMNS)
                + [c for c in all_ids if c not in DEFAULT_HUD_COLUMNS]
            )
            for c in all_ids:
                checked_vars[c].set(c in DEFAULT_HUD_COLUMNS)
            render_rows()

        def apply_and_close():
            chosen = [c for c in ordered_ids if checked_vars[c].get()]
            if not chosen:
                messagebox.showwarning(
                    "No Columns Selected",
                    "Please keep at least 1 HUD column checked.",
                    parent=dlg
                )
                return
            selected_hud_columns.clear()
            selected_hud_columns.extend(chosen)
            hud_cols_btn.config(text=f"📊 HUD Columns ({len(chosen)})")
            dlg.destroy()

        b_bar = tk.Frame(dlg, bg="#161616", pady=10)
        b_bar.pack(fill="x")
        tk.Button(
            b_bar,
            text="Reset Default 5",
            font=("Arial", 9, "bold"),
            bg="#333333",
            fg="white",
            padx=12,
            pady=4,
            command=reset_standard_5
        ).pack(side="left")
        tk.Button(
            b_bar,
            text="Done ✓",
            font=("Arial", 9, "bold"),
            bg="#1e8449",
            fg="white",
            padx=18,
            pady=4,
            command=apply_and_close
        ).pack(side="right")

    hud_cols_btn = tk.Button(
        top_bar,
        text=f"📊 HUD Columns ({len(selected_hud_columns)})",
        font=("Arial", 9, "bold"),
        bg="#2c3e50",
        fg="#aed6f1",
        padx=9,
        pady=3,
        command=open_hud_columns_dialog
    )
    hud_cols_btn.pack(side="left", padx=(0, 6))
    attach_tooltip(
        hud_cols_btn,
        "Choose which metrics appear on your live HUD bar (Realized PnL, Open PnL, Net PnL,\n"
        "Terminate Level, $ to Terminate, Session High, From High, Trades W/L) and reorder them."
    )

    def open_log_file():
        if not os.path.exists(LOG_PATH):
            init_daily_log()
        try:
            os.startfile(LOG_PATH)
        except Exception as e:
            messagebox.showinfo(
                "Session Log Path",
                f"Your session log file is located at:\n{LOG_PATH}\n\n({e})",
                parent=pf
            )

    btn_view_log = tk.Button(
        top_bar,
        text="📂 View Log",
        font=("Arial", 9, "bold"),
        bg="#333333",
        fg="white",
        padx=9,
        pady=3,
        command=open_log_file
    )
    btn_view_log.pack(side="left", padx=(0, 10))
    attach_tooltip(
        btn_view_log,
        f"Open today's audit & trade log in Notepad:\n{LOG_PATH}"
    )

    populate_account_dropdown()
    var_broker.trace_add("write", on_broker_change)

    def apply_dollar_preset(preset_dict):
        for k, val in preset_dict.items():
            if k in dollar_vars:
                dollar_vars[k].set(f"{val:.0f}")

    def apply_half_risk_preset():
        base_src = config.get("user_defaults") or DEFAULT_CONFIG
        half_dict = {}
        for k in dollar_keys:
            full_val = float(base_src.get(k, DEFAULT_CONFIG[k]))
            half_dict[k] = round(full_val * 0.5) if full_val > 0 else 0.0
        apply_dollar_preset(half_dict)
        if default_status_lbl is not None:
            src_name = "your saved Default" if config.get("user_defaults") else "Factory Default"
            default_status_lbl.config(
                text=f"⚡ Applied 50% Low Energy preset (50% of {src_name} dollar thresholds).",
                fg="#f5b041"
            )

    def apply_standard_full_preset():
        base_src = config.get("user_defaults") or DEFAULT_CONFIG
        apply_dollar_preset(base_src)
        if default_status_lbl is not None:
            src_name = "your saved Default" if config.get("user_defaults") else "Factory Default"
            default_status_lbl.config(
                text=f"✓ Applied Standard Full Risk preset (100% of {src_name} dollar thresholds).",
                fg="#5dade2"
            )

    btn_half_risk = tk.Button(
        top_bar,
        text="50% Low Energy",
        font=("Arial", 9, "bold"),
        bg="#7d6608",
        fg="white",
        padx=9,
        pady=3,
        command=apply_half_risk_preset
    )
    btn_half_risk.pack(side="right", padx=3)
    attach_tooltip(
        btn_half_risk,
        "Cuts all dollar risk thresholds, warning alarms, and tier triggers in half (50%)\n"
        "relative to your saved Default settings (or Factory Defaults if none saved yet).\n"
        "Ideal for choppy markets, B-setup days, or low-energy sessions."
    )

    btn_full_risk = tk.Button(
        top_bar,
        text="Standard Full Risk",
        font=("Arial", 9, "bold"),
        bg="#1f538d",
        fg="white",
        padx=9,
        pady=3,
        command=apply_standard_full_preset
    )
    btn_full_risk.pack(side="right", padx=3)
    attach_tooltip(
        btn_full_risk,
        "Restores 100% of your saved Default dollar thresholds\n"
        "(or Factory Default dollar thresholds if you haven't clicked 'Save as Default' yet)."
    )

    tk.Label(
        top_bar,
        text="PRESETS:",
        font=("Arial", 9, "bold"),
        fg="#dddddd",
        bg="#1c1c1c"
    ).pack(side="right", padx=(6, 4))

    default_status_lbl = None

    def restore_factory_defaults():
        src = config.get("user_defaults") or DEFAULT_CONFIG
        var_open_flat.set(
            src.get("enable_open_flatten", DEFAULT_CONFIG["enable_open_flatten"])
        )
        var_open_cd.set(
            src.get("enable_open_cooldown", DEFAULT_CONFIG["enable_open_cooldown"])
        )
        var_cd_mins.set(
            f"{src.get('open_cooldown_mins', DEFAULT_CONFIG['open_cooldown_mins']):g}"
        )
        var_flatten.set(
            src.get("enable_auto_flatten", DEFAULT_CONFIG["enable_auto_flatten"])
        )
        var_kill_tos.set(
            src.get("enable_kill_tos", DEFAULT_CONFIG["enable_kill_tos"])
        )
        var_kill_wb.set(
            src.get("enable_kill_webull", DEFAULT_CONFIG["enable_kill_webull"])
        )
        var_lock_os.set(
            src.get("enable_lock_os", DEFAULT_CONFIG["enable_lock_os"])
        )
        var_daily_lock_mins.set(
            f"{src.get('daily_lock_mins', DEFAULT_CONFIG['daily_lock_mins']):g}"
        )
        var_reset925.set(
            src.get("reset_at_925", DEFAULT_CONFIG["reset_at_925"])
        )
        var_voice_cues.set(
            src.get("enable_voice_cues", DEFAULT_CONFIG["enable_voice_cues"])
        )
        var_upside_chime.set(
            src.get("enable_upside_chime", DEFAULT_CONFIG["enable_upside_chime"])
        )
        var_pm_w1_on.set(
            src.get("enable_pm_warn_1", DEFAULT_CONFIG["enable_pm_warn_1"])
        )
        var_pm_w2_on.set(
            src.get("enable_pm_warn_2", DEFAULT_CONFIG["enable_pm_warn_2"])
        )
        var_pm_lock_on.set(
            src.get("enable_pm_lock", DEFAULT_CONFIG["enable_pm_lock"])
        )
        var_t1_w1_on.set(
            src.get("enable_t1_warn_1", DEFAULT_CONFIG["enable_t1_warn_1"])
        )
        var_t1_w2_on.set(
            src.get("enable_t1_warn_2", DEFAULT_CONFIG["enable_t1_warn_2"])
        )
        var_t2_on.set(
            src.get("enable_t2", DEFAULT_CONFIG["enable_t2"])
        )
        var_t3_on.set(
            src.get("enable_t3", DEFAULT_CONFIG["enable_t3"])
        )
        var_t4_on.set(
            src.get("enable_t4", DEFAULT_CONFIG["enable_t4"])
        )
        selected_hud_columns.clear()
        selected_hud_columns.extend(get_active_hud_columns(src))
        hud_cols_btn.config(
            text=f"📊 HUD Columns ({len(selected_hud_columns)})"
        )
        var_reanchor.set(False)
        var_poll.set(
            str(int(src.get("poll_interval", DEFAULT_CONFIG["poll_interval"])))
        )
        apply_dollar_preset(src)
        refresh_smart_dimming()
        if default_status_lbl is not None:
            msg = (
                "↺ Restored your saved defaults."
                if config.get("user_defaults")
                else "↺ Restored factory defaults."
            )
            default_status_lbl.config(text=msg, fg="#5dade2")

    def save_as_user_defaults():
        try:
            custom_def = {
                "enable_open_flatten": bool(var_open_flat.get()),
                "enable_open_cooldown": bool(var_open_cd.get()),
                "open_cooldown_mins": max(0.1, abs(float(var_cd_mins.get()))),
                "enable_auto_flatten": bool(var_flatten.get()),
                "enable_kill_tos": bool(var_kill_tos.get()),
                "enable_kill_webull": bool(var_kill_wb.get()),
                "enable_lock_os": bool(var_lock_os.get()),
                "daily_lock_mins": max(0.0, abs(float(var_daily_lock_mins.get()))),
                "reset_at_925": bool(var_reset925.get()),
                "enable_voice_cues": bool(var_voice_cues.get()),
                "enable_upside_chime": bool(var_upside_chime.get()),
                "enable_pm_warn_1": bool(var_pm_w1_on.get()),
                "enable_pm_warn_2": bool(var_pm_w2_on.get()),
                "enable_pm_lock": bool(var_pm_lock_on.get()),
                "enable_t1_warn_1": bool(var_t1_w1_on.get()),
                "enable_t1_warn_2": bool(var_t1_w2_on.get()),
                "enable_t2": bool(var_t2_on.get()),
                "enable_t3": bool(var_t3_on.get()),
                "enable_t4": bool(var_t4_on.get()),
                "hud_columns": list(selected_hud_columns),
                "poll_interval": max(1, int(float(var_poll.get())))
            }
            for k in dollar_keys:
                custom_def[k] = abs(float(dollar_vars[k].get()))

            config["user_defaults"] = custom_def
            save_config(config)
            log_event("CONFIG", "Saved current Pre-Flight settings as User Defaults.")
            if default_status_lbl is not None:
                default_status_lbl.config(
                    text="✓ Saved as your Default! ('Restore Defaults' & '50% Low Energy' now use these values)",
                    fg="#58d68d"
                )
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Please ensure all fields contain valid numbers before saving defaults.",
                parent=pf
            )

    def save_and_launch():
        global settings_win_open, triggered_alarms, first_poll_of_launch
        global force_reanchor, is_locked_down, current_is_flat, active_adapter

        if parent is not None and not current_is_flat:
            log_event(
                "GUARDRAIL",
                "BLOCKED: Attempted to save Settings while in a position!"
            )
            messagebox.showwarning(
                "Locked In Trade",
                "Settings cannot be modified while a position is open.\n"
                "Flatten your position first.",
                parent=pf
            )
            return

        if active_adapter is None:
            messagebox.showerror(
                "Broker Not Connected",
                "Please connect a valid Schwab or Webull account first.",
                parent=pf
            )
            return

        try:
            new_cfg = json.loads(json.dumps(config))
            chosen_b = var_broker.get()
            new_cfg["active_broker"] = chosen_b

            chosen_lbl = var_account_label.get()
            chosen_id = account_label_to_id.get(
                chosen_lbl, active_adapter.account_id
            )
            if chosen_id:
                active_adapter.account_id = chosen_id
                new_cfg["brokers"][chosen_b]["selected_account_id"] = chosen_id

            had_saved = restore_account_session(
                chosen_b, active_adapter.account_id, log_restore=False
            )
            if not had_saved:
                force_reanchor = True

            new_cfg["enable_open_flatten"] = bool(var_open_flat.get())
            new_cfg["enable_open_cooldown"] = bool(var_open_cd.get())
            new_cfg["open_cooldown_mins"] = max(
                0.1, abs(float(var_cd_mins.get()))
            )
            new_cfg["enable_auto_flatten"] = bool(var_flatten.get())
            new_cfg["enable_kill_tos"] = bool(var_kill_tos.get())
            new_cfg["enable_kill_webull"] = bool(var_kill_wb.get())
            new_cfg["enable_lock_os"] = bool(var_lock_os.get())
            new_cfg["daily_lock_mins"] = max(
                0.0, abs(float(var_daily_lock_mins.get()))
            )
            new_cfg["reset_at_925"] = bool(var_reset925.get())
            new_cfg["enable_voice_cues"] = bool(var_voice_cues.get())
            new_cfg["enable_upside_chime"] = bool(var_upside_chime.get())
            new_cfg["enable_pm_warn_1"] = bool(var_pm_w1_on.get())
            new_cfg["enable_pm_warn_2"] = bool(var_pm_w2_on.get())
            new_cfg["enable_pm_lock"] = bool(var_pm_lock_on.get())
            new_cfg["enable_t1_warn_1"] = bool(var_t1_w1_on.get())
            new_cfg["enable_t1_warn_2"] = bool(var_t1_w2_on.get())
            new_cfg["enable_t2"] = bool(var_t2_on.get())
            new_cfg["enable_t3"] = bool(var_t3_on.get())
            new_cfg["enable_t4"] = bool(var_t4_on.get())
            new_cfg["hud_columns"] = list(selected_hud_columns)
            new_cfg["poll_interval"] = max(1, int(float(var_poll.get())))

            for k in dollar_keys:
                new_cfg[k] = abs(float(dollar_vars[k].get()))

            is_locked_down = False
            first_poll_of_launch = True

            if var_reanchor.get():
                force_reanchor = True
                triggered_alarms.clear()
                s_key = get_session_key(chosen_b, active_adapter.account_id)
                if s_key and s_key in new_cfg.get("account_sessions", {}):
                    del new_cfg["account_sessions"][s_key]
                new_cfg["saved_start_equity"] = None
                new_cfg["saved_daily_max_equity"] = None
                log_event("CONFIG", "User checked Force Re-Anchor Baseline.")

            save_config(new_cfg)
            log_event("CONFIG", format_config_summary(new_cfg))
            rebuild_hud_columns()

            if not alarm_active and not cooldown_active:
                if mute_btn is not None:
                    mute_btn.config(text=get_idle_button_text())

            launched["status"] = True
            settings_win_open = False
            pf.destroy()
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Please ensure all fields contain valid numbers.",
                parent=pf
            )

    # --- SPACIOUS 2-COLUMN BODY CONTAINER ---
    body_frame = tk.Frame(pf, bg="#121212")
    body_frame.pack(fill="both", expand=True)
    body_frame.columnconfigure(0, weight=1, minsize=520)
    body_frame.columnconfigure(1, weight=1, minsize=520)

    left_col = tk.Frame(body_frame, bg="#121212")
    left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

    right_col = tk.Frame(body_frame, bg="#121212")
    right_col.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

    def make_card(parent_col, title, subtitle, accent="#5dade2", expand=False):
        card = tk.Frame(
            parent_col, bg="#1b1b1b", bd=1, relief="solid", padx=18, pady=12
        )
        card.pack(fill="both", expand=expand, pady=6)
        tk.Label(
            card,
            text=title,
            font=("Arial", 11, "bold"),
            fg=accent,
            bg="#1b1b1b",
            anchor="w"
        ).pack(fill="x")
        if subtitle:
            tk.Label(
                card,
                text=subtitle,
                font=("Arial", 9),
                fg="#aaaaaa",
                bg="#1b1b1b",
                anchor="w"
            ).pack(fill="x", pady=(2, 8))
        return card

    def make_entry(parent_w, var, width=8):
        return tk.Entry(
            parent_w,
            textvariable=var,
            font=("Arial", 11, "bold"),
            width=width,
            bg="#2e2e2e",
            fg="#ffffff",
            disabledbackground="#161616",
            disabledforeground="#555555",
            insertbackground="white",
            justify="center",
            bd=1,
            relief="solid"
        )

    def make_dual_field_row(
        parent_w,
        lbl1,
        var1,
        lbl2=None,
        var2=None,
        cb_var1=None,
        cb_var2=None,
        tip1=None,
        tip2=None
    ):
        row = tk.Frame(parent_w, bg="#1b1b1b")
        row.pack(fill="x", pady=4)
        row.columnconfigure(0, weight=1)
        row.columnconfigure(2, weight=1)

        if cb_var1 is not None:
            w1 = tk.Checkbutton(
                row,
                text=lbl1,
                variable=cb_var1,
                font=("Arial", 10, "bold"),
                fg="#f2f2f2",
                bg="#1b1b1b",
                selectcolor="#2a2a2a",
                activebackground="#1b1b1b",
                activeforeground="#ffffff",
                anchor="w"
            )
        else:
            w1 = tk.Label(
                row,
                text=lbl1,
                font=("Arial", 10, "bold"),
                fg="#f2f2f2",
                bg="#1b1b1b",
                anchor="w"
            )
        w1.grid(row=0, column=0, sticky="w", padx=(0, 8))
        e1 = make_entry(row, var1, width=8)
        e1.grid(row=0, column=1, padx=(0, 24))
        if tip1:
            attach_tooltip(w1, tip1)
            attach_tooltip(e1, tip1)

        w2, e2 = None, None
        if lbl2 and var2 is not None:
            if cb_var2 is not None:
                w2 = tk.Checkbutton(
                    row,
                    text=lbl2,
                    variable=cb_var2,
                    font=("Arial", 10, "bold"),
                    fg="#f2f2f2",
                    bg="#1b1b1b",
                    selectcolor="#2a2a2a",
                    activebackground="#1b1b1b",
                    activeforeground="#ffffff",
                    anchor="w"
                )
            else:
                w2 = tk.Label(
                    row,
                    text=lbl2,
                    font=("Arial", 10, "bold"),
                    fg="#f2f2f2",
                    bg="#1b1b1b",
                    anchor="w"
                )
            w2.grid(row=0, column=2, sticky="w", padx=(0, 8))
            e2 = make_entry(row, var2, width=8)
            e2.grid(row=0, column=3)
            if tip2:
                attach_tooltip(w2, tip2)
                attach_tooltip(e2, tip2)
        return w1, e1, w2, e2

    # ==========================================================
    # LEFT COLUMN: 1. SINGLE-TRADE STOP, 2. DAILY ACTIONS, 3. SYSTEM
    # ==========================================================
    c1 = make_card(
        left_col,
        "1. SINGLE-TRADE CIRCUIT BREAKER (Open PnL Stop)",
        "Flattens open Equities in PM or RTH without ending your day "
        "(Options = Siren Only).",
        accent="#5dade2"
    )

    r_open1 = tk.Frame(c1, bg="#1b1b1b")
    r_open1.pack(fill="x", pady=4)
    cb_open_flat = tk.Checkbutton(
        r_open1,
        text="Enable Open PnL Auto-Flatten (Equities)",
        variable=var_open_flat,
        font=("Arial", 10, "bold"),
        fg="#ffffff",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#ffffff",
        anchor="w"
    )
    cb_open_flat.pack(side="left")
    ent_open_loss = make_entry(r_open1, dollar_vars["open_max_loss"], width=8)
    ent_open_loss.pack(side="right")
    lbl_open_loss = tk.Label(
        r_open1,
        text="Max Open Loss ($):",
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b"
    )
    lbl_open_loss.pack(side="right", padx=(16, 8))
    open_stop_tip = (
        "Single-Trade Circuit Breaker:\n"
        "If your combined unrealized Open PnL drops to or below -Max Open Loss ($),\n"
        "Enforcer cancels working orders and flattens open EQUITY shares immediately\n"
        "(Market order in RTH 9:30–4:00 ET; marketable GTC_EXT limit order in Extended Hours).\n"
        "• Does NOT end your trading day.\n"
        "• Option contracts are never auto-flattened (sounds siren only)."
    )
    attach_tooltip(cb_open_flat, open_stop_tip)
    attach_tooltip(lbl_open_loss, open_stop_tip)
    attach_tooltip(ent_open_loss, open_stop_tip)

    r_open2 = tk.Frame(c1, bg="#1b1b1b")
    r_open2.pack(fill="x", pady=4)
    cb_open_cd = tk.Checkbutton(
        r_open2,
        text="   └─ Penalty Box OS Lock After Open Stop",
        variable=var_open_cd,
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b",
        disabledforeground="#555555",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#ffffff",
        anchor="w"
    )
    cb_open_cd.pack(side="left")
    ent_cd_mins = make_entry(r_open2, var_cd_mins, width=8)
    ent_cd_mins.pack(side="right")
    lbl_cd_mins = tk.Label(
        r_open2,
        text="Lock Duration (Mins):",
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b"
    )
    lbl_cd_mins.pack(side="right", padx=(16, 8))
    open_cd_tip = (
        "Penalty Box Cooldown Lock:\n"
        "Locks your Windows screen for the set duration (supports decimals like 0.5 for 30s)\n"
        "so you cannot immediately revenge-enter the same trade.\n"
        "• SAFETY GUARANTEE: The app ALWAYS confirms with the broker API that 100% of open\n"
        "  positions are closed (flat) before locking your computer — it will never lock you\n"
        "  out while a position is still open."
    )
    attach_tooltip(cb_open_cd, open_cd_tip)
    attach_tooltip(lbl_cd_mins, open_cd_tip)
    attach_tooltip(ent_cd_mins, open_cd_tip)

    # --- CARD 2: DAILY FLOOR BREACH ACTIONS (END-OF-DAY) ---
    c2 = make_card(
        left_col,
        "2. DAILY FLOOR BREACH ACTIONS (End-of-Day)",
        "Fires ONLY when total Net PnL breaches your Pre-Market "
        "or RTH Termination Floor.",
        accent="#f5b041"
    )

    cb_day_flat = tk.Checkbutton(
        c2,
        text="Auto-Flatten Equities on Daily Floor Breach",
        variable=var_flatten,
        font=("Arial", 10, "bold"),
        fg="#ffffff",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#ffffff",
        anchor="w"
    )
    cb_day_flat.pack(fill="x", pady=3)
    attach_tooltip(
        cb_day_flat,
        "When your total Net PnL (Realized + Open) touches your active Daily Termination Floor,\n"
        "cancels all working orders and liquidates open Equity shares immediately.\n"
        "(Options are never auto-flattened; if options are open, siren blares until you close them.)"
    )

    r_kill = tk.Frame(c2, bg="#1b1b1b")
    r_kill.pack(fill="x", pady=3)
    lbl_kill = tk.Label(
        r_kill,
        text="Kill Apps (When Flat):",
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b"
    )
    lbl_kill.pack(side="left", padx=(0, 10))
    cb_kill_tos = tk.Checkbutton(
        r_kill,
        text="Thinkorswim",
        variable=var_kill_tos,
        font=("Arial", 10, "bold"),
        fg="#eb7067",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#eb7067"
    )
    cb_kill_tos.pack(side="left", padx=(0, 12))
    cb_kill_wb = tk.Checkbutton(
        r_kill,
        text="Webull Desktop",
        variable=var_kill_wb,
        font=("Arial", 10, "bold"),
        fg="#eb7067",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#eb7067"
    )
    cb_kill_wb.pack(side="left")
    kill_tip = (
        "Force-closes your desktop trading platform (thinkorswim.exe and/or Webull Desktop)\n"
        "ONLY after confirming your account is 100% flat."
    )
    attach_tooltip(lbl_kill, kill_tip)
    attach_tooltip(cb_kill_tos, kill_tip)
    attach_tooltip(cb_kill_wb, kill_tip)

    r_day_lock = tk.Frame(c2, bg="#1b1b1b")
    r_day_lock.pack(fill="x", pady=3)
    cb_lock_os = tk.Checkbutton(
        r_day_lock,
        text="Lock Windows OS on Daily Breach",
        variable=var_lock_os,
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#ffffff",
        anchor="w"
    )
    cb_lock_os.pack(side="left")
    ent_daily_lock_mins = make_entry(r_day_lock, var_daily_lock_mins, width=8)
    ent_daily_lock_mins.pack(side="right")
    lbl_daily_lock_mins = tk.Label(
        r_day_lock,
        text="Lock Duration (Mins, 0 = 1x):",
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b"
    )
    lbl_daily_lock_mins.pack(side="right", padx=(12, 8))
    day_lock_tip = (
        "Locks your Windows workstation for the set duration after a Daily Floor Breach:\n"
        "• 0 = Locks Windows one single time.\n"
        "• > 0 (e.g. 15) = Persistent lockout timer that re-locks Windows every few seconds\n"
        "  if you log back in before the timer finishes.\n"
        "• SAFETY GUARANTEE: The app ALWAYS confirms with the broker API that 100% of open\n"
        "  positions are closed (flat) before locking your computer — it will never lock you\n"
        "  out while a position is still open."
    )
    attach_tooltip(cb_lock_os, day_lock_tip)
    attach_tooltip(lbl_daily_lock_mins, day_lock_tip)
    attach_tooltip(ent_daily_lock_mins, day_lock_tip)

    # --- CARD 3: SESSION & SYSTEM SETTINGS (WITH EXPLICIT BASELINE LABEL) ---
    c3 = tk.Frame(
        left_col, bg="#1b1b1b", bd=1, relief="solid", padx=18, pady=12
    )
    c3.pack(fill="both", expand=True, pady=6)
    tk.Label(
        c3,
        text="3. SESSION & SYSTEM SETTINGS",
        font=("Arial", 11, "bold"),
        fg="#58d68d",
        bg="#1b1b1b",
        anchor="w"
    ).pack(fill="x")

    base_sub_lbl = tk.Label(
        c3,
        text="Checking active broker baseline...",
        font=("Arial", 9),
        fg="#aaaaaa",
        bg="#1b1b1b",
        anchor="w"
    )
    base_sub_lbl.pack(fill="x", pady=(2, 6))
    refresh_baseline_preview()
    attach_tooltip(
        base_sub_lbl,
        "Shows today's anchored starting account equity ($0.00 PnL reference point),\n"
        "remaining Schwab 7-day token lifetime, and today's completed Win/Loss trade count."
    )

    cb_reset925 = tk.Checkbutton(
        c3,
        text="Start Fresh at RTH Open (9:25 AM) — Don't Carry PM Peak into RTH",
        variable=var_reset925,
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#ffffff",
        anchor="w"
    )
    cb_reset925.pack(fill="x", pady=2)
    attach_tooltip(
        cb_reset925,
        "If checked, at 9:25 AM ET your RTH Rulebook starts fresh from current flat equity\n"
        "so a Pre-Market profit peak won't immediately trigger an RTH Tier ratchet/trailing stop\n"
        "on normal morning volatility. (Your SESSION HIGH column still preserves your full-day peak.)"
    )

    cb_reanchor = tk.Checkbutton(
        c3,
        text="Re-Zero Today's Starting Baseline to Current Equity (One-Time Reset)",
        variable=var_reanchor,
        font=("Arial", 10, "bold"),
        fg="#f5b041",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#f5b041",
        anchor="w"
    )
    cb_reanchor.pack(fill="x", pady=2)
    attach_tooltip(
        cb_reanchor,
        "One-Time Reset:\n"
        "Re-anchors today's starting baseline equity to your current account balance right now\n"
        "(resetting today's Realized PnL, Session High, and W/L counter to 0).\n"
        "Useful after a deposit/withdrawal or if starting a fresh afternoon session."
    )

    r_audio = tk.Frame(c3, bg="#1b1b1b")
    r_audio.pack(fill="x", pady=2)
    cb_voice = tk.Checkbutton(
        r_audio,
        text="Verbal Lockout Voice Cues",
        variable=var_voice_cues,
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#ffffff",
        anchor="w"
    )
    cb_voice.pack(side="left", padx=(0, 18))
    attach_tooltip(
        cb_voice,
        "Uses Windows Speech Synthesis to speak the lockout reason and duration out loud\n"
        "when a Penalty Box or Daily Lockout triggers (e.g. 'Open PnL stop triggered. Locked out\n"
        "for 2 minutes'), plus a '30 seconds remaining' heads-up before your screen unlocks."
    )

    cb_chime = tk.Checkbutton(
        r_audio,
        text="Upside Tier Chime & Glow",
        variable=var_upside_chime,
        font=("Arial", 10, "bold"),
        fg="#58d68d",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#58d68d",
        anchor="w"
    )
    cb_chime.pack(side="left")
    attach_tooltip(
        cb_chime,
        "When you close a winning trade (100% flat) that unlocks a higher profit ratchet tier\n"
        "(PM Profit Lock or RTH Tier 2 / 3 / 4), plays a pleasant 4-note ascending chime\n"
        "and glows the HUD status bar emerald green for 3 seconds."
    )

    r_test_audio = tk.Frame(c3, bg="#1b1b1b")
    r_test_audio.pack(fill="x", pady=(4, 2))
    lbl_preview_audio = tk.Label(
        r_test_audio,
        text="Preview Audio Cue:",
        font=("Arial", 9, "bold"),
        fg="#bbbbbb",
        bg="#1b1b1b",
        anchor="w"
    )
    lbl_preview_audio.pack(side="left", padx=(0, 8))

    audio_choices = [
        "Warning Siren (Short Preview)",
        "Upside Tier Chime",
        "Voice: Lockout Alert",
        "Voice: 30s Warning",
        "Unlock Chime (3-Tone)",
    ]
    audio_menu = tk.OptionMenu(r_test_audio, var_audio_test, *audio_choices)
    audio_menu.config(
        font=("Arial", 9, "bold"),
        bg="#2a2a2a",
        fg="white",
        activebackground="#1f538d",
        activeforeground="white",
        highlightthickness=0,
        bd=1,
        relief="solid",
        width=24
    )
    audio_menu["menu"].config(
        font=("Arial", 9, "bold"), bg="#2a2a2a", fg="white"
    )
    audio_menu.pack(side="left", padx=(0, 8))

    def play_selected_test_audio():
        choice = var_audio_test.get()
        if choice == "Warning Siren (Short Preview)":
            def _siren_sample():
                try:
                    for _ in range(4):
                        winsound.Beep(2600, 180)
                        time.sleep(0.04)
                except Exception:
                    pass
            threading.Thread(target=_siren_sample, daemon=True).start()
        elif choice == "Upside Tier Chime":
            play_upside_tier_chime()
        elif choice == "Voice: Lockout Alert":
            speak_async(
                "Open P and L stop triggered. Locked out for 2 minutes.",
                force=True
            )
        elif choice == "Voice: 30s Warning":
            speak_async("30 seconds remaining until unlock.", force=True)
        elif choice == "Unlock Chime (3-Tone)":
            threading.Thread(target=play_unlock_chimes, daemon=True).start()

    btn_test_audio = tk.Button(
        r_test_audio,
        text="🔊 Test",
        font=("Arial", 9, "bold"),
        bg="#2c3e50",
        fg="#aed6f1",
        padx=10,
        pady=2,
        command=play_selected_test_audio
    )
    btn_test_audio.pack(side="left")
    audio_test_tip = (
        "Select any sound or voice announcement from the dropdown and click '🔊 Test'\n"
        "to preview how it sounds at your current speaker/headset volume."
    )
    attach_tooltip(lbl_preview_audio, audio_test_tip)
    attach_tooltip(audio_menu, audio_test_tip)
    attach_tooltip(btn_test_audio, audio_test_tip)

    r_poll = tk.Frame(c3, bg="#1b1b1b")
    r_poll.pack(fill="x", pady=(4, 2))
    lbl_poll = tk.Label(
        r_poll,
        text="Broker API Poll Interval (Seconds):",
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b",
        anchor="w"
    )
    lbl_poll.pack(side="left")
    ent_poll = make_entry(r_poll, var_poll, width=8)
    ent_poll.pack(side="right")
    poll_tip = (
        "How often (in seconds) Enforcer polls your broker API for live equity and positions.\n"
        "Recommended: 2 seconds (30 requests/min — well within Schwab & Webull rate limits)."
    )
    attach_tooltip(lbl_poll, poll_tip)
    attach_tooltip(ent_poll, poll_tip)

    # ==========================================================
    # RIGHT COLUMN: 4. PRE-MARKET RULEBOOK, 5. RTH TIERED RISK
    # ==========================================================
    c4 = make_card(
        right_col,
        "4. PRE-MARKET RULEBOOK (Before 9:25 AM)",
        "Extended-hours warning sirens, max loss floor, "
        "and trailing profit lock. Uncheck any alarm/lock to disable it.",
        accent="#5dade2"
    )
    cb_pm_w1, ent_pm_w1, cb_pm_w2, ent_pm_w2 = make_dual_field_row(
        c4,
        "Warning Alarm 1 (-$):",
        dollar_vars["pm_warn_1"],
        "Warning Alarm 2 (-$):",
        dollar_vars["pm_warn_2"],
        cb_var1=var_pm_w1_on,
        cb_var2=var_pm_w2_on,
        tip1=(
            "Pre-Market Warning Alarm 1:\n"
            "Sounds a warning siren (no flatten) when Pre-Market Net PnL reaches this loss.\n"
            "Uncheck to disable Warning Alarm 1."
        ),
        tip2=(
            "Pre-Market Warning Alarm 2:\n"
            "Sounds a second warning siren when Pre-Market Net PnL reaches this deeper loss.\n"
            "Uncheck if you only want a single warning alarm before your Max Loss Floor."
        )
    )
    make_dual_field_row(
        c4,
        "PM Max Loss Floor (-$):",
        dollar_vars["pm_max_loss"],
        None,
        None,
        tip1=(
            "Pre-Market Hard Termination Floor:\n"
            "If Pre-Market Net PnL reaches this loss, triggers your Card 2 Daily Floor Breach Actions\n"
            "(Auto-Flatten Equities via Extended-Hours limit order, OS Lock, etc.)."
        )
    )
    tk.Frame(c4, bg="#2c2c2c", height=1).pack(fill="x", pady=7)
    cb_pm_lock, ent_pm_trig, lbl_pm_trail, ent_pm_trail = make_dual_field_row(
        c4,
        "Profit Lock Trigger (+$):",
        dollar_vars["pm_lock_trigger"],
        "Trail Peak By ($):",
        dollar_vars["pm_trail_cushion"],
        cb_var1=var_pm_lock_on,
        tip1=(
            "Pre-Market Trailing Profit Lock:\n"
            "Once your closed Pre-Market Realized PnL reaches +Profit Lock Trigger ($),\n"
            "activates a trailing floor behind your highest Pre-Market realized peak.\n"
            "Uncheck to disable Pre-Market profit trailing."
        ),
        tip2=(
            "Pre-Market Trailing Cushion ($):\n"
            "Once Profit Lock Trigger (+$) is reached, your Pre-Market floor trails behind\n"
            "your highest closed Realized PnL by this dollar amount.\n"
            "(Example: Trigger +$500 with $500 Trail locks your floor at $0.00 breakeven\n"
            "at +$500, and raises it to +$200 if you reach +$700.)"
        )
    )

    c5 = make_card(
        right_col,
        "5. REGULAR HOURS TIERED RISK (9:25 AM – 4:00 PM)",
        "Starts at Base Tier 1 and ratchets your floor upward "
        "as realized profit grows. Uncheck any alarm or tier to skip it.",
        accent="#5dade2",
        expand=True
    )

    tk.Label(
        c5,
        text="BASE TIER 1 — Starting Daily Leash",
        font=("Arial", 10, "bold"),
        fg="#aed6f1",
        bg="#1b1b1b",
        anchor="w"
    ).pack(fill="x", pady=(2, 4))

    cb_t1_w1, ent_t1_w1, cb_t1_w2, ent_t1_w2 = make_dual_field_row(
        c5,
        "Warning Alarm 1 (-$):",
        dollar_vars["t1_warn_1"],
        "Warning Alarm 2 (-$):",
        dollar_vars["t1_warn_2"],
        cb_var1=var_t1_w1_on,
        cb_var2=var_t1_w2_on,
        tip1=(
            "RTH Base Tier 1 — Warning Alarm 1:\n"
            "Sounds a warning siren (no flatten) when Net PnL reaches this loss.\n"
            "Uncheck to disable Warning Alarm 1."
        ),
        tip2=(
            "RTH Base Tier 1 — Warning Alarm 2:\n"
            "Sounds a second warning siren when Net PnL reaches this deeper loss.\n"
            "Uncheck if you only want 1 warning alarm before Hard Termination."
        )
    )
    make_dual_field_row(
        c5,
        "Hard Termination (-$):",
        dollar_vars["t1_max_loss"],
        None,
        None,
        tip1=(
            "RTH Base Tier 1 — Hard Daily Max Loss:\n"
            "Your starting worst-case daily loss floor before any profit tiers are unlocked.\n"
            "Breaching this floor triggers your Card 2 Daily Floor Breach Actions."
        )
    )

    tk.Frame(c5, bg="#2c2c2c", height=1).pack(fill="x", pady=8)

    tbl = tk.Frame(c5, bg="#1b1b1b")
    tbl.pack(fill="x")
    tbl.columnconfigure(0, weight=2)
    tbl.columnconfigure(1, weight=1)
    tbl.columnconfigure(2, weight=1)

    tk.Label(
        tbl,
        text="PROFIT RATCHET TIERS (Optional)",
        font=("Arial", 10, "bold"),
        fg="#aed6f1",
        bg="#1b1b1b",
        anchor="w"
    ).grid(row=0, column=0, sticky="w", pady=(0, 6))
    tk.Label(
        tbl,
        text="ACTIVATE AT (+$)",
        font=("Arial", 9, "bold"),
        fg="#aaaaaa",
        bg="#1b1b1b"
    ).grid(row=0, column=1, pady=(0, 6))
    tk.Label(
        tbl,
        text="NEW FLOOR / TRAIL",
        font=("Arial", 9, "bold"),
        fg="#aaaaaa",
        bg="#1b1b1b"
    ).grid(row=0, column=2, pady=(0, 6))

    tier_rows = [
        (
            "Tier 2 — Tighten Floor ($0 Siren)",
            var_t2_on,
            dollar_vars["t2_trigger"],
            "New Max Loss (-$):",
            dollar_vars["t2_max_loss"],
            (
                "RTH Tier 2 — Reduced Daily Loss Floor:\n"
                "Once your closed Realized PnL reaches 'Activate At (+$)', your daily max loss\n"
                "tightens to 'New Max Loss (-$)' (e.g. from -$1,500 up to -$1,000), and a warning\n"
                "siren sounds if your PnL pulls back to $0.00. Uncheck to skip Tier 2."
            )
        ),
        (
            "Tier 3 — Tighten Floor ($0 Siren)",
            var_t3_on,
            dollar_vars["t3_trigger"],
            "New Max Loss (-$):",
            dollar_vars["t3_max_loss"],
            (
                "RTH Tier 3 — Tighter Daily Loss / Breakeven Floor:\n"
                "Once your closed Realized PnL reaches 'Activate At (+$)', your daily max loss\n"
                "tightens further to 'New Max Loss (-$)' (set to 0 for a $0.00 breakeven floor),\n"
                "with a warning siren at $0.00. Uncheck to skip Tier 3."
            )
        ),
        (
            "Tier 4 — Trailing Profit Lock",
            var_t4_on,
            dollar_vars["t4_trigger"],
            "Trail Peak By ($):",
            dollar_vars["t4_trail"],
            (
                "RTH Tier 4 — Dynamic Trailing Profit Lock:\n"
                "Once your closed Realized PnL reaches 'Activate At (+$)', your termination floor\n"
                "locks in green and trails behind your highest realized PnL peak by 'Trail Peak By ($)'.\n"
                "(Example: Activate at +$1,000 with $500 Trail locks in +$500 minimum, and ratchets\n"
                "to +$900 if your closed Realized PnL reaches +$1,400.) Uncheck to disable Tier 4."
            )
        )
    ]

    tier_widget_refs = []
    for idx, (t_name, t_cb_var, trig_var, fl_lbl, fl_var, t_tip) in enumerate(
        tier_rows, start=1
    ):
        cb_t = tk.Checkbutton(
            tbl,
            text=t_name,
            variable=t_cb_var,
            font=("Arial", 10, "bold"),
            fg="#f2f2f2",
            bg="#1b1b1b",
            selectcolor="#2a2a2a",
            activebackground="#1b1b1b",
            activeforeground="#ffffff",
            anchor="w"
        )
        cb_t.grid(row=idx, column=0, sticky="w", pady=4)

        ent_trig = make_entry(tbl, trig_var, width=8)
        ent_trig.grid(row=idx, column=1, padx=8, pady=4)

        fl_cell = tk.Frame(tbl, bg="#1b1b1b")
        fl_cell.grid(row=idx, column=2, pady=4, sticky="e")
        lbl_fl = tk.Label(
            fl_cell,
            text=fl_lbl,
            font=("Arial", 9, "bold"),
            fg="#bbbbbb",
            bg="#1b1b1b"
        )
        lbl_fl.pack(side="left", padx=(0, 6))
        ent_fl = make_entry(fl_cell, fl_var, width=8)
        ent_fl.pack(side="right")

        attach_tooltip(cb_t, t_tip)
        attach_tooltip(ent_trig, t_tip)
        attach_tooltip(lbl_fl, t_tip)
        attach_tooltip(ent_fl, t_tip)
        tier_widget_refs.append((t_cb_var, cb_t, ent_trig, lbl_fl, ent_fl))

    # --- INTERACTIVE SMART DIMMING LOGIC ---
    def refresh_smart_dimming(*_):
        if var_open_flat.get():
            ent_open_loss.config(state="normal")
            lbl_open_loss.config(fg="#f2f2f2")
            cb_open_cd.config(state="normal")
            if var_open_cd.get():
                ent_cd_mins.config(state="normal")
                lbl_cd_mins.config(fg="#f2f2f2")
            else:
                ent_cd_mins.config(state="disabled")
                lbl_cd_mins.config(fg="#555555")
        else:
            ent_open_loss.config(state="disabled")
            lbl_open_loss.config(fg="#555555")
            cb_open_cd.config(state="disabled")
            ent_cd_mins.config(state="disabled")
            lbl_cd_mins.config(fg="#555555")

        if var_lock_os.get():
            ent_daily_lock_mins.config(state="normal")
            lbl_daily_lock_mins.config(fg="#f2f2f2")
        else:
            ent_daily_lock_mins.config(state="disabled")
            lbl_daily_lock_mins.config(fg="#555555")

        # Card 4: Pre-Market Warning Alarms & Profit Lock
        ent_pm_w1.config(state="normal" if var_pm_w1_on.get() else "disabled")
        cb_pm_w1.config(fg="#f2f2f2" if var_pm_w1_on.get() else "#666666")
        ent_pm_w2.config(state="normal" if var_pm_w2_on.get() else "disabled")
        cb_pm_w2.config(fg="#f2f2f2" if var_pm_w2_on.get() else "#666666")
        if var_pm_lock_on.get():
            cb_pm_lock.config(fg="#f2f2f2")
            ent_pm_trig.config(state="normal")
            lbl_pm_trail.config(fg="#f2f2f2")
            ent_pm_trail.config(state="normal")
        else:
            cb_pm_lock.config(fg="#666666")
            ent_pm_trig.config(state="disabled")
            lbl_pm_trail.config(fg="#555555")
            ent_pm_trail.config(state="disabled")

        # Card 5: RTH Tier 1 Warning Alarms & Profit Ratchet Tiers 2-4
        ent_t1_w1.config(state="normal" if var_t1_w1_on.get() else "disabled")
        cb_t1_w1.config(fg="#f2f2f2" if var_t1_w1_on.get() else "#666666")
        ent_t1_w2.config(state="normal" if var_t1_w2_on.get() else "disabled")
        cb_t1_w2.config(fg="#f2f2f2" if var_t1_w2_on.get() else "#666666")
        for t_cb_var, cb_t, ent_trig, lbl_fl, ent_fl in tier_widget_refs:
            if t_cb_var.get():
                cb_t.config(fg="#f2f2f2")
                ent_trig.config(state="normal")
                lbl_fl.config(fg="#bbbbbb")
                ent_fl.config(state="normal")
            else:
                cb_t.config(fg="#666666")
                ent_trig.config(state="disabled")
                lbl_fl.config(fg="#555555")
                ent_fl.config(state="disabled")

    for trace_var in (
        var_open_flat, var_open_cd, var_lock_os,
        var_pm_w1_on, var_pm_w2_on, var_pm_lock_on,
        var_t1_w1_on, var_t1_w2_on, var_t2_on, var_t3_on, var_t4_on
    ):
        trace_var.trace_add("write", refresh_smart_dimming)
    refresh_smart_dimming()

    # --- BOTTOM ACTION BAR ---
    btn_frame = tk.Frame(pf, bg="#121212", pady=12)
    btn_frame.pack(fill="x")

    btn_restore_def = tk.Button(
        btn_frame,
        text="Restore Defaults",
        font=("Arial", 10, "bold"),
        bg="#333333",
        fg="white",
        padx=16,
        pady=7,
        command=restore_factory_defaults
    )
    btn_restore_def.pack(side="left")
    attach_tooltip(
        btn_restore_def,
        "Resets all checkboxes, HUD columns, and dollar values on this screen\n"
        "back to your saved Default settings (or Factory Defaults if none saved yet)."
    )

    btn_save_def = tk.Button(
        btn_frame,
        text="Save as Default",
        font=("Arial", 10, "bold"),
        bg="#2c3e50",
        fg="#aed6f1",
        padx=16,
        pady=7,
        command=save_as_user_defaults
    )
    btn_save_def.pack(side="left", padx=(10, 14))
    attach_tooltip(
        btn_save_def,
        "Saves every setting and dollar threshold currently on this screen as your personal\n"
        "Default profile (used by 'Restore Defaults', 'Standard Full Risk', and '50% Low Energy')."
    )

    init_def_txt = (
        "Custom defaults saved ✓"
        if config.get("user_defaults")
        else "No custom default saved yet"
    )
    default_status_lbl = tk.Label(
        btn_frame,
        text=init_def_txt,
        font=("Arial", 9, "bold"),
        fg="#888888",
        bg="#121212",
        anchor="w"
    )
    default_status_lbl.pack(side="left")

    launch_txt = (
        "SAVE & LAUNCH ENFORCER >>"
        if parent is None else "SAVE & APPLY CHANGES >>"
    )
    tk.Button(
        btn_frame,
        text=launch_txt,
        font=("Arial", 10, "bold"),
        bg="#1e8449",
        fg="white",
        padx=24,
        pady=7,
        command=save_and_launch
    ).pack(side="right")

    if parent is None:
        pf.mainloop()
        return launched["status"]
    return True


# ==========================================
# 9. DYNAMIC MULTI-COLUMN HUD SETUP
# ==========================================
acct_badge_mode = 0  # 0 = FLAT, 1 = BASE, 2 = W/L
acct_badge_lbl = None
hud_root = None
hud_grid_frame = None
hud_ui_labels = []
hud_start_move_fn = None
hud_do_move_fn = None


def refresh_acct_badge():
    """Updates the clickable left account badge (FLAT -> BASE -> W/L)."""
    if acct_badge_lbl is None:
        return

    if acct_badge_mode == 1:
        val = start_equity
        txt = f"BASE: ${val:,.2f}" if (val is not None and val > 0) else "BASE: ---"
        fg_col = "#85929e"
    elif acct_badge_mode == 2:
        txt = format_trades_wl_inline(win_trades, loss_trades)
        fg_col = "#a6acaf"
    else:
        val = last_flat_equity if last_flat_equity is not None else start_equity
        txt = f"FLAT: ${val:,.2f}" if (val is not None and val > 0) else "FLAT: ---"
        fg_col = "#a6acaf"

    acct_badge_lbl.config(text=txt, fg=fg_col)


def toggle_acct_badge(event=None):
    global acct_badge_mode
    acct_badge_mode = (acct_badge_mode + 1) % 3
    refresh_acct_badge()


def rebuild_hud_columns():
    """Dynamically builds or rebuilds the HUD columns inside hud_grid_frame
    and adjusts the HUD window width while preserving screen position."""
    global hud_ui_labels
    if hud_grid_frame is None or hud_root is None:
        return

    for child in hud_grid_frame.winfo_children():
        child.destroy()

    for c_idx in range(12):
        hud_grid_frame.columnconfigure(c_idx, weight=0, uniform="")

    active_cols = get_active_hud_columns(config)
    hud_ui_labels.clear()

    for i, col_id in enumerate(active_cols):
        title = HUD_COL_HEADERS.get(col_id, col_id.upper())
        hud_grid_frame.columnconfigure(i, weight=1, uniform="col")

        col_frame = tk.Frame(hud_grid_frame, bg="#222222", bd=1, relief="solid")
        col_frame.grid(row=0, column=i, sticky="nsew", padx=1, pady=1)

        hdr_lbl = tk.Label(
            col_frame,
            text=title,
            font=("Arial", 8, "bold"),
            fg="#cccccc",
            bg="#1a1a1a",
            pady=3
        )
        hdr_lbl.pack(fill="x")

        val_font = (
            ("Arial", 9, "bold")
            if col_id == "trades_wl"
            else ("Arial", 12, "bold")
        )
        val_lbl = tk.Label(
            col_frame,
            text="---",
            font=val_font,
            fg="white",
            bg="#2c3e50",
            justify="center"
        )
        val_lbl.pack(fill="both", expand=True)

        if hud_start_move_fn and hud_do_move_fn:
            for widget in (col_frame, hdr_lbl, val_lbl):
                widget.bind("<Button-1>", hud_start_move_fn)
                widget.bind("<B1-Motion>", hud_do_move_fn)

        hud_ui_labels.append(val_lbl)

    w_px = max(800, len(active_cols) * 160)
    try:
        hud_root.update_idletasks()
        cur_x = hud_root.winfo_x()
        cur_y = hud_root.winfo_y()
        if cur_x <= 0 and cur_y <= 0:
            cur_x, cur_y = 50, 50
        hud_root.geometry(f"{w_px}x85+{cur_x}+{cur_y}")
    except Exception:
        hud_root.geometry(f"{w_px}x85+50+50")


def update_gui(ui_labels, col_data, is_flat, settings_btn, close_btn):
    for i, (text_val, bg_col) in enumerate(col_data):
        if i < len(ui_labels):
            ui_labels[i].config(text=text_val, bg=bg_col)

    refresh_acct_badge()

    if is_flat:
        settings_btn.config(
            text="⚙ SETTINGS", bg="#1f538d", fg="white", state="normal"
        )
        close_btn.config(
            text="✕", bg="#922b21", fg="white", state="normal"
        )
    else:
        settings_btn.config(
            text="🔒 IN TRADE", bg="#444444", fg="#888888", state="disabled"
        )
        close_btn.config(
            text="🔒", bg="#444444", fg="#888888", state="disabled"
        )

    if not settings_win_open and ui_labels:
        top = ui_labels[0].winfo_toplevel()
        top.attributes("-topmost", True)
        top.lift()


def start_gui():
    global acct_badge_lbl, hud_root, hud_grid_frame
    global hud_ui_labels, hud_start_move_fn, hud_do_move_fn
    root = tk.Tk()
    hud_root = root
    root.title("PnL Enforcer")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    w_init = max(800, len(get_active_hud_columns(config)) * 160)
    root.geometry(f"{w_init}x85+50+50")
    root.config(bg="#1a1a1a")

    def start_move(event):
        root.x = event.x_root - root.winfo_x()
        root.y = event.y_root - root.winfo_y()

    def do_move(event):
        x = event.x_root - root.x
        y = event.y_root - root.y
        root.geometry(f"+{x}+{y}")

    hud_start_move_fn = start_move
    hud_do_move_fn = do_move

    def close_app(event=None):
        global alarm_active, current_is_flat
        if not current_is_flat:
            log_event(
                "GUARDRAIL",
                "BLOCKED: Attempted to close HUD while in a position!"
            )
            return "break"
        alarm_active = False
        log_event("SESSION", "User closed Enforcer via HUD X button.")
        root.destroy()
        sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", close_app)
    root.bind("<Alt-F4>", close_app)

    grid_frame = tk.Frame(root, bg="#1a1a1a")
    grid_frame.pack(fill="both", expand=True)
    hud_grid_frame = grid_frame

    rebuild_hud_columns()
    ui_labels = hud_ui_labels

    bottom_bar = tk.Frame(root, bg="#1a1a1a")
    bottom_bar.pack(fill="x", side="bottom")

    # Muted clickable Left Badge (Toggles between FLAT and BASE)
    acct_badge_lbl = tk.Label(
        bottom_bar,
        text="FLAT: ---",
        font=("Arial", 8, "bold"),
        bg="#262626",
        fg="#a6acaf",
        padx=10,
        bd=1,
        relief="solid",
        cursor="hand2"
    )
    acct_badge_lbl.pack(side="left", fill="y", padx=(1, 1))
    acct_badge_lbl.bind("<Button-1>", toggle_acct_badge)
    refresh_acct_badge()

    mute_btn = tk.Button(
        bottom_bar,
        text=get_idle_button_text(),
        font=("Arial", 8, "bold"),
        bg="#333333",
        fg="white",
        state="disabled",
        command=lambda: mute_alarm(mute_btn)
    )
    mute_btn.pack(side="left", fill="x", expand=True)

    close_btn = tk.Button(
        bottom_bar,
        text="✕",
        font=("Arial", 8, "bold"),
        bg="#922b21",
        fg="white",
        padx=8,
        command=close_app
    )
    close_btn.pack(side="right")

    settings_btn = tk.Button(
        bottom_bar,
        text="⚙ SETTINGS",
        font=("Arial", 8, "bold"),
        bg="#1f538d",
        fg="white",
        padx=10,
        command=lambda: show_preflight_window(parent=root, mute_btn=mute_btn)
    )
    settings_btn.pack(side="right")

    threading.Thread(
        target=data_loop,
        args=(ui_labels, mute_btn, settings_btn, close_btn, root),
        daemon=True
    ).start()
    root.mainloop()


# ==========================================
# 10. ENTRY POINT & SAFE FALLBACK
# ==========================================
if __name__ == "__main__":
    init_daily_log()
    print("\n=========================================")
    print("      INITIALIZING PnL ENFORCER BETA     ")
    print("=========================================\n")
    try:
        if not show_liability_waiver():
            log_event("SESSION", "Liability waiver declined. Exiting.")
            sys.exit(0)

        load_config(log_restore=True)
        initial_broker = config.get("active_broker", "SCHWAB")
        active_adapter = connect_broker_adapter(initial_broker)

        # Safe fallback: if the active broker failed to connect and the other
        # broker already has saved credentials, switch to it automatically.
        if active_adapter is None:
            fallback_broker = (
                "SCHWAB" if initial_broker == "WEBULL" else "WEBULL"
            )
            fb_cfg = config.get("brokers", {}).get(fallback_broker, {})
            if fb_cfg.get("app_key") and fb_cfg.get("app_secret"):
                log_event(
                    "SESSION",
                    f"{initial_broker} connection failed. "
                    f"Falling back to configured broker {fallback_broker}..."
                )
                config["active_broker"] = fallback_broker
                save_config(config)
                active_adapter = connect_broker_adapter(fallback_broker)

        # Always open Pre-Flight even if active_adapter is None so the user
        # is never locked out of the Broker dropdown or API Keys button.
        if show_preflight_window():
            log_event("SESSION", "Launching 5-Column HUD.")
            start_gui()
        else:
            log_event("SESSION", "Pre-Flight closed without launching. Exiting.")
            sys.exit(0)
    except Exception as e:
        log_event("ERROR", f"Startup failed: {e}")