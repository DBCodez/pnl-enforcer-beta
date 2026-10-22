"""
PnL Enforcer (Closed Beta) — Dual-Broker Edition (Charles Schwab & Webull)
MIT License — Provided "AS IS" without warranty of any kind.
"""

import os
import sys
import re
import uuid
import json
import ctypes
import time
import builtins
import webbrowser
import threading
import tkinter as tk
from tkinter import messagebox
import winsound
import logging
import subprocess
from datetime import datetime, time as dt_time

logging.basicConfig(level=logging.INFO)

# ==========================================
# 1. DYNAMIC USER PATHS (NO HARDCODED KEYS)
# ==========================================
USER_HOME = os.path.expanduser("~")
SCHWAB_TOKEN_PATH = os.path.join(USER_HOME, "schwab_token.json")
CONFIG_PATH = os.path.join(USER_HOME, "enforcer_config.json")
LOG_PATH = os.path.join(USER_HOME, "enforcer_log.txt")
CALLBACK_URL = "https://127.0.0.1"

# ==========================================
# 2. DEFAULT CONFIGURATION
# ==========================================
DEFAULT_CONFIG = {
    "waiver_accepted": False,
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
    "enable_auto_flatten": False,
    "enable_kill_tos": False,
    "enable_kill_webull": False,
    "enable_lock_os": False,
    "daily_lock_mins": 15.0,
    "enable_open_flatten": False,
    "open_max_loss": 500.0,
    "enable_open_cooldown": False,
    "open_cooldown_mins": 1.0,
    "reset_at_925": True,
    "poll_interval": 2,
    "pm_warn_1": 500.0,
    "pm_warn_2": 1000.0,
    "pm_max_loss": 1500.0,
    "pm_lock_trigger": 500.0,
    "pm_trail_cushion": 500.0,
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
    "saved_account_id": ""
}

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
triggered_alarms = {}
ALARM_COOLDOWN_SEC = 180
RECOVERY_BUFFER_DOLLARS = 150.0

settings_win_open = False
log_lock = threading.Lock()
prev_pos_snapshot = {}
active_adapter = None


def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


def format_dollar(val):
    rounded = round(val, 2)
    if rounded > 0:
        return f"+${rounded:,.2f}"
    elif rounded < 0:
        return f"-${abs(rounded):,.2f}"
    return "$0.00"


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
        f"PM_Max=-${cfg.get('pm_max_loss', 0):,.0f} | "
        f"T1_Max=-${cfg.get('t1_max_loss', 0):,.0f}"
    )


def load_config():
    global config, start_equity, max_equity
    global daily_max_equity, last_flat_equity, has_reset_at_open
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                saved_brokers = saved.pop("brokers", {})
                config.update(saved)
                for b_name in ("SCHWAB", "WEBULL"):
                    if b_name in saved_brokers:
                        config["brokers"][b_name].update(saved_brokers[b_name])
        except Exception as e:
            print(f"Could not load saved config: {e}")

    active_b = config.get("active_broker", "SCHWAB")
    sel_acct = config["brokers"].get(active_b, {}).get("selected_account_id", "")
    saved_start = config.get("saved_start_equity")

    if (
        config.get("session_date") == get_today_str()
        and saved_start is not None
        and float(saved_start) > 0.0
        and config.get("saved_account_id") in ("", sel_acct)
        and start_equity is None
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
        log_event(
            "SESSION",
            f"Restored today's baseline from memory: "
            f"Start=${start_equity:,.2f} | "
            f"LastFlat=${last_flat_equity:,.2f} | "
            f"SessionHighPnL={format_dollar(daily_max_equity - start_equity)}"
        )


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
    active_b = config.get("active_broker", "SCHWAB")
    sel_acct = config["brokers"].get(active_b, {}).get("selected_account_id", "")
    changed = (
        config.get("session_date") != today_str
        or config.get("saved_start_equity") != start_equity
        or config.get("saved_max_equity") != max_equity
        or config.get("saved_daily_max_equity") != daily_max_equity
        or config.get("saved_last_flat_equity") != last_flat_equity
        or config.get("saved_has_reset_at_open") != has_reset_at_open
        or config.get("saved_account_id") != sel_acct
    )
    if changed:
        config["session_date"] = today_str
        config["saved_start_equity"] = start_equity
        config["saved_max_equity"] = max_equity
        config["saved_daily_max_equity"] = daily_max_equity
        config["saved_last_flat_equity"] = last_flat_equity
        config["saved_has_reset_at_open"] = has_reset_at_open
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


# ==========================================
# 4. DUAL-BROKER ADAPTER ENGINE (SCHWAB & WEBULL)
# ==========================================
class SchwabAdapter:
    name = "SCHWAB"

    def __init__(self, app_key, app_secret):
        self.app_key = app_key.strip()
        self.app_secret = app_secret.strip()
        self.client = None
        self.account_id = None
        self.accounts = []

    def authenticate(self):
        from schwab.auth import client_from_manual_flow, client_from_token_file
        try:
            if os.path.exists(SCHWAB_TOKEN_PATH):
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
        print("  SCHWAB OAUTH LOGIN — OPENING BROWSER FOR AUTHENTICATION")
        print("  After logging in, copy the FULL https://127.0.0.1/... URL")
        print("  from your browser address bar and paste it below!")
        print("=======================================================\n")

        opened = {"done": False}

        def try_open_url(text):
            if not opened["done"]:
                match = re.search(
                    r"(https://api\.schwabapi\.com/v1/oauth/authorize\S+)",
                    str(text)
                )
                if match:
                    opened["done"] = True
                    webbrowser.open(match.group(1))

        class BrowserLogHandler(logging.Handler):
            def emit(self, record):
                try_open_url(record.getMessage())

        handler = BrowserLogHandler()
        logging.getLogger().addHandler(handler)
        orig_print = builtins.print

        def hooked_print(*args, **kwargs):
            orig_print(*args, **kwargs)
            try_open_url(" ".join(str(a) for a in args))

        builtins.print = hooked_print
        try:
            self.client = client_from_manual_flow(
                self.app_key, self.app_secret, CALLBACK_URL, SCHWAB_TOKEN_PATH
            )
        finally:
            builtins.print = orig_print
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
                    log_event(
                        "ORDER_OUT",
                        f"Submitting EXT GTC_EXT Limit Sell: {int(qty)} {symbol} "
                        f"@ ${lim_price} (Live Bid: ${bid})"
                    )
                    spec = (
                        equity_sell_limit(symbol, int(qty), lim_price)
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
                    log_event(
                        "ORDER_OUT",
                        f"Submitting EXT GTC_EXT Limit Cover: {abs_q} {symbol} "
                        f"@ ${lim_price} (Live Ask: ${ask})"
                    )
                    spec = (
                        equity_buy_to_cover_limit(symbol, abs_q, lim_price)
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
                        live_price = (
                            quote_info.get("lastPrice")
                            or quote_info.get("mark")
                            or quote_info.get("bidPrice")
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
                log_event(
                    "ERROR", f"Schwab get_account returned HTTP {resp.status_code}"
                )
        except Exception as e:
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
        self._logged_balance_keys = False

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
                log_event(
                    "ORDER_OUT",
                    f"Submitting Webull EXT Limit {side}: {abs_q} {symbol} "
                    f"@ ${lim_price} (Ref Last: ${ref_lp})"
                )
                order_item = {
                    "client_order_id": client_oid,
                    "symbol": symbol,
                    "instrument_type": "EQUITY",
                    "market": "US",
                    "order_type": "LIMIT",
                    "limit_price": str(lim_price),
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
            if not self._logged_balance_keys:
                self._logged_balance_keys = True
                log_event(
                    "SESSION",
                    f"Webull Balance Parsed -> TotalAccountValue=${raw_eq:,.2f} "
                    f"(Cash=${cash_bal if cash_bal is not None else 0.0:,.2f})"
                )

            p_res = self._call_get_positions()
            if p_res.status_code != 200:
                return raw_eq, True, 0.0, {}, False

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
                lp = float(
                    p.get("last_price")
                    or p.get("market_price")
                    or avg_price
                )

                pos_mkt_val = float(
                    p.get("market_value") or (qty * lp * mult)
                )
                total_pos_mkt_val += pos_mkt_val

                if "unrealized_profit_loss" in p and p.get(
                    "unrealized_profit_loss"
                ) is not None:
                    pos_open_pnl = float(p["unrealized_profit_loss"])
                else:
                    pos_open_pnl = (
                        (lp - avg_price) * qty * mult
                        if avg_price > 0 else 0.0
                    )

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

            # Reconcile total equity with live positions so 1-poll lag
            # between balance & position endpoints never spikes Realized PnL
            if cash_bal is not None and cash_bal > 0:
                adj_eq = round(cash_bal + total_pos_mkt_val, 2)
            else:
                adj_eq = round(raw_eq, 2)

            return (
                adj_eq,
                is_flat,
                round(total_open_pnl, 2),
                pos_details,
                has_options
            )
        except Exception as e:
            log_event("ERROR", f"Webull account fetch exception: {e}")
            return None, True, 0.0, {}, False


def c_resp_code(res):
    return getattr(res, "status_code", "OK")


# ==========================================
# 5. FIRST-TIME WAIVER & BROKER SETUP WIZARD
# ==========================================
def show_liability_waiver():
    load_config()
    if config.get("waiver_accepted", False):
        return True

    accepted = {"ok": False}
    w = tk.Tk()
    w.title("PnL Enforcer Beta — Legal Disclaimer & Assumption of Risk")
    w.config(bg="#141414", padx=28, pady=22)
    w.resizable(False, False)
    w.attributes("-topmost", True)

    tk.Label(
        w,
        text="⚠️ EXPERIMENTAL BETA SOFTWARE — ASSUMPTION OF RISK",
        font=("Arial", 12, "bold"),
        fg="#f5b041",
        bg="#141414",
        anchor="w"
    ).pack(fill="x", pady=(0, 12))

    waiver_text = (
        "1. NO WARRANTY OR FINANCIAL LIABILITY:\n"
        "   This software is an experimental beta tool provided 'AS IS' without warranty of any kind.\n"
        "   The authors and contributors are NOT liable for any trading losses, slippage, missed fills,\n"
        "   API outages, rate limits, or unexpected software behavior.\n\n"
        "2. EQUITIES vs. OPTIONS BEHAVIOR:\n"
        "   • Equities (Stocks) are tracked for HUD display, Alarms, AND automated Market/Limit flatten orders.\n"
        "   • Options contracts are tracked for HUD PnL display and Warning Sirens ONLY. Because option\n"
        "     bid-ask spreads can widen dramatically, this software will NEVER auto-flatten option contracts.\n"
        "     If a guardrail breaches while holding options, you must manually flatten your options.\n\n"
        "3. SAFE TESTING RECOMMENDATION:\n"
        "   Always test first in Observation Mode (all enforcement checkboxes unchecked) or with 1 share\n"
        "   to verify your API connection and PnL calculations before trading live size."
    )

    msg_box = tk.Label(
        w,
        text=waiver_text,
        font=("Arial", 10),
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
        text="I have read this disclaimer, understand the risks, and assume 100% sole responsibility for my account.",
        variable=var_agree,
        font=("Arial", 10, "bold"),
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
        config["waiver_accepted"] = True
        save_config(config)
        log_event("SESSION", "User accepted Beta Liability Waiver.")
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
            "   address bar and paste it into the black console window."
        )
        portal_url = "https://developer.schwab.com"
    else:
        guide_txt = (
            "HOW TO GET YOUR WEBULL OPENAPI KEYS (One-Time Setup):\n"
            "1. Go to https://developer.webull.com (or Webull Web -> Account Management -> OpenAPI).\n"
            "2. Apply for a Retail Trading API Key (often approved within minutes).\n"
            "3. Generate your App Key and App Secret in the Webull portal and paste them below.\n"
            "4. ⚠️ IMPORTANT MOBILE 2FA STEP: On your first connection attempt, check your\n"
            "   Webull Mobile App / SMS! Webull will push a notification asking you to enter\n"
            "   a texted 2FA verification code to authorize OpenAPI access for your keys."
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
    guide_lbl.pack(fill="x", pady=(0, 12))

    tk.Button(
        wiz,
        text=f"Open {portal_url} in Browser",
        font=("Arial", 9, "bold"),
        bg="#1f538d",
        fg="white",
        padx=12,
        pady=4,
        command=lambda: webbrowser.open(portal_url)
    ).pack(anchor="w", pady=(0, 14))

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

    def save_keys():
        k = var_key.get().strip()
        s = var_sec.get().strip()
        if not k or not s:
            messagebox.showwarning(
                "Missing Credentials",
                f"Please paste both your {broker_name} App Key and App Secret.",
                parent=wiz
            )
            return
        config["brokers"][broker_name]["app_key"] = k
        config["brokers"][broker_name]["app_secret"] = s
        config["active_broker"] = broker_name
        save_config(config)
        saved_ok["status"] = True
        wiz.destroy()

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
        command=save_keys
    ).pack(side="right")

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
            "1. Check your Webull mobile app / SMS! Webull sends a 2FA code prompt "
            "the first time your API keys are used.\n"
            "2. Once you approve the 2FA code in your Webull app, click 'No' below "
            "and relaunch, or click 'Yes' to verify your keys."
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
        return f"[{b_name}] ALARMS CLEAR  |  MODE: ALARM ONLY (OBSERVATION)"
    return "ALARMS CLEAR  |  ARMED: " + " + ".join(active_modes)


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


def start_cooldown_lock(duration_mins, ui_button, label_prefix="COOL-DOWN LOCK"):
    global cooldown_active, alarm_active
    if cooldown_active:
        return

    duration_sec = max(5, int(round(float(duration_mins) * 60)))
    cooldown_active = True
    alarm_active = False

    def cooldown_worker():
        global cooldown_active, alarm_active
        end_time = time.time() + duration_sec
        log_event(
            "COOLDOWN",
            f"Persistent {label_prefix} started for {duration_sec}s "
            f"({duration_mins:g} min). Siren muted."
        )
        while time.time() < end_time:
            alarm_active = False
            rem = int(round(end_time - time.time()))
            txt = (
                f"{label_prefix} ACTIVE: {rem}s REMAINING "
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
            f"{label_prefix} timer expired. Workstation unlocked."
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
    global prev_pos_snapshot
    curr_qty_map = {s: d["qty"] for s, d in pos_details.items()}
    prev_qty_map = {s: d["qty"] for s, d in prev_pos_snapshot.items()}

    if curr_qty_map == prev_qty_map:
        return

    all_syms = sorted(set(curr_qty_map.keys()) | set(prev_qty_map.keys()))
    changes = []
    for sym in all_syms:
        old_q = prev_qty_map.get(sym, 0)
        new_q = curr_qty_map.get(sym, 0)
        if old_q != new_q:
            if new_q != 0:
                info = pos_details[sym]
                changes.append(
                    f"{sym}: {old_q:+d} -> {new_q:+d} "
                    f"(Avg: ${info['avg']:.4f}, Last: ${info['last']:.4f})"
                )
            else:
                changes.append(f"{sym}: {old_q:+d} -> 0 (CLOSED FLAT)")

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

    while True:
        poll_sec = max(1, int(config.get("poll_interval", 2)))
        try:
            if active_adapter is None:
                time.sleep(poll_sec)
                continue

            current_eq, is_flat, live_open_pnl, pos_details, has_options = (
                active_adapter.fetch_account_data()
            )

            if current_eq is not None and current_eq > 0:
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

                log_position_transitions(
                    pos_details,
                    realized_pnl,
                    open_pnl,
                    net_pnl,
                    session_high_pnl
                )

                open_flat_on = config.get("enable_open_flatten", False)
                open_max = config.get("open_max_loss", 500.0)

                pm_w1 = config["pm_warn_1"]
                pm_w2 = config["pm_warn_2"]
                pm_max = config["pm_max_loss"]
                pm_trig = config["pm_lock_trigger"]
                pm_trail = config["pm_trail_cushion"]

                t1_w1 = config["t1_warn_1"]
                t1_w2 = config["t1_warn_2"]
                t1_max = config["t1_max_loss"]
                t2_trig = config["t2_trigger"]
                t2_max = config["t2_max_loss"]
                t3_trig = config["t3_trigger"]
                t3_max = config["t3_max_loss"]
                t4_trig = config["t4_trigger"]
                t4_trail = config["t4_trail"]

                # Prevent immediate siren blast on startup when resuming a
                # session while flat and already sitting below a warning level
                if first_poll_of_launch and is_flat:
                    first_poll_of_launch = False
                    if net_pnl <= -pm_w1:
                        triggered_alarms[f"Pre-market -${pm_w1:,.0f} Warn 1"] = time.time()
                    if net_pnl <= -pm_w2:
                        triggered_alarms[f"Pre-market -${pm_w2:,.0f} Warn 2"] = time.time()
                    if current_eq <= start_equity:
                        triggered_alarms["Hit $0 (Tier 2)"] = time.time()
                        triggered_alarms["Hit $0 (Tier 3)"] = time.time()
                    if current_eq <= (start_equity - t1_w1):
                        triggered_alarms[f"Hit -${t1_w1:,.0f} (Tier 1)"] = time.time()
                    if current_eq <= (start_equity - t1_w2):
                        triggered_alarms[f"Hit -${t1_w2:,.0f} (Tier 1)"] = time.time()
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
                    check_alarm_rearm(r_pm_w2, net_pnl, -pm_w2)
                    check_alarm_rearm(r_pm_w1, net_pnl, -pm_w1)

                    if max_realized_profit >= pm_trig:
                        floor_equity = max_equity - pm_trail
                        check_alarm_rearm(
                            r_pm_tr, current_eq, floor_equity
                        )
                    else:
                        floor_equity = start_equity - pm_max

                    if (
                        not is_locked_down
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
                        if net_pnl <= -pm_w2:
                            triggered_alarms.setdefault(r_pm_w2, time.time())
                        if net_pnl <= -pm_w1:
                            triggered_alarms.setdefault(r_pm_w1, time.time())
                        r_open = f"Open PnL -${open_max:,.0f} Stop"
                        trigger_open_pnl_flatten(
                            active_adapter, r_open, mute_btn, has_options, ctx
                        )
                    elif net_pnl <= -pm_w2:
                        triggered_alarms.setdefault(r_pm_w1, time.time())
                        trigger_alarm(r_pm_w2, mute_btn, ctx)
                    elif net_pnl <= -pm_w1:
                        trigger_alarm(r_pm_w1, mute_btn, ctx)

                else:
                    if max_realized_profit >= t4_trig:
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

                    elif max_realized_profit >= t3_trig:
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

                    elif max_realized_profit >= t2_trig:
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

                        check_alarm_rearm(
                            r_t1_w2, current_eq, start_equity - t1_w2
                        )
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
                            if current_eq <= (start_equity - t1_w2):
                                triggered_alarms.setdefault(
                                    r_t1_w2, time.time()
                                )
                            if current_eq <= (start_equity - t1_w1):
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
                        elif current_eq <= (start_equity - t1_w2):
                            triggered_alarms.setdefault(
                                r_t1_w1, time.time()
                            )
                            trigger_alarm(r_t1_w2, mute_btn, ctx)
                        elif current_eq <= (start_equity - t1_w1):
                            trigger_alarm(r_t1_w1, mute_btn, ctx)

                terminate_pnl_level = round(floor_equity - start_equity, 2)
                distance_to_terminate = round(current_eq - floor_equity, 2)

                c1_bg = (
                    "#1e8449" if realized_pnl > 0
                    else ("#b03a2e" if realized_pnl < 0 else "#2c3e50")
                )
                c2_bg = (
                    "#1e8449" if open_pnl > 0
                    else ("#b03a2e" if open_pnl < 0 else "#2c3e50")
                )
                c3_bg = "#1e8449" if terminate_pnl_level > 0 else "#1f538d"
                c4_bg = (
                    "#b03a2e" if distance_to_terminate <= 0
                    else ("#d35400" if distance_to_terminate <= 500 else "#2c3e50")
                )
                c5_bg = "#1e8449" if session_high_pnl > 0 else "#2c3e50"

                col_data = [
                    (format_dollar(realized_pnl), c1_bg),
                    (format_dollar(open_pnl), c2_bg),
                    (format_dollar(terminate_pnl_level), c3_bg),
                    (f"${distance_to_terminate:,.2f}", c4_bg),
                    (format_dollar(session_high_pnl), c5_bg)
                ]

                root.after(
                    0,
                    lambda d=col_data, f=is_flat: update_gui(
                        ui_labels, d, f, settings_btn, close_btn
                    )
                )

        except Exception as e:
            log_event("ERROR", f"Main data_loop error: {e}")

        time.sleep(poll_sec)


# ==========================================
# 8. SPACIOUS WIDESCREEN PRE-FLIGHT WINDOW
# ==========================================
def show_preflight_window(parent=None, mute_btn=None):
    global settings_win_open, triggered_alarms
    global force_reanchor, is_locked_down, current_is_flat, active_adapter

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
        global settings_win_open
        settings_win_open = False
        pf.destroy()

    pf.protocol("WM_DELETE_WINDOW", on_close)

    # --- STATE VARIABLES ---
    var_broker = tk.StringVar(value=config.get("active_broker", "SCHWAB"))
    var_account_label = tk.StringVar(value="")
    account_label_to_id = {}

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
    var_poll = tk.StringVar(value=str(int(config["poll_interval"])))

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
        width=22
    )
    acct_menu["menu"].config(
        font=("Arial", 10, "bold"), bg="#2a2a2a", fg="white"
    )
    acct_menu.pack(side="left", padx=(0, 8))

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
                    command=lambda v=lbl: var_account_label.set(v)
                )
                if aid == active_adapter.account_id:
                    selected_lbl = lbl
            var_account_label.set(selected_lbl)
        else:
            var_account_label.set("No Account Connected")

    def on_broker_change(*_):
        global active_adapter, force_reanchor
        chosen = var_broker.get()
        if active_adapter is None or active_adapter.name != chosen:
            new_ad = connect_broker_adapter(chosen, parent=pf, force_wizard=False)
            if new_ad is not None:
                active_adapter = new_ad
                config["active_broker"] = chosen
                force_reanchor = True
                populate_account_dropdown()
            else:
                if active_adapter is not None:
                    var_broker.set(active_adapter.name)

    def edit_api_keys():
        global active_adapter
        chosen = var_broker.get()
        new_ad = connect_broker_adapter(chosen, parent=pf, force_wizard=True)
        if new_ad is not None:
            active_adapter = new_ad
            populate_account_dropdown()

    tk.Button(
        top_bar,
        text="🔑 API Keys",
        font=("Arial", 9, "bold"),
        bg="#333333",
        fg="white",
        padx=10,
        pady=3,
        command=edit_api_keys
    ).pack(side="left", padx=(0, 18))

    populate_account_dropdown()
    var_broker.trace_add("write", on_broker_change)

    def apply_dollar_preset(preset_dict):
        for k, val in preset_dict.items():
            if k in dollar_vars:
                dollar_vars[k].set(f"{val:.0f}")

    tk.Button(
        top_bar,
        text="50% Low Energy",
        font=("Arial", 9, "bold"),
        bg="#7d6608",
        fg="white",
        padx=10,
        pady=3,
        command=lambda: apply_dollar_preset(HALF_RISK_DOLLARS)
    ).pack(side="right", padx=4)

    tk.Button(
        top_bar,
        text="Standard Full Risk",
        font=("Arial", 9, "bold"),
        bg="#1f538d",
        fg="white",
        padx=10,
        pady=3,
        command=lambda: apply_dollar_preset(DEFAULT_CONFIG)
    ).pack(side="right", padx=4)

    tk.Label(
        top_bar,
        text="PRESETS:",
        font=("Arial", 9, "bold"),
        fg="#dddddd",
        bg="#1c1c1c"
    ).pack(side="right", padx=(8, 4))

    def restore_factory_defaults():
        var_open_flat.set(DEFAULT_CONFIG["enable_open_flatten"])
        var_open_cd.set(DEFAULT_CONFIG["enable_open_cooldown"])
        var_cd_mins.set(f"{DEFAULT_CONFIG['open_cooldown_mins']:g}")
        var_flatten.set(DEFAULT_CONFIG["enable_auto_flatten"])
        var_kill_tos.set(DEFAULT_CONFIG["enable_kill_tos"])
        var_kill_wb.set(DEFAULT_CONFIG["enable_kill_webull"])
        var_lock_os.set(DEFAULT_CONFIG["enable_lock_os"])
        var_daily_lock_mins.set(f"{DEFAULT_CONFIG['daily_lock_mins']:g}")
        var_reset925.set(DEFAULT_CONFIG["reset_at_925"])
        var_reanchor.set(False)
        var_poll.set(str(int(DEFAULT_CONFIG["poll_interval"])))
        apply_dollar_preset(DEFAULT_CONFIG)
        refresh_smart_dimming()

    def save_and_launch():
        global settings_win_open, triggered_alarms
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
            prev_id = new_cfg["brokers"][chosen_b].get(
                "selected_account_id", ""
            )
            if chosen_id and chosen_id != prev_id:
                active_adapter.account_id = chosen_id
                new_cfg["brokers"][chosen_b]["selected_account_id"] = chosen_id
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
            new_cfg["poll_interval"] = max(1, int(float(var_poll.get())))

            for k in dollar_keys:
                new_cfg[k] = abs(float(dollar_vars[k].get()))

            is_locked_down = False

            if var_reanchor.get():
                force_reanchor = True
                triggered_alarms.clear()
                new_cfg["saved_start_equity"] = None
                new_cfg["saved_daily_max_equity"] = None
                log_event("CONFIG", "User checked Force Re-Anchor Baseline.")

            save_config(new_cfg)
            log_event("CONFIG", format_config_summary(new_cfg))

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

    def make_dual_field_row(parent_w, lbl1, var1, lbl2=None, var2=None):
        row = tk.Frame(parent_w, bg="#1b1b1b")
        row.pack(fill="x", pady=4)
        row.columnconfigure(0, weight=1)
        row.columnconfigure(2, weight=1)

        tk.Label(
            row,
            text=lbl1,
            font=("Arial", 10, "bold"),
            fg="#f2f2f2",
            bg="#1b1b1b",
            anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        e1 = make_entry(row, var1, width=8)
        e1.grid(row=0, column=1, padx=(0, 24))

        if lbl2 and var2 is not None:
            tk.Label(
                row,
                text=lbl2,
                font=("Arial", 10, "bold"),
                fg="#f2f2f2",
                bg="#1b1b1b",
                anchor="w"
            ).grid(row=0, column=2, sticky="w", padx=(0, 8))
            e2 = make_entry(row, var2, width=8)
            e2.grid(row=0, column=3)

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

    # --- CARD 2: DAILY FLOOR BREACH ACTIONS (END-OF-DAY) ---
    c2 = make_card(
        left_col,
        "2. DAILY FLOOR BREACH ACTIONS (End-of-Day)",
        "Fires ONLY when total Net PnL breaches your Pre-Market "
        "or RTH Termination Floor.",
        accent="#f5b041"
    )

    tk.Checkbutton(
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
    ).pack(fill="x", pady=3)

    r_kill = tk.Frame(c2, bg="#1b1b1b")
    r_kill.pack(fill="x", pady=3)
    tk.Label(
        r_kill,
        text="Kill Apps (When Flat):",
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b"
    ).pack(side="left", padx=(0, 10))
    tk.Checkbutton(
        r_kill,
        text="Thinkorswim",
        variable=var_kill_tos,
        font=("Arial", 10, "bold"),
        fg="#eb7067",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#eb7067"
    ).pack(side="left", padx=(0, 12))
    tk.Checkbutton(
        r_kill,
        text="Webull Desktop",
        variable=var_kill_wb,
        font=("Arial", 10, "bold"),
        fg="#eb7067",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#eb7067"
    ).pack(side="left")

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
        text="Lock Mins (0 = 1x):",
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b"
    )
    lbl_daily_lock_mins.pack(side="right", padx=(16, 8))

    # --- CARD 3: SESSION & SYSTEM SETTINGS ---
    if start_equity is not None and start_equity > 0:
        base_sub = f"Active Baseline: ${start_equity:,.2f} (Preserved across restarts)"
    else:
        base_sub = "Baseline will anchor automatically on first API poll."

    c3 = make_card(
        left_col,
        "3. SESSION & SYSTEM SETTINGS",
        base_sub,
        accent="#58d68d",
        expand=True
    )

    tk.Checkbutton(
        c3,
        text="Reset Rulebook High-Water Mark at 9:25 AM Open",
        variable=var_reset925,
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#ffffff",
        anchor="w"
    ).pack(fill="x", pady=3)

    tk.Checkbutton(
        c3,
        text="Force Re-Anchor Baseline to Current Cash (One-Time Zero)",
        variable=var_reanchor,
        font=("Arial", 10, "bold"),
        fg="#f5b041",
        bg="#1b1b1b",
        selectcolor="#2a2a2a",
        activebackground="#1b1b1b",
        activeforeground="#f5b041",
        anchor="w"
    ).pack(fill="x", pady=3)

    r_poll = tk.Frame(c3, bg="#1b1b1b")
    r_poll.pack(fill="x", pady=(6, 2))
    tk.Label(
        r_poll,
        text="Broker API Poll Interval (Seconds):",
        font=("Arial", 10, "bold"),
        fg="#f2f2f2",
        bg="#1b1b1b",
        anchor="w"
    ).pack(side="left")
    make_entry(r_poll, var_poll, width=8).pack(side="right")

    # ==========================================================
    # RIGHT COLUMN: 4. PRE-MARKET RULEBOOK, 5. RTH TIERED RISK
    # ==========================================================
    c4 = make_card(
        right_col,
        "4. PRE-MARKET RULEBOOK (Before 9:25 AM)",
        "Extended-hours warning sirens, max loss floor, "
        "and trailing profit lock.",
        accent="#5dade2"
    )
    make_dual_field_row(
        c4,
        "Warning Alarm 1 (-$):",
        dollar_vars["pm_warn_1"],
        "Warning Alarm 2 (-$):",
        dollar_vars["pm_warn_2"]
    )
    make_dual_field_row(
        c4,
        "PM Max Loss Floor (-$):",
        dollar_vars["pm_max_loss"],
        None,
        None
    )
    tk.Frame(c4, bg="#2c2c2c", height=1).pack(fill="x", pady=7)
    make_dual_field_row(
        c4,
        "Profit Lock Trigger (+$):",
        dollar_vars["pm_lock_trigger"],
        "Trailing Cushion ($):",
        dollar_vars["pm_trail_cushion"]
    )

    c5 = make_card(
        right_col,
        "5. REGULAR HOURS TIERED RISK (9:25 AM – 4:00 PM)",
        "Starts at Base Tier 1 and ratchets your floor upward "
        "as realized profit grows.",
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

    make_dual_field_row(
        c5,
        "Warning Alarm 1 (-$):",
        dollar_vars["t1_warn_1"],
        "Warning Alarm 2 (-$):",
        dollar_vars["t1_warn_2"]
    )
    make_dual_field_row(
        c5,
        "Hard Termination (-$):",
        dollar_vars["t1_max_loss"],
        None,
        None
    )

    tk.Frame(c5, bg="#2c2c2c", height=1).pack(fill="x", pady=8)

    tbl = tk.Frame(c5, bg="#1b1b1b")
    tbl.pack(fill="x")
    tbl.columnconfigure(0, weight=2)
    tbl.columnconfigure(1, weight=1)
    tbl.columnconfigure(2, weight=1)

    tk.Label(
        tbl,
        text="PROFIT RATCHET TIERS",
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
            "Tier 2 — Small Cushion ($0 Alarm)",
            dollar_vars["t2_trigger"],
            "-$ Max Loss:",
            dollar_vars["t2_max_loss"]
        ),
        (
            "Tier 3 — Solid Cushion ($0 Alarm)",
            dollar_vars["t3_trigger"],
            "-$ Max Loss:",
            dollar_vars["t3_max_loss"]
        ),
        (
            "Tier 4 — Home Run Trailing Lock",
            dollar_vars["t4_trigger"],
            "$ Trail Peak:",
            dollar_vars["t4_trail"]
        )
    ]

    for idx, (t_name, trig_var, fl_lbl, fl_var) in enumerate(
        tier_rows, start=1
    ):
        tk.Label(
            tbl,
            text=t_name,
            font=("Arial", 10, "bold"),
            fg="#f2f2f2",
            bg="#1b1b1b",
            anchor="w"
        ).grid(row=idx, column=0, sticky="w", pady=4)

        make_entry(tbl, trig_var, width=8).grid(
            row=idx, column=1, padx=8, pady=4
        )

        fl_cell = tk.Frame(tbl, bg="#1b1b1b")
        fl_cell.grid(row=idx, column=2, pady=4, sticky="e")
        tk.Label(
            fl_cell,
            text=fl_lbl,
            font=("Arial", 9, "bold"),
            fg="#bbbbbb",
            bg="#1b1b1b"
        ).pack(side="left", padx=(0, 6))
        make_entry(fl_cell, fl_var, width=8).pack(side="right")

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

    var_open_flat.trace_add("write", refresh_smart_dimming)
    var_open_cd.trace_add("write", refresh_smart_dimming)
    var_lock_os.trace_add("write", refresh_smart_dimming)
    refresh_smart_dimming()

    # --- BOTTOM ACTION BAR ---
    btn_frame = tk.Frame(pf, bg="#121212", pady=12)
    btn_frame.pack(fill="x")

    tk.Button(
        btn_frame,
        text="Restore Defaults",
        font=("Arial", 10, "bold"),
        bg="#333333",
        fg="white",
        padx=16,
        pady=7,
        command=restore_factory_defaults
    ).pack(side="left")

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
# 9. 5-COLUMN HUD SETUP
# ==========================================
def update_gui(ui_labels, col_data, is_flat, settings_btn, close_btn):
    for i, (text_val, bg_col) in enumerate(col_data):
        ui_labels[i].config(text=text_val, bg=bg_col)

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
    root = tk.Tk()
    root.title("PnL Enforcer")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.geometry("800x85+50+50")
    root.config(bg="#1a1a1a")

    def start_move(event):
        root.x = event.x_root - root.winfo_x()
        root.y = event.y_root - root.winfo_y()

    def do_move(event):
        x = event.x_root - root.x
        y = event.y_root - root.y
        root.geometry(f"+{x}+{y}")

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

    headers = [
        "REALIZED PnL",
        "OPEN PnL",
        "TERMINATE LVL",
        "$ TO TERMINATE",
        "SESSION HIGH"
    ]

    ui_labels = []
    for i, title in enumerate(headers):
        grid_frame.columnconfigure(i, weight=1, uniform="col")

        col_frame = tk.Frame(grid_frame, bg="#222222", bd=1, relief="solid")
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

        val_lbl = tk.Label(
            col_frame,
            text="---",
            font=("Arial", 12, "bold"),
            fg="white",
            bg="#2c3e50"
        )
        val_lbl.pack(fill="both", expand=True)

        for widget in (col_frame, hdr_lbl, val_lbl):
            widget.bind("<Button-1>", start_move)
            widget.bind("<B1-Motion>", do_move)

        ui_labels.append(val_lbl)

    bottom_bar = tk.Frame(root, bg="#1a1a1a")
    bottom_bar.pack(fill="x", side="bottom")

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
# 10. ENTRY POINT
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

        load_config()
        initial_broker = config.get("active_broker", "SCHWAB")
        active_adapter = connect_broker_adapter(initial_broker)
        if active_adapter is None:
            log_event("SESSION", "Broker setup canceled. Exiting.")
            sys.exit(0)

        if show_preflight_window():
            log_event("SESSION", "Launching 5-Column HUD.")
            start_gui()
        else:
            log_event("SESSION", "Pre-Flight closed without launching. Exiting.")
            sys.exit(0)
    except Exception as e:
        log_event("ERROR", f"Startup failed: {e}")