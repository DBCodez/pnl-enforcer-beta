"""
PnL Enforcer (Closed Beta) — Dual-Broker Edition (Charles Schwab & Webull)
MIT License & Trading Risk Disclaimer — Provided "AS IS" without warranty of any kind.
Not financial advice; no guarantee of loss prevention; not affiliated with Schwab or Webull.
See LICENSE.txt for full terms, limitation of liability, and indemnification.
"""

APP_VERSION = "0.9.46"

import os
import sys
import re
import math
import zlib
import struct
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
import traceback
import warnings
import subprocess
from datetime import datetime, time as dt_time, timedelta, timezone

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
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(SCRIPT_DIR, "enforcer.ico")
# Keep working directory in USER_HOME so Webull SDK stores conf/token.txt
# safely in C:\Users\<Username>\conf\ instead of inside the repo folder.
try:
    os.chdir(USER_HOME)
except Exception:
    pass

# Set explicit Windows AppUserModelID and default Tkinter icon so the custom
# .ico displays in all window titlebars and on the Windows Taskbar.
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "DBCodez.PnLEnforcer.Beta"
    )
except Exception:
    pass

def apply_dark_title_bar(win):
    """Applies native Windows 10/11 dark mode to a Tkinter window's title bar
    via DwmSetWindowAttribute (checking attribute 20 and fallback 19)."""
    try:
        hwnd = win.winfo_id()
        parent_hwnd = ctypes.windll.user32.GetParent(hwnd)
        target_hwnds = [h for h in (parent_hwnd, hwnd) if h]
        val = ctypes.c_int(1)
        for h in target_hwnds:
            for attr in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    h, attr, ctypes.byref(val), ctypes.sizeof(val)
                )
    except Exception:
        pass


_orig_tk_init = tk.Tk.__init__
_orig_toplevel_init = tk.Toplevel.__init__


def _icon_tk_init(self, *args, **kwargs):
    _orig_tk_init(self, *args, **kwargs)
    if os.path.exists(ICON_PATH):
        try:
            self.iconbitmap(default=ICON_PATH)
        except Exception:
            pass
    try:
        self.after(15, lambda w=self: apply_dark_title_bar(w))
    except Exception:
        pass


def _dark_toplevel_init(self, *args, **kwargs):
    _orig_toplevel_init(self, *args, **kwargs)
    try:
        self.withdraw()
    except Exception:
        pass
    try:
        self.after(15, lambda w=self: apply_dark_title_bar(w))
    except Exception:
        pass


tk.Tk.__init__ = _icon_tk_init
tk.Toplevel.__init__ = _dark_toplevel_init


_NAMED_COLOR_HEX = {
    "yellow": "facc15",
    "gold": "eab308",
    "amber": "f59e0b",
    "orange": "f97316",
    "red": "ef4444",
    "green": "10b981",
    "white": "ffffff",
    "black": "000000",
}


def _normalize_color_hex6(c):
    s = str(c).strip().lower()
    if s in _NAMED_COLOR_HEX:
        return _NAMED_COLOR_HEX[s]
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    return s


def _blend_hex(c1, c2, t):
    """Smoothly interpolates between two #RRGGBB hex colors (0.0 <= t <= 1.0)."""
    try:
        t = max(0.0, min(1.0, float(t)))
        h1 = _normalize_color_hex6(c1)
        h2 = _normalize_color_hex6(c2)
        if len(h1) != 6 or len(h2) != 6:
            return c2 if t >= 0.5 else c1
        r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
        r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
        r = int(round(r1 + (r2 - r1) * t))
        g = int(round(g1 + (g2 - g1) * t))
        b = int(round(b1 + (b2 - b1) * t))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return c2


def _hex_to_rgb_tuple(h, fallback=(20, 26, 36)):
    try:
        s = _normalize_color_hex6(h)
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        pass
    return fallback


def _pack_rgba_png(w, h, raw_rows_bytes):
    """Packs raw scanlines (each prefixed with filter byte 0x00) into an RGBA PNG."""
    def _chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", int(w), int(h), 8, 6, 0, 0, 0)
    idat = zlib.compress(raw_rows_bytes, 1)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


try:
    from PIL import Image as _PILImage, ImageDraw as _PILImageDraw, ImageFilter as _PILImageFilter, ImageTk as _PILImageTk
    _HAS_PIL = True
except ImportError:
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "pillow"],
            check=False,
        )
        from PIL import Image as _PILImage, ImageDraw as _PILImageDraw, ImageFilter as _PILImageFilter, ImageTk as _PILImageTk
        _HAS_PIL = True
    except Exception:
        _HAS_PIL = False

_GLASS_PIL_IMAGE_CACHE = {}
_GLASS_PNG_BYTES_CACHE = {}
_GLASS_PHOTO_CACHE = {}


def _render_glass_pill_image(
    w,
    h,
    bg_hex="#0d1117",
    fill_hex="#141820",
    border_hex="#2e3746",
    glow_hex=None,
    hover=False,
    glow_strength=0.0,
    pad=0.5,
    corner_radius=6,
    fill_top_hex=None,
):
    """Renders a crisp, sub-pixel anti-aliased rounded rectangle (default 6px
    squircle for buttons/dropdowns, or full stadium capsule when corner_radius
    is None) with:
    1. Subtle one-way top-to-bottom linear micro-fade (slightly lighter at y=0
       fading smoothly downward to fill_hex at y=height — zero dark-center tube)
    2. Razor-sharp 1px anti-aliased border (zero fuzzy GaussianBlur) where the
       top horizontal edge is 25% brighter to simulate an overhead catch-light."""
    w = max(16, int(w))
    h = max(14, int(h))
    pad = 0.5
    rad_key = -1 if corner_radius is None else int(corner_radius)
    cache_key = (
        "modern_squircle_v5",
        w,
        h,
        bg_hex,
        fill_hex,
        fill_top_hex or "",
        border_hex,
        bool(hover),
        rad_key,
    )
    cached_img = _GLASS_PIL_IMAGE_CACHE.get(cache_key)
    if cached_img is not None:
        return cached_img

    bg_r, bg_g, bg_b = _hex_to_rgb_tuple(bg_hex, (13, 17, 23))
    fl_r, fl_g, fl_b = _hex_to_rgb_tuple(fill_hex, (20, 24, 32))
    bd_r, bd_g, bd_b = _hex_to_rgb_tuple(border_hex, (46, 55, 70))

    if fill_top_hex:
        top_r, top_g, top_b = _hex_to_rgb_tuple(fill_top_hex, (28, 33, 43))
    else:
        # One-way top-down fade: start ~10% lighter at y=0 and fade to fill_hex
        lift = 0.13 if hover else 0.10
        tint_r = bd_r * 0.35 + 255.0 * 0.65
        tint_g = bd_g * 0.35 + 255.0 * 0.65
        tint_b = bd_b * 0.35 + 255.0 * 0.65
        top_r = fl_r + (tint_r - fl_r) * lift
        top_g = fl_g + (tint_g - fl_g) * lift
        top_b = fl_b + (tint_b - fl_b) * lift

    cx = (w - 1.0) / 2.0
    cy = (h - 1.0) / 2.0
    hw = max(4.0, (w - 2.0 * pad) / 2.0)
    hh = max(4.0, (h - 2.0 * pad) / 2.0)
    if corner_radius is None:
        r = min(hw, hh)
    else:
        r = min(hw, hh, float(corner_radius))

    left_cx = min(w // 2, int(math.ceil(pad + r + 1.5)))
    mid_w = max(0, w - 2 * left_cx)
    border_w = 1.05
    span_h = max(1.0, h - 2.0 * pad)

    def _squircle_rgba(d, t):
        if d > 0.5:
            return b"\x00\x00\x00\x00"

        # 1. One-way top-to-bottom linear gradient (top_rgb at t=0 -> fl_rgb at t=1)
        ir = top_r + (fl_r - top_r) * t
        ig = top_g + (fl_g - top_g) * t
        ib = top_b + (fl_b - top_b) * t

        # 2. Razor-sharp 1px border with 25% brighter top horizontal catch-light
        if t < 0.22:
            top_catch = ((0.22 - t) / 0.22) * (0.30 if hover else 0.25)
        else:
            top_catch = 0.0
        br = bd_r + (255.0 - bd_r) * top_catch
        bg_c = bd_g + (255.0 - bd_g) * top_catch
        bb = bd_b + (255.0 - bd_b) * top_catch

        outer_cov = max(0.0, min(1.0, 0.5 - d))
        inner_cov = max(0.0, min(1.0, (-border_w + 0.5) - d))

        pr = br * (1.0 - inner_cov) + ir * inner_cov
        pg = bg_c * (1.0 - inner_cov) + ig * inner_cov
        pb = bb * (1.0 - inner_cov) + ib * inner_cov
        pa = int(round(outer_cov * 255.0))
        return bytes(
            (
                max(0, min(255, int(round(pr)))),
                max(0, min(255, int(round(pg)))),
                max(0, min(255, int(round(pb)))),
                max(0, min(255, pa)),
            )
        )

    hx_inner = hw - r
    hy_inner = hh - r
    raw_buf = bytearray()
    for y in range(h):
        t = max(0.0, min(1.0, (y - pad) / span_h))
        qy = abs(y - cy) - hy_inner
        left_row = bytearray()
        right_row = bytearray()
        for x in range(left_cx):
            qx = abs(x - cx) - hx_inner
            d = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r
            px = _squircle_rgba(d, t)
            left_row += px
            right_row = px + right_row
        mid_d = qy - r
        mid_px = _squircle_rgba(mid_d, t) * mid_w
        raw_buf += left_row + mid_px + right_row

    if _HAS_PIL:
        base_img = _PILImage.new("RGBA", (w, h), (bg_r, bg_g, bg_b, 255))
        pill_layer = _PILImage.frombytes("RGBA", (w, h), bytes(raw_buf))
        final_img = _PILImage.alpha_composite(base_img, pill_layer).convert("RGB")
        if len(_GLASS_PIL_IMAGE_CACHE) > 400:
            _GLASS_PIL_IMAGE_CACHE.clear()
        _GLASS_PIL_IMAGE_CACHE[cache_key] = final_img
        return final_img
    return bytes(raw_buf)


def _get_glass_pill_photo(
    widget,
    w,
    h,
    bg_hex="#0d1117",
    fill_hex="#141820",
    border_hex="#2e3746",
    glow_hex=None,
    hover=False,
    glow_strength=0.0,
    pad=0.5,
    corner_radius=6,
    fill_top_hex=None,
):
    """Returns a cached ImageTk.PhotoImage (or tk.PhotoImage fallback) for a
    crisp 6px rounded rectangle (or stadium capsule when corner_radius is None)
    with a one-way top-down linear micro-fade and razor-sharp 1px border."""
    w = max(16, int(w))
    h = max(14, int(h))
    rad_key = -1 if corner_radius is None else int(corner_radius)
    bytes_key = (
        "modern_squircle_v5",
        w,
        h,
        bg_hex,
        fill_hex,
        fill_top_hex or "",
        border_hex,
        bool(hover),
        rad_key,
    )
    tk_id = id(widget.tk)
    photo_key = (tk_id, bytes_key)
    cached_photo = _GLASS_PHOTO_CACHE.get(photo_key)
    if cached_photo is not None:
        return cached_photo

    rendered = _render_glass_pill_image(
        w,
        h,
        bg_hex=bg_hex,
        fill_hex=fill_hex,
        border_hex=border_hex,
        glow_hex=glow_hex,
        hover=hover,
        glow_strength=glow_strength,
        pad=pad,
        corner_radius=corner_radius,
        fill_top_hex=fill_top_hex,
    )
    if _HAS_PIL and not isinstance(rendered, (bytes, bytearray)):
        photo = _PILImageTk.PhotoImage(rendered, master=widget)
    else:
        bg_r, bg_g, bg_b = _hex_to_rgb_tuple(bg_hex, (13, 17, 23))
        rows = []
        stride = w * 4
        for y in range(h):
            row_bytes = bytearray(b"\x00")
            off = y * stride
            for x in range(w):
                px = rendered[off + x * 4 : off + x * 4 + 4]
                a = px[3] / 255.0
                row_bytes += bytes(
                    (
                        int(bg_r * (1.0 - a) + px[0] * a),
                        int(bg_g * (1.0 - a) + px[1] * a),
                        int(bg_b * (1.0 - a) + px[2] * a),
                        255,
                    )
                )
            rows.append(bytes(row_bytes))
        png_bytes = _pack_rgba_png(w, h, b"".join(rows))
        photo = tk.PhotoImage(master=widget, data=png_bytes)

    if len(_GLASS_PHOTO_CACHE) > 400:
        _GLASS_PHOTO_CACHE.clear()
    _GLASS_PHOTO_CACHE[photo_key] = photo
    return photo


def _get_glow_dot_photo(widget, bg_hex="#141c28", dot_hex="#00e676", size=18):
    """Renders an anti-aliased glowing LED status orb with radial neon bloom."""
    bytes_key = ("glow_dot", bg_hex, dot_hex, int(size))
    tk_id = id(widget.tk)
    photo_key = (tk_id, bytes_key)
    cached = _GLASS_PHOTO_CACHE.get(photo_key)
    if cached is not None:
        return cached
    png_bytes = _GLASS_PNG_BYTES_CACHE.get(bytes_key)
    if png_bytes is None:
        bg_r, bg_g, bg_b = _hex_to_rgb_tuple(bg_hex, (20, 28, 40))
        dt_r, dt_g, dt_b = _hex_to_rgb_tuple(dot_hex, (0, 230, 118))
        cx = (size - 1) / 2.0
        cy = (size - 1) / 2.0
        core_r = 4.2
        rows = []
        for y in range(size):
            row = bytearray(b"\x00")
            for x in range(size):
                dist = math.hypot(x - cx, y - cy)
                if dist <= core_r + 0.5:
                    cov = max(0.0, min(1.0, (core_r + 0.5) - dist))
                    # Specular white highlight near upper-left of orb
                    spec = max(
                        0.0,
                        1.0 - math.hypot(x - (cx - 1.3), y - (cy - 1.3)) / 3.2,
                    ) * 0.65
                    cr = dt_r + (255 - dt_r) * spec
                    cg = dt_g + (255 - dt_g) * spec
                    cb = dt_b + (255 - dt_b) * spec
                    ga = 0.55
                    or_ = bg_r + (dt_r - bg_r) * ga
                    og_ = bg_g + (dt_g - bg_g) * ga
                    ob_ = bg_b + (dt_b - bg_b) * ga
                    fr = int(or_ * (1.0 - cov) + cr * cov)
                    fg = int(og_ * (1.0 - cov) + cg * cov)
                    fb = int(ob_ * (1.0 - cov) + cb * cov)
                else:
                    ga = 0.55 * math.exp(-(dist - core_r) * 0.55)
                    fr = int(bg_r + (dt_r - bg_r) * ga)
                    fg = int(bg_g + (dt_g - bg_g) * ga)
                    fb = int(bg_b + (dt_b - bg_b) * ga)
                row += bytes(
                    (
                        max(0, min(255, fr)),
                        max(0, min(255, fg)),
                        max(0, min(255, fb)),
                        255,
                    )
                )
            rows.append(bytes(row))
        png_bytes = _pack_rgba_png(size, size, b"".join(rows))
        _GLASS_PNG_BYTES_CACHE[bytes_key] = png_bytes
    photo = tk.PhotoImage(master=widget, data=png_bytes)
    _GLASS_PHOTO_CACHE[photo_key] = photo
    return photo


def _get_glass_checkbox_photo(
    widget,
    bg_hex="#131922",
    checked=True,
    dimmed=False,
    accent_hex="#28b882",
    check_hex="#4ade80",
):
    """Renders an anti-aliased 18x18 rounded dark-glass checkbox icon with 6px
    right spacing before the label text."""
    bytes_key = (
        "cb_v2",
        bg_hex,
        bool(checked),
        bool(dimmed),
        accent_hex,
        check_hex,
    )
    tk_id = id(widget.tk)
    photo_key = (tk_id, bytes_key)
    cached = _GLASS_PHOTO_CACHE.get(photo_key)
    if cached is not None:
        return cached

    png_bytes = _GLASS_PNG_BYTES_CACHE.get(bytes_key)
    if png_bytes is None:
        bg_r, bg_g, bg_b = _hex_to_rgb_tuple(bg_hex, (19, 25, 34))
        if checked and not dimmed:
            fl_r, fl_g, fl_b = _hex_to_rgb_tuple(
                _blend_hex(bg_hex, accent_hex, 0.30), (16, 54, 42)
            )
            bd_r, bd_g, bd_b = _hex_to_rgb_tuple(accent_hex, (40, 184, 130))
            ck_r, ck_g, ck_b = _hex_to_rgb_tuple(check_hex, (105, 240, 174))
        elif checked and dimmed:
            fl_r, fl_g, fl_b = _hex_to_rgb_tuple("#121e1d", (18, 30, 29))
            bd_r, bd_g, bd_b = _hex_to_rgb_tuple("#264a40", (38, 74, 64))
            ck_r, ck_g, ck_b = _hex_to_rgb_tuple("#3a7560", (58, 117, 96))
        elif not checked and not dimmed:
            fl_r, fl_g, fl_b = _hex_to_rgb_tuple("#151f2c", (21, 31, 44))
            bd_r, bd_g, bd_b = _hex_to_rgb_tuple("#475b73", (71, 91, 115))
            ck_r, ck_g, ck_b = (0, 0, 0)
        else:
            fl_r, fl_g, fl_b = _hex_to_rgb_tuple("#121720", (18, 23, 32))
            bd_r, bd_g, bd_b = _hex_to_rgb_tuple("#283444", (40, 52, 68))
            ck_r, ck_g, ck_b = (0, 0, 0)

        size = 18
        w = size + 6
        h = size
        cx = (size - 1) / 2.0
        cy = (size - 1) / 2.0
        half = 6.5
        rad = 3.4
        border_w = 1.45

        def _seg_dist(px, py, ax, ay, bx, by):
            vx, vy = bx - ax, by - ay
            wx, wy = px - ax, py - ay
            c1 = vx * wx + vy * wy
            c2 = vx * vx + vy * vy
            t_seg = max(0.0, min(1.0, c1 / c2)) if c2 > 0 else 0.0
            return math.hypot(px - (ax + t_seg * vx), py - (ay + t_seg * vy))

        rows = []
        for y in range(h):
            row = bytearray(b"\x00")
            for x in range(w):
                if x >= size:
                    row += bytes((bg_r, bg_g, bg_b, 255))
                    continue
                dx = abs(x - cx) - (half - rad)
                dy = abs(y - cy) - (half - rad)
                d = (
                    math.hypot(max(dx, 0.0), max(dy, 0.0))
                    + min(max(dx, dy), 0.0)
                    - rad
                )
                ny = max(-1.0, min(1.0, (y - cy) / half))
                t = (ny + 1.0) * 0.5

                if d > 0.5:
                    if checked and not dimmed and d < 2.6:
                        ga = 0.26 * math.exp(-d * 1.0)
                        r_ = int(bg_r + (bd_r - bg_r) * ga)
                        g_ = int(bg_g + (bd_g - bg_g) * ga)
                        b_ = int(bg_b + (bd_b - bg_b) * ga)
                        row += bytes((r_, g_, b_, 255))
                    else:
                        row += bytes((bg_r, bg_g, bg_b, 255))
                    continue

                ir, ig, ib = float(fl_r), float(fl_g), float(fl_b)
                if t < 0.48:
                    sheen = 0.24 * ((0.48 - t) / 0.48)
                    ir = ir + (230 - ir) * sheen
                    ig = ig + (245 - ig) * sheen
                    ib = ib + (255 - ib) * sheen

                if checked:
                    d1 = _seg_dist(x, y, cx - 3.2, cy + 0.2, cx - 0.7, cy + 2.7)
                    d2 = _seg_dist(x, y, cx - 0.7, cy + 2.7, cx + 3.6, cy - 2.4)
                    cd = min(d1, d2)
                    ck_cov = max(0.0, min(1.0, 1.30 - cd))
                    ir = ir * (1.0 - ck_cov) + ck_r * ck_cov
                    ig = ig * (1.0 - ck_cov) + ck_g * ck_cov
                    ib = ib * (1.0 - ck_cov) + ck_b * ck_cov

                spec = max(0.0, -ny) * 0.36
                br = bd_r + (255 - bd_r) * spec
                bg_c = bd_g + (255 - bd_g) * spec
                bb = bd_b + (255 - bd_b) * spec

                outer_cov = max(0.0, min(1.0, 0.5 - d))
                inner_cov = max(0.0, min(1.0, (-border_w + 0.5) - d))
                pr = br * (1.0 - inner_cov) + ir * inner_cov
                pg = bg_c * (1.0 - inner_cov) + ig * inner_cov
                pb = bb * (1.0 - inner_cov) + ib * inner_cov
                fr = int(bg_r * (1.0 - outer_cov) + pr * outer_cov)
                fg = int(bg_g * (1.0 - outer_cov) + pg * outer_cov)
                fb = int(bg_b * (1.0 - outer_cov) + pb * outer_cov)
                row += bytes(
                    (
                        max(0, min(255, fr)),
                        max(0, min(255, fg)),
                        max(0, min(255, fb)),
                        255,
                    )
                )
            rows.append(bytes(row))

        png_bytes = _pack_rgba_png(w, h, b"".join(rows))
        _GLASS_PNG_BYTES_CACHE[bytes_key] = png_bytes

    photo = tk.PhotoImage(master=widget, data=png_bytes)
    _GLASS_PHOTO_CACHE[photo_key] = photo
    return photo


class GlassCheckbutton(tk.Label):
    """Dark-glass custom checkbox widget backed by tk.Label so it never suffers
    from Windows tk.Checkbutton white selectcolor boxes, sunken relief borders,
    or GDI disabled stipple dithering."""

    def __init__(
        self,
        parent,
        text="",
        variable=None,
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#131922",
        disabledforeground="#526070",
        accent_hex="#28b882",
        check_hex="#69f0ae",
        anchor="w",
        command=None,
        **kwargs,
    ):
        for k in (
            "selectcolor",
            "activebackground",
            "activeforeground",
            "indicatoron",
        ):
            kwargs.pop(k, None)
        self._bg_hex = bg
        self._fg_normal = fg
        self._fg_disabled = disabledforeground
        self._accent_hex = accent_hex
        self._check_hex = check_hex
        self._variable = variable
        self._command = command
        self._disabled = False
        self._img_off = _get_glass_checkbox_photo(
            parent, bg, checked=False, dimmed=False,
            accent_hex=accent_hex, check_hex=check_hex
        )
        self._img_on = _get_glass_checkbox_photo(
            parent, bg, checked=True, dimmed=False,
            accent_hex=accent_hex, check_hex=check_hex
        )
        self._img_off_dim = _get_glass_checkbox_photo(
            parent, bg, checked=False, dimmed=True,
            accent_hex=accent_hex, check_hex=check_hex
        )
        self._img_on_dim = _get_glass_checkbox_photo(
            parent, bg, checked=True, dimmed=True,
            accent_hex=accent_hex, check_hex=check_hex
        )
        is_checked = bool(variable.get()) if variable is not None else False
        super().__init__(
            parent,
            text=text,
            font=font,
            fg=fg,
            bg=bg,
            image=self._img_on if is_checked else self._img_off,
            compound="left",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=1,
            anchor=anchor,
            cursor="hand2",
            **kwargs,
        )
        self.bind("<Button-1>", self._on_click, add="+")
        if self._variable is not None:
            try:
                self._variable.trace_add(
                    "write", lambda *_: self._sync_visual()
                )
            except Exception:
                pass

    def _is_checked(self):
        if self._variable is not None:
            try:
                return bool(self._variable.get())
            except Exception:
                return False
        return False

    def _sync_visual(self):
        try:
            if not self.winfo_exists():
                return
            chk = self._is_checked()
            if self._disabled:
                img = self._img_on_dim if chk else self._img_off_dim
                super().configure(image=img, fg=self._fg_disabled, cursor="")
            else:
                img = self._img_on if chk else self._img_off
                super().configure(image=img, fg=self._fg_normal, cursor="hand2")
        except Exception:
            pass

    def _on_click(self, _event=None):
        if self._disabled:
            return "break"
        if self._variable is not None:
            try:
                self._variable.set(not bool(self._variable.get()))
            except Exception:
                pass
        self._sync_visual()
        if self._command is not None:
            self._command()
        return "break"

    def config(self, **kwargs):
        self.configure(**kwargs)

    def configure(self, **kwargs):
        if "state" in kwargs:
            st = str(kwargs.pop("state")).lower()
            self._disabled = st == "disabled"
        if "fg" in kwargs:
            new_fg = kwargs.pop("fg")
            if new_fg not in ("#555555", "#666666", "#526070"):
                self._fg_normal = new_fg
            if not self._disabled:
                super().configure(fg=new_fg)
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "variable" in kwargs:
            self._variable = kwargs.pop("variable")
        if "disabledforeground" in kwargs:
            dfg = kwargs.pop("disabledforeground")
            if dfg:
                self._fg_disabled = dfg
        for k in (
            "selectcolor",
            "activebackground",
            "activeforeground",
        ):
            kwargs.pop(k, None)
        if kwargs:
            super().configure(**kwargs)
        self._sync_visual()


def make_glass_checkbutton(parent, **kwargs):
    """Factory helper to create a GlassCheckbutton."""
    return GlassCheckbutton(parent, **kwargs)


def _draw_filled_stadium(cv, x1, y1, x2, y2, color):
    """Draws a seamless filled stadium capsule on a tk.Canvas."""
    w = x2 - x1
    h = y2 - y1
    if w <= 0 or h <= 0:
        return
    if w <= h:
        cv.create_oval(x1, y1, x2, y2, fill=color, outline=color)
        return
    r = h / 2.0
    cv.create_oval(x1, y1, x1 + h, y2, fill=color, outline=color)
    cv.create_oval(x2 - h, y1, x2, y2, fill=color, outline=color)
    cv.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)


class NeonBarCanvas(tk.Canvas):
    """Vertical neon left-accent bar with a soft horizontal glass fade into the card."""

    def __init__(self, parent, core_color="#38bdf8", card_bg="#131922", glow_on=True):
        super().__init__(
            parent,
            width=12,
            height=1,
            bg=card_bg,
            bd=0,
            highlightthickness=0
        )
        self._core_color = core_color
        self._card_bg = card_bg
        self._glow_on = glow_on
        self.bind("<Configure>", self._redraw)

    def set_neon(self, core_color, glow_on=True):
        self._core_color = core_color
        self._glow_on = glow_on
        self._redraw()

    def _redraw(self, event=None):
        self.delete("all")
        h = self.winfo_height()
        if h <= 4:
            h = 300
        if self._glow_on:
            # Soft 8px horizontal ambient light-bleed into card interior (x = 4..11)
            for x in range(4, 12):
                falloff = ((12 - x) / 8.0) ** 2.2
                col = _blend_hex(self._card_bg, self._core_color, falloff * 0.26)
                self.create_line(x, 0, x, h, fill=col)
            # Crisp 4px vertical accent bar with subtle specular spine
            self.create_rectangle(0, 0, 4, h, fill=self._core_color, outline="")
            spine_col = _blend_hex(self._core_color, "#ffffff", 0.42)
            self.create_rectangle(1, 0, 2, h, fill=spine_col, outline="")
        else:
            self.create_rectangle(0, 0, 3, h, fill=self._core_color, outline="")


class RulebookPillBadge(tk.Canvas):
    """Flat-glass rounded stadium badge ('● ACTIVE NOW' vs 'STANDBY') for Rulebook cards."""

    def __init__(self, parent, card_bg="#131922"):
        super().__init__(
            parent,
            width=148,
            height=26,
            bg=card_bg,
            bd=0,
            highlightthickness=0
        )
        self._card_bg = card_bg
        self._active = True
        self._locked = False
        self._bg_photo = None
        self.bind("<Configure>", self._redraw)

    def set_active(self, is_active, locked=False):
        self._active = bool(is_active)
        self._locked = bool(locked)
        self._redraw()

    def _redraw(self, event=None):
        self.delete("all")
        w = max(148, self.winfo_width())
        h = max(26, self.winfo_height())
        if self._active and self._locked:
            self._bg_photo = _get_glass_pill_photo(
                self,
                w,
                h,
                bg_hex=self._card_bg,
                fill_hex="#33220c",
                fill_top_hex="#473010",
                border_hex="#f59e0b",
                hover=True,
                corner_radius=None,
            )
            self.create_image(0, 0, image=self._bg_photo, anchor="nw")
            self.create_text(
                int(w // 2),
                int(h // 2),
                text="🔒 ACTIVE (LOCKED)",
                font=("Arial", 8, "bold"),
                fill="#fde68a"
            )
        elif self._active:
            self._bg_photo = _get_glass_pill_photo(
                self,
                w,
                h,
                bg_hex=self._card_bg,
                fill_hex="#0d3b20",
                fill_top_hex="#14532d",
                border_hex="#10b981",
                hover=True,
                corner_radius=None,
            )
            self.create_image(0, 0, image=self._bg_photo, anchor="nw")
            self.create_text(
                int(w // 2),
                int(h // 2),
                text="● ACTIVE NOW",
                font=("Arial", 8, "bold"),
                fill="#69f0ae"
            )
        elif self._locked:
            self._bg_photo = _get_glass_pill_photo(
                self,
                w,
                h,
                bg_hex=self._card_bg,
                fill_hex="#141820",
                fill_top_hex="#1c212b",
                border_hex="#4b5563",
                hover=False,
                corner_radius=None,
            )
            self.create_image(0, 0, image=self._bg_photo, anchor="nw")
            self.create_text(
                int(w // 2),
                int(h // 2),
                text="🔒 STANDBY (LOCKED)",
                font=("Arial", 8, "bold"),
                fill="#94a3b8"
            )
        else:
            self._bg_photo = _get_glass_pill_photo(
                self,
                w,
                h,
                bg_hex=self._card_bg,
                fill_hex="#141820",
                fill_top_hex="#1c212b",
                border_hex="#2e3746",
                hover=False,
                corner_radius=None,
            )
            self.create_image(0, 0, image=self._bg_photo, anchor="nw")
            self.create_text(
                int(w // 2),
                int(h // 2),
                text="STANDBY",
                font=("Arial", 8, "bold"),
                fill="#7f8fa3"
            )


class HudCapsulePill(tk.Canvas):
    """Anti-aliased flat-glass stadium capsule widget for the HUD bottom bar
    with a single 1px border, flat dark fill, and drop-in tk.Button / tk.Label
    .config() compatibility."""

    def __init__(
        self,
        parent,
        text="",
        bg="#282c31",
        fg="#f8f9fa",
        rim="#4b5563",
        glow="#343a40",
        font=("Arial", 8, "bold"),
        width=140,
        height=24,
        state="normal",
        command=None,
        cursor="",
        auto_width=False,
        pad_x=26
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg="#1a1a1a",
            bd=0,
            highlightthickness=0,
            cursor=cursor
        )
        self._text = text
        self._bg = bg
        self._fg = fg
        self._disabled_fg = fg
        self._rim = rim
        self._glow = glow
        self._font = font
        self._state = state
        self._command = command
        self._min_width = int(width)
        self._auto_width = bool(auto_width)
        self._pad_x = int(pad_x)
        self._bg_photo = None
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", self._on_click)

    def _on_click(self, event=None):
        if self._command is not None and self._state == "normal":
            self._command()

    def config(self, **kwargs):
        self.configure(**kwargs)

    def configure(self, **kwargs):
        redraw_needed = False
        if "text" in kwargs:
            self._text = kwargs.pop("text")
            redraw_needed = True
        if "bg" in kwargs:
            new_bg = kwargs.pop("bg")
            if new_bg in ("#333333", "#222629", "#262626", "#282c31"):
                self._bg = "#1b222c"
                self._rim = "#475569"
                self._glow = "#3b4c63"
            elif new_bg in ("#ff0000", "#8b0000", "#922b21"):
                self._bg = "#45141e"
                self._rim = "#ff5252"
                self._glow = "#ff1744"
            elif new_bg in ("yellow", "#facc15", "#eab308", "#f59e0b", "#fbbf24"):
                self._bg = "#eab308"
                self._rim = "#fef08a"
                self._glow = "#facc15"
            elif new_bg in (
                "#00e676", "#2ecc71", "#27ae60", "#1e8449", "#196f3d", "#145a32"
            ):
                self._bg = "#10452c"
                self._rim = "#00e676"
                self._glow = "#00e676"
            else:
                self._bg = new_bg
                self._rim = _blend_hex(new_bg, "#ffffff", 0.32)
                self._glow = self._rim
            redraw_needed = True
        if "fg" in kwargs:
            self._fg = kwargs.pop("fg")
            redraw_needed = True
        if "disabledforeground" in kwargs:
            self._disabled_fg = kwargs.pop("disabledforeground")
            redraw_needed = True
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            self.configure(
                cursor="hand2"
                if (self._state == "normal" and self._command is not None)
                else ""
            )
            redraw_needed = True
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if kwargs:
            super().configure(**kwargs)
        if redraw_needed:
            self._redraw()

    def _redraw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 10:
            w = int(self["width"])
        if h <= 6:
            h = int(self["height"])

        render_font = self._font
        render_text = self._text
        if render_text:
            probe_id = self.create_text(
                0, 0, text=render_text, font=self._font, anchor="nw"
            )
            bbox = self.bbox(probe_id)
            self.delete(probe_id)
            text_w = (bbox[2] - bbox[0]) if bbox else 0
            if self._auto_width:
                target_w = max(self._min_width, int(text_w + self._pad_x))
                if abs(int(self["width"]) - target_w) > 1:
                    super().configure(width=target_w)
                w = max(w, target_w) if w <= target_w + 4 else target_w
            elif text_w > (w - 14) and isinstance(self._font, tuple) and len(self._font) >= 2:
                smaller_pt = max(7, int(self._font[1]) - 1)
                render_font = (self._font[0], smaller_pt) + tuple(self._font[2:])
                probe_id2 = self.create_text(
                    0, 0, text=render_text, font=render_font, anchor="nw"
                )
                bbox2 = self.bbox(probe_id2)
                self.delete(probe_id2)
                text_w2 = (bbox2[2] - bbox2[0]) if bbox2 else 0
                max_txt_w = max(24, w - 12)
                if text_w2 > max_txt_w and len(render_text) > 4:
                    trimmed = render_text
                    while len(trimmed) > 3:
                        trimmed = trimmed[:-1].rstrip()
                        cand = trimmed + "…"
                        pid = self.create_text(
                            0, 0, text=cand, font=render_font, anchor="nw"
                        )
                        bb = self.bbox(pid)
                        self.delete(pid)
                        if not bb or (bb[2] - bb[0]) <= max_txt_w:
                            render_text = cand
                            break

        self._bg_photo = _get_glass_pill_photo(
            self,
            w,
            h,
            bg_hex="#1a1a1a",
            fill_hex=self._bg if self._bg != "#282c31" else "#181d26",
            border_hex=self._rim if self._rim != "#6c757d" else "#364152",
            glow_hex=self._glow,
            hover=False,
            corner_radius=None,
        )
        self.create_image(0, 0, image=self._bg_photo, anchor="nw")
        txt_col = (
            self._fg if self._state == "normal" else (self._disabled_fg or self._fg)
        )
        self.create_text(
            int(w // 2),
            int(h // 2),
            text=render_text,
            font=render_font,
            fill=txt_col
        )


class _WIN32_POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _WIN32_RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _WIN32_MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _WIN32_RECT),
        ("rcWork", _WIN32_RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def get_monitor_work_area(x=None, y=None, widget=None):
    """Returns (left, top, right, bottom) of the taskbar-aware work area for the
    physical monitor containing (x, y), the given widget's toplevel window, or
    the current mouse cursor across multi-monitor setups (including negative X/Y)."""
    try:
        u32 = ctypes.windll.user32
        if x is None or y is None:
            resolved = False
            if widget is not None:
                try:
                    top = widget.winfo_toplevel()
                    top.update_idletasks()
                    tw = int(top.winfo_width())
                    th = int(top.winfo_height())
                    if tw > 40 and th > 30:
                        x = int(top.winfo_rootx()) + tw // 2
                        y = int(top.winfo_rooty()) + th // 2
                        resolved = True
                except Exception:
                    pass
            if not resolved:
                pt = _WIN32_POINT()
                if u32.GetCursorPos(ctypes.byref(pt)):
                    x, y = int(pt.x), int(pt.y)
                else:
                    x, y = 100, 100
        pt_struct = _WIN32_POINT(int(x), int(y))
        mon_from_pt = u32.MonitorFromPoint
        mon_from_pt.argtypes = [_WIN32_POINT, ctypes.c_ulong]
        mon_from_pt.restype = ctypes.c_void_p
        get_mon_info = u32.GetMonitorInfoW
        get_mon_info.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WIN32_MONITORINFO),
        ]
        get_mon_info.restype = ctypes.c_int

        # MONITOR_DEFAULTTONEAREST = 2
        h_mon = mon_from_pt(pt_struct, 2)
        if h_mon:
            mi = _WIN32_MONITORINFO()
            mi.cbSize = ctypes.sizeof(_WIN32_MONITORINFO)
            if get_mon_info(h_mon, ctypes.byref(mi)):
                r = mi.rcWork
                if (r.right - r.left) > 100 and (r.bottom - r.top) > 100:
                    return (int(r.left), int(r.top), int(r.right), int(r.bottom))
    except Exception:
        pass
    try:
        if widget is not None:
            sw = int(widget.winfo_screenwidth())
            sh = int(widget.winfo_screenheight())
            return (0, 0, sw, sh - 48)
    except Exception:
        pass
    return (0, 0, 1920, 1032)


def center_dialog_over_parent(dlg, parent=None, width=None, height=None):
    """Centers `dlg` directly over `parent` (or on the active monitor if `parent`
    is None or unmapped), clamps its coordinates to that monitor's work area,
    and only reveals (`deiconify`) the window after its final geometry and dark
    title bar are applied so it never flashes on the primary monitor first."""
    try:
        try:
            dlg.withdraw()
        except Exception:
            pass
        dlg.update_idletasks()
        w = int(width) if width is not None else int(dlg.winfo_reqwidth())
        h = int(height) if height is not None else int(dlg.winfo_reqheight())
        ref_parent = parent
        if ref_parent is None:
            try:
                pf_win = globals().get("active_preflight_win")
                hr_win = globals().get("hud_root")
                if pf_win is not None and pf_win is not dlg and pf_win.winfo_exists():
                    ref_parent = pf_win
                elif hr_win is not None and hr_win is not dlg and hr_win.winfo_exists():
                    ref_parent = hr_win
            except Exception:
                ref_parent = None

        centered_on_parent = False
        if ref_parent is not None:
            try:
                top = ref_parent.winfo_toplevel()
                top.update_idletasks()
                pw = int(top.winfo_width())
                ph = int(top.winfo_height())
                if pw > 60 and ph > 35:
                    px = int(top.winfo_rootx())
                    py = int(top.winfo_rooty())
                    cx = px + pw // 2
                    cy = py + ph // 2
                    m_left, m_top, m_right, m_bottom = get_monitor_work_area(
                        cx, cy, widget=top
                    )
                    x = px + (pw - w) // 2
                    y = py + (ph - h) // 2
                    x = max(m_left + 12, min(x, m_right - w - 12))
                    y = max(m_top + 12, min(y, m_bottom - h - 12))
                    centered_on_parent = True
            except Exception:
                centered_on_parent = False

        if not centered_on_parent:
            m_left, m_top, m_right, m_bottom = get_monitor_work_area(widget=dlg)
            mw = max(200, m_right - m_left)
            mh = max(200, m_bottom - m_top)
            x = m_left + max(12, (mw - w) // 2)
            y = m_top + max(12, (mh - h) // 2)

        if width is not None and height is not None:
            dlg.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
        else:
            dlg.geometry(f"+{int(x)}+{int(y)}")
        apply_dark_title_bar(dlg)
        dlg.deiconify()
        dlg.lift()
        if parent is not None and isinstance(dlg, tk.Toplevel):
            try:
                dlg.grab_set()
            except Exception:
                pass
    except Exception:
        try:
            dlg.deiconify()
        except Exception:
            pass


class DarkDropdownMenu:
    """Custom borderless dark-slate popup menu replacing native Win32 tk.Menu
    so dropdowns render with a crisp 1px #334155 dark border instead of
    Windows' thick white system menu border."""

    _active_instance = None

    def __init__(
        self,
        parent,
        font=("Arial", 9, "bold"),
        bg="#141820",
        fg="#e2e8f0",
        activebackground="#1e293b",
        activeforeground="#ffffff",
        border_color="#334155",
        **_ignored,
    ):
        self._parent = parent
        self._font = font
        self._bg = bg
        self._fg = fg
        self._active_bg = activebackground
        self._active_fg = activeforeground
        self._border = border_color
        self._items = []
        self._win = None
        self._owner = None
        self._on_close = None
        self._top_bind_ids = []
        self._last_close_ts = 0.0

    def add_command(
        self, label="", command=None, fg=None, activeforeground=None, **_ignored
    ):
        self._items.append(
            {
                "type": "command",
                "label": str(label),
                "command": command,
                "fg": fg,
                "active_fg": activeforeground,
            }
        )

    def add_separator(self):
        self._items.append({"type": "separator"})

    def delete(self, start, end=None):
        self._items.clear()

    def grab_release(self):
        pass

    @classmethod
    def close_active(cls):
        if cls._active_instance is not None:
            cls._active_instance.close()

    def close(self, _event=None):
        if DarkDropdownMenu._active_instance is self:
            DarkDropdownMenu._active_instance = None
        top = None
        try:
            top = self._parent.winfo_toplevel()
        except Exception:
            pass
        if top is not None and self._top_bind_ids:
            for seq, bid in self._top_bind_ids:
                try:
                    top.unbind(seq, bid)
                except Exception:
                    pass
        self._top_bind_ids = []
        if self._win is not None:
            self._last_close_ts = time.monotonic()
            w = self._win
            self._win = None
            try:
                w.destroy()
            except Exception:
                pass
        if self._owner is not None:
            try:
                self._owner._menu_open = False
            except Exception:
                pass
            self._owner = None
        if callable(self._on_close):
            cb = self._on_close
            self._on_close = None
            try:
                cb()
            except Exception:
                pass

    def tk_popup(self, x, y, min_width=0, owner=None, on_close=None):
        if self._win is not None and self._win.winfo_exists():
            self.close()
            return
        if (time.monotonic() - self._last_close_ts) < 0.16:
            return
        DarkDropdownMenu.close_active()
        if not self._items:
            if callable(on_close):
                on_close()
            return

        self._owner = owner
        self._on_close = on_close
        if owner is not None:
            try:
                owner._menu_open = True
            except Exception:
                pass

        try:
            tw = tk.Toplevel(self._parent)
            tw.withdraw()
            tw.wm_overrideredirect(True)
            tw.attributes("-topmost", True)
            tw.config(bg=self._border, padx=1, pady=1)
            self._win = tw
            DarkDropdownMenu._active_instance = self

            inner = tk.Frame(tw, bg=self._bg, padx=2, pady=3)
            inner.pack(fill="both", expand=True)

            def _invoke_item(cmd):
                self.close()
                if callable(cmd):
                    try:
                        self._parent.after(10, cmd)
                    except Exception:
                        cmd()

            for item in self._items:
                if item.get("type") == "separator":
                    sep = tk.Frame(inner, bg="#263142", height=1)
                    sep.pack(fill="x", padx=6, pady=4)
                    continue
                lbl_txt = item.get("label", "")
                cmd = item.get("command")
                item_fg = item.get("fg") or self._fg
                item_active_fg = item.get("active_fg") or self._active_fg
                row = tk.Label(
                    inner,
                    text=lbl_txt,
                    font=self._font,
                    bg=self._bg,
                    fg=item_fg,
                    anchor="w",
                    padx=10,
                    pady=4,
                    cursor="hand2",
                )
                row.pack(fill="x")
                row.bind(
                    "<Enter>",
                    lambda _e, r=row, afg=item_active_fg: r.config(
                        bg=self._active_bg, fg=afg
                    ),
                )
                row.bind(
                    "<Leave>",
                    lambda _e, r=row, nfg=item_fg: r.config(
                        bg=self._bg, fg=nfg
                    ),
                )
                row.bind(
                    "<Button-1>",
                    lambda _e, c=cmd: _invoke_item(c),
                )

            tw.update_idletasks()
            req_w = max(int(min_width), int(tw.winfo_reqwidth()))
            req_h = int(tw.winfo_reqheight())
            pos_x = int(x)
            pos_y = int(y)
            try:
                m_left, m_top, m_right, m_bottom = get_monitor_work_area(
                    pos_x, pos_y, widget=(owner or self._parent)
                )
                top = self._parent.winfo_toplevel()
                top_x = int(top.winfo_rootx())
                top_y = int(top.winfo_rooty())
                top_w = int(top.winfo_width())
                top_h = int(top.winfo_height())
                min_top = (
                    max(m_top + 8, top_y + 8)
                    if top_h > 120
                    else (m_top + 8)
                )
                max_bottom = (
                    min(top_y + top_h - 8, m_bottom - 8)
                    if top_h > 120
                    else (m_bottom - 8)
                )
                if pos_y + req_h > max_bottom and owner is not None:
                    up_y = int(owner.winfo_rooty()) - req_h - 2
                    if up_y >= min_top:
                        pos_y = up_y
                    else:
                        pos_y = max(min_top, max_bottom - req_h)
                min_left = (
                    max(m_left + 8, top_x + 8)
                    if top_w > 120
                    else (m_left + 8)
                )
                max_right = (
                    min(top_x + top_w - 8, m_right - 8)
                    if top_w > 120
                    else (m_right - 8)
                )
                if pos_x + req_w > max_right:
                    pos_x = max(min_left, max_right - req_w)
                if pos_x < min_left:
                    pos_x = min_left
            except Exception:
                pass
            tw.wm_geometry(f"{req_w}x{req_h}+{pos_x}+{pos_y}")
            tw.deiconify()
            tw.lift()
            try:
                tw.focus_force()
            except Exception:
                pass

            tw.bind("<Escape>", self.close)
            tw.bind("<FocusOut>", self.close)

            def _bind_outside_dismiss():
                if self._win is None or not self._win.winfo_exists():
                    return
                try:
                    top = self._parent.winfo_toplevel()
                    for seq in ("<Button-1>", "<Configure>", "<Unmap>"):
                        bid = top.bind(seq, self.close, add="+")
                        if bid:
                            self._top_bind_ids.append((seq, bid))
                except Exception:
                    pass

            tw.after(30, _bind_outside_dismiss)
        except Exception:
            self.close()


class GlassStadiumButton(tk.Canvas):
    """Reusable crisp 6px rounded-rectangle (squircle) button with a one-way
    top-to-bottom linear micro-fade, razor-sharp 1px border (top catch-light),
    hover illumination, and dropdown support."""

    def __init__(
        self,
        parent,
        text="",
        fill_color="#141820",
        fill_top_color=None,
        border_color="#2e3746",
        fg="#e2e8f0",
        hover_fill=None,
        hover_fill_top=None,
        hover_border=None,
        hover_fg=None,
        glow_color=None,
        glow_strength=0.0,
        corner_radius=6,
        canvas_bg=None,
        font=("Arial", 9, "bold"),
        width=90,
        height=32,
        auto_width=True,
        pad_x=22,
        state="normal",
        command=None,
        menu=None,
        chevron=None,
        chevron_color=None,
        inner_highlight=True,
        cursor="hand2",
    ):
        if canvas_bg is None:
            try:
                canvas_bg = parent.cget("bg")
            except Exception:
                canvas_bg = "#0d1117"
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=canvas_bg,
            bd=0,
            highlightthickness=0,
            cursor=cursor if state == "normal" else "",
        )
        self._text = text
        self._fill = fill_color
        self._fill_top = fill_top_color
        self._border = border_color
        self._fg = fg
        self._disabled_fg = "#7a8899"
        self._hover_fill = hover_fill
        self._hover_fill_top = hover_fill_top
        self._hover_border = hover_border
        self._hover_fg = hover_fg
        self._glow = glow_color
        self._glow_strength = float(glow_strength)
        self._corner_radius = corner_radius
        self._canvas_bg = canvas_bg
        self._font = font
        self._min_width = int(width)
        self._height = int(height)
        self._auto_width = bool(auto_width)
        self._pad_x = int(pad_x)
        self._state = state
        self._command = command
        self._menu = menu
        self._chevron = chevron
        self._chevron_color = chevron_color
        self._inner_highlight = bool(inner_highlight)
        self._hovered = False
        self._bg_photo = None

        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<Button-1>", self._on_click, add="+")

    def _on_enter(self, _event=None):
        if self._state == "normal" and not self._hovered:
            self._hovered = True
            self._redraw()

    def _on_leave(self, _event=None):
        if self._hovered:
            self._hovered = False
            self._redraw()

    def _on_click(self, _event=None):
        hide_fn = getattr(self, "_hide_tooltip_fn", None)
        if callable(hide_fn):
            hide_fn()
        if self._state != "normal":
            return
        if self._menu is not None:
            def _after_menu_close():
                if callable(hide_fn):
                    hide_fn()
                self._hovered = False
                self._redraw()

            if isinstance(self._menu, DarkDropdownMenu):
                self._menu.tk_popup(
                    self.winfo_rootx(),
                    self.winfo_rooty() + self.winfo_height() + 2,
                    min_width=self.winfo_width(),
                    owner=self,
                    on_close=_after_menu_close,
                )
            else:
                self._menu_open = True
                try:
                    self._menu.tk_popup(
                        self.winfo_rootx(),
                        self.winfo_rooty() + self.winfo_height() + 2,
                    )
                finally:
                    self._menu_open = False
                    _after_menu_close()
                    try:
                        self._menu.grab_release()
                    except Exception:
                        pass
        elif self._command is not None:
            self._command()

    def config(self, **kwargs):
        self.configure(**kwargs)

    def configure(self, **kwargs):
        redraw_needed = False
        if "text" in kwargs:
            self._text = kwargs.pop("text")
            redraw_needed = True
        if "fill_color" in kwargs:
            self._fill = kwargs.pop("fill_color")
            redraw_needed = True
        if "fill_top_color" in kwargs:
            self._fill_top = kwargs.pop("fill_top_color")
            redraw_needed = True
        if "bg" in kwargs:
            self._fill = kwargs.pop("bg")
            redraw_needed = True
        if "border_color" in kwargs:
            self._border = kwargs.pop("border_color")
            redraw_needed = True
        if "rim" in kwargs:
            self._border = kwargs.pop("rim")
            redraw_needed = True
        if "fg" in kwargs:
            self._fg = kwargs.pop("fg")
            redraw_needed = True
        if "disabledforeground" in kwargs:
            self._disabled_fg = kwargs.pop("disabledforeground")
            redraw_needed = True
        if "hover_fill" in kwargs:
            self._hover_fill = kwargs.pop("hover_fill")
            redraw_needed = True
        if "hover_fill_top" in kwargs:
            self._hover_fill_top = kwargs.pop("hover_fill_top")
            redraw_needed = True
        if "activebackground" in kwargs:
            self._hover_fill = kwargs.pop("activebackground")
            redraw_needed = True
        if "hover_border" in kwargs:
            self._hover_border = kwargs.pop("hover_border")
            redraw_needed = True
        if "hover_fg" in kwargs:
            self._hover_fg = kwargs.pop("hover_fg")
            redraw_needed = True
        if "activeforeground" in kwargs:
            self._hover_fg = kwargs.pop("activeforeground")
            redraw_needed = True
        if "glow_color" in kwargs:
            self._glow = kwargs.pop("glow_color")
            redraw_needed = True
        if "glow_strength" in kwargs:
            self._glow_strength = float(kwargs.pop("glow_strength"))
            redraw_needed = True
        if "corner_radius" in kwargs:
            self._corner_radius = kwargs.pop("corner_radius")
            redraw_needed = True
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            if self._state != "normal":
                self._hovered = False
            super().configure(
                cursor="hand2"
                if (
                    self._state == "normal"
                    and (self._command is not None or self._menu is not None)
                )
                else ""
            )
            redraw_needed = True
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "menu" in kwargs:
            self._menu = kwargs.pop("menu")
        if "chevron" in kwargs:
            self._chevron = kwargs.pop("chevron")
            redraw_needed = True
        if "chevron_color" in kwargs:
            self._chevron_color = kwargs.pop("chevron_color")
            redraw_needed = True
        for ignored_k in ("bd", "relief", "padx", "pady"):
            kwargs.pop(ignored_k, None)
        if kwargs:
            super().configure(**kwargs)
        if redraw_needed:
            self._redraw()

    def _redraw(self, _event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 10:
            w = int(self["width"])
        if h <= 6:
            h = int(self["height"])

        text_w = 0
        if self._text:
            probe_id = self.create_text(
                0, 0, text=self._text, font=self._font, anchor="nw"
            )
            bbox = self.bbox(probe_id)
            self.delete(probe_id)
            text_w = (bbox[2] - bbox[0]) if bbox else 0

        chev_extra = 16 if self._chevron else 0
        if self._auto_width:
            target_w = max(
                self._min_width, int(text_w + chev_extra + self._pad_x)
            )
            if abs(int(self["width"]) - target_w) > 1:
                super().configure(width=target_w)
            w = max(w, target_w) if w <= target_w + 4 else target_w

        if self._state != "normal":
            cur_fill = self._fill
            cur_top = self._fill_top
            cur_border = self._border
            cur_fg = self._disabled_fg or self._fg
            is_hov = False
        elif self._hovered:
            cur_fill = self._hover_fill or _blend_hex(
                self._fill, "#ffffff", 0.06
            )
            cur_top = self._hover_fill_top or (
                _blend_hex(self._fill_top, "#ffffff", 0.08)
                if self._fill_top
                else None
            )
            cur_border = self._hover_border or _blend_hex(
                self._border, "#ffffff", 0.25
            )
            cur_fg = self._hover_fg or "#ffffff"
            is_hov = True
        else:
            cur_fill = self._fill
            cur_top = self._fill_top
            cur_border = self._border
            cur_fg = self._fg
            is_hov = False

        self._bg_photo = _get_glass_pill_photo(
            self,
            w,
            h,
            bg_hex=self._canvas_bg,
            fill_hex=cur_fill,
            fill_top_hex=cur_top,
            border_hex=cur_border,
            hover=is_hov,
            corner_radius=self._corner_radius,
        )
        self.create_image(0, 0, image=self._bg_photo, anchor="nw")

        cy_i = int(h // 2)
        if self._chevron:
            self.create_text(
                int((w - 13) // 2),
                cy_i,
                text=self._text,
                font=self._font,
                fill=cur_fg,
            )
            c_col = (
                _blend_hex(self._chevron_color or cur_border, "#ffffff", 0.35)
                if self._hovered
                else (self._chevron_color or cur_border)
            )
            self.create_text(
                int(w - 14),
                cy_i,
                text=self._chevron,
                font=self._font,
                fill=c_col,
            )
        else:
            self.create_text(
                int(w // 2),
                cy_i,
                text=self._text,
                font=self._font,
                fill=cur_fg,
            )


def make_stadium_button(parent, text="", **kwargs):
    """Factory helper to create a GlassStadiumButton."""
    if text and "text" not in kwargs:
        kwargs["text"] = text
    return GlassStadiumButton(parent, **kwargs)

SCHWAB_TOKEN_PATH = os.path.join(USER_HOME, "schwab_token.json")
CONFIG_PATH = os.path.join(USER_HOME, "enforcer_config.json")
LOG_PATH = os.path.join(USER_HOME, "enforcer_log.txt")
SANITIZED_LOG_PATH = os.path.join(USER_HOME, "enforcer_log_sanitized.txt")
LOG_ARCHIVE_DIR = os.path.join(USER_HOME, "enforcer_logs")
SANITIZED_ARCHIVE_DIR = os.path.join(LOG_ARCHIVE_DIR, "sanitized")
LOG_RETENTION_DAYS = 90
CALLBACK_URL = "https://127.0.0.1"
BUG_REPORT_FORM_URL = "https://tally.so/r/Z98y4V"
BETA_TELEMETRY_WEBHOOK_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbwNR51toSgE4izajaN1hvX0R84Z6m169JNTD-54CTzu9sAVvOz0Ripk3BU-u59bZJ_W/exec"
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("webull").setLevel(logging.CRITICAL)
logging.getLogger("webull.core").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ==========================================
# 2. DEFAULT CONFIGURATION
# ==========================================
WAIVER_VERSION = "2026.11.12"
OPTIONS_WAIVER_VERSION = "2026.11.10-BETA"

OPTIONS_WAIVER_TEXT = (
    "1. EXPERIMENTAL BETA FEATURE — USE AT YOUR OWN SOLE RISK:\n"
    "   Automated Options Flattening is an experimental BETA feature provided strictly 'AS IS' without warranty\n"
    "   of any kind. By enabling this toggle, you expressly release, indemnify, and hold harmless the author(s)\n"
    "   and contributors from any and all claims, damages, or financial losses arising from option orders.\n\n"
    "2. SEVERE BID-ASK SPREAD & MARKET ORDER SLIPPAGE RISK:\n"
    "   When an Open PnL Stop or Daily Stop triggers with this toggle enabled, Enforcer submits RTH Market\n"
    "   orders (BUY_TO_CLOSE / SELL_TO_CLOSE) to exit open option contracts immediately. Unlike liquid stocks,\n"
    "   options frequently have WIDE BID-ASK SPREADS, thin order books, or zero bids. Submitting a Market order\n"
    "   on an option contract can result in SEVERE SLIPPAGE and fills far worse than the displayed mark price.\n\n"
    "3. MULTI-LEG SPREADS & MARGIN REJECTION RISK:\n"
    "   Enforcer liquidates open options leg-by-leg as individual single-leg Market orders (buying back short\n"
    "   option legs first before selling long option legs), NOT as a single complex net-debit/net-credit spread\n"
    "   order. Legging out of spreads, condors, or covered positions via Market orders carries compounding\n"
    "   slippage on each leg and may be rejected by your broker's margin or options-approval level.\n\n"
    "4. REGULAR TRADING HOURS (9:30 AM – 4:00 PM ET) ONLY:\n"
    "   Standard US equity options only trade during Regular Trading Hours (9:30 AM – 4:00 PM ET) and cannot\n"
    "   be auto-flattened in Pre-Market or After-Hours. If any option contract fails to close, is rejected,\n"
    "   or has no bid, Enforcer will abort Windows OS Lock / App Kill and sound the continuous emergency siren.\n\n"
    "5. 100% SOLE RESPONSIBILITY FOR ACCOUNT & FILLS:\n"
    "   You acknowledge that automated option liquidation is a last-resort mechanical backstop, not a substitute\n"
    "   for in-broker stop orders or active risk management, and you assume 100% sole responsibility for all fills."
)


def get_options_waiver_expected_sha():
    return hashlib.sha256(OPTIONS_WAIVER_TEXT.encode("utf-8")).hexdigest()


def is_options_waiver_verified(cfg=None):
    c = cfg or config
    return bool(
        c.get("options_waiver_accepted", False)
        and c.get("options_waiver_version") == OPTIONS_WAIVER_VERSION
        and c.get("options_waiver_sha256") == get_options_waiver_expected_sha()
    )


def is_options_flatten_armed(cfg=None):
    c = cfg or config
    return bool(
        not c.get("alarms_only_mode", False)
        and c.get("enable_flatten_options", False)
        and is_options_waiver_verified(c)
    )


DEFAULT_CONFIG = {
    "waiver_accepted": False,
    "waiver_accepted_version": "",
    "waiver_accepted_at": "",
    "waiver_sha256": "",
    "options_waiver_accepted": False,
    "options_waiver_version": "",
    "options_waiver_accepted_at": "",
    "options_waiver_sha256": "",
    "auto_share_sanitized_logs": False,
    "last_uploaded_sanitized_log": "",
    "anonymous_tester_id": "",
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
    "alarms_only_mode": False,
    "enable_auto_flatten": False,
    "enable_flatten_options": False,
    "enable_kill_tos": False,
    "enable_kill_webull": False,
    "enable_lock_os": False,
    "daily_lock_mins": 15.0,
    "enable_open_flatten": False,
    "open_max_loss": 500.0,
    "enable_consec_loss_cooldown": False,
    "consec_loss_count": 3,
    "consec_loss_min_dollars": 25.0,
    "consec_win_reset_dollars": 10.0,
    "consec_loss_window_mins": 15.0,
    "enable_open_cooldown": False,
    "open_cooldown_mins": 1.0,
    "enable_voice_cues": True,
    "tts_voice": "Zira",
    "enable_upside_chime": True,
    "hud_columns": [
        "realized_pnl",
        "open_pnl",
        "terminate_lvl",
        "dist_to_term",
        "session_high",
    ],
    "reset_at_925": True,
    "ignore_preexisting_positions": True,
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
    "t2_max_loss": -1000.0,
    "t3_trigger": 500.0,
    "t3_max_loss": -500.0,
    "t4_trigger": 1000.0,
    "t4_trail": 500.0,
    "signed_tier_stops": True,
    "session_date": "",
    "saved_start_equity": None,
    "saved_max_equity": None,
    "saved_daily_max_equity": None,
    "saved_last_flat_equity": None,
    "saved_has_reset_at_open": False,
    "saved_has_reset_at_close": False,
    "saved_win_trades": 0,
    "saved_loss_trades": 0,
    "saved_account_id": ""
}

SIGNED_DOLLAR_KEYS = ("t2_max_loss", "t3_max_loss")

def _discover_windows_tts_voices():
    """Dynamically enumerates installed Windows OneCore and SAPI5 TTS voices
    from the local Windows Registry (<1ms) with a safe fallback."""
    found = {}
    try:
        import winreg
        reg_paths = (
            r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens",
            r"SOFTWARE\Microsoft\Speech\Voices\Tokens",
        )
        for r_path in reg_paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r_path) as k_root:
                    num_sub = winreg.QueryInfoKey(k_root)[0]
                    for i in range(num_sub):
                        sub_name = winreg.EnumKey(k_root, i)
                        try:
                            with winreg.OpenKey(
                                k_root, f"{sub_name}\\Attributes"
                            ) as k_attr:
                                raw_name, _ = winreg.QueryValueEx(k_attr, "Name")
                                try:
                                    gender, _ = winreg.QueryValueEx(
                                        k_attr, "Gender"
                                    )
                                except OSError:
                                    gender = ""
                                short_id = (
                                    str(raw_name)
                                    .replace("Microsoft ", "")
                                    .replace(" Desktop", "")
                                    .strip()
                                )
                                if short_id and short_id not in found:
                                    lbl = (
                                        f"{short_id} ({gender})"
                                        if gender
                                        else short_id
                                    )
                                    found[short_id] = (lbl, short_id)
                        except OSError:
                            continue
            except OSError:
                continue
    except Exception:
        pass

    if not found:
        return [
            ("Zira (Female)", "Zira"),
            ("Mark (Male)", "Mark"),
            ("David (Male)", "David"),
        ]

    preferred_order = ["Zira", "Mark", "David"]
    ordered = [found.pop(k) for k in preferred_order if k in found]
    ordered.extend(sorted(found.values(), key=lambda x: x[0]))
    return ordered


TTS_VOICE_CATALOG = _discover_windows_tts_voices()
TTS_LABEL_TO_ID = {lbl: vid for lbl, vid in TTS_VOICE_CATALOG}
TTS_ID_TO_LABEL = {vid: lbl for lbl, vid in TTS_VOICE_CATALOG}

HUD_COLUMN_CATALOG = [
    ("realized_pnl", "REALIZED PnL", "Closed (flat) PnL for the day"),
    ("open_pnl", "OPEN PnL", "Live unrealized PnL on open positions"),
    ("net_pnl", "NET PnL", "Total daily PnL (Realized + Open)"),
    ("terminate_lvl", "DAILY STOP", "Active Rulebook stop (Starting Max Loss, Ratcheted Tier, or Trailing Profit Lock)"),
    ("dist_to_term", "$ TO STOP", "Remaining dollar cushion before hitting your active Daily Stop"),
    ("session_high", "SESSION HIGH", "Highest flat realized PnL of the day"),
    ("from_high", "FROM HIGH", "Current drawdown/giveback from Session High"),
    ("trades_wl", "TRADES (W/L)", "Completed round-trip Wins & Losses (%)"),
    ("loss_streak", "LOSS STREAK", "Consecutive qualifying losses (e.g. 3/5) & live reset timer"),
]
HUD_COL_HEADERS = {col_id: hdr for col_id, hdr, _ in HUD_COLUMN_CATALOG}
DEFAULT_HUD_COLUMNS = [
    "realized_pnl",
    "open_pnl",
    "terminate_lvl",
    "dist_to_term",
    "session_high",
]
COMPACT_HUD_COLUMNS = [
    "net_pnl",
    "terminate_lvl",
    "dist_to_term",
]

HALF_RISK_DOLLARS = {
    "open_max_loss": 250.0,
    "consec_loss_min_dollars": 12.5,
    "pm_warn_1": 250.0,
    "pm_warn_2": 500.0,
    "pm_max_loss": 750.0,
    "pm_lock_trigger": 250.0,
    "pm_trail_cushion": 250.0,
    "t1_warn_1": 500.0,
    "t1_warn_2": 750.0,
    "t1_max_loss": 1000.0,
    "t2_trigger": 125.0,
    "t2_max_loss": -500.0,
    "t3_trigger": 250.0,
    "t3_max_loss": -250.0,
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
anchor_cash_flow = 0.0
_last_logged_unanchored_cash_flow = 0.0
has_reset_at_open = False
has_reset_at_close = False
is_locked_down = False
force_reanchor = False
current_is_flat = True
first_poll_of_launch = True

alarm_active = False
cooldown_active = False
dry_run_lock_active = False
consecutive_api_failures = 0
api_disconnect_alerted = False
cooldown_end_time = 0.0
cooldown_label = "COOL-DOWN LOCK"
cooldown_30s_announced = False
cooldown_announced_mins = set()
current_upside_tier = 1
last_rth_mode = None
win_trades = 0
loss_trades = 0
prev_flat_realized_pnl = 0.0
settled_realized_pnl = None
flat_desync_streak = 0
in_trade_desync_streak = 0
pending_scale_out_tol = 0.0
recent_loss_timestamps = []
triggered_alarms = {}
pending_halt_breach = None
ALARM_COOLDOWN_SEC = 180
RECOVERY_BUFFER_DOLLARS = 150.0

settings_win_open = False
broker_reconfig_in_progress = False
active_preflight_close_fn = None
active_preflight_win = None
last_preflight_pos = None
log_lock = threading.Lock()
prev_pos_snapshot = {}
ignored_positions = {}
active_adapter = None


def get_eastern_now():
    """Returns the current datetime in US Eastern Time (America/New_York,
    automatically handling EST UTC-5 and EDT UTC-4 via US DST rules) so market
    hours (9:30 AM, 4:00 PM ET) and session dates are 100% synced
    regardless of the user's local computer timezone."""
    utc_now = datetime.now(timezone.utc)
    y = utc_now.year
    # US DST starts 2nd Sunday in March at 02:00 EST (07:00 UTC)
    mar1_w = datetime(y, 3, 1).weekday()
    dst_start_day = 8 + (6 - mar1_w) % 7
    dst_start_utc = datetime(y, 3, dst_start_day, 7, 0, 0, tzinfo=timezone.utc)
    # US DST ends 1st Sunday in November at 02:00 EDT (06:00 UTC)
    nov1_w = datetime(y, 11, 1).weekday()
    dst_end_day = 1 + (6 - nov1_w) % 7
    dst_end_utc = datetime(y, 11, dst_end_day, 6, 0, 0, tzinfo=timezone.utc)
    offset_hours = -4 if (dst_start_utc <= utc_now < dst_end_utc) else -5
    return (utc_now + timedelta(hours=offset_hours)).replace(tzinfo=None)


def get_today_str():
    return get_eastern_now().strftime("%Y-%m-%d")


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


def is_compact_hud(cfg=None):
    """Returns True when the HUD is configured with 3 or fewer columns
    (Small HUD mode), enabling compact status pill text."""
    return len(get_active_hud_columns(cfg)) <= 3


def compute_hud_width(n_cols):
    """Computes HUD pixel width: preserves the classic 480px (3-col) and
    800px (5-col) layouts while tapering column width for 6–8 columns so the
    bar does not over-stretch across the screen."""
    n = max(1, int(n_cols))
    if n <= 3:
        return 480
    if n == 4:
        return 640
    if n == 5:
        return 800
    if n == 6:
        return 840
    if n == 7:
        return 900
    return n * 120


def format_hud_cols_btn_label(cols):
    return f"📊 HUD Columns ({len(cols)})"


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


def _format_countdown_mm_ss(seconds):
    """Formats a positive second count as MM:SS (or H:MM:SS if >= 60 mins)."""
    s = max(0, int(seconds))
    m, sec = divmod(s, 60)
    if m >= 60:
        h, rem_m = divmod(m, 60)
        return f"{h:d}:{rem_m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def get_loss_streak_status(now_ts=None):
    """Prunes expired timestamps from recent_loss_timestamps against the active
    rolling window and returns:
      (cur_streak, req_losses, next_drop_sec, full_clear_sec, is_enabled)
    where next_drop_sec is seconds until the oldest loss ages out (-1 to streak)
    and full_clear_sec is seconds until the newest loss ages out (0/X clear)."""
    global recent_loss_timestamps
    if now_ts is None:
        now_ts = time.time()
    req_losses = max(2, int(round(float(config.get("consec_loss_count", 3)))))
    win_mins = max(0.5, float(config.get("consec_loss_window_mins", 15.0)))
    win_sec = win_mins * 60.0
    is_enabled = (
        not config.get("alarms_only_mode", False)
        and bool(config.get("enable_consec_loss_cooldown", False))
    )
    if recent_loss_timestamps:
        recent_loss_timestamps[:] = [
            float(ts)
            for ts in recent_loss_timestamps
            if 0.0 <= (now_ts - float(ts)) < win_sec
        ]
    cur_streak = len(recent_loss_timestamps)
    if cur_streak > 0:
        oldest_rem = (recent_loss_timestamps[0] + win_sec) - now_ts
        newest_rem = (recent_loss_timestamps[-1] + win_sec) - now_ts
        next_drop_sec = max(1, int(math.ceil(oldest_rem)))
        full_clear_sec = max(1, int(math.ceil(newest_rem)))
    else:
        next_drop_sec = 0
        full_clear_sec = 0
    return cur_streak, req_losses, next_drop_sec, full_clear_sec, is_enabled


def format_loss_streak_multiline(now_ts=None):
    """Returns (two_line_text, bg_hex) for the HUD 'LOSS STREAK' column."""
    cur_s, req_l, next_s, _full_s, is_en = get_loss_streak_status(now_ts)
    if cur_s <= 0:
        top_ln = f"0 / {req_l}" if is_en else f"0 / {req_l} (OFF)"
        return f"{top_ln}\nCLEAR", "#2c3e50"
    timer_str = _format_countdown_mm_ss(next_s)
    if not is_en:
        bg_c = "#2c3e50"
    elif cur_s >= (req_l - 1):
        bg_c = "#b03a2e"
    else:
        bg_c = "#d35400"
    return f"{cur_s} / {req_l}\nRST {timer_str}", bg_c


def format_loss_streak_inline(now_ts=None):
    """Returns a single-line streak summary for the HUD bottom-left badge."""
    cur_s, req_l, next_s, _full_s, is_en = get_loss_streak_status(now_ts)
    if cur_s > 0:
        return f"STREAK: {cur_s}/{req_l} ({_format_countdown_mm_ss(next_s)})"
    if is_en:
        return f"STREAK: 0/{req_l} (CLEAR)"
    return f"STREAK: 0/{req_l} (OFF)"


def format_dist_to_stop_hud(distance_to_terminate, locked_down=None):
    """Formats the HUD '$ TO STOP' ('dist_to_term') column value.
    When the Daily Stop is breached/disarmed (is_locked_down) or distance <= 0,
    displays a clear two-line 'BREACHED\\n-$X.XX OVER' readout instead of a
    raw negative dollar string like '$-449.91'."""
    is_ld = is_locked_down if locked_down is None else bool(locked_down)
    dist_val = round(float(distance_to_terminate), 2)
    if is_ld or dist_val <= 0.0:
        if dist_val <= 0.0:
            return f"BREACHED\n-${abs(dist_val):,.2f} OVER"
        return f"BREACHED\n+${dist_val:,.2f} BUF"
    return f"${dist_val:,.2f}"


def describe_active_floor(cfg=None, rth_mode=None):
    """Returns (floor_equity, stop_pnl, hud_hdr_tag, tier_short_label,
    tier_full_desc, setting_field_hint) for the currently active Daily Stop
    tier so the HUD, Post-Breach Review dialog, and audit logs always state
    explicitly WHICH rulebook & tier controls the active floor."""
    c = cfg or config
    rth_now = is_rth() if rth_mode is None else bool(rth_mode)
    if start_equity is None or start_equity <= 0.0:
        if not rth_now:
            pm_max = float(c.get("pm_max_loss", 1500.0))
            return (
                None,
                -pm_max,
                "EXT",
                "Ext-Hours Base Stop",
                f"Ext-Hours Starting Max Loss (-${pm_max:,.0f})",
                "Card 4 'Starting Max Loss ($)'",
            )
        t1_max = float(c.get("t1_max_loss", 2000.0))
        return (
            None,
            -t1_max,
            "T1",
            "RTH Tier 1 Base",
            f"RTH Tier 1 Starting Max Loss (-${t1_max:,.0f})",
            "Card 5 'Starting Max Loss ($)'",
        )

    hwm_eq = max_equity if max_equity is not None else start_equity
    max_realized_profit = round(hwm_eq - start_equity, 2)
    if not rth_now:
        pm_lock_on = bool(c.get("enable_pm_lock", True))
        pm_trig = float(c.get("pm_lock_trigger", 500.0))
        pm_trail = float(c.get("pm_trail_cushion", 500.0))
        pm_max = float(c.get("pm_max_loss", 1500.0))
        if pm_lock_on and max_realized_profit >= pm_trig:
            fl_eq = hwm_eq - pm_trail
            st_pnl = round(fl_eq - start_equity, 2)
            return (
                fl_eq,
                st_pnl,
                "EXT LOCK",
                "Ext-Hours Profit Lock",
                f"Ext-Hours Profit Lock (Unlocked at High {format_dollar(max_realized_profit)} >= +${pm_trig:,.0f}, Trail ${pm_trail:,.0f})",
                "Card 4 'Trail Peak By ($)' (or uncheck 'Profit Lock Trigger')",
            )
        fl_eq = start_equity - pm_max
        return (
            fl_eq,
            round(fl_eq - start_equity, 2),
            "EXT",
            "Ext-Hours Base Stop",
            f"Ext-Hours Starting Max Loss (-${pm_max:,.0f})",
            "Card 4 'Starting Max Loss ($)'",
        )

    t4_on = bool(c.get("enable_t4", True))
    t3_on = bool(c.get("enable_t3", True))
    t2_on = bool(c.get("enable_t2", True))
    t4_trig = float(c.get("t4_trigger", 1000.0))
    t4_trail = float(c.get("t4_trail", 500.0))
    t3_trig = float(c.get("t3_trigger", 500.0))
    t3_max = float(c.get("t3_max_loss", -500.0))
    t2_trig = float(c.get("t2_trigger", 250.0))
    t2_max = float(c.get("t2_max_loss", -1000.0))
    t1_max = float(c.get("t1_max_loss", 2000.0))
    if t4_on and max_realized_profit >= t4_trig:
        fl_eq = hwm_eq - t4_trail
        st_pnl = round(fl_eq - start_equity, 2)
        return (
            fl_eq,
            st_pnl,
            "T4",
            "RTH Tier 4 Trail",
            f"RTH Tier 4 Trailing Lock (Unlocked at RTH High {format_dollar(max_realized_profit)} >= +${t4_trig:,.0f}, Trail ${t4_trail:,.0f})",
            "Card 5 'Tier 4 — Trail Peak By ($)' (or uncheck Tier 4)",
        )
    if t3_on and max_realized_profit >= t3_trig:
        fl_eq = start_equity + t3_max
        st_pnl = round(fl_eq - start_equity, 2)
        return (
            fl_eq,
            st_pnl,
            "T3",
            "RTH Tier 3 Ratchet",
            f"RTH Tier 3 Stop Ratchet (Unlocked at RTH High {format_dollar(max_realized_profit)} >= +${t3_trig:,.0f})",
            "Card 5 'Tier 3 — Stop Level ($)' (or uncheck Tier 3)",
        )
    if t2_on and max_realized_profit >= t2_trig:
        fl_eq = start_equity + t2_max
        st_pnl = round(fl_eq - start_equity, 2)
        return (
            fl_eq,
            st_pnl,
            "T2",
            "RTH Tier 2 Ratchet",
            f"RTH Tier 2 Stop Ratchet (Unlocked at RTH High {format_dollar(max_realized_profit)} >= +${t2_trig:,.0f})",
            "Card 5 'Tier 2 — Stop Level ($)' (or uncheck Tier 2)",
        )
    fl_eq = start_equity - t1_max
    return (
        fl_eq,
        round(fl_eq - start_equity, 2),
        "T1",
        "RTH Tier 1 Base",
        f"RTH Tier 1 Starting Max Loss (-${t1_max:,.0f})",
        "Card 5 'Starting Max Loss ($)'",
    )


def compute_active_floor_equity(cfg=None, rth_mode=None):
    """Computes the active Daily Stop floor equity for the given config and
    session state (or returns None if start_equity is not yet initialized)."""
    return describe_active_floor(cfg, rth_mode)[0]


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
def _archive_previous_log_and_prune(today_str):
    """Archives an older enforcer_log.txt into ~/enforcer_logs/enforcer_log_YYYY-MM-DD.txt
    and prunes archived log files older than LOG_RETENTION_DAYS (90 days)."""
    archived_path = None
    pruned_count = 0

    try:
        os.makedirs(LOG_ARCHIVE_DIR, exist_ok=True)
    except Exception:
        return None, 0

    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if content.strip():
                first_line = content.splitlines()[0] if content else ""
                m = re.search(r"DATE:\s*(\d{4}-\d{2}-\d{2})", first_line)
                if m:
                    old_date = m.group(1)
                else:
                    mtime = os.path.getmtime(LOG_PATH)
                    old_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

                if old_date != today_str:
                    dest_path = os.path.join(
                        LOG_ARCHIVE_DIR, f"enforcer_log_{old_date}.txt"
                    )
                    if os.path.exists(dest_path):
                        with open(dest_path, "a", encoding="utf-8") as af:
                            af.write("\n" + content)
                    else:
                        with open(dest_path, "w", encoding="utf-8") as af:
                            af.write(content)
                    archived_path = dest_path
        except Exception as e:
            print(f"Could not archive previous log file: {e}")

    try:
        cutoff_dt = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
        cutoff_date_str = cutoff_dt.strftime("%Y-%m-%d")
        for fname in os.listdir(LOG_ARCHIVE_DIR):
            m = re.match(r"^enforcer_log_(\d{4}-\d{2}-\d{2})\.txt$", fname)
            if m and m.group(1) < cutoff_date_str:
                try:
                    os.remove(os.path.join(LOG_ARCHIVE_DIR, fname))
                    pruned_count += 1
                except Exception:
                    pass
    except Exception:
        pass

    return archived_path, pruned_count


def _mask_last4(val):
    """Masks an order ID or account identifier to its last 4 characters."""
    s = str(val or "").strip()
    if len(s) > 4:
        return f"...{s[-4:]}"
    return s


def _mask_user_path(text):
    """Replaces the user's home directory path with '~' so Windows usernames
    are never exposed in log files (including JSON-escaped double/quadruple
    backslash paths emitted by third-party SDKs)."""
    out = str(text or "")
    if USER_HOME:
        norm_home = USER_HOME.replace("/", "\\")
        for variant in (
            norm_home.replace("\\", "\\\\\\\\"),
            norm_home.replace("\\", "\\\\"),
            USER_HOME,
            USER_HOME.replace("\\", "/"),
            norm_home,
        ):
            if variant:
                out = re.sub(
                    re.escape(variant), "~", out, flags=re.IGNORECASE
                )
    out = re.sub(r"[A-Za-z]:(?:\\+Users\\+|/Users/)[^\\/\s'\"]+", "~", out)
    return out


def _scrub_log_line(message):
    """Sanitizes a single log message before writing to disk:
    - Masks USER_HOME paths as '~' (including JSON-escaped backslashes)
    - Masks any configured account_id (>4 chars) to '...last4'
    - Masks URL /accounts/<hash> segments, Bearer/OAuth tokens, and SDK JSON headers
    - Masks any long numeric/alphanumeric order IDs in cancel/order lines"""
    msg = _mask_user_path(message)

    try:
        brokers_cfg = config.get("brokers", {})
        for b_info in brokers_cfg.values():
            if isinstance(b_info, dict):
                aid = str(b_info.get("selected_account_id") or "").strip()
                if len(aid) > 4:
                    msg = msg.replace(aid, _mask_last4(aid))
                for secret_k in ("app_key", "app_secret"):
                    sec_v = str(b_info.get(secret_k) or "").strip()
                    if len(sec_v) > 4:
                        msg = msg.replace(sec_v, "[REDACTED]")
    except Exception:
        pass

    # Scrub /accounts/<hash> in HTTP exception URLs
    msg = re.sub(
        r"(/accounts/)([A-Za-z0-9_-]{5,})",
        lambda m: f"{m.group(1)}...{m.group(2)[-4:]}",
        msg,
    )
    # Scrub Bearer tokens and OAuth query/body parameters
    msg = re.sub(
        r"(Bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"\1[REDACTED]",
        msg,
        flags=re.IGNORECASE,
    )
    msg = re.sub(
        r"((?:access_token|refresh_token|id_token|client_secret|app_secret|code)=)[^&\s'\"]+",
        r"\1[REDACTED]",
        msg,
        flags=re.IGNORECASE,
    )
    # Scrub JSON/dict serialized SDK auth headers (e.g. Webull x-access-token, x-signature)
    msg = re.sub(
        r'(["\'](?:x-access-token|x-signature|x-app-key|access_token|refresh_token|id_token|client_secret|app_secret|authorization)["\']\s*:\s*["\'])[^"\']+(["\'])',
        r"\1[REDACTED]\2",
        msg,
        flags=re.IGNORECASE,
    )
    # Ensure any order ID in cancel/order log lines is masked to last 4
    msg = re.sub(
        r"(order ID:\s*)(?!\.\.\.)([A-Za-z0-9_-]{5,})",
        lambda m: f"{m.group(1)}...{m.group(2)[-4:]}",
        msg,
        flags=re.IGNORECASE,
    )
    msg = re.sub(
        r"(Cancel response\s+)(?!\.\.\.)([A-Za-z0-9_-]{5,})(:)",
        lambda m: f"{m.group(1)}...{m.group(2)[-4:]}{m.group(3)}",
        msg,
        flags=re.IGNORECASE,
    )
    return msg


def sanitize_log_for_export(raw_log_text):
    """Produces a share-safe version of a session log with all total account
    balances/equities redacted ($[REDACTED]) while keeping all relative PnL
    (Realized, Open, Net, High, ratchets, and risk floors) intact."""
    lines = str(raw_log_text or "").splitlines()
    out_lines = []
    inserted_notice = False

    for line in lines:
        s = _scrub_log_line(line)
        # Redact total account equity / balance figures while keeping relative PnL
        s = re.sub(
            r"(Baseline anchored to:\s*)\$[0-9,]+(?:\.[0-9]{2})?",
            r"\1$[REDACTED]",
            s,
        )
        s = re.sub(
            r"((?:Start|Baseline|LastFlat|TotalAccountValue|NetLiq|Cash|MarketVal)=)\$[0-9,]+(?:\.[0-9]{2})?",
            r"\1$[REDACTED]",
            s,
        )
        out_lines.append(s)
        if not inserted_notice and s.startswith("==="):
            out_lines.append(
                "[SANITIZED EXPORT: Total account balances, user paths, "
                "and full order IDs redacted for safe sharing]"
            )
            inserted_notice = True

    return "\n".join(out_lines) + "\n"


def _sync_sanitized_log_archive():
    """Ensures every archived log in ~/enforcer_logs/ has a corresponding
    balance-redacted copy in ~/enforcer_logs/sanitized/enforcer_log_YYYY-MM-DD_sanitized.txt
    (retroactively backfilling any existing archived logs) and prunes files
    older than LOG_RETENTION_DAYS."""
    backfilled = 0
    try:
        os.makedirs(LOG_ARCHIVE_DIR, exist_ok=True)
        os.makedirs(SANITIZED_ARCHIVE_DIR, exist_ok=True)
    except Exception:
        return 0

    cutoff_dt = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    cutoff_date_str = cutoff_dt.strftime("%Y-%m-%d")

    try:
        for fname in os.listdir(LOG_ARCHIVE_DIR):
            m = re.match(r"^enforcer_log_(\d{4}-\d{2}-\d{2})\.txt$", fname)
            if not m:
                continue
            date_part = m.group(1)
            raw_path = os.path.join(LOG_ARCHIVE_DIR, fname)
            if date_part < cutoff_date_str:
                continue
            san_fname = f"enforcer_log_{date_part}_sanitized.txt"
            san_path = os.path.join(SANITIZED_ARCHIVE_DIR, san_fname)
            needs_gen = not os.path.exists(san_path)
            if not needs_gen:
                try:
                    if os.path.getmtime(raw_path) > os.path.getmtime(san_path):
                        needs_gen = True
                except OSError:
                    pass
            if needs_gen:
                try:
                    with open(
                        raw_path, "r", encoding="utf-8", errors="replace"
                    ) as rf:
                        raw_txt = rf.read()
                    san_txt = sanitize_log_for_export(raw_txt)
                    with open(san_path, "w", encoding="utf-8") as sf:
                        sf.write(san_txt)
                    backfilled += 1
                except Exception:
                    pass
    except Exception:
        pass

    try:
        for s_fname in os.listdir(SANITIZED_ARCHIVE_DIR):
            m_s = re.match(
                r"^enforcer_log_(\d{4}-\d{2}-\d{2})_sanitized\.txt$", s_fname
            )
            if m_s and m_s.group(1) < cutoff_date_str:
                try:
                    os.remove(os.path.join(SANITIZED_ARCHIVE_DIR, s_fname))
                except Exception:
                    pass
    except Exception:
        pass

    return backfilled


_telemetry_auto_upload_in_flight = False


def _upload_sanitized_log_to_drive(
    filename, sanitized_text, active_broker, anonymous_id
) -> bool:
    """Uploads a balance-redacted session log to the Google Apps Script Drive
    webhook. Treats HTTP 200 or Google Apps Script's post-write 302/405 redirect
    to googleusercontent.com as True; returns False on network timeouts or
    400/403/413/500 errors without raising."""
    import urllib.error
    import urllib.request

    try:
        payload_bytes = json.dumps(
            {
                "filename": str(filename),
                "version": APP_VERSION,
                "broker": str(active_broker or "SCHWAB"),
                "tester_id": str(anonymous_id or ""),
                "content": str(sanitized_text or ""),
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            BETA_TELEMETRY_WEBHOOK_URL,
            data=payload_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            return code == 200 or (200 <= int(code or 0) < 300)
    except urllib.error.HTTPError as he:
        code = int(getattr(he, "code", 0) or 0)
        err_url = str(getattr(he, "url", "") or "").lower()
        loc_hdr = ""
        try:
            if getattr(he, "headers", None) is not None:
                loc_hdr = str(he.headers.get("Location", "") or "").lower()
        except Exception:
            pass
        if code == 200:
            return True
        if code in (302, 405) and (
            "googleusercontent.com" in err_url
            or "googleusercontent.com" in loc_hdr
        ):
            return True
        return False
    except Exception:
        return False


def _find_most_recent_prior_sanitized_log():
    """Returns (filename, full_path) for the most recent prior-day sanitized log
    in ~/enforcer_logs/sanitized/ (where YYYY-MM-DD < get_today_str()), or
    (None, None) if none exists."""
    today_str = get_today_str()
    best_date = ""
    best_fname = None
    best_path = None
    try:
        if not os.path.isdir(SANITIZED_ARCHIVE_DIR):
            return None, None
        for s_fname in os.listdir(SANITIZED_ARCHIVE_DIR):
            m_s = re.match(
                r"^enforcer_log_(\d{4}-\d{2}-\d{2})_sanitized\.txt$", s_fname
            )
            if not m_s:
                continue
            d_part = m_s.group(1)
            if d_part < today_str and d_part > best_date:
                cand_path = os.path.join(SANITIZED_ARCHIVE_DIR, s_fname)
                try:
                    if os.path.isfile(cand_path) and os.path.getsize(cand_path) > 0:
                        best_date = d_part
                        best_fname = s_fname
                        best_path = cand_path
                except OSError:
                    pass
    except Exception:
        return None, None
    return best_fname, best_path


def _maybe_upload_prior_day_sanitized_log():
    """Non-blocking startup auto-uploader: if auto_share_sanitized_logs is True,
    checks for the most recent prior-day sanitized log in ~/enforcer_logs/sanitized/
    and uploads it in a background daemon thread if not already uploaded."""
    global _telemetry_auto_upload_in_flight
    try:
        if _telemetry_auto_upload_in_flight:
            return
        if not config.get("auto_share_sanitized_logs", False):
            return
        fname, fpath = _find_most_recent_prior_sanitized_log()
        if not fname or not fpath:
            return
        if fname == config.get("last_uploaded_sanitized_log", ""):
            return
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            san_text = f.read()
        if not san_text.strip():
            return

        tester_id = str(config.get("anonymous_tester_id", "") or "").strip()
        if not tester_id:
            tester_id = uuid.uuid4().hex[:6]
            config["anonymous_tester_id"] = tester_id
            save_config(config)
        active_b = str(config.get("active_broker", "SCHWAB") or "SCHWAB")
        _telemetry_auto_upload_in_flight = True

        def _bg_upload():
            global _telemetry_auto_upload_in_flight
            try:
                ok = _upload_sanitized_log_to_drive(
                    fname, san_text, active_b, tester_id
                )
                if ok:
                    config["last_uploaded_sanitized_log"] = fname
                    save_config(config)
                    log_event(
                        "TELEMETRY",
                        f"Auto-shared prior-day sanitized log "
                        f"({fname}, Tester ID: {tester_id})",
                    )
            except Exception:
                pass
            finally:
                _telemetry_auto_upload_in_flight = False

        threading.Thread(target=_bg_upload, daemon=True).start()
    except Exception:
        _telemetry_auto_upload_in_flight = False


def _get_os_env_summary():
    py_ver = sys.version.split()[0]
    try:
        wv = sys.getwindowsversion()
        os_lbl = "Win11" if wv.build >= 22000 else f"Win{wv.major}"
        os_str = f"{os_lbl}(Build {wv.build})"
    except Exception:
        os_str = sys.platform
    return f"OS={os_str} | Py={py_ver}"


def init_daily_log():
    today_str = get_today_str()
    env_info = _get_os_env_summary()
    header_line = (
        f"=== ENFORCER SESSION LOG | v{APP_VERSION} | DATE: {today_str} | {env_info} ===\n"
    )
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
            archived_path, pruned_cnt = _archive_previous_log_and_prune(today_str)
            _sync_sanitized_log_archive()
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.write(header_line)
                f.write(f"Log File Path: {_mask_user_path(LOG_PATH)}\n")
                f.write(
                    f"Archive Folder ({LOG_RETENTION_DAYS}-day retention): "
                    f"{_mask_user_path(LOG_ARCHIVE_DIR)}\n" + "=" * 50 + "\n"
                )
            log_event(
                "SESSION",
                f"Initialized fresh daily log file (v{APP_VERSION} | {env_info})."
            )
            if archived_path:
                log_event(
                    "SESSION",
                    f"Archived previous session log to: {_mask_user_path(archived_path)}"
                )
            if pruned_cnt > 0:
                log_event(
                    "SESSION",
                    f"Pruned {pruned_cnt} archived log(s) older than "
                    f"{LOG_RETENTION_DAYS} days."
                )
        else:
            _sync_sanitized_log_archive()
            log_event(
                "SESSION",
                f"--- APPLICATION LAUNCHED / RESUMED (v{APP_VERSION} | {env_info}) ---"
            )
        load_config(log_restore=False)
        _maybe_upload_prior_day_sanitized_log()
    except Exception as e:
        try:
            print(f"Could not initialize log file: {e}")
        except Exception:
            pass


def log_event(category, message):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    clean_msg = _scrub_log_line(message)
    line = f"[{ts}] [{category:<10}] {clean_msg}"
    try:
        print(line)
    except Exception:
        pass
    with log_lock:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            try:
                print(f"Log write error: {e}")
            except Exception:
                pass


def _custom_showwarning(message, category, filename, lineno, file=None, line=None):
    short_file = os.path.basename(str(filename)) if filename else "unknown"
    cat_name = getattr(category, "__name__", str(category))
    msg_clean = str(message).strip().replace("\n", " ")
    if cat_name == "AuthlibDeprecationWarning" or "httpx2" in msg_clean:
        return
    log_event("PY_WARN", f"{cat_name} ({short_file}:{lineno}): {msg_clean}")


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


class _StderrToLogTee:
    """Tees any raw stderr output (such as Tcl/Tk C-level 'after' script errors
    or C-extension messages) into enforcer_log.txt while preserving console stderr."""

    def __init__(self, orig_stderr):
        self._orig = orig_stderr
        self._buf = ""
        self._in_write = False

    def write(self, data):
        if self._orig is not None:
            try:
                self._orig.write(data)
            except Exception:
                pass
        if self._in_write or not data:
            return
        try:
            self._in_write = True
            self._buf += str(data)
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                clean = line.strip()
                if clean and not re.match(r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\]", clean):
                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    scrubbed = _scrub_log_line(clean)
                    entry = f"[{ts}] [{'STDERR':<10}] {scrubbed}"
                    with log_lock:
                        try:
                            with open(LOG_PATH, "a", encoding="utf-8") as f:
                                f.write(entry + "\n")
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            self._in_write = False

    def flush(self):
        if self._orig is not None:
            try:
                self._orig.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._orig, name)


def _install_global_error_hooks():
    """Routes all uncaught main-thread, background-thread, Tkinter callback,
    and Tcl/stderr errors into enforcer_log.txt."""
    warnings.showwarning = _custom_showwarning
    logging.getLogger().addHandler(_EnforcerFileLogHandler())
    if not isinstance(sys.stderr, _StderrToLogTee):
        sys.stderr = _StderrToLogTee(sys.stderr)

    def _handle_uncaught(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        tb_str = " | ".join(
            ln.strip()
            for ln in traceback.format_exception(exc_type, exc_value, exc_tb)
            if ln.strip()
        )
        log_event("UNCAUGHT", tb_str)

    def _handle_thread_uncaught(args):
        if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
            return
        t_name = getattr(args.thread, "name", "Thread")
        tb_str = " | ".join(
            ln.strip()
            for ln in traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback
            )
            if ln.strip()
        )
        log_event("THRD_ERR", f"[{t_name}] {tb_str}")

    def _handle_tk_callback_exc(self, exc_type, exc_value, exc_tb):
        tb_str = " | ".join(
            ln.strip()
            for ln in traceback.format_exception(exc_type, exc_value, exc_tb)
            if ln.strip()
        )
        log_event("TK_ERROR", tb_str)

    sys.excepthook = _handle_uncaught
    if hasattr(threading, "excepthook"):
        threading.excepthook = _handle_thread_uncaught
    tk.Tk.report_callback_exception = _handle_tk_callback_exc


if __name__ == "__main__":
    _install_global_error_hooks()


def format_config_summary(cfg):
    broker = cfg.get("active_broker", "SCHWAB")
    cd_str = (
        f"ON({cfg.get('open_cooldown_mins', 1):g}m)"
        if cfg.get("enable_open_cooldown") else "OFF"
    )
    tilt_str = (
        f"ON({int(cfg.get('consec_loss_count', 3))}L/"
        f"{cfg.get('consec_loss_window_mins', 15):g}m, "
        f"Loss<=-${abs(float(cfg.get('consec_loss_min_dollars', 25))):,.0f}, "
        f"WinRst>=+${abs(float(cfg.get('consec_win_reset_dollars', 10))):,.0f})"
        if cfg.get("enable_consec_loss_cooldown") else "OFF"
    )
    dl_mins = cfg.get("daily_lock_mins", 15.0)
    dl_str = (
        f"ON({dl_mins:g}m)" if dl_mins > 0 else "ON(Once)"
    ) if cfg.get("enable_lock_os") else "OFF"
    eh_lock_str = (
        f"ON(+${cfg.get('pm_lock_trigger', 500):,.0f}/Trail:${cfg.get('pm_trail_cushion', 500):,.0f})"
        if cfg.get("enable_pm_lock", True)
        else "OFF"
    )
    t2_str = (
        f"ON(+${cfg.get('t2_trigger', 250):,.0f}->${cfg.get('t2_max_loss', -1000):+,.0f})"
        if cfg.get("enable_t2", True)
        else "OFF"
    )
    t3_str = (
        f"ON(+${cfg.get('t3_trigger', 500):,.0f}->${cfg.get('t3_max_loss', -500):+,.0f})"
        if cfg.get("enable_t3", True)
        else "OFF"
    )
    t4_str = (
        f"ON(+${cfg.get('t4_trigger', 1000):,.0f}/Trail:${cfg.get('t4_trail', 500):,.0f})"
        if cfg.get("enable_t4", True)
        else "OFF"
    )

    return (
        f"Broker={broker} | Cols={len(get_active_hud_columns(cfg))} | "
        f"Poll={cfg.get('poll_interval')}s | "
        f"AlarmsOnly={'ON' if cfg.get('alarms_only_mode') else 'OFF'} | "
        f"OpenStop={'ON' if cfg.get('enable_open_flatten') else 'OFF'}"
        f"(-${cfg.get('open_max_loss', 0):,.0f}, CoolDown={cd_str}) | "
        f"TiltStop={tilt_str} | "
        f"DayFlat={'ON' if cfg.get('enable_auto_flatten') else 'OFF'} | "
        f"OptFlat={'ON(BETA)' if is_options_flatten_armed(cfg) else 'OFF'} | "
        f"KillTOS={'ON' if cfg.get('enable_kill_tos') else 'OFF'} | "
        f"KillWB={'ON' if cfg.get('enable_kill_webull') else 'OFF'} | "
        f"LockOS={dl_str} | "
        f"Voice={'ON' if cfg.get('enable_voice_cues', True) else 'OFF'} | "
        f"UpChime={'ON' if cfg.get('enable_upside_chime', True) else 'OFF'} | "
        f"ResetSwitch={'ON' if cfg.get('reset_at_925', True) else 'OFF'} | "
        f"IgnorePrePos={'ON' if cfg.get('ignore_preexisting_positions', True) else 'OFF'} | "
        f"EH_Max=-${cfg.get('pm_max_loss', 0):,.0f} | "
        f"EH_Lock={eh_lock_str} | "
        f"T1_Max=-${cfg.get('t1_max_loss', 0):,.0f} | "
        f"T2={t2_str} | T3={t3_str} | T4={t4_str}"
    )


def restore_account_session(broker_name, account_id, log_restore=False):
    """Restores today's saved baseline for a specific broker + account_id.
    Returns True if a valid baseline for today was found, False otherwise."""
    global start_equity, max_equity, daily_max_equity
    global last_flat_equity, anchor_cash_flow, _last_logged_unanchored_cash_flow
    global has_reset_at_open, has_reset_at_close
    global win_trades, loss_trades, prev_flat_realized_pnl
    global settled_realized_pnl, flat_desync_streak
    global in_trade_desync_streak, pending_scale_out_tol
    global current_upside_tier, first_poll_of_launch, recent_loss_timestamps
    global ignored_positions, pending_halt_breach

    recent_loss_timestamps.clear()
    ignored_positions.clear()
    pending_halt_breach = None
    flat_desync_streak = 0
    in_trade_desync_streak = 0
    pending_scale_out_tol = 0.0
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
            anchor_cash_flow = float(
                s_data.get("anchor_cash_flow", 0.0) or 0.0
            )
            has_reset_at_open = bool(
                s_data.get("has_reset_at_open", False)
            )
            has_reset_at_close = bool(
                s_data.get("has_reset_at_close", False)
            )
            win_trades = int(s_data.get("win_trades", 0) or 0)
            loss_trades = int(s_data.get("loss_trades", 0) or 0)
            saved_lts = s_data.get("loss_timestamps")
            if isinstance(saved_lts, list):
                now_ts = time.time()
                win_sec = max(
                    0.5, float(config.get("consec_loss_window_mins", 15.0))
                ) * 60.0
                recent_loss_timestamps.extend(
                    float(t)
                    for t in saved_lts
                    if isinstance(t, (int, float))
                    and 0.0 <= (now_ts - float(t)) < win_sec
                )
            saved_ig = s_data.get("ignored_positions")
            if isinstance(saved_ig, dict):
                ignored_positions.update(json.loads(json.dumps(saved_ig)))
            prev_flat_realized_pnl = round(last_flat_equity - start_equity, 2)
            settled_realized_pnl = prev_flat_realized_pnl
            if (
                "win_trades" not in s_data
                and win_trades == 0
                and loss_trades == 0
            ):
                bw, bl, _ = backfill_trades_from_today_log(broker_name)
                if bw > 0 or bl > 0:
                    win_trades, loss_trades = bw, bl
            current_upside_tier = compute_upside_tier(
                is_rth(), round(max_equity - start_equity, 2), config
            )
            first_poll_of_launch = True
            if log_restore:
                ig_note = (
                    f" | IgnoredPreExisting={list(ignored_positions.keys())}"
                    if ignored_positions
                    else ""
                )
                _, st_pnl, _, tier_short, _, _ = describe_active_floor(config)
                log_event(
                    "SESSION",
                    f"Restored {broker_name} baseline from memory: "
                    f"Start=${start_equity:,.2f} | "
                    f"LastFlat=${last_flat_equity:,.2f} | "
                    f"RulebookHWM={format_dollar(max_equity - start_equity)} | "
                    f"SessionHighPnL={format_dollar(daily_max_equity - start_equity)} | "
                    f"ActiveStop={format_dollar(st_pnl)} ({tier_short}) | "
                    f"{format_trades_wl_inline(win_trades, loss_trades)}{ig_note}"
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
        has_reset_at_close = bool(config.get("saved_has_reset_at_close", False))
        win_trades = int(config.get("saved_win_trades", 0) or 0)
        loss_trades = int(config.get("saved_loss_trades", 0) or 0)
        prev_flat_realized_pnl = round(last_flat_equity - start_equity, 2)
        settled_realized_pnl = prev_flat_realized_pnl
        if win_trades == 0 and loss_trades == 0:
            bw, bl, _ = backfill_trades_from_today_log(broker_name)
            if bw > 0 or bl > 0:
                win_trades, loss_trades = bw, bl
        current_upside_tier = compute_upside_tier(
            is_rth(), round(max_equity - start_equity, 2), config
        )
        first_poll_of_launch = True
        if log_restore:
            _, st_pnl, _, tier_short, _, _ = describe_active_floor(config)
            log_event(
                "SESSION",
                f"Restored {broker_name} baseline from memory: "
                f"Start=${start_equity:,.2f} | "
                f"LastFlat=${last_flat_equity:,.2f} | "
                f"RulebookHWM={format_dollar(max_equity - start_equity)} | "
                f"SessionHighPnL={format_dollar(daily_max_equity - start_equity)} | "
                f"ActiveStop={format_dollar(st_pnl)} ({tier_short}) | "
                f"{format_trades_wl_inline(win_trades, loss_trades)}"
            )
        return True

    start_equity = None
    max_equity = None
    daily_max_equity = None
    last_flat_equity = None
    anchor_cash_flow = 0.0
    has_reset_at_open = False
    has_reset_at_close = False
    win_trades = 0
    loss_trades = 0
    prev_flat_realized_pnl = 0.0
    settled_realized_pnl = None
    current_upside_tier = 1
    first_poll_of_launch = True
    return False


def load_config(log_restore=False):
    global config
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                was_signed = bool(saved.get("signed_tier_stops", False))
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

                # One-time migration: convert legacy unsigned t2_max_loss /
                # t3_max_loss values (where 1000 meant -$1000) to signed values.
                if not was_signed:
                    for sk in SIGNED_DOLLAR_KEYS:
                        if sk in config and float(config[sk]) > 0:
                            config[sk] = -abs(float(config[sk]))
                        if (
                            isinstance(config.get("user_defaults"), dict)
                            and sk in config["user_defaults"]
                            and float(config["user_defaults"][sk]) > 0
                        ):
                            config["user_defaults"][sk] = -abs(
                                float(config["user_defaults"][sk])
                            )
                    config["signed_tier_stops"] = True
                    save_config(config)
        except Exception as e:
            print(f"Could not load saved config: {e}")

    tester_id = str(config.get("anonymous_tester_id", "") or "").strip()
    if not tester_id:
        config["anonymous_tester_id"] = uuid.uuid4().hex[:6]
        save_config(config)

    active_b = config.get("active_broker", "SCHWAB")
    sel_acct = (
        config["brokers"].get(active_b, {}).get("selected_account_id", "")
    )
    if (start_equity is None or log_restore) and sel_acct:
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
        "anchor_cash_flow": round(float(anchor_cash_flow or 0.0), 2),
        "has_reset_at_open": has_reset_at_open,
        "has_reset_at_close": has_reset_at_close,
        "win_trades": win_trades,
        "loss_trades": loss_trades,
        "loss_timestamps": [round(float(t), 2) for t in recent_loss_timestamps],
        "ignored_positions": json.loads(json.dumps(ignored_positions)),
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
        or config.get("saved_has_reset_at_close") != has_reset_at_close
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
        config["saved_has_reset_at_close"] = has_reset_at_close
        config["saved_win_trades"] = win_trades
        config["saved_loss_trades"] = loss_trades
        config["saved_account_id"] = sel_acct
        save_config(config)


def get_unanchored_cash_flow(intraday_cf):
    """Returns the net intraday cash deposit/transfer that has occurred SINCE
    `start_equity` was anchored today (`intraday_cf - anchor_cash_flow`).
    Subtracting this from raw liquidationValue prevents mid-session cash
    deposits from inflating Realized/Net PnL while preserving the user's
    morning baseline unless they explicitly Re-Zero Baseline."""
    global _last_logged_unanchored_cash_flow
    if (
        force_reanchor
        or start_equity is None
        or float(start_equity) <= 0.0
    ):
        return 0.0
    unanchored = round(
        float(intraday_cf or 0.0) - float(anchor_cash_flow or 0.0), 2
    )
    if abs(unanchored) < 0.01:
        _last_logged_unanchored_cash_flow = 0.0
        return 0.0
    if abs(unanchored - _last_logged_unanchored_cash_flow) >= 0.01:
        _last_logged_unanchored_cash_flow = unanchored
        cf_kind = "deposit" if unanchored >= 0.0 else "withdrawal"
        log_event(
            "SESSION",
            f"Neutralized intraday cash {cf_kind}/transfer of "
            f"{format_dollar(unanchored)} from daily PnL calculation "
            f"(Baseline=${start_equity:,.2f} preserved; use Re-Zero Baseline "
            f"if you wish to reset PnL to $0.00).",
        )
    return unanchored


def is_position_ignored(sym_or_tag, is_opt=False):
    """Returns True if sym_or_tag is currently registered in ignored_positions
    and 'ignore_preexisting_positions' is enabled in config."""
    if not config.get("ignore_preexisting_positions", True) or not ignored_positions:
        return False
    s = str(sym_or_tag or "").strip()
    if not s:
        return False
    tag = f"{s} (OPT)" if (is_opt and not s.endswith(" (OPT)")) else s
    if tag in ignored_positions:
        return True
    base_s = s[:-6].strip() if s.endswith(" (OPT)") else s
    for ig_tag, ig in ignored_positions.items():
        if not isinstance(ig, dict):
            continue
        ig_is_opt = (ig.get("asset_type") == "OPTION") or ig_tag.endswith(" (OPT)")
        if bool(is_opt) != bool(ig_is_opt):
            continue
        if (
            str(ig.get("symbol", "")).strip() == base_s
            or str(ig.get("raw_symbol", "")).strip() == base_s
        ):
            return True
    return False


def build_ignored_position_entry(tag, d, lock_existing_open_pnl=False):
    """Builds a fresh ignored_positions entry from a raw position dict d.
    If lock_existing_open_pnl is True (e.g. a new position opened mid-day while
    Enforcer was closed and marked Ignored on re-launch without re-zeroing
    start_equity), initializes locked_impact to d['open_pnl'] so its unrealized
    gain/loss since purchase is neutralized relative to the morning baseline."""
    qty = float(d.get("qty", 0.0))
    lp = float(d.get("last", 0.0))
    avg = float(d.get("avg", 0.0))
    opnl = round(float(d.get("open_pnl", 0.0)), 2)
    a_type = str(d.get("asset_type", "EQUITY")).upper()
    base_sym = tag[:-6].strip() if str(tag).endswith(" (OPT)") else str(tag)
    init_locked = opnl if lock_existing_open_pnl else 0.0
    return {
        "symbol": str(d.get("symbol") or base_sym),
        "raw_symbol": str(d.get("raw_symbol") or base_sym),
        "asset_type": a_type,
        "init_qty": qty,
        "init_price": round(lp, 4),
        "ref_qty": qty,
        "ref_price": round(lp, 4),
        "ref_avg": round(avg, 4),
        "ref_open_pnl": opnl,
        "last_seen_price": round(lp, 4),
        "locked_impact": init_locked,
    }


def reanchor_ignored_positions_to_live(raw_pos_details):
    """Re-anchors all currently tracked ignored_positions entries to their
    current live price with locked_impact = 0.0 when start_equity is freshly
    anchored or re-zeroed."""
    if not ignored_positions or not isinstance(raw_pos_details, dict):
        return
    for tag, ig in list(ignored_positions.items()):
        if not isinstance(ig, dict):
            continue
        d = raw_pos_details.get(tag)
        if d is not None:
            qty = float(d.get("qty", 0.0))
            lp = float(d.get("last", 0.0))
            avg = float(d.get("avg", 0.0))
            opnl = round(float(d.get("open_pnl", 0.0)), 2)
            ig["init_qty"] = qty
            ig["init_price"] = round(lp, 4)
            ig["ref_qty"] = qty
            ig["ref_price"] = round(lp, 4)
            ig["ref_avg"] = round(avg, 4)
            ig["ref_open_pnl"] = opnl
            ig["last_seen_price"] = round(lp, 4)
            ig["locked_impact"] = 0.0
        else:
            ig["ref_qty"] = 0.0
            ig["ref_open_pnl"] = 0.0
            ig["locked_impact"] = 0.0


def _apply_ignored_positions_to_snapshot(
    raw_adj_eq, raw_pos_details, open_eq_cache, open_opt_cache
):
    """Filters out any ignored pre-existing positions (Ticker-Level Ignore) from
    pos_details, open_pnl, has_options, and flatten caches, and neutralizes
    their intraday PnL impact (across price moves, adds, partial sells, and
    full closes) from raw_adj_eq."""
    if not isinstance(raw_pos_details, dict):
        raw_pos_details = {}
    if not config.get("ignore_preexisting_positions", True) or not ignored_positions:
        tot_open = round(
            sum(float(d.get("open_pnl", 0.0)) for d in raw_pos_details.values()),
            2,
        )
        has_opt = any(
            d.get("asset_type") == "OPTION" for d in raw_pos_details.values()
        )
        return (
            raw_adj_eq,
            (len(raw_pos_details) == 0),
            tot_open,
            dict(raw_pos_details),
            has_opt,
            list(open_eq_cache or []),
            list(open_opt_cache or []),
        )

    filt_pos_details = {
        k: v
        for k, v in raw_pos_details.items()
        if not is_position_ignored(k, v.get("asset_type") == "OPTION")
    }
    filt_eq_cache = [
        item
        for item in (open_eq_cache or [])
        if not is_position_ignored(item[0], is_opt=False)
    ]
    filt_opt_cache = [
        item
        for item in (open_opt_cache or [])
        if not is_position_ignored(item[0], is_opt=True)
    ]
    tot_open_pnl = round(
        sum(float(d.get("open_pnl", 0.0)) for d in filt_pos_details.values()),
        2,
    )
    has_options = any(
        d.get("asset_type") == "OPTION" for d in filt_pos_details.values()
    )
    is_flat = (len(filt_pos_details) == 0)

    sum_ignored_impact = 0.0
    state_mutated = False
    mutated_igs = []
    transition_notes = []

    for tag, ig in list(ignored_positions.items()):
        if not isinstance(ig, dict):
            continue
        d = raw_pos_details.get(tag)
        if d is None:
            base_s = str(ig.get("symbol", "")).strip()
            for cand_tag, cand_d in raw_pos_details.items():
                cand_base = (
                    cand_tag[:-6].strip()
                    if str(cand_tag).endswith(" (OPT)")
                    else str(cand_tag)
                )
                if cand_base == base_s and (
                    cand_d.get("asset_type") == ig.get("asset_type")
                ):
                    d = cand_d
                    break

        a_type = str(
            (d or {}).get("asset_type") or ig.get("asset_type") or "EQUITY"
        ).upper()
        mult = 100.0 if a_type == "OPTION" else 1.0
        ref_qty = float(ig.get("ref_qty", 0.0))
        ref_price = float(ig.get("ref_price", 0.0))
        ref_avg = float(ig.get("ref_avg", 0.0))
        ref_open_pnl = ig.get("ref_open_pnl")
        last_seen_lp = float(ig.get("last_seen_price") or ref_price)
        locked_impact = float(ig.get("locked_impact", 0.0))

        if d is None or float(d.get("qty", 0.0)) == 0.0:
            # Position is currently closed (0 shares/contracts)
            if abs(ref_qty) > 1e-6:
                exit_lp = last_seen_lp if last_seen_lp > 0 else ref_price
                locked_impact = round(
                    locked_impact + ref_qty * (exit_lp - ref_price) * mult, 2
                )
                transition_notes.append(
                    f"{tag}: {int(ref_qty):+d} -> 0 (Ignored position closed @ ~${exit_lp:.4f})"
                )
                ig["ref_qty"] = 0.0
                ig["ref_price"] = round(exit_lp, 4)
                ig["ref_avg"] = 0.0
                ig["ref_open_pnl"] = 0.0
                ig["locked_impact"] = locked_impact
                state_mutated = True
                mutated_igs.append(ig)
            sum_ignored_impact += locked_impact
            continue

        curr_qty = float(d.get("qty", 0.0))
        curr_lp = float(d.get("last", 0.0))
        curr_avg = float(d.get("avg", 0.0))
        curr_open_pnl = float(d.get("open_pnl", 0.0))

        if abs(curr_qty - ref_qty) > 1e-6:
            # Ignored position quantity changed (added, trimmed, re-opened, or flipped)
            if abs(ref_qty) < 1e-6:
                # Re-opened from 0 on an ignored ticker
                locked_impact = round(locked_impact + curr_open_pnl, 2)
            elif (curr_qty * ref_qty) > 0 and abs(curr_qty) > abs(ref_qty):
                # Added to ignored position in same direction (0 shares closed,
                # so exact equity delta since ref is curr_open_pnl - ref_open_pnl)
                if ref_open_pnl is not None:
                    locked_impact = round(
                        locked_impact + (curr_open_pnl - float(ref_open_pnl)), 2
                    )
                else:
                    added_q = curr_qty - ref_qty
                    old_delta = ref_qty * (curr_lp - ref_price) * mult
                    new_delta = 0.0
                    if curr_avg > 0 and ref_avg > 0 and abs(added_q) > 1e-6:
                        inferred_fill = (
                            (abs(curr_qty) * curr_avg) - (abs(ref_qty) * ref_avg)
                        ) / abs(added_q)
                        if (
                            curr_lp > 0
                            and (0.5 * curr_lp) <= inferred_fill <= (1.5 * curr_lp)
                        ):
                            new_delta = added_q * (curr_lp - inferred_fill) * mult
                    locked_impact = round(locked_impact + old_delta + new_delta, 2)
            elif (curr_qty * ref_qty) > 0 and abs(curr_qty) < abs(ref_qty):
                # Trimmed / partially sold ignored position
                locked_impact = round(
                    locked_impact + ref_qty * (curr_lp - ref_price) * mult, 2
                )
            else:
                # Flipped sign on ignored ticker
                locked_impact = round(
                    locked_impact
                    + ref_qty * (curr_lp - ref_price) * mult
                    + curr_open_pnl,
                    2,
                )
            transition_notes.append(
                f"{tag}: {int(ref_qty):+d} -> {int(curr_qty):+d} (Ignored ticker)"
            )
            ig["ref_qty"] = curr_qty
            ig["ref_price"] = round(curr_lp, 4)
            ig["ref_avg"] = round(curr_avg, 4)
            ig["ref_open_pnl"] = round(curr_open_pnl, 2)
            ig["last_seen_price"] = round(curr_lp, 4)
            ig["locked_impact"] = locked_impact
            state_mutated = True
            mutated_igs.append(ig)
            sum_ignored_impact += locked_impact
        else:
            ig["last_seen_price"] = round(curr_lp, 4)
            open_impact = curr_qty * (curr_lp - ref_price) * mult
            sum_ignored_impact += locked_impact + open_impact

    if state_mutated:
        if mutated_igs and raw_adj_eq is not None:
            tracked_qty_changed = (
                set(filt_pos_details.keys()) != set(prev_pos_snapshot.keys())
                or any(
                    abs(
                        float(filt_pos_details[k].get("qty", 0.0))
                        - float(prev_pos_snapshot[k].get("qty", 0.0))
                    )
                    > 1e-6
                    for k in filt_pos_details
                )
            )
            ref_flat_eq = (
                last_flat_equity if last_flat_equity is not None else start_equity
            )
            if (
                not tracked_qty_changed
                and ref_flat_eq is not None
                and float(ref_flat_eq) > 0.0
            ):
                target_sum_ignored = round(
                    (float(raw_adj_eq) - tot_open_pnl) - float(ref_flat_eq), 2
                )
                drift = round(target_sum_ignored - sum_ignored_impact, 2)
                if abs(drift) >= 0.01 and abs(drift) <= 50000.0:
                    last_ig = mutated_igs[-1]
                    last_ig["locked_impact"] = round(
                        float(last_ig.get("locked_impact", 0.0)) + drift, 2
                    )
                    sum_ignored_impact = round(sum_ignored_impact + drift, 2)
        save_session_state()
        if transition_notes:
            log_event(
                "SESSION",
                f"Ignored pre-existing position activity neutralized: "
                f"{', '.join(transition_notes)}",
            )

    adj_eq = (
        round(float(raw_adj_eq) - sum_ignored_impact, 2)
        if raw_adj_eq is not None
        else None
    )
    return (
        adj_eq,
        is_flat,
        tot_open_pnl,
        filt_pos_details,
        has_options,
        filt_eq_cache,
        filt_opt_cache,
    )


def is_rth():
    now = get_eastern_now().time()
    return dt_time(9, 30) <= now < dt_time(16, 0)


def is_after_hours():
    now = get_eastern_now().time()
    return now >= dt_time(16, 0)


def is_market_hours():
    now = get_eastern_now().time()
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


def compute_book_confirmed_price(
    lp, bid=None, ask=None, mark=None, acct_lp=None, net_qty=0
):
    """Computes the book-confirmed reference price across the live NBBO midpoint
    (or mark) and the broker's position snapshot price so real market moves fire
    immediately (0s delay) while single-order wicks or entry-sweep quote lags
    are caught and verified."""
    def _pos_f(v):
        try:
            f = float(v)
            return f if f > 0.0 else None
        except Exception:
            return None

    b = _pos_f(bid)
    a = _pos_f(ask)
    m = _pos_f(mark)
    ac = _pos_f(acct_lp)

    if b is not None and a is not None and b <= a:
        mid_p = round((b + a) / 2.0, 4)
    elif m is not None:
        mid_p = m
    else:
        mid_p = lp

    cands = [lp, mid_p]
    if ac is not None:
        cands.append(ac)
    if net_qty > 0:
        return max(cands)
    if net_qty < 0:
        return min(cands)
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
    pf_win = globals().get("active_preflight_win")
    if pf_win is not None:
        try:
            if not pf_win.winfo_exists():
                pf_win = None
        except Exception:
            pf_win = None
    parent = pf_win or getattr(tk, "_default_root", None)
    is_standalone = parent is None

    dlg = tk.Tk() if is_standalone else tk.Toplevel(parent)
    dlg.withdraw()
    if not is_standalone:
        dlg.grab_set()

    dlg.title("Schwab 7-Day Security Login — Step-by-Step")
    dlg.config(bg="#0d1117", padx=24, pady=18)
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)

    tk.Label(
        dlg,
        text="🔐 SCHWAB 7-DAY SECURITY LOGIN (STEP-BY-STEP)",
        font=("Arial", 12, "bold"),
        fg="#5dade2",
        bg="#0d1117",
        anchor="w"
    ).pack(fill="x", pady=(0, 8))

    steps_outer = tk.Frame(
        dlg, bg="#131922", bd=0, highlightthickness=1, highlightbackground="#243040"
    )
    steps_outer.pack(fill="x", pady=(0, 12))
    NeonBarCanvas(
        steps_outer, core_color="#38bdf8", card_bg="#131922", glow_on=True
    ).pack(side="left", fill="y")
    steps_frame = tk.Frame(
        steps_outer, bg="#131922", padx=16, pady=12
    )
    steps_frame.pack(side="left", fill="both", expand=True)

    tk.Label(
        steps_frame,
        text=(
            "STEP 1: Log into your Charles Schwab account in the browser window that just opened\n"
            "        and approve account access. (If your browser didn't open, click the link below):"
        ),
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#131922",
        justify="left",
        anchor="w"
    ).pack(fill="x", pady=(0, 4))

    link_lbl = tk.Label(
        steps_frame,
        text="🌐 Click Here to Open / Re-Open the Charles Schwab Login Page in Your Browser",
        font=("Arial", 10, "bold underline"),
        fg="#38bdf8",
        bg="#131922",
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
        fg="#97a7b9",
        bg="#131922",
        justify="left",
        anchor="w"
    ).pack(fill="x")

    tk.Label(
        dlg,
        text="Redirected Browser URL (https://127.0.0.1/?code=...):",
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#0d1117",
        anchor="w"
    ).pack(fill="x", pady=(2, 4))

    url_entry = tk.Entry(
        dlg,
        font=("Consolas", 10, "bold"),
        width=74,
        bg="#12202e",
        fg="#e2e8f0",
        insertbackground="#e2e8f0",
        bd=0,
        highlightthickness=1,
        highlightbackground="#294760",
        highlightcolor="#38bdf8"
    )
    url_entry.pack(fill="x", pady=(0, 6), ipady=4)
    url_entry.focus_set()

    status_lbl = tk.Label(
        dlg,
        text="⏳ Waiting for https://127.0.0.1/?code=... URL (auto-fills as soon as you copy it in your browser)...",
        font=("Arial", 9, "bold"),
        fg="#f5b041",
        bg="#0d1117",
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

    btn_row = tk.Frame(dlg, bg="#0d1117", pady=6)
    btn_row.pack(fill="x")

    make_stadium_button(
        btn_row,
        text="Cancel",
        font=("Arial", 10, "bold"),
        fill_color="#182230",
        border_color="#52657c",
        hover_fill="#223042",
        hover_border="#7a90ad",
        fg="#e2e8f0",
        canvas_bg="#0d1117",
        width=108,
        height=36,
        pad_x=28,
        glow_strength=0.38,
        command=dlg.destroy,
    ).pack(side="left")

    make_stadium_button(
        btn_row,
        text="📋 Paste from Clipboard",
        font=("Arial", 10, "bold"),
        fill_color="#142942",
        border_color="#38bdf8",
        hover_fill="#1c3859",
        hover_border="#7dd3fc",
        fg="#e0f2fe",
        canvas_bg="#0d1117",
        width=192,
        height=36,
        pad_x=28,
        glow_strength=0.45,
        command=paste_from_clipboard,
    ).pack(side="left", padx=10)

    make_stadium_button(
        btn_row,
        text="Complete Schwab Login >>",
        font=("Arial", 10, "bold"),
        fill_color="#105e35",
        border_color="#22ff88",
        hover_fill="#157a46",
        hover_border="#69f0ae",
        glow_color="#00e676",
        fg="#ffffff",
        canvas_bg="#0d1117",
        width=226,
        height=36,
        pad_x=32,
        glow_strength=0.65,
        command=submit_url,
    ).pack(side="right")

    center_dialog_over_parent(dlg, parent=parent)
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
        self._last_good_snapshot = {}
        self._last_raw_pos_details = {}
        self._last_open_eq = {}
        self._last_open_opt = {}
        self._last_intraday_cash_flow = {}
        self.last_preserved_close_qty = {}
        self.last_cancel_failed_syms = set()
        self._rate_limit_until = 0.0
        self._last_429_log_ts = 0.0
        self.last_error = ""

    def get_last_raw_pos_details(self):
        return json.loads(
            json.dumps(self._last_raw_pos_details.get(self.account_id, {}))
        )

    def get_last_intraday_cash_flow(self):
        return float(self._last_intraday_cash_flow.get(self.account_id, 0.0))

    def authenticate(self):
        try:
            from schwab.auth import client_from_manual_flow, client_from_token_file
        except ImportError:
            print("[SETUP] Installing required Schwab SDK (schwab-py)...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "schwab-py"],
                check=False
            )
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
                try:
                    self.client.set_timeout(4.5)
                except Exception:
                    pass
                resp = self.client.get_account_numbers()
                if resp.status_code == 200:
                    self._parse_accounts(resp.json())
                    return True
                if resp.status_code in (400, 401, 403):
                    raise RuntimeError(
                        f"Schwab token rejected (HTTP {resp.status_code})"
                    )
                raise ConnectionError(
                    f"Schwab API temporary HTTP {resp.status_code}"
                )
        except Exception as e:
            err_l = str(e).lower()
            is_token_invalid = any(
                k in err_l
                for k in (
                    "safety buffer",
                    "invalid_grant",
                    "unsupported_token_type",
                    "token rejected",
                    "expired",
                    "unauthorized",
                    "http 401",
                    "http 400",
                    "jsondecodeerror",
                )
            )
            if not is_token_invalid:
                log_event(
                    "WARN",
                    f"Schwab network/connection error during startup ({e}). "
                    f"Preserving saved token file.",
                )
                raise RuntimeError(
                    f"Network connection failed while reaching Schwab API ({e}).\n"
                    f"Your saved 7-day token was preserved — please check your internet connection and retry."
                ) from e
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
            try:
                self.client.set_timeout(4.5)
            except Exception:
                pass
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

    def reconnect_session(self):
        """Rebuilds the underlying Schwab HTTP client from SCHWAB_TOKEN_PATH
        with a 4.5s timeout to flush stale TCP sockets after an internet drop."""
        try:
            if os.path.exists(SCHWAB_TOKEN_PATH):
                from schwab.auth import client_from_token_file
                new_client = client_from_token_file(
                    SCHWAB_TOKEN_PATH, self.app_key, self.app_secret
                )
                try:
                    new_client.set_timeout(4.5)
                except Exception:
                    pass
                self.client = new_client
                return True
        except Exception as e:
            self.last_error = str(e)
        return False

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

    def cancel_all_working_orders(self, preserve_market_close_map=None):
        self.last_preserved_close_qty = {}
        self.last_cancel_failed_syms = set()
        preserve_map = (
            dict(preserve_market_close_map)
            if isinstance(preserve_market_close_map, dict)
            else {}
        )
        try:
            today_start = datetime.combine(
                get_eastern_now().date() - timedelta(days=2), dt_time(0, 0)
            )
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
            preserved_any = False
            for order in orders_resp.json():
                status = order.get("status")
                if status in active_statuses:
                    order_id = order.get("orderId")
                    masked_oid = _mask_last4(order_id)
                    legs = order.get("orderLegCollection") or []
                    if legs and all(
                        is_position_ignored(
                            (lg.get("instrument") or {}).get("symbol", ""),
                            is_opt=(
                                str(
                                    (lg.get("instrument") or {}).get(
                                        "assetType", ""
                                    )
                                ).upper()
                                == "OPTION"
                            ),
                        )
                        for lg in legs
                        if isinstance(lg, dict)
                    ):
                        leg_syms = [
                            (lg.get("instrument") or {}).get("symbol", "")
                            for lg in legs
                            if isinstance(lg, dict)
                        ]
                        log_event(
                            "FLATTEN",
                            f"Skipping working order {masked_oid} on ignored pre-existing ticker(s): {leg_syms}",
                        )
                        continue

                    order_type = str(order.get("orderType") or "").upper()
                    single_leg = (
                        legs[0]
                        if len(legs) == 1 and isinstance(legs[0], dict)
                        else None
                    )
                    leg_sym = (
                        str(
                            (single_leg.get("instrument") or {}).get(
                                "symbol", ""
                            )
                        ).strip()
                        if single_leg
                        else ""
                    )
                    leg_instr = (
                        str(single_leg.get("instruction") or "").upper()
                        if single_leg
                        else ""
                    )
                    try:
                        rem_q = float(
                            order.get("remainingQuantity")
                            or (single_leg or {}).get("quantity")
                            or order.get("quantity")
                            or 0.0
                        )
                    except Exception:
                        rem_q = 0.0

                    is_closing_dir = False
                    if leg_sym and leg_sym in preserve_map:
                        open_q = float(preserve_map[leg_sym])
                        if open_q > 0 and leg_instr in (
                            "SELL",
                            "SELL_TO_CLOSE",
                        ):
                            is_closing_dir = True
                        elif open_q < 0 and leg_instr in (
                            "BUY",
                            "BUY_TO_COVER",
                            "BUY_TO_CLOSE",
                        ):
                            is_closing_dir = True

                    if (
                        is_closing_dir
                        and is_market_hours()
                        and order_type == "MARKET"
                    ):
                        eff_q = rem_q if rem_q > 0 else abs(float(preserve_map[leg_sym]))
                        self.last_preserved_close_qty[leg_sym] = (
                            self.last_preserved_close_qty.get(leg_sym, 0.0)
                            + eff_q
                        )
                        preserved_any = True
                        log_event(
                            "FLATTEN",
                            f"Preserving working Schwab RTH Market close order {masked_oid} "
                            f"({leg_instr} {int(eff_q)} {leg_sym}, {status}) — "
                            f"keeping halt/auction queue priority.",
                        )
                        continue

                    log_event(
                        "FLATTEN",
                        f"Canceling Schwab order ID: {masked_oid} ({status})"
                    )
                    c_resp = self.client.cancel_order(self.account_id, order_id)
                    log_event(
                        "FLATTEN",
                        f"Cancel response {masked_oid}: HTTP {c_resp.status_code}"
                    )
                    if c_resp.status_code in (200, 201, 202, 204):
                        cancelled_any = True
                    else:
                        for lg in legs:
                            if isinstance(lg, dict):
                                s_nm = str(
                                    (lg.get("instrument") or {}).get(
                                        "symbol", ""
                                    )
                                ).strip()
                                if s_nm:
                                    self.last_cancel_failed_syms.add(s_nm)
                        if is_closing_dir and leg_sym:
                            eff_q = (
                                rem_q
                                if rem_q > 0
                                else abs(float(preserve_map[leg_sym]))
                            )
                            self.last_preserved_close_qty[leg_sym] = (
                                self.last_preserved_close_qty.get(leg_sym, 0.0)
                                + eff_q
                            )
            if cancelled_any:
                time.sleep(0.2)
            elif not preserved_any:
                log_event("FLATTEN", "No working orders found to cancel.")
            return cancelled_any
        else:
            log_event(
                "ERROR",
                f"Failed to query working orders: HTTP {orders_resp.status_code}"
            )
            return False

    def get_open_equity_positions(self):
        """Returns ONLY Equity positions for Auto-Flatten, or None on API error."""
        try:
            resp = self.client.get_account(
                self.account_id, fields=self.client.Account.Fields.POSITIONS
            )
            if resp.status_code == 200:
                open_eq = []
                open_opt = []
                sec_acc = resp.json().get("securitiesAccount", {})
                for pos in sec_acc.get("positions", []):
                    inst = pos.get("instrument", {})
                    a_type = inst.get("assetType")
                    qty = (
                        pos.get("longQuantity", 0)
                        - pos.get("shortQuantity", 0)
                    )
                    if qty != 0:
                        sym = inst.get("symbol", "")
                        if a_type == "EQUITY" and not is_position_ignored(
                            sym, is_opt=False
                        ):
                            open_eq.append((sym, qty))
                        elif a_type == "OPTION" and not is_position_ignored(
                            sym, is_opt=True
                        ):
                            open_opt.append((sym, qty))
                open_opt.sort(
                    key=lambda item: (0 if item[1] < 0 else 1, str(item[0]))
                )
                now_t = time.time()
                self._last_open_eq[self.account_id] = (now_t, list(open_eq))
                self._last_open_opt[self.account_id] = (now_t, list(open_opt))
                return open_eq
            log_event(
                "ERROR",
                f"get_open_equity_positions HTTP {resp.status_code}"
            )
        except Exception as e:
            log_event(
                "ERROR",
                f"Schwab get_open_equity_positions exception: {e}"
            )
        cached = self._last_open_eq.get(self.account_id)
        if cached and (time.time() - cached[0]) <= 10.0 and cached[1]:
            log_event(
                "FLATTEN",
                "Using cached Schwab open equity snapshot (<10s) after API error."
            )
            return [
                item
                for item in cached[1]
                if not is_position_ignored(item[0], is_opt=False)
            ]
        return None

    def get_open_option_positions(self):
        """Returns ONLY Option positions (symbol, qty) sorted with short legs
        (qty < 0) first for BETA Options Auto-Flatten, or None on API error."""
        cached = self._last_open_opt.get(self.account_id)
        if cached and (time.time() - cached[0]) < 0.45:
            return [
                item
                for item in cached[1]
                if not is_position_ignored(item[0], is_opt=True)
            ]
        try:
            resp = self.client.get_account(
                self.account_id, fields=self.client.Account.Fields.POSITIONS
            )
            if resp.status_code == 200:
                open_eq = []
                open_opt = []
                sec_acc = resp.json().get("securitiesAccount", {})
                for pos in sec_acc.get("positions", []):
                    inst = pos.get("instrument", {})
                    a_type = inst.get("assetType")
                    qty = (
                        pos.get("longQuantity", 0)
                        - pos.get("shortQuantity", 0)
                    )
                    if qty != 0:
                        sym = inst.get("symbol", "")
                        if a_type == "EQUITY" and not is_position_ignored(
                            sym, is_opt=False
                        ):
                            open_eq.append((sym, qty))
                        elif a_type == "OPTION" and not is_position_ignored(
                            sym, is_opt=True
                        ):
                            open_opt.append((inst["symbol"], qty))
                open_opt.sort(
                    key=lambda item: (0 if item[1] < 0 else 1, str(item[0]))
                )
                now_t = time.time()
                self._last_open_eq[self.account_id] = (now_t, list(open_eq))
                self._last_open_opt[self.account_id] = (now_t, list(open_opt))
                return open_opt
            log_event(
                "ERROR",
                f"Schwab get_open_option_positions HTTP {resp.status_code}"
            )
        except Exception as e:
            log_event(
                "ERROR",
                f"Schwab get_open_option_positions exception: {e}"
            )
        if cached and (time.time() - cached[0]) <= 10.0 and cached[1]:
            log_event(
                "FLATTEN",
                "Using cached Schwab open option snapshot (<10s) after API error."
            )
            return [
                item
                for item in cached[1]
                if not is_position_ignored(item[0], is_opt=True)
            ]
        return None

    def submit_option_liquidation_batch(self, open_opt_positions):
        """Submits single-leg RTH Market orders to close open option positions
        (BUY_TO_CLOSE on short legs first, then SELL_TO_CLOSE on long legs)."""
        submitted_ok = {}
        if not open_opt_positions:
            return submitted_ok
        if not is_market_hours():
            log_event(
                "GUARDRAIL",
                f"Cannot submit Schwab option market flatten outside RTH "
                f"(9:30 AM – 4:00 PM ET): {open_opt_positions}"
            )
            return submitted_ok
        from schwab.orders.options import (
            option_buy_to_close_market,
            option_sell_to_close_market,
        )
        sorted_opts = sorted(
            open_opt_positions,
            key=lambda item: (0 if item[1] < 0 else 1, str(item[0])),
        )
        for item in sorted_opts:
            symbol = item[0]
            qty = item[1]
            abs_q = int(abs(qty))
            if abs_q <= 0:
                continue
            try:
                if qty < 0:
                    log_event(
                        "ORDER_OUT",
                        f"Submitting Schwab RTH Option Market BUY_TO_CLOSE (BETA): "
                        f"{abs_q} {symbol}"
                    )
                    spec = option_buy_to_close_market(symbol, abs_q).build()
                    r = self.client.place_order(self.account_id, spec)
                    log_event(
                        "ORDER_RESP",
                        f"Schwab Option Buy-to-Close {symbol} -> HTTP {r.status_code}"
                    )
                    if r.status_code in (200, 201, 202):
                        submitted_ok[symbol] = float(abs_q)
                else:
                    log_event(
                        "ORDER_OUT",
                        f"Submitting Schwab RTH Option Market SELL_TO_CLOSE (BETA): "
                        f"{abs_q} {symbol}"
                    )
                    spec = option_sell_to_close_market(symbol, abs_q).build()
                    r = self.client.place_order(self.account_id, spec)
                    log_event(
                        "ORDER_RESP",
                        f"Schwab Option Sell-to-Close {symbol} -> HTTP {r.status_code}"
                    )
                    if r.status_code in (200, 201, 202):
                        submitted_ok[symbol] = float(abs_q)
            except Exception as e:
                log_event(
                    "ERROR",
                    f"Schwab option place_order exception ({symbol}): {e}"
                )
        return submitted_ok

    def submit_liquidation_batch(self, open_positions):
        from schwab.orders.common import Session, Duration
        from schwab.orders.equities import (
            equity_sell_market,
            equity_buy_to_cover_market,
            equity_sell_limit,
            equity_buy_to_cover_limit
        )
        submitted_ok = {}
        if not open_positions:
            return submitted_ok

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
                    if r.status_code in (200, 201, 202):
                        submitted_ok[symbol] = float(abs(qty))
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
                    if r.status_code in (200, 201, 202):
                        submitted_ok[symbol] = float(abs_q)
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
                    if r.status_code in (200, 201, 202):
                        submitted_ok[symbol] = float(abs(qty))
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
                    if r.status_code in (200, 201, 202):
                        submitted_ok[symbol] = float(abs_q)
        return submitted_ok

    def fetch_account_data(self):
        """Returns (adj_eq, is_flat, open_pnl, pos_details, has_options)
        tracking BOTH Equities (1x) and Options (100x)."""
        now_ts = time.time()
        if now_ts < self._rate_limit_until:
            cached_snap = self._last_good_snapshot.get(self.account_id)
            if cached_snap and (now_ts - cached_snap[0]) <= 15.0:
                return cached_snap[1]

        try:
            resp = self.client.get_account(
                self.account_id, fields=self.client.Account.Fields.POSITIONS
            )
            if resp.status_code == 200:
                self.last_error = ""
                data = resp.json().get("securitiesAccount", {})
                init_balances = data.get("initialBalances", {}) or {}
                balances = data.get("currentBalances", {}) or {}
                raw_eq = float(balances.get("liquidationValue", 0))
                init_cr = float(init_balances.get("cashReceipts") or 0.0)
                init_pend = float(init_balances.get("pendingDeposits") or 0.0)
                curr_cr = float(balances.get("cashReceipts") or 0.0)
                curr_pend = float(balances.get("pendingDeposits") or 0.0)
                cr_delta = curr_cr - init_cr
                new_pend = max(0.0, curr_pend - init_pend)
                intraday_cf = round(
                    (cr_delta + new_pend)
                    if cr_delta < 0.0
                    else max(cr_delta, new_pend),
                    2,
                )
                self._last_intraday_cash_flow[self.account_id] = intraday_cf
                raw_eq = round(
                    raw_eq - get_unanchored_cash_flow(intraday_cf), 2
                )

                positions = data.get("positions", [])
                open_assets = []
                open_eq_cache = []
                open_opt_cache = []
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
                                open_opt_cache.append(
                                    (pos["instrument"]["symbol"], net_q)
                                )
                            else:
                                open_eq_cache.append(
                                    (pos["instrument"]["symbol"], net_q)
                                )
                            open_assets.append((pos, net_q, a_type))

                open_opt_cache.sort(
                    key=lambda item: (0 if item[1] < 0 else 1, str(item[0]))
                )
                now_snap_t = time.time()

                if not open_assets:
                    self._last_raw_pos_details[self.account_id] = {}
                    (
                        adj_eq,
                        is_flat,
                        tot_open_pnl,
                        filt_pos,
                        has_opt,
                        filt_eq,
                        filt_opt,
                    ) = _apply_ignored_positions_to_snapshot(
                        raw_eq, {}, [], []
                    )
                    self._last_open_eq[self.account_id] = (now_snap_t, filt_eq)
                    self._last_open_opt[self.account_id] = (
                        now_snap_t,
                        filt_opt,
                    )
                    flat_res = (adj_eq, is_flat, tot_open_pnl, filt_pos, has_opt)
                    self._last_good_snapshot[self.account_id] = (
                        time.time(), flat_res
                    )
                    return flat_res

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

                    acct_lp = (
                        abs(acct_mkt_val / (net_q * mult))
                        if net_q != 0 else avg_price
                    )
                    if live_price is not None and float(live_price) > 0:
                        lp = float(live_price)
                        live_mkt_val = net_q * lp * mult
                        adj_eq += (live_mkt_val - acct_mkt_val)
                    else:
                        lp = acct_lp

                    if a_type == "OPTION":
                        conf_lp = lp
                    else:
                        conf_lp = compute_book_confirmed_price(
                            lp=lp,
                            bid=quote_info.get("bidPrice"),
                            ask=quote_info.get("askPrice"),
                            mark=quote_info.get("mark"),
                            acct_lp=acct_lp,
                            net_qty=net_q
                        )

                    pos_open_pnl = (
                        (lp - avg_price) * net_q * mult
                        if avg_price > 0 else 0.0
                    )
                    conf_open_pnl = (
                        (conf_lp - avg_price) * net_q * mult
                        if avg_price > 0 else pos_open_pnl
                    )
                    total_open_pnl += pos_open_pnl
                    tag = f"{sym} (OPT)" if a_type == "OPTION" else sym
                    pos_details[tag] = {
                        "symbol": sym,
                        "raw_symbol": sym,
                        "qty": int(net_q),
                        "avg": round(avg_price, 4),
                        "last": round(lp, 4),
                        "open_pnl": round(pos_open_pnl, 2),
                        "confirmed_open_pnl": round(conf_open_pnl, 2),
                        "asset_type": a_type
                    }

                self._last_raw_pos_details[self.account_id] = json.loads(
                    json.dumps(pos_details)
                )
                (
                    adj_eq,
                    is_flat,
                    tot_open_pnl,
                    filt_pos,
                    has_opt,
                    filt_eq,
                    filt_opt,
                ) = _apply_ignored_positions_to_snapshot(
                    adj_eq, pos_details, open_eq_cache, open_opt_cache
                )
                self._last_open_eq[self.account_id] = (now_snap_t, filt_eq)
                self._last_open_opt[self.account_id] = (now_snap_t, filt_opt)

                open_res = (
                    adj_eq,
                    is_flat,
                    tot_open_pnl,
                    filt_pos,
                    has_opt
                )
                self._last_good_snapshot[self.account_id] = (
                    time.time(), open_res
                )
                return open_res
            elif resp.status_code == 429:
                self._rate_limit_until = time.time() + 2.5
                if (time.time() - self._last_429_log_ts) >= 30.0:
                    self._last_429_log_ts = time.time()
                    log_event(
                        "WARN",
                        "Schwab rate limit (HTTP 429) — backing off 2.5s and holding last snapshot."
                    )
                cached_snap = self._last_good_snapshot.get(self.account_id)
                if cached_snap and (time.time() - cached_snap[0]) <= 15.0:
                    return cached_snap[1]
                self.last_error = "HTTP 429"
            else:
                self.last_error = f"HTTP {resp.status_code}"
                log_event(
                    "ERROR", f"Schwab get_account returned HTTP {resp.status_code}"
                )
        except Exception as e:
            err_s = str(e)
            if "429" in err_s or "too many requests" in err_s.lower():
                self._rate_limit_until = time.time() + 2.5
                if (time.time() - self._last_429_log_ts) >= 30.0:
                    self._last_429_log_ts = time.time()
                    log_event(
                        "WARN",
                        "Schwab rate limit (HTTP 429) — backing off 2.5s and holding last snapshot."
                    )
                cached_snap = self._last_good_snapshot.get(self.account_id)
                if cached_snap and (time.time() - cached_snap[0]) <= 15.0:
                    return cached_snap[1]
            self.last_error = err_s
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
        self._prev_pos_qty_map = {}
        self._last_pos_call_ts = 0.0
        self._last_good_snapshot = {}
        self._last_raw_pos_details = {}
        self._last_open_eq = {}
        self._last_open_opt = {}
        self._last_intraday_cash_flow = {}
        self.last_preserved_close_qty = {}
        self.last_cancel_failed_syms = set()
        self._rate_limit_until = 0.0
        self._last_429_log_ts = 0.0
        self.last_error = ""

    def get_last_raw_pos_details(self):
        return json.loads(
            json.dumps(self._last_raw_pos_details.get(self.account_id, {}))
        )

    def get_last_intraday_cash_flow(self):
        return float(self._last_intraday_cash_flow.get(self.account_id, 0.0))

    def authenticate(self):
        logging.getLogger("webull").setLevel(logging.CRITICAL)
        logging.getLogger("webull.core").setLevel(logging.CRITICAL)
        try:
            import six  # noqa: F401
            import jmespath  # noqa: F401
            from webull.core.client import ApiClient
            from webull.trade.trade_client import TradeClient
        except ImportError:
            print("[SETUP] Installing required Webull OpenAPI SDK & dependencies...")
            subprocess.run(
                [
                    sys.executable, "-m", "pip", "install", "--upgrade",
                    "six", "jmespath", "protobuf", "paho-mqtt",
                    "requests", "urllib3", "certifi", "cryptography", "cachetools"
                ],
                check=False
            )
            subprocess.run(
                [
                    sys.executable, "-m", "pip", "install", "--upgrade",
                    "--no-deps", "--ignore-requires-python",
                    "webull-openapi-python-sdk"
                ],
                check=False
            )
            from webull.core.client import ApiClient
            from webull.trade.trade_client import TradeClient
        try:
            self.api_client = ApiClient(
                self.app_key,
                self.app_secret,
                "us",
                connect_timeout=3.5,
                timeout=4.5,
            )
        except TypeError:
            self.api_client = ApiClient(self.app_key, self.app_secret, "us")
        self.api_client._stream_logger_set = True
        self.api_client._file_logger_set = True
        if hasattr(self.api_client, "set_token_dir"):
            self.api_client.set_token_dir(os.path.join(USER_HOME, "conf"))
        self.api_client.add_endpoint("us", "api.webull.com")
        self.trade_client = TradeClient(self.api_client)
        logging.getLogger("webull").setLevel(logging.CRITICAL)
        logging.getLogger("webull.core").setLevel(logging.CRITICAL)

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

    def reconnect_session(self):
        """Refreshes Webull client timeout state (or rebuilds ApiClient/TradeClient
        atomically on auth/token errors) without clobbering the active in-memory
        access token if a reconnect attempt times out mid-outage."""
        try:
            err_l = str(getattr(self, "last_error", "") or "").lower()
            needs_full_reinit = (
                self.api_client is None
                or self.trade_client is None
                or any(
                    k in err_l
                    for k in (
                        "401",
                        "403",
                        "unauthorized",
                        "token",
                        "expired",
                        "sign",
                    )
                )
            )
            if not needs_full_reinit:
                self.api_client._connect_timeout = 3.5
                self.api_client._read_timeout = 4.5
                if not self.api_client.get_token():
                    tok_file = os.path.join(USER_HOME, "conf", "token.txt")
                    if os.path.exists(tok_file):
                        try:
                            with open(tok_file, "r", encoding="utf-8") as tf:
                                saved_tok = tf.readline().strip()
                            if saved_tok:
                                self.api_client.set_token(saved_tok)
                        except Exception:
                            pass
                return True

            from webull.core.client import ApiClient
            from webull.trade.trade_client import TradeClient
            old_tok = (
                self.api_client.get_token()
                if self.api_client is not None
                else None
            )
            try:
                new_api = ApiClient(
                    self.app_key,
                    self.app_secret,
                    "us",
                    connect_timeout=3.5,
                    timeout=4.5,
                )
            except TypeError:
                new_api = ApiClient(self.app_key, self.app_secret, "us")
            new_api._stream_logger_set = True
            new_api._file_logger_set = True
            if hasattr(new_api, "set_token_dir"):
                new_api.set_token_dir(os.path.join(USER_HOME, "conf"))
            new_api.add_endpoint("us", "api.webull.com")
            if old_tok and not new_api.get_token():
                new_api.set_token(old_tok)
            new_trade = TradeClient(new_api)
            self.api_client = new_api
            self.trade_client = new_trade
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

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

    def cancel_all_working_orders(self, preserve_market_close_map=None):
        self.last_preserved_close_qty = {}
        self.last_cancel_failed_syms = set()
        preserve_map = (
            dict(preserve_market_close_map)
            if isinstance(preserve_market_close_map, dict)
            else {}
        )
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
                preserved_any = False
                for o in orders:
                    cid = (
                        o.get("client_order_id")
                        or o.get("order_id")
                    )
                    if cid:
                        masked_cid = _mask_last4(cid)
                        o_itype = str(
                            o.get("instrument_type")
                            or o.get("asset_type")
                            or "EQUITY"
                        ).upper()
                        o_is_opt = ("OPT" in o_itype) or bool(o.get("legs"))
                        if o_is_opt:
                            o_meta = self._parse_option_contract_meta(o)
                            o_sym = o_meta.get("display_sym") or o_meta.get(
                                "raw_symbol", ""
                            )
                        else:
                            o_sym = (
                                o.get("symbol")
                                or (o.get("ticker") or {}).get("symbol")
                                or ""
                            )
                        o_sym = str(o_sym or "").strip()
                        if o_sym and is_position_ignored(
                            o_sym, is_opt=o_is_opt
                        ):
                            log_event(
                                "FLATTEN",
                                f"Skipping working Webull order {masked_cid} on ignored pre-existing ticker: {o_sym}",
                            )
                            continue

                        o_type = str(
                            o.get("order_type") or o.get("orderType") or ""
                        ).upper()
                        o_side = str(
                            o.get("side") or o.get("action") or ""
                        ).upper()
                        try:
                            o_qty = float(
                                o.get("remain_quantity")
                                or o.get("unfilled_quantity")
                                or o.get("quantity")
                                or o.get("total_quantity")
                                or 0.0
                            )
                        except Exception:
                            o_qty = 0.0

                        is_closing_dir = False
                        if o_sym and o_sym in preserve_map:
                            open_q = float(preserve_map[o_sym])
                            if open_q > 0 and o_side == "SELL":
                                is_closing_dir = True
                            elif open_q < 0 and o_side == "BUY":
                                is_closing_dir = True

                        if (
                            is_closing_dir
                            and is_market_hours()
                            and o_type in ("MARKET", "MKT")
                        ):
                            eff_q = (
                                o_qty
                                if o_qty > 0
                                else abs(float(preserve_map[o_sym]))
                            )
                            self.last_preserved_close_qty[o_sym] = (
                                self.last_preserved_close_qty.get(o_sym, 0.0)
                                + eff_q
                            )
                            preserved_any = True
                            log_event(
                                "FLATTEN",
                                f"Preserving working Webull RTH Market close order {masked_cid} "
                                f"({o_side} {int(eff_q)} {o_sym}) — "
                                f"keeping halt/auction queue priority.",
                            )
                            continue

                        log_event(
                            "FLATTEN", f"Canceling Webull order ID: {masked_cid}"
                        )
                        if hasattr(self.trade_client, "order_v3"):
                            c_res = self.trade_client.order_v3.cancel_order(
                                self.account_id, cid
                            )
                        else:
                            c_res = self.trade_client.cancel_order(
                                self.account_id, cid
                            )
                        code = c_resp_code(c_res)
                        log_event(
                            "FLATTEN",
                            f"Cancel response {masked_cid}: HTTP {code}"
                        )
                        if code in (200, 201, 202, 204, "OK"):
                            cancelled_any = True
                        else:
                            if o_sym:
                                self.last_cancel_failed_syms.add(o_sym)
                            if is_closing_dir and o_sym:
                                eff_q = (
                                    o_qty
                                    if o_qty > 0
                                    else abs(float(preserve_map[o_sym]))
                                )
                                self.last_preserved_close_qty[o_sym] = (
                                    self.last_preserved_close_qty.get(
                                        o_sym, 0.0
                                    )
                                    + eff_q
                                )
                if cancelled_any:
                    time.sleep(0.2)
                elif not preserved_any:
                    log_event("FLATTEN", "No working Webull orders to cancel.")
                return cancelled_any
        except Exception as e:
            log_event("ERROR", f"Webull cancel working orders exception: {e}")
        return False

    @staticmethod
    def _parse_option_contract_meta(p):
        """Extracts normalized option contract metadata from a Webull position
        record (supporting both v2 'legs' arrays, top-level fields, and OCC symbols)."""
        legs = p.get("legs")
        leg0 = (
            legs[0]
            if isinstance(legs, list) and len(legs) > 0 and isinstance(legs[0], dict)
            else {}
        )
        raw_qty = (
            p.get("quantity")
            or p.get("position")
            or leg0.get("quantity")
            or leg0.get("position")
            or 0
        )
        try:
            qty = float(raw_qty)
        except Exception:
            qty = 0.0
        side_hint = str(
            p.get("side")
            or p.get("position_side")
            or leg0.get("side")
            or leg0.get("position_side")
            or ""
        ).upper()
        if qty > 0 and side_hint in ("SHORT", "SELL"):
            qty = -abs(qty)

        raw_sym = str(
            leg0.get("symbol")
            or p.get("symbol")
            or p.get("ticker", {}).get("symbol")
            or ""
        ).strip()
        opt_type = str(
            leg0.get("option_type")
            or p.get("option_type")
            or ""
        ).strip().upper()
        exp_date = str(
            leg0.get("option_expire_date")
            or p.get("option_expire_date")
            or leg0.get("expire_date")
            or p.get("expire_date")
            or ""
        ).strip()
        strike_raw = (
            leg0.get("option_exercise_pricestring")
            or leg0.get("option_exercise_price")
            or leg0.get("strike_price")
            or p.get("option_exercise_pricestring")
            or p.get("option_exercise_price")
            or p.get("strike_price")
            or ""
        )
        inst_id = str(
            leg0.get("instrument_id")
            or p.get("instrument_id")
            or p.get("ticker_id")
            or ""
        ).strip()

        underlying = raw_sym
        m_occ = re.match(
            r"^([A-Za-z]+)\s*(\d{2})(\d{2})(\d{2})([CPcp])(\d{8})$", raw_sym
        )
        if m_occ:
            underlying = m_occ.group(1).upper()
            if not exp_date:
                exp_date = f"20{m_occ.group(2)}-{m_occ.group(3)}-{m_occ.group(4)}"
            if not opt_type:
                opt_type = "CALL" if m_occ.group(5).upper() == "C" else "PUT"
            if not strike_raw:
                strike_val = int(m_occ.group(6)) / 1000.0
                strike_raw = f"{strike_val:g}"

        if opt_type.startswith("C"):
            opt_type = "CALL"
        elif opt_type.startswith("P"):
            opt_type = "PUT"

        strike_str = str(strike_raw).strip()
        if strike_str:
            try:
                sv = float(strike_str)
                strike_str = (
                    f"{int(sv)}" if abs(sv - round(sv)) < 1e-6 else f"{sv:g}"
                )
            except Exception:
                pass

        if underlying and exp_date and strike_str and opt_type:
            display_sym = f"{underlying} {exp_date} {strike_str}{opt_type[:1]}"
        else:
            display_sym = raw_sym or "UNKNOWN_OPT"

        return {
            "display_sym": display_sym,
            "qty": qty,
            "underlying": underlying,
            "option_type": opt_type,
            "option_expire_date": exp_date,
            "strike_price": strike_str,
            "instrument_id": inst_id,
            "raw_symbol": raw_sym,
        }

    def get_open_equity_positions(self):
        """Returns (symbol, qty, last_price) for EQUITIES ONLY, or None on API error."""
        cached = self._last_open_eq.get(self.account_id)
        if cached and (time.time() - cached[0]) < 0.45 and cached[1]:
            return [
                item
                for item in cached[1]
                if not is_position_ignored(item[0], is_opt=False)
            ]
        try:
            res = self._call_get_positions()
            self._last_pos_call_ts = time.time()
            if res.status_code == 200:
                open_eq = []
                open_opt = []
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
                    is_opt = ("OPT" in itype) or bool(p.get("legs"))
                    if is_opt:
                        meta = self._parse_option_contract_meta(p)
                        if meta["qty"] != 0 and not is_position_ignored(
                            meta["display_sym"], is_opt=True
                        ):
                            open_opt.append(
                                (meta["display_sym"], meta["qty"], meta)
                            )
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
                        if sym and not is_position_ignored(sym, is_opt=False):
                            open_eq.append((sym, qty, lp))
                open_opt.sort(
                    key=lambda item: (0 if item[1] < 0 else 1, str(item[0]))
                )
                now_t = time.time()
                self._last_open_eq[self.account_id] = (now_t, list(open_eq))
                self._last_open_opt[self.account_id] = (now_t, list(open_opt))
                return open_eq
            log_event(
                "ERROR",
                f"Webull get_open_equity_positions HTTP {res.status_code}"
            )
        except Exception as e:
            log_event(
                "ERROR",
                f"Webull get_open_equity_positions exception: {e}"
            )
        if cached and (time.time() - cached[0]) <= 10.0 and cached[1]:
            log_event(
                "FLATTEN",
                "Using cached Webull open equity snapshot (<10s) after API error."
            )
            return [
                item
                for item in cached[1]
                if not is_position_ignored(item[0], is_opt=False)
            ]
        return None

    def get_open_option_positions(self):
        """Returns (display_sym, qty, meta) for OPTIONS ONLY sorted with short
        legs (qty < 0) first, or None on API error."""
        cached = self._last_open_opt.get(self.account_id)
        if cached and (time.time() - cached[0]) < 0.45:
            return [
                item
                for item in cached[1]
                if not is_position_ignored(item[0], is_opt=True)
            ]
        try:
            res = self._call_get_positions()
            self._last_pos_call_ts = time.time()
            if res.status_code == 200:
                open_eq = []
                open_opt = []
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
                    is_opt = ("OPT" in itype) or bool(p.get("legs"))
                    if is_opt:
                        meta = self._parse_option_contract_meta(p)
                        if meta["qty"] != 0 and not is_position_ignored(
                            meta["display_sym"], is_opt=True
                        ):
                            open_opt.append(
                                (meta["display_sym"], meta["qty"], meta)
                            )
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
                        if sym and not is_position_ignored(sym, is_opt=False):
                            open_eq.append((sym, qty, lp))
                open_opt.sort(
                    key=lambda item: (0 if item[1] < 0 else 1, str(item[0]))
                )
                now_t = time.time()
                self._last_open_eq[self.account_id] = (now_t, list(open_eq))
                self._last_open_opt[self.account_id] = (now_t, list(open_opt))
                return open_opt
            log_event(
                "ERROR",
                f"Webull get_open_option_positions HTTP {res.status_code}"
            )
        except Exception as e:
            log_event(
                "ERROR",
                f"Webull get_open_option_positions exception: {e}"
            )
        if cached and (time.time() - cached[0]) <= 10.0 and cached[1]:
            log_event(
                "FLATTEN",
                "Using cached Webull open option snapshot (<10s) after API error."
            )
            return [
                item
                for item in cached[1]
                if not is_position_ignored(item[0], is_opt=True)
            ]
        return None

    def submit_option_liquidation_batch(self, open_opt_positions):
        """Submits single-leg RTH Market option orders on Webull
        (BUY_TO_CLOSE on short legs first, then SELL_TO_CLOSE on long legs)."""
        submitted_ok = {}
        if not open_opt_positions:
            return submitted_ok
        if not is_market_hours():
            log_event(
                "GUARDRAIL",
                f"Cannot submit Webull option market flatten outside RTH "
                f"(9:30 AM – 4:00 PM ET): {[x[0] for x in open_opt_positions]}"
            )
            return submitted_ok

        sorted_opts = sorted(
            open_opt_positions,
            key=lambda item: (0 if item[1] < 0 else 1, str(item[0])),
        )
        for item in sorted_opts:
            display_sym = item[0]
            qty = item[1]
            meta = item[2] if len(item) > 2 and isinstance(item[2], dict) else {}
            abs_q = int(abs(qty))
            if abs_q <= 0:
                continue

            side = "BUY" if qty < 0 else "SELL"
            pos_intent = "BUY_TO_CLOSE" if qty < 0 else "SELL_TO_CLOSE"
            underlying = meta.get("underlying") or display_sym.split()[0]
            opt_type = meta.get("option_type") or ""
            exp_date = meta.get("option_expire_date") or ""
            strike_str = meta.get("strike_price") or ""
            inst_id = meta.get("instrument_id") or ""
            client_oid = uuid.uuid4().hex[:24]

            leg_item = {
                "instrument_type": "OPTION",
                "market": "US",
                "symbol": underlying,
                "side": side,
                "quantity": str(abs_q),
                "position_intent": pos_intent,
            }
            if opt_type:
                leg_item["option_type"] = opt_type
            if exp_date:
                leg_item["option_expire_date"] = exp_date
            if strike_str:
                leg_item["strike_price"] = strike_str
            if inst_id:
                leg_item["instrument_id"] = inst_id

            order_item = {
                "client_order_id": client_oid,
                "combo_type": "NORMAL",
                "option_strategy": "SINGLE",
                "instrument_type": "OPTION",
                "market": "US",
                "symbol": underlying,
                "order_type": "MARKET",
                "side": side,
                "position_intent": pos_intent,
                "quantity": str(abs_q),
                "time_in_force": "DAY",
                "support_trading_session": "CORE",
                "entrust_type": "QTY",
                "legs": [leg_item],
            }

            log_event(
                "ORDER_OUT",
                f"Submitting Webull RTH Option Market {pos_intent} (BETA): "
                f"{abs_q} {display_sym}"
            )
            try:
                if hasattr(self.trade_client, "order_v3"):
                    r = self.trade_client.order_v3.place_order(
                        self.account_id, [order_item]
                    )
                elif hasattr(self.trade_client, "order_v2") and hasattr(
                    self.trade_client.order_v2, "place_option"
                ):
                    r = self.trade_client.order_v2.place_option(
                        self.account_id, [order_item]
                    )
                else:
                    r = self.trade_client.place_order(
                        self.account_id, order_item
                    )
                code = c_resp_code(r)
                if (
                    code not in (200, 201, "OK")
                    and hasattr(self.trade_client, "order_v2")
                    and hasattr(self.trade_client.order_v2, "place_option")
                ):
                    r2 = self.trade_client.order_v2.place_option(
                        self.account_id, [order_item]
                    )
                    code = c_resp_code(r2)
                    r = r2
                log_event(
                    "ORDER_RESP",
                    f"Webull Option {pos_intent} {display_sym} -> HTTP {code}"
                )
                if code in (200, 201, 202, "OK"):
                    submitted_ok[display_sym] = float(abs_q)
            except Exception as e:
                log_event(
                    "ERROR",
                    f"Webull option place_order exception ({display_sym}): {e}"
                )
        return submitted_ok

    def submit_liquidation_batch(self, open_positions):
        submitted_ok = {}
        if not open_positions:
            return submitted_ok
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
                code = c_resp_code(r)
                log_event(
                    "ORDER_RESP",
                    f"Webull {side} {symbol} -> HTTP {code}"
                )
                if code in (200, 201, 202, "OK"):
                    submitted_ok[symbol] = float(abs_q)
            except Exception as e:
                log_event("ERROR", f"Webull place_order exception: {e}")
        return submitted_ok

    @staticmethod
    def _extract_webull_equity_and_cash(b_data):
        """Extracts Total Account Value (Net Liquidation), Cash Balance, and
        Balance-Snapshot Market Value from Webull's balance payload without
        ever mistaking Market Value of positions for Total Account Value."""
        def to_f(val):
            try:
                return float(val) if val is not None and val != "" else None
            except Exception:
                return None

        top_mkt = to_f(
            b_data.get("total_market_value")
            or b_data.get("market_value")
        )

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
                return v, cash, top_mkt

        # 2. Check inside account_currency_assets (USD)
        assets = b_data.get("account_currency_assets")
        if isinstance(assets, list) and assets:
            for item in assets:
                sub_mkt = to_f(
                    item.get("market_value")
                    or item.get("total_market_value")
                )
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
                        return v, cash, (sub_mkt if sub_mkt is not None else top_mkt)

        # 3. Fallback: Sum Cash Balance + Market Value
        cash = to_f(
            b_data.get("total_cash_balance")
            or b_data.get("cash_balance")
            or b_data.get("total_cash")
        )
        mkt = top_mkt or 0.0
        if cash is not None:
            return cash + mkt, cash, top_mkt

        if isinstance(assets, list) and assets:
            for item in assets:
                c_sub = to_f(
                    item.get("cash_balance")
                    or item.get("total_cash_balance")
                    or item.get("settled_cash")
                )
                m_sub_raw = to_f(
                    item.get("market_value")
                    or item.get("total_market_value")
                )
                m_sub = m_sub_raw or 0.0
                if c_sub is not None:
                    return c_sub + m_sub, c_sub, m_sub_raw

        return 0.0, None, None

    def fetch_account_data(self):
        """Returns (adj_eq, is_flat, open_pnl, pos_details, has_options)
        for Webull accounts."""
        now_ts = time.time()
        if now_ts < self._rate_limit_until:
            cached_snap = self._last_good_snapshot.get(self.account_id)
            if cached_snap and (now_ts - cached_snap[0]) <= 15.0:
                return cached_snap[1]

        try:
            elapsed_pos = time.time() - self._last_pos_call_ts
            if 0.0 <= elapsed_pos < 2.10:
                time.sleep(2.10 - elapsed_pos)
            p_res = self._call_get_positions()
            self._last_pos_call_ts = time.time()
            if p_res.status_code == 429:
                self._rate_limit_until = time.time() + 2.5
                if (time.time() - self._last_429_log_ts) >= 30.0:
                    self._last_429_log_ts = time.time()
                    log_event(
                        "WARN",
                        "Webull rate limit (HTTP 429) — backing off 2.5s and holding last snapshot."
                    )
                cached_snap = self._last_good_snapshot.get(self.account_id)
                if cached_snap and (time.time() - cached_snap[0]) <= 15.0:
                    return cached_snap[1]
                self.last_error = "HTTP 429"
                return None, True, 0.0, {}, False
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

            b_res = self._call_get_balance()
            if b_res.status_code == 429:
                self._rate_limit_until = time.time() + 2.5
                if (time.time() - self._last_429_log_ts) >= 30.0:
                    self._last_429_log_ts = time.time()
                    log_event(
                        "WARN",
                        "Webull balance rate limit (HTTP 429) — backing off 2.5s and holding last snapshot."
                    )
                cached_snap = self._last_good_snapshot.get(self.account_id)
                if cached_snap and (time.time() - cached_snap[0]) <= 15.0:
                    return cached_snap[1]
                self.last_error = "HTTP 429"
                return None, True, 0.0, {}, False
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

            raw_eq, cash_bal, bal_mkt_val = (
                self._extract_webull_equity_and_cash(b_data)
            )
            wb_pos_dep = 0.0
            for dep_k in (
                "pending_deposit",
                "incoming_funds",
                "unsettled_deposit",
                "cash_receipts",
            ):
                try:
                    dv = b_data.get(dep_k)
                    if dv is not None and dv != "":
                        fval = float(dv)
                        if fval > wb_pos_dep:
                            wb_pos_dep = fval
                except Exception:
                    pass
            wb_neg_cf = 0.0
            try:
                cr_raw = b_data.get("cash_receipts")
                if cr_raw is not None and cr_raw != "":
                    cr_val = float(cr_raw)
                    if cr_val < 0.0:
                        wb_neg_cf = cr_val
            except Exception:
                pass
            wb_dep = round(wb_pos_dep + wb_neg_cf, 2)
            self._last_intraday_cash_flow[self.account_id] = wb_dep
            raw_eq = round(raw_eq - get_unanchored_cash_flow(wb_dep), 2)
            if self.account_id not in self._logged_accounts:
                self._logged_accounts.add(self.account_id)
                log_event(
                    "SESSION",
                    f"Webull Balance Parsed -> TotalAccountValue=${raw_eq:,.2f} "
                    f"(Cash=${cash_bal if cash_bal is not None else 0.0:,.2f})"
                )

            total_open_pnl = 0.0
            total_pos_mkt_val = 0.0
            total_raw_pos_mkt_val = 0.0
            pos_details = {}
            open_eq_cache = []
            open_opt_cache = []
            has_options = False

            for p in pos_list:
                itype = str(
                    p.get("instrument_type")
                    or p.get("asset_type")
                    or "EQUITY"
                ).upper()
                is_opt = ("OPT" in itype) or bool(p.get("legs"))
                opt_meta = self._parse_option_contract_meta(p) if is_opt else None
                qty = (
                    opt_meta["qty"]
                    if opt_meta is not None
                    else float(p.get("quantity") or p.get("position") or 0)
                )
                if qty == 0:
                    continue
                if is_opt:
                    has_options = True
                    open_opt_cache.append(
                        (opt_meta["display_sym"], qty, opt_meta)
                    )
                mult = 100.0 if is_opt else 1.0

                sym = (
                    opt_meta["display_sym"]
                    if opt_meta is not None
                    else (
                        p.get("symbol")
                        or p.get("ticker", {}).get("symbol")
                        or "UNKNOWN"
                    )
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
                raw_mkt_val = float(
                    p.get("market_value") or (qty * raw_lp * mult)
                )
                acct_lp = (
                    abs(raw_mkt_val / (qty * mult))
                    if qty != 0 else avg_price
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
                    conf_lp = compute_book_confirmed_price(
                        lp=lp,
                        bid=p.get("bid_price") or p.get("bid"),
                        ask=p.get("ask_price") or p.get("ask"),
                        mark=p.get("market_price"),
                        acct_lp=acct_lp,
                        net_qty=qty
                    )
                    if sym and sym != "UNKNOWN":
                        open_eq_cache.append((sym, qty, lp))
                else:
                    lp = raw_lp
                    conf_lp = lp

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
                conf_open_pnl = (
                    (conf_lp - avg_price) * qty * mult
                    if avg_price > 0 else pos_open_pnl
                )
                total_raw_pos_mkt_val += raw_mkt_val
                total_pos_mkt_val += pos_mkt_val

                total_open_pnl += pos_open_pnl
                tag = f"{sym} (OPT)" if is_opt else sym
                raw_sym_val = (
                    opt_meta.get("raw_symbol", sym)
                    if opt_meta is not None
                    else sym
                )
                pos_details[tag] = {
                    "symbol": sym,
                    "raw_symbol": raw_sym_val,
                    "qty": int(qty),
                    "avg": round(avg_price, 4),
                    "last": round(lp, 4),
                    "open_pnl": round(pos_open_pnl, 2),
                    "confirmed_open_pnl": round(conf_open_pnl, 2),
                    "asset_type": "OPTION" if is_opt else "EQUITY"
                }

            open_opt_cache.sort(
                key=lambda item: (0 if item[1] < 0 else 1, str(item[0]))
            )
            now_snap_t = time.time()
            self._last_raw_pos_details[self.account_id] = json.loads(
                json.dumps(pos_details)
            )
            self._prev_pos_qty_map[self.account_id] = {
                s_k.replace(" (OPT)", ""): d_v["qty"]
                for s_k, d_v in pos_details.items()
            }

            ref_bal_mkt_val = (
                bal_mkt_val
                if (bal_mkt_val is not None and len(pos_details) > 0)
                else total_raw_pos_mkt_val
            )
            raw_adj_eq = (
                round(raw_eq + (total_pos_mkt_val - ref_bal_mkt_val), 2)
                if (raw_eq is not None and raw_eq > 0)
                else None
            )
            if cash_bal is not None and cash_bal > 0:
                cash_plus_pos = round(cash_bal + total_pos_mkt_val, 2)
                if (
                    raw_adj_eq is not None
                    and abs(cash_plus_pos - raw_adj_eq) > 15.0
                ):
                    adj_eq = raw_adj_eq
                else:
                    adj_eq = cash_plus_pos
            else:
                adj_eq = (
                    raw_adj_eq
                    if raw_adj_eq is not None
                    else round(raw_eq or 0.0, 2)
                )

            (
                adj_eq,
                is_flat,
                tot_open_pnl,
                filt_pos,
                has_opt,
                filt_eq,
                filt_opt,
            ) = _apply_ignored_positions_to_snapshot(
                adj_eq, pos_details, open_eq_cache, open_opt_cache
            )
            self._last_open_eq[self.account_id] = (now_snap_t, filt_eq)
            self._last_open_opt[self.account_id] = (now_snap_t, filt_opt)

            self.last_error = ""
            res_tuple = (
                adj_eq,
                is_flat,
                tot_open_pnl,
                filt_pos,
                has_opt
            )
            self._last_good_snapshot[self.account_id] = (
                time.time(), res_tuple
            )
            return res_tuple
        except Exception as e:
            err_s = str(e)
            if "429" in err_s or "too many requests" in err_s.lower():
                self._rate_limit_until = time.time() + 2.5
                if (time.time() - self._last_429_log_ts) >= 30.0:
                    self._last_429_log_ts = time.time()
                    log_event(
                        "WARN",
                        "Webull rate limit (HTTP 429) — backing off 2.5s and holding last snapshot."
                    )
                cached_snap = self._last_good_snapshot.get(self.account_id)
                if cached_snap and (time.time() - cached_snap[0]) <= 15.0:
                    return cached_snap[1]
            self.last_error = err_s
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
        "4. EQUITIES, OPTIONS & IGNORED SWING POSITIONS:\n"
        "   • Equities (Stocks): Tracked for HUD PnL, Alarms, AND automated Market (RTH) / Limit (Ext-Hours) flatten orders.\n"
        "   • Options Contracts: Tracked for HUD PnL and Warning Sirens ONLY by default ('Include Options in Auto-Flatten'\n"
        "     is OFF by default). If you explicitly enable the optional BETA Options Auto-Flatten toggle in Card 2 and\n"
        "     accept the separate Options Risk Waiver, single-leg RTH (9:30 AM – 4:00 PM ET) Market orders carry severe\n"
        "     bid-ask spread, illiquidity, multi-leg legging, and market-order slippage risks.\n"
        "   • Ignored Pre-Existing Positions ('Swing / Hold'): Any position marked as Ignored is excluded from daytrade\n"
        "     PnL, alarms, stops, order cancellation, and auto-flatten. You are 100% solely responsible for managing it.\n\n"
        "5. SAFE TESTING ('ALARMS ONLY MODE') & POST-BREACH DISARMED MODE:\n"
        "   Always test first with 'Alarms Only Mode' checked in Card 2 (or with 1 share) to verify your API connection\n"
        "   and PnL tracking before trading live size. If you continue trading after a Daily Stop lockout without raising\n"
        "   your Daily Max Loss or re-zeroing your baseline, the breached Daily Stop remains in 'DISARMED' mode."
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
        if config.get("enable_flatten_options", False):
            if is_options_waiver_verified(config):
                opt_at = config.get("options_waiver_accepted_at", "Unknown")
                opt_sha = get_options_waiver_expected_sha()
                log_event(
                    "WAIVER",
                    f"Options Auto-Flatten BETA Waiver v{OPTIONS_WAIVER_VERSION} verified "
                    f"(Accepted at: {opt_at} | SHA256: {opt_sha[:12]}...)"
                )
            elif not show_options_flatten_beta_waiver(parent=None, force_prompt=True):
                config["enable_flatten_options"] = False
                save_config(config)
                log_event(
                    "WAIVER",
                    "Options Auto-Flatten BETA Waiver not accepted on startup — "
                    "reverted enable_flatten_options to OFF (Siren-Only)."
                )
        return True

    accepted = {"ok": False}
    w = tk.Tk()
    w.withdraw()
    if os.path.exists(ICON_PATH):
        try:
            w.iconbitmap(ICON_PATH)
        except Exception:
            pass
    apply_dark_title_bar(w)
    w.title(f"PnL Enforcer Beta — Legal Disclaimer & Assumption of Risk (v{WAIVER_VERSION})")
    w.config(bg="#0d1117", padx=28, pady=22)
    w.resizable(False, False)
    w.attributes("-topmost", True)

    tk.Label(
        w,
        text=f"⚠️ EXPERIMENTAL BETA SOFTWARE — ASSUMPTION OF RISK (v{WAIVER_VERSION})",
        font=("Arial", 13, "bold"),
        fg="#fbbf24",
        bg="#0d1117",
        anchor="w"
    ).pack(fill="x", pady=(0, 12))

    msg_outer = tk.Frame(
        w, bg="#131922", bd=0, highlightthickness=1, highlightbackground="#243040"
    )
    msg_outer.pack(fill="x", pady=(0, 16))
    NeonBarCanvas(
        msg_outer, core_color="#fbbf24", card_bg="#131922", glow_on=True
    ).pack(side="left", fill="y")
    msg_card = tk.Frame(msg_outer, bg="#131922", padx=22, pady=16)
    msg_card.pack(side="left", fill="both", expand=True)

    def _add_main_waiver_section(num_str, title_txt, lines_of_segments, is_last=False):
        sec = tk.Frame(msg_card, bg="#131922")
        sec.pack(fill="x")

        hdr = tk.Frame(sec, bg="#131922")
        hdr.pack(fill="x", pady=(0, 4))
        tk.Label(
            hdr,
            text=f"{num_str}.",
            font=("Arial", 10, "bold"),
            fg="#fb7185",
            bg="#131922",
            anchor="w",
        ).pack(side="left", padx=(0, 6))
        tk.Label(
            hdr,
            text=title_txt,
            font=("Arial", 10, "bold"),
            fg="#fbbf24",
            bg="#131922",
            anchor="w",
        ).pack(side="left")

        body = tk.Frame(sec, bg="#131922", padx=20)
        body.pack(fill="x")
        for line_idx, seg_list in enumerate(lines_of_segments):
            l_frame = tk.Frame(body, bg="#131922")
            l_frame.pack(fill="x", pady=(2 if line_idx > 0 else 0, 1))
            for seg_txt, seg_fg, seg_font, seg_bg in seg_list:
                tk.Label(
                    l_frame,
                    text=seg_txt,
                    font=seg_font,
                    fg=seg_fg,
                    bg=seg_bg or "#131922",
                    padx=5 if seg_bg else 0,
                    pady=1 if seg_bg else 0,
                    anchor="w",
                ).pack(side="left")

        if not is_last:
            tk.Frame(msg_card, bg="#222d3d", height=1).pack(
                fill="x", pady=(10, 10)
            )

    _b_txt = "#e2e8f0"
    _b_fnt = ("Arial", 10)
    _b_bld = ("Arial", 10, "bold")
    _c_fnt = ("Consolas", 10, "bold")

    _add_main_waiver_section(
        "1",
        "NO WARRANTY, LIMITATION OF LIABILITY & INDEMNIFICATION:",
        [
            [
                ("This software is an ", _b_txt, _b_fnt, None),
                ("experimental beta tool", "#fbbf24", _b_bld, "#262115"),
                (" provided strictly ", _b_txt, _b_fnt, None),
                ("'AS IS'", "#ffffff", _b_bld, None),
                (" without warranty of any kind.", _b_txt, _b_fnt, None),
            ],
            [
                ("In no event shall the authors or contributors be liable for any direct or indirect trading losses,", _b_txt, _b_fnt, None),
            ],
            [
                ("slippage, missed fills, API outages, rate limits, rejected orders, or unexpected software behavior.", _b_txt, _b_fnt, None),
            ],
            [
                ("By using this software, you agree to ", _b_txt, _b_fnt, None),
                ("indemnify and hold harmless", "#ffffff", _b_bld, None),
                (" the authors from any claims or losses.", _b_txt, _b_fnt, None),
            ],
        ],
    )

    _add_main_waiver_section(
        "2",
        "NOT FINANCIAL ADVICE & NO GUARANTEE OF LOSS PREVENTION:",
        [
            [
                ("This tool is a self-directed mechanical utility, ", _b_txt, _b_fnt, None),
                ("NOT a registered investment advisor, broker-dealer,", "#ffffff", _b_bld, None),
            ],
            [
                ("or fiduciary. It ", _b_txt, _b_fnt, None),
                ("DOES NOT and CANNOT guarantee", "#fda4af", _b_bld, "#2e161d"),
                (" that losses will be capped at your configured limits.", _b_txt, _b_fnt, None),
            ],
            [
                ("Market gaps, illiquid spreads, halts, API latency, or order rejections can cause actual account losses", _b_txt, _b_fnt, None),
            ],
            [
                ("to ", _b_txt, _b_fnt, None),
                ("significantly exceed", "#fda4af", _b_bld, None),
                (" your configured thresholds.", _b_txt, _b_fnt, None),
            ],
        ],
    )

    _add_main_waiver_section(
        "3",
        "NO BROKER AFFILIATION & API TERMS RISK:",
        [
            [
                ("This project is an independent third-party tool and is ", _b_txt, _b_fnt, None),
                ("NOT affiliated with, endorsed by, or sponsored", "#ffffff", _b_bld, None),
            ],
            [
                ("by Charles Schwab, Thinkorswim, or Webull. Automated API polling and liquidation orders are subject", _b_txt, _b_fnt, None),
            ],
            [
                ("to your broker's terms of service and rate limits.", _b_txt, _b_fnt, None),
            ],
        ],
    )

    _add_main_waiver_section(
        "4",
        "EQUITIES, OPTIONS & IGNORED SWING POSITIONS:",
        [
            [
                ("• Equities (Stocks): ", "#7dd3fc", _b_bld, None),
                ("Tracked for HUD PnL, Alarms, AND automated Market (RTH) / Limit (Ext-Hours) flatten orders.", _b_txt, _b_fnt, None),
            ],
            [
                ("• Options Contracts: ", "#fbbf24", _b_bld, None),
                ("Tracked for HUD PnL and Warning Sirens ", _b_txt, _b_fnt, None),
                ("ONLY by default", "#ffffff", _b_bld, None),
                (" (", _b_txt, _b_fnt, None),
                ("Include Options in Auto-Flatten", "#7dd3fc", _c_fnt, "#132235"),
                (" is OFF).", _b_txt, _b_fnt, None),
            ],
            [
                ("  If you enable the optional BETA Options Auto-Flatten toggle in Card 2 and accept the separate Options", _b_txt, _b_fnt, None),
            ],
            [
                ("  Risk Waiver, single-leg RTH Market orders carry ", _b_txt, _b_fnt, None),
                ("severe bid-ask spread, legging, and slippage risks.", "#fda4af", _b_bld, "#2e161d"),
            ],
            [
                ("• Ignored Pre-Existing Positions ('Swing / Hold'): ", "#a3e4d7", _b_bld, None),
                ("Any position marked as Ignored is excluded from daytrade", _b_txt, _b_fnt, None),
            ],
            [
                ("  PnL, alarms, stops, order cancellation, and auto-flatten. You are ", _b_txt, _b_fnt, None),
                ("100% solely responsible", "#ffffff", _b_bld, None),
                (" for managing it.", _b_txt, _b_fnt, None),
            ],
        ],
    )

    _add_main_waiver_section(
        "5",
        "SAFE TESTING ('ALARMS ONLY MODE') & POST-BREACH DISARMED MODE:",
        [
            [
                ("Always test first with ", _b_txt, _b_fnt, None),
                ("Alarms Only Mode", "#34d399", _c_fnt, "#0f2922"),
                (" checked in Card 2 (or with 1 share) to verify your API connection", _b_txt, _b_fnt, None),
            ],
            [
                ("and PnL tracking before trading live size. If you continue trading after a Daily Stop lockout without raising", _b_txt, _b_fnt, None),
            ],
            [
                ("your Daily Max Loss or re-zeroing your baseline, the breached Daily Stop remains in ", _b_txt, _b_fnt, None),
                ("DISARMED", "#fbbf24", _c_fnt, "#262115"),
                (" mode.", _b_txt, _b_fnt, None),
            ],
        ],
        is_last=True,
    )

    var_agree = tk.BooleanVar(value=False)
    make_glass_checkbutton(
        w,
        text=(
            "I have read this disclaimer and LICENSE.txt, understand that losses cannot be guaranteed, "
            "and assume 100% sole responsibility for my account."
        ),
        variable=var_agree,
        font=("Arial", 10, "bold"),
        fg="#58d68d",
        bg="#0d1117",
    ).pack(anchor="w", pady=(0, 14))

    btn_row = tk.Frame(w, bg="#0d1117")
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

    make_stadium_button(
        btn_row,
        text="Decline & Exit",
        font=("Arial", 10, "bold"),
        fill_color="#3b1520",
        border_color="#f43f5e",
        hover_fill="#4f1c2b",
        hover_border="#fb7185",
        fg="#ffe4e6",
        canvas_bg="#0d1117",
        width=142,
        height=36,
        pad_x=28,
        glow_strength=0.45,
        command=w.destroy,
    ).pack(side="left")

    make_stadium_button(
        btn_row,
        text="I Understand & Assume All Risk >>",
        font=("Arial", 10, "bold"),
        fill_color="#105e35",
        border_color="#22ff88",
        hover_fill="#157a46",
        hover_border="#69f0ae",
        glow_color="#00e676",
        fg="#ffffff",
        canvas_bg="#0d1117",
        width=268,
        height=36,
        pad_x=32,
        glow_strength=0.65,
        command=on_accept,
    ).pack(side="right")

    center_dialog_over_parent(w)
    w.lift()
    w.focus_force()
    w.mainloop()
    return accepted["ok"]


def show_options_flatten_beta_waiver(parent=None, force_prompt=True):
    """Displays the dedicated Options Auto-Flatten (BETA) Assumption of Risk &
    Spread Slippage Disclaimer modal, requiring explicit checkbox confirmation
    and writing a cryptographic [WAIVER] audit record to enforcer_log.txt and
    enforcer_config.json."""
    expected_opt_sha = get_options_waiver_expected_sha()
    if not force_prompt and is_options_waiver_verified(config):
        acc_at = config.get("options_waiver_accepted_at", "Unknown")
        log_event(
            "WAIVER",
            f"Options Auto-Flatten BETA Waiver v{OPTIONS_WAIVER_VERSION} verified "
            f"(Accepted at: {acc_at} | SHA256: {expected_opt_sha[:12]}...)"
        )
        return True

    accepted = {"ok": False}
    dlg = tk.Tk() if parent is None else tk.Toplevel(parent)
    dlg.withdraw()
    if parent is not None:
        dlg.grab_set()
    if os.path.exists(ICON_PATH):
        try:
            dlg.iconbitmap(ICON_PATH)
        except Exception:
            pass
    apply_dark_title_bar(dlg)

    dlg.title(
        f"PnL Enforcer — Options Auto-Flatten BETA Risk Waiver (v{OPTIONS_WAIVER_VERSION})"
    )
    dlg.config(bg="#0d1117", padx=28, pady=22)
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)

    def on_decline():
        log_event(
            "WAIVER",
            f"User declined Options Auto-Flatten BETA Waiver v{OPTIONS_WAIVER_VERSION} "
            f"— keeping Options Siren-Only."
        )
        dlg.destroy()

    dlg.protocol("WM_DELETE_WINDOW", on_decline)

    tk.Label(
        dlg,
        text=(
            f"⚠️ EXPERIMENTAL BETA FEATURE — OPTIONS AUTO-FLATTEN WAIVER "
            f"(v{OPTIONS_WAIVER_VERSION})"
        ),
        font=("Arial", 13, "bold"),
        fg="#fbbf24",
        bg="#0d1117",
        anchor="w",
    ).pack(fill="x", pady=(0, 12))

    msg_outer = tk.Frame(
        dlg,
        bg="#131922",
        bd=0,
        highlightthickness=1,
        highlightbackground="#5c2836",
    )
    msg_outer.pack(fill="x", pady=(0, 16))
    NeonBarCanvas(
        msg_outer, core_color="#f43f5e", card_bg="#131922", glow_on=True
    ).pack(side="left", fill="y")
    msg_card = tk.Frame(msg_outer, bg="#131922", padx=22, pady=16)
    msg_card.pack(side="left", fill="both", expand=True)

    def _add_waiver_section(num_str, title_txt, lines_of_segments, is_last=False):
        sec = tk.Frame(msg_card, bg="#131922")
        sec.pack(fill="x")

        hdr = tk.Frame(sec, bg="#131922")
        hdr.pack(fill="x", pady=(0, 4))
        tk.Label(
            hdr,
            text=f"{num_str}.",
            font=("Arial", 10, "bold"),
            fg="#fb7185",
            bg="#131922",
            anchor="w",
        ).pack(side="left", padx=(0, 6))
        tk.Label(
            hdr,
            text=title_txt,
            font=("Arial", 10, "bold"),
            fg="#fbbf24",
            bg="#131922",
            anchor="w",
        ).pack(side="left")

        body = tk.Frame(sec, bg="#131922", padx=20)
        body.pack(fill="x")
        for line_idx, seg_list in enumerate(lines_of_segments):
            l_frame = tk.Frame(body, bg="#131922")
            l_frame.pack(fill="x", pady=(2 if line_idx > 0 else 0, 1))
            for seg_txt, seg_fg, seg_font, seg_bg in seg_list:
                tk.Label(
                    l_frame,
                    text=seg_txt,
                    font=seg_font,
                    fg=seg_fg,
                    bg=seg_bg or "#131922",
                    padx=5 if seg_bg else 0,
                    pady=1 if seg_bg else 0,
                    anchor="w",
                ).pack(side="left")

        if not is_last:
            tk.Frame(msg_card, bg="#222d3d", height=1).pack(
                fill="x", pady=(10, 10)
            )

    _b_txt = "#e2e8f0"
    _b_fnt = ("Arial", 10)
    _b_bld = ("Arial", 10, "bold")
    _c_fnt = ("Consolas", 10, "bold")

    _add_waiver_section(
        "1",
        "EXPERIMENTAL BETA FEATURE — USE AT YOUR OWN SOLE RISK:",
        [
            [
                ("Automated Options Flattening is an ", _b_txt, _b_fnt, None),
                ("experimental BETA feature", "#fbbf24", _b_bld, "#262115"),
                (" provided strictly ", _b_txt, _b_fnt, None),
                ("'AS IS'", "#ffffff", _b_bld, None),
                (" without warranty of any kind.", _b_txt, _b_fnt, None),
            ],
            [
                ("By enabling this toggle, you expressly ", _b_txt, _b_fnt, None),
                ("release, indemnify, and hold harmless", "#ffffff", _b_bld, None),
                (" the author(s) and contributors from any", _b_txt, _b_fnt, None),
            ],
            [
                ("and all claims, damages, or financial losses arising from option orders.", _b_txt, _b_fnt, None),
            ],
        ],
    )

    _add_waiver_section(
        "2",
        "SEVERE BID-ASK SPREAD & MARKET ORDER SLIPPAGE RISK:",
        [
            [
                ("When an Open PnL Stop or Daily Stop triggers with this toggle enabled, Enforcer submits ", _b_txt, _b_fnt, None),
                ("RTH Market orders", "#ffffff", _b_bld, None),
            ],
            [
                ("(", _b_txt, _b_fnt, None),
                ("BUY_TO_CLOSE / SELL_TO_CLOSE", "#7dd3fc", _c_fnt, "#162436"),
                (") to exit open option contracts immediately. Unlike liquid stocks, options frequently", _b_txt, _b_fnt, None),
            ],
            [
                ("have ", _b_txt, _b_fnt, None),
                ("WIDE BID-ASK SPREADS", "#fda4af", _b_bld, "#311520"),
                (", thin order books, or zero bids. Submitting a Market order on an option contract can", _b_txt, _b_fnt, None),
            ],
            [
                ("result in ", _b_txt, _b_fnt, None),
                ("SEVERE SLIPPAGE", "#fda4af", _b_bld, "#311520"),
                (" and fills far worse than the displayed mark price.", _b_txt, _b_fnt, None),
            ],
        ],
    )

    _add_waiver_section(
        "3",
        "MULTI-LEG SPREADS & MARGIN REJECTION RISK:",
        [
            [
                ("Enforcer liquidates open options ", _b_txt, _b_fnt, None),
                ("leg-by-leg as individual single-leg Market orders", "#ffffff", _b_bld, None),
                (" (buying back short option legs", _b_txt, _b_fnt, None),
            ],
            [
                ("first before selling long option legs), ", _b_txt, _b_fnt, None),
                ("NOT as a single complex net-debit/net-credit spread order", "#fbbf24", _b_bld, None),
                (". Legging out of", _b_txt, _b_fnt, None),
            ],
            [
                ("spreads, condors, or covered positions via Market orders carries compounding slippage on each leg and may be", _b_txt, _b_fnt, None),
            ],
            [
                ("rejected by your broker's margin or options-approval level.", _b_txt, _b_fnt, None),
            ],
        ],
    )

    _add_waiver_section(
        "4",
        "REGULAR TRADING HOURS (9:30 AM – 4:00 PM ET) ONLY:",
        [
            [
                ("Standard US equity options only trade during ", _b_txt, _b_fnt, None),
                ("Regular Trading Hours (9:30 AM – 4:00 PM ET)", "#69f0ae", _b_bld, "#122b22"),
                (" and cannot be auto-flattened", _b_txt, _b_fnt, None),
            ],
            [
                ("in Pre-Market or After-Hours. If any option contract fails to close, is rejected, or has no bid, Enforcer will", _b_txt, _b_fnt, None),
            ],
            [
                ("abort Windows OS Lock / App Kill", "#ffffff", _b_bld, None),
                (" and sound the continuous emergency siren.", _b_txt, _b_fnt, None),
            ],
        ],
    )

    _add_waiver_section(
        "5",
        "100% SOLE RESPONSIBILITY FOR ACCOUNT & FILLS:",
        [
            [
                ("You acknowledge that automated option liquidation is a ", _b_txt, _b_fnt, None),
                ("last-resort mechanical backstop", "#ffffff", _b_bld, None),
                (", not a substitute for", _b_txt, _b_fnt, None),
            ],
            [
                ("in-broker stop orders or active risk management, and you assume ", _b_txt, _b_fnt, None),
                ("100% sole responsibility for all fills", "#fbbf24", _b_bld, None),
                (".", _b_txt, _b_fnt, None),
            ],
        ],
        is_last=True,
    )

    var_opt_agree = tk.BooleanVar(value=False)
    make_glass_checkbutton(
        dlg,
        text=(
            "I understand that Options Auto-Flatten is an experimental BETA feature, that Market orders on "
            "option spreads can suffer severe slippage, and I assume 100% sole responsibility for all fills."
        ),
        variable=var_opt_agree,
        font=("Arial", 10, "bold"),
        fg="#fbbf24",
        bg="#0d1117",
        accent_hex="#d97706",
        check_hex="#fbbf24",
    ).pack(anchor="w", pady=(0, 14))

    btn_row = tk.Frame(dlg, bg="#0d1117")
    btn_row.pack(fill="x")

    def on_accept_opt():
        if not var_opt_agree.get():
            messagebox.showwarning(
                "Confirmation Required",
                "Please check the box confirming you understand the BETA status, "
                "option spread slippage risks, and assume 100% sole responsibility.",
                parent=dlg,
            )
            return
        accepted_ts = datetime.now().isoformat(timespec="seconds")
        config["options_waiver_accepted"] = True
        config["options_waiver_version"] = OPTIONS_WAIVER_VERSION
        config["options_waiver_accepted_at"] = accepted_ts
        config["options_waiver_sha256"] = expected_opt_sha
        save_config(config)
        log_event(
            "WAIVER",
            f"User accepted Options Auto-Flatten BETA Waiver v{OPTIONS_WAIVER_VERSION} "
            f"(Accepted at: {accepted_ts} | SHA256: {expected_opt_sha[:12]}...)"
        )
        accepted["ok"] = True
        dlg.destroy()

    make_stadium_button(
        btn_row,
        text="Cancel (Keep Options Siren-Only)",
        font=("Arial", 10, "bold"),
        fill_color="#3b1520",
        border_color="#f43f5e",
        hover_fill="#4f1c2b",
        hover_border="#fb7185",
        fg="#ffe4e6",
        canvas_bg="#0d1117",
        width=238,
        height=36,
        pad_x=28,
        glow_strength=0.45,
        command=on_decline,
    ).pack(side="left")

    make_stadium_button(
        btn_row,
        text="I Accept Options BETA Risk >>",
        font=("Arial", 10, "bold"),
        fill_color="#105e35",
        border_color="#22ff88",
        hover_fill="#157a46",
        hover_border="#69f0ae",
        glow_color="#00e676",
        fg="#ffffff",
        canvas_bg="#0d1117",
        width=248,
        height=36,
        pad_x=32,
        glow_strength=0.65,
        command=on_accept_opt,
    ).pack(side="right")

    center_dialog_over_parent(dlg, parent=parent)
    if parent is None:
        dlg.mainloop()
    else:
        parent.wait_window(dlg)
    return accepted["ok"]


def show_broker_setup_wizard(broker_name, parent=None):
    """Step-by-step tailored guide & API Key setup dialog for Schwab or Webull."""
    load_config()
    saved_ok = {"status": False}

    wiz = tk.Tk() if parent is None else tk.Toplevel(parent)
    wiz.withdraw()
    if parent is not None:
        wiz.grab_set()
    if os.path.exists(ICON_PATH):
        try:
            wiz.iconbitmap(ICON_PATH)
        except Exception:
            pass
    apply_dark_title_bar(wiz)

    wiz.title(f"PnL Enforcer — {broker_name} API Setup Wizard")
    wiz.config(bg="#0d1117", padx=26, pady=20)
    wiz.resizable(False, False)
    wiz.attributes("-topmost", True)

    hdr_row = tk.Frame(wiz, bg="#0d1117")
    hdr_row.pack(fill="x", pady=(0, 10))
    tk.Label(
        hdr_row,
        text=f"▶ 🔑 {broker_name} API CREDENTIAL SETUP",
        font=("Arial", 12, "bold"),
        fg="#38bdf8",
        bg="#0d1117",
        anchor="w"
    ).pack(side="left")

    if broker_name == "SCHWAB":
        portal_url = "https://developer.schwab.com"
        portal_btn_lbl = "🌐 Open Schwab Developer Portal ↗"
        guide_title = "HOW TO GET YOUR SCHWAB API KEYS (One-Time Setup)"
    else:
        portal_url = "https://developer.webull.com/apis/docs/authentication/IndividualApplicationAPI"
        portal_btn_lbl = "🌐 Open Webull API Setup Guide ↗"
        guide_title = "HOW TO GET YOUR WEBULL OPENAPI KEYS (One-Time Setup)"

    make_stadium_button(
        hdr_row,
        text=portal_btn_lbl,
        font=("Arial", 9, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#475569",
        fg="#e2e8f0",
        canvas_bg="#0d1117",
        height=30,
        pad_x=22,
        command=lambda: webbrowser.open(portal_url),
    ).pack(side="right")

    guide_outer = tk.Frame(
        wiz, bg="#131922", bd=0, highlightthickness=1, highlightbackground="#243040"
    )
    guide_outer.pack(fill="x", pady=(0, 14))
    NeonBarCanvas(
        guide_outer, core_color="#38bdf8", card_bg="#131922", glow_on=True
    ).pack(side="left", fill="y")
    guide_card = tk.Frame(guide_outer, bg="#131922", padx=18, pady=14)
    guide_card.pack(side="left", fill="both", expand=True)

    tk.Label(
        guide_card,
        text=guide_title,
        font=("Arial", 10, "bold"),
        fg="#7dd3fc",
        bg="#131922",
        anchor="w",
    ).pack(fill="x", pady=(0, 6))
    tk.Frame(guide_card, bg="#222d3d", height=1).pack(fill="x", pady=(0, 8))

    def _add_step_row(step_num, lines_of_segments):
        row = tk.Frame(guide_card, bg="#131922")
        row.pack(fill="x", pady=4)
        tk.Label(
            row,
            text=f"{step_num}.",
            font=("Arial", 10, "bold"),
            fg="#38bdf8",
            bg="#131922",
            width=2,
            anchor="nw",
        ).pack(side="left", padx=(0, 6), anchor="n")
        body_col = tk.Frame(row, bg="#131922")
        body_col.pack(side="left", fill="x", expand=True)
        line_frames = []
        for line_idx, seg_list in enumerate(lines_of_segments):
            l_frame = tk.Frame(body_col, bg="#131922")
            l_frame.pack(fill="x", pady=(2 if line_idx > 0 else 0, 0))
            for seg_txt, seg_fg, seg_font, seg_bg in seg_list:
                tk.Label(
                    l_frame,
                    text=seg_txt,
                    font=seg_font,
                    fg=seg_fg,
                    bg=seg_bg or "#131922",
                    padx=5 if seg_bg else 0,
                    pady=1 if seg_bg else 0,
                    anchor="w",
                ).pack(side="left")
            line_frames.append(l_frame)
        return line_frames[0] if line_frames else body_col

    if broker_name == "SCHWAB":
        _add_step_row(
            1,
            [
                [
                    ("Log in at ", "#cbd5e1", ("Arial", 10), None),
                    ("https://developer.schwab.com", "#7dd3fc", ("Consolas", 10, "bold"), "#192536"),
                    (" and create a free ", "#cbd5e1", ("Arial", 10), None),
                    ("Individual Developer", "#ffffff", ("Arial", 10, "bold"), None),
                    (" account.", "#cbd5e1", ("Arial", 10), None),
                ]
            ],
        )
        _add_step_row(
            2,
            [
                [
                    ("Click ", "#cbd5e1", ("Arial", 10), None),
                    ("'Apps' ➔ 'Create App'", "#ffffff", ("Arial", 10, "bold"), None),
                    (" and select the API product ", "#cbd5e1", ("Arial", 10), None),
                    ("Accounts and Trading Production", "#fbbf24", ("Arial", 10, "bold"), "#262115"),
                    (".", "#cbd5e1", ("Arial", 10), None),
                ]
            ],
        )
        s3_body = _add_step_row(
            3,
            [
                [
                    ("Set the ", "#cbd5e1", ("Arial", 10), None),
                    ("Callback URL", "#ffffff", ("Arial", 10, "bold"), None),
                    (" to exactly:  ", "#cbd5e1", ("Arial", 10), None),
                    ("https://127.0.0.1", "#69f0ae", ("Consolas", 10, "bold"), "#122b22"),
                ]
            ],
        )

        def _copy_cb_url():
            try:
                wiz.clipboard_clear()
                wiz.clipboard_append("https://127.0.0.1")
                wiz.update()
                btn_copy_cb.config(text="✓ Copied", fg="#69f0ae", border_color="#00e676")
            except Exception:
                pass

        btn_copy_cb = make_stadium_button(
            s3_body,
            text="📋 Copy",
            font=("Arial", 8, "bold"),
            fill_color="#141820",
            fill_top_color="#1c212b",
            border_color="#2e3746",
            hover_fill="#181e28",
            hover_fill_top="#232a36",
            hover_border="#475569",
            fg="#e2e8f0",
            canvas_bg="#131922",
            width=72,
            height=22,
            auto_width=False,
            command=_copy_cb_url,
        )
        btn_copy_cb.pack(side="left", padx=(8, 0))

        _add_step_row(
            4,
            [
                [
                    ("Once your App status changes to ", "#cbd5e1", ("Arial", 10), None),
                    ("Ready for Use", "#69f0ae", ("Arial", 10, "bold"), "#122b22"),
                    (", paste your ", "#cbd5e1", ("Arial", 10), None),
                    ("App Key", "#ffffff", ("Arial", 10, "bold"), None),
                    (" & ", "#cbd5e1", ("Arial", 10), None),
                    ("App Secret", "#ffffff", ("Arial", 10, "bold"), None),
                    (" into the fields below.", "#cbd5e1", ("Arial", 10), None),
                ]
            ],
        )
        _add_step_row(
            5,
            [
                [
                    ("When you click ", "#cbd5e1", ("Arial", 10), None),
                    ("Save & Connect", "#69f0ae", ("Arial", 10, "bold"), None),
                    (", your browser will open to log into Schwab and approve your account.", "#cbd5e1", ("Arial", 10), None),
                ],
                [
                    ("After approving, copy the full ", "#cbd5e1", ("Arial", 10), None),
                    ("https://127.0.0.1/?code=...", "#7dd3fc", ("Consolas", 9, "bold"), "#192536"),
                    (" URL from your browser address bar", "#cbd5e1", ("Arial", 10), None),
                ],
                [
                    ("— our popup window will ", "#94a3b8", ("Arial", 10), None),
                    ("auto-detect it directly from your clipboard!", "#ffffff", ("Arial", 10, "bold"), None),
                ],
            ],
        )
    else:
        _add_step_row(
            1,
            [
                [
                    ("Log in to ", "#cbd5e1", ("Arial", 10), None),
                    ("Webull Web ➔ Account Management ➔ OpenAPI Management", "#ffffff", ("Arial", 10, "bold"), None),
                    (".", "#cbd5e1", ("Arial", 10), None),
                ]
            ],
        )
        _add_step_row(
            2,
            [
                [
                    ("Apply for a ", "#cbd5e1", ("Arial", 10), None),
                    ("Retail Trading API Key", "#7dd3fc", ("Arial", 10, "bold"), "#192536"),
                    (" (typically approved within a few minutes).", "#cbd5e1", ("Arial", 10), None),
                ]
            ],
        )
        _add_step_row(
            3,
            [
                [
                    ("Generate your ", "#cbd5e1", ("Arial", 10), None),
                    ("App Key", "#ffffff", ("Arial", 10, "bold"), None),
                    (" and ", "#cbd5e1", ("Arial", 10), None),
                    ("App Secret", "#ffffff", ("Arial", 10, "bold"), None),
                    (" in the Webull portal and paste both into the fields below.", "#cbd5e1", ("Arial", 10), None),
                ]
            ],
        )
        _add_step_row(
            4,
            [
                [
                    ("Click ", "#cbd5e1", ("Arial", 10), None),
                    ("Save & Connect", "#69f0ae", ("Arial", 10, "bold"), None),
                    (" below to verify your credentials and load your Webull trading accounts.", "#cbd5e1", ("Arial", 10), None),
                ]
            ],
        )
        _add_step_row(
            5,
            [
                [
                    ("⚠️ Mobile 2FA:", "#fbbf24", ("Arial", 10, "bold"), "#262115"),
                    (" On first connection, check your ", "#cbd5e1", ("Arial", 10), None),
                    ("Webull Mobile App / SMS", "#ffffff", ("Arial", 10, "bold"), None),
                    (" if prompted for a verification code.", "#cbd5e1", ("Arial", 10), None),
                ]
            ],
        )

    b_cfg = config.get("brokers", {}).get(broker_name, {})
    var_key = tk.StringVar(value=b_cfg.get("app_key", ""))
    var_sec = tk.StringVar(value=b_cfg.get("app_secret", ""))

    form = tk.Frame(wiz, bg="#0d1117")
    form.pack(fill="x", pady=4)

    tk.Label(
        form,
        text=f"{broker_name} App Key:",
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#0d1117",
        width=18,
        anchor="w"
    ).grid(row=0, column=0, pady=6, sticky="w")
    tk.Entry(
        form,
        textvariable=var_key,
        font=("Consolas", 10, "bold"),
        width=52,
        bg="#0e141d",
        fg="#e2e8f0",
        insertbackground="#e2e8f0",
        bd=0,
        highlightthickness=1,
        highlightbackground="#28374a",
        highlightcolor="#38bdf8",
    ).grid(row=0, column=1, pady=6, padx=8, ipady=5)

    tk.Label(
        form,
        text=f"{broker_name} App Secret:",
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#0d1117",
        width=18,
        anchor="w"
    ).grid(row=1, column=0, pady=6, sticky="w")
    tk.Entry(
        form,
        textvariable=var_sec,
        font=("Consolas", 10, "bold"),
        width=52,
        bg="#0e141d",
        fg="#e2e8f0",
        insertbackground="#e2e8f0",
        show="*",
        bd=0,
        highlightthickness=1,
        highlightbackground="#28374a",
        highlightcolor="#38bdf8",
    ).grid(row=1, column=1, pady=6, padx=8, ipady=5)

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
            tok_info = f"● Current 7-Day Schwab Token Status: {rem_h / 24.0:.1f} days ({rem_h:.0f}h) remaining."
            tok_col = "#4ade80" if rem_h >= 36.0 else "#fbbf24"
        elif os.path.exists(SCHWAB_TOKEN_PATH):
            tok_info = "● Current 7-Day Schwab Token Status: Expired — will prompt browser login on connect."
            tok_col = "#eb7067"
        else:
            tok_info = "● Current 7-Day Schwab Token Status: Not yet authenticated."
            tok_col = "#8b9bb0"
        tk.Label(
            wiz,
            text=tok_info,
            font=("Arial", 9, "bold"),
            fg=tok_col,
            bg="#0d1117",
            anchor="w"
        ).pack(fill="x", pady=(6, 2))

    btn_bar = tk.Frame(wiz, bg="#0d1117", pady=12)
    btn_bar.pack(fill="x")

    make_stadium_button(
        btn_bar,
        text="Cancel",
        font=("Arial", 10, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#475569",
        fg="#cbd5e1",
        canvas_bg="#0d1117",
        width=112,
        height=36,
        pad_x=28,
        command=wiz.destroy,
    ).pack(side="left")

    make_stadium_button(
        btn_bar,
        text=f"🚀 Save & Connect {broker_name} >>",
        font=("Arial", 10, "bold"),
        fill_color="#0d3b20",
        fill_top_color="#14532d",
        border_color="#10b981",
        hover_fill="#114b29",
        hover_fill_top="#196638",
        hover_border="#34d399",
        fg="#ffffff",
        canvas_bg="#0d1117",
        width=226,
        height=36,
        pad_x=32,
        command=lambda: save_keys(force_token_renew=False),
    ).pack(side="right")

    if broker_name == "SCHWAB" and os.path.exists(SCHWAB_TOKEN_PATH):
        make_stadium_button(
            btn_bar,
            text="🔄 Renew 7-Day Token Now",
            font=("Arial", 10, "bold"),
            fill_color="#141820",
            fill_top_color="#1c212b",
            border_color="#2e3746",
            hover_fill="#181e28",
            hover_fill_top="#232a36",
            hover_border="#475569",
            fg="#e2e8f0",
            canvas_bg="#0d1117",
            width=206,
            height=36,
            pad_x=28,
            command=lambda: save_keys(force_token_renew=True),
        ).pack(side="right", padx=(0, 10))

    center_dialog_over_parent(wiz, parent=parent)
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
last_alarm_reason = ""
daily_breach_settings_prompted = False


def get_full_idle_button_text():
    b_name = config.get("active_broker", "SCHWAB")
    if pending_halt_breach is not None:
        w_syms = (
            ", ".join(
                (pending_halt_breach.get("watched_positions") or {}).keys()
            )
            or "OPEN SHARES"
        )
        return (
            f"⏳ HALT WATCH ({w_syms}): EXIT ORDER WORKING — "
            f"OS LOCK DEFERRED UNTIL 100% FLAT"
        )
    if config.get("alarms_only_mode", False):
        return f"{b_name} : ALARMS ONLY MODE (OBSERVATION / SIREN ONLY)"
    opt_armed = is_options_flatten_armed(config)
    pills = [b_name]
    if config.get("enable_open_flatten", False):
        oml = config.get("open_max_loss", 500.0)
        if config.get("enable_open_cooldown", False):
            cd_m = config.get("open_cooldown_mins", 1.0)
            pills.append(f"OPEN STOP (-${oml:,.0f} + {cd_m:g}m LOCK)")
        else:
            pills.append(f"OPEN STOP (-${oml:,.0f})")
    if config.get("enable_consec_loss_cooldown", False):
        cur_s, c_cnt, next_s, _full_s, _is_en = get_loss_streak_status()
        c_win = float(config.get("consec_loss_window_mins", 15.0))
        if cur_s > 0:
            pills.append(
                f"TILT STOP ({cur_s}/{c_cnt} · {_format_countdown_mm_ss(next_s)})"
            )
        else:
            pills.append(f"TILT STOP (0/{c_cnt} · {c_win:g}m)")
    if is_locked_down:
        pills.append("DAY STOP: BREACHED (DISARMED)")
    else:
        daily_parts = []
        if config.get("enable_auto_flatten", False):
            daily_parts.append(
                "DAY FLATTEN + OPT(BETA)" if opt_armed else "DAY FLATTEN"
            )
        elif opt_armed and config.get("enable_open_flatten", False):
            daily_parts.append("OPT FLAT(BETA)")
        if config.get("enable_kill_tos", False):
            daily_parts.append("KILL TOS")
        if config.get("enable_kill_webull", False):
            daily_parts.append("KILL WEBULL")
        if config.get("enable_lock_os", False):
            dl_m = config.get("daily_lock_mins", 15.0)
            daily_parts.append(
                f"LOCK OS ({dl_m:g}m)" if dl_m > 0 else "LOCK OS (1x)"
            )
        if daily_parts:
            pills.append(" + ".join(daily_parts))

    if len(pills) == 1:
        return f"{b_name} : ALARM ONLY (OBSERVATION MODE)"
    return "ARMED: " + " + ".join(pills)


def get_medium_idle_button_text():
    """Returns a concise summary for 4-column HUD mode (~335px middle pill)
    that shows the active broker and all armed stops without overflowing."""
    b_name = config.get("active_broker", "SCHWAB")
    if pending_halt_breach is not None:
        w_syms = (
            ", ".join(
                (pending_halt_breach.get("watched_positions") or {}).keys()
            )
            or "OPEN"
        )
        return f"⏳ HALT WATCH ({w_syms}) — LOCK DEFERRED UNTIL FLAT"
    if config.get("alarms_only_mode", False):
        return f"{b_name} : ALARMS ONLY MODE (SIREN ONLY)"
    opt_armed = is_options_flatten_armed(config)
    pills = [b_name]
    if config.get("enable_open_flatten", False):
        oml = config.get("open_max_loss", 500.0)
        if config.get("enable_open_cooldown", False):
            cd_m = config.get("open_cooldown_mins", 1.0)
            pills.append(f"OPEN(-${oml:,.0f}/{cd_m:g}m)")
        else:
            pills.append(f"OPEN(-${oml:,.0f})")
    if config.get("enable_consec_loss_cooldown", False):
        cur_s, c_cnt, next_s, _full_s, _is_en = get_loss_streak_status()
        c_win = float(config.get("consec_loss_window_mins", 15.0))
        if cur_s > 0:
            pills.append(
                f"TILT({cur_s}/{c_cnt} {_format_countdown_mm_ss(next_s)})"
            )
        else:
            pills.append(f"TILT(0/{c_cnt} {c_win:g}m)")
    if is_locked_down:
        pills.append("DAY STOP: BREACHED")
    else:
        daily_parts = []
        if config.get("enable_auto_flatten", False):
            daily_parts.append("DAY+OPT(BETA)" if opt_armed else "DAY FLAT")
        elif opt_armed and config.get("enable_open_flatten", False):
            daily_parts.append("OPT(BETA)")
        if config.get("enable_kill_tos", False) or config.get("enable_kill_webull", False):
            daily_parts.append("KILL APP")
        if config.get("enable_lock_os", False):
            dl_m = config.get("daily_lock_mins", 15.0)
            daily_parts.append(
                f"LOCK({dl_m:g}m)" if dl_m > 0 else "LOCK(1x)"
            )
        if daily_parts:
            pills.extend(daily_parts)

    if len(pills) == 1:
        return f"{b_name} : ALARM ONLY (OBSERVATION)"
    return "ARMED: " + " · ".join(pills)


def get_idle_button_text():
    n_cols = len(get_active_hud_columns(config))
    full_txt = get_full_idle_button_text()
    if n_cols <= 3:
        if pending_halt_breach is not None:
            w_syms = (
                ", ".join(
                    (pending_halt_breach.get("watched_positions") or {}).keys()
                )
                or "OPEN"
            )
            return f"⏳ HALT ({w_syms})"
        if "ALARM" in full_txt and not full_txt.startswith("ARMED:"):
            return "● ALARMS ONLY"
        if is_locked_down:
            return "⚠️ DAY BREACHED"
        return "● ARMED"
    if n_cols == 4:
        return get_medium_idle_button_text()
    return full_txt


def format_alarm_button_text(reason):
    if is_compact_hud():
        return "MUTE ALARM"
    return f"ACKNOWLEDGE ALARM ({reason})"


def is_disconnect_alarm_reason(reason):
    """Returns True when an alarm reason represents a broker API connection
    drop or token expiration rather than a position/loss threshold breach."""
    r_up = str(reason or "").upper()
    return any(
        k in r_up
        for k in ("CONNECTION LOST", "DISCONNECTED", "TOKEN EXPIRED")
    )


def play_disconnect_tone_once():
    """Plays a calm, non-startling 2-note descending telemetry tone
    (660 Hz E5 -> 440 Hz A4) so API connection drops never sound like an
    emergency position/loss siren."""
    try:
        winsound.Beep(660, 150)
        time.sleep(0.04)
        winsound.Beep(440, 220)
    except Exception:
        pass


def sound_disconnect_alert_loop():
    """Plays the calm 2-note descending connection-loss tone once immediately
    and then repeats gently every 4.5 seconds until acknowledged or restored."""
    global alarm_active
    while alarm_active and not cooldown_active:
        if not is_disconnect_alarm_reason(last_alarm_reason):
            break
        play_disconnect_tone_once()
        # Wait 4.5s between gentle reminders in 0.15s slices for instant mute/recovery
        for _ in range(30):
            if (
                not alarm_active
                or cooldown_active
                or not is_disconnect_alarm_reason(last_alarm_reason)
            ):
                break
            time.sleep(0.15)


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
    global alarm_active, triggered_alarms, last_alarm_reason
    if reason in triggered_alarms:
        return

    triggered_alarms[reason] = time.time()
    last_alarm_reason = reason
    extra = f" | {context_str}" if context_str else ""

    if cooldown_active:
        log_event(
            "ALARM",
            f"Suppressed siren during OS Cool-Down Lock: {reason}{extra}"
        )
        return

    log_event("ALARM", f"Triggered: {reason}{extra}")
    alarm_active = True
    btn_txt = format_alarm_button_text(reason)
    ui_button.after(
        0,
        lambda: ui_button.config(
            text=btn_txt,
            bg="#eab308",
            fg="#090d16",
            disabledforeground="#090d16",
            state="normal",
        )
    )
    loop_fn = (
        sound_disconnect_alert_loop
        if is_disconnect_alarm_reason(reason)
        else sound_alarm_loop
    )
    threading.Thread(target=loop_fn, daemon=True).start()


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


def _prompt_daily_breach_settings_on_unlock(ui_button=None):
    """Automatically opens Pre-Flight Settings with the Post-Daily-Breach
    Review prompt once a Daily Stop lockout finishes, so the trader can either
    raise their Daily Max Loss / Re-Zero Baseline or leave it disarmed."""
    global daily_breach_settings_prompted
    if daily_breach_settings_prompted:
        return
    if not is_locked_down or not current_is_flat or settings_win_open:
        return
    if hud_root is None or not hud_root.winfo_exists():
        return
    daily_breach_settings_prompted = True
    log_event(
        "SESSION",
        "Auto-opening Pre-Flight Settings after Daily Stop Breach lockout "
        "for limit review."
    )
    show_preflight_window(
        parent=hud_root,
        mute_btn=ui_button,
        post_daily_breach_prompt=True,
    )


def mute_alarm(ui_button):
    global alarm_active, last_alarm_reason
    alarm_active = False
    last_alarm_reason = ""
    hide_fn = getattr(ui_button, "_hide_tooltip_fn", None)
    if callable(hide_fn):
        hide_fn()
    log_event("ALARM", "User acknowledged and muted siren.")
    if not cooldown_active:
        if api_disconnect_alerted or consecutive_api_failures >= 2:
            att = max(1, consecutive_api_failures)
            re_txt = (
                f"🔄 RECONNECTING (#{att})..."
                if is_compact_hud()
                else f"🔄 CONNECTION LOST — AUTO-RECONNECTING (ATTEMPT #{att})..."
            )
            ui_button.config(
                text=re_txt,
                bg="#78350f",
                fg="#fde68a",
                disabledforeground="#fde68a",
                state="disabled",
            )
        else:
            ui_button.config(
                text=get_idle_button_text(),
                bg="#222629",
                fg="#f5b041",
                disabledforeground="#f5b041",
                state="disabled"
            )
            if is_locked_down and not daily_breach_settings_prompted:
                ui_button.after(
                    250,
                    lambda: _prompt_daily_breach_settings_on_unlock(ui_button),
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


_tts_state_lock = threading.Lock()
_tts_queue = []
_tts_active_proc = None
_tts_worker_running = False


def _build_tts_ps_cmd(safe_text, safe_voice):
    return (
        "$sp = $null; "
        "try { "
        "$sp = New-Object -ComObject SAPI.SpVoice; "
        "$cat = New-Object -ComObject SAPI.SpObjectTokenCategory; "
        "$cat.SetId('HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech_OneCore\\Voices', $false); "
        f"foreach ($t in $cat.EnumerateTokens()) {{ if ($t.GetDescription() -match '{safe_voice}') {{ $sp.Voice = $t; break }} }}; "
        "$sp.Rate = 1 "
        "} catch { $sp = $null }; "
        "if ($sp -ne $null) { "
        f"try {{ [void]$sp.Speak('{safe_text}') }} catch {{}} "
        "} else { "
        "try { "
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"try {{ $s.SelectVoice('Microsoft {safe_voice} Desktop') }} catch {{}}; "
        f"$s.Speak('{safe_text}') "
        "} catch {} "
        "}"
    )


def _tts_worker_loop():
    global _tts_active_proc, _tts_worker_running
    while True:
        with _tts_state_lock:
            if not _tts_queue:
                _tts_active_proc = None
                _tts_worker_running = False
                return
            safe_text, safe_voice = _tts_queue.pop(0)
            ps_cmd = _build_tts_ps_cmd(safe_text, safe_voice)
            try:
                proc = subprocess.Popen(
                    [
                        "powershell",
                        "-NoProfile",
                        "-WindowStyle",
                        "Hidden",
                        "-Command",
                        ps_cmd,
                    ],
                    creationflags=getattr(
                        subprocess, "CREATE_NO_WINDOW", 0x08000000
                    ),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                _tts_active_proc = proc
            except Exception:
                proc = None
                _tts_active_proc = None
        if proc is not None:
            try:
                proc.wait(timeout=15)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def speak_async(text, force=False, voice_override=None, interrupt=False):
    """Speaks text asynchronously using Windows OneCore / SAPI speech synthesis
    (supports Zira, Mark, and David voices). Serializes queued phrases so two
    voice cues never talk over each other, or preempts active speech immediately
    when interrupt=True."""
    global _tts_active_proc, _tts_worker_running
    if not force and not config.get("enable_voice_cues", True):
        return
    try:
        safe_text = str(text).replace("'", "")
        voice_id = (
            voice_override
            or config.get("tts_voice", "Zira")
            or "Zira"
        )
        safe_voice = str(voice_id).replace("'", "")
        with _tts_state_lock:
            if interrupt:
                _tts_queue.clear()
                if _tts_active_proc is not None:
                    try:
                        _tts_active_proc.kill()
                    except Exception:
                        pass
                    _tts_active_proc = None
            _tts_queue.append((safe_text, safe_voice))
            if not _tts_worker_running:
                _tts_worker_running = True
                threading.Thread(target=_tts_worker_loop, daemon=True).start()
    except Exception:
        pass


def stop_active_tts():
    """Clears any queued speech and terminates any currently speaking TTS
    subprocess so unlock chimes or completion announcements start cleanly."""
    global _tts_active_proc
    with _tts_state_lock:
        _tts_queue.clear()
        if _tts_active_proc is not None:
            try:
                _tts_active_proc.kill()
            except Exception:
                pass
            _tts_active_proc = None


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


def trigger_upside_tier_glow(
    ui_button, banner_text, log_msg, log_tag="RATCHET"
):
    """Logs the tier ratchet (or connection recovery when log_tag='SESSION')
    and, if enabled, plays the upside chime and pulses the bottom HUD status
    bar with a 3-second emerald glow."""
    log_event(log_tag, log_msg)
    if not config.get("enable_upside_chime", True):
        return
    if alarm_active or cooldown_active or ui_button is None:
        return

    play_upside_tier_chime()

    # 6 steps x 500ms = 3.0 seconds total
    glow_steps = [
        ("#00e676", "#ffffff"),
        ("#2ecc71", "#ffffff"),
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
            disp_banner = (
                "★ FLOOR RAISED ★" if is_compact_hud() else banner_text
            )
            ui_button.config(
                text=disp_banner,
                bg=bg_c,
                fg=fg_c,
                disabledforeground=fg_c,
                state="disabled"
            )
            ui_button.after(500, lambda: _step(idx + 1))
        else:
            if not alarm_active and not cooldown_active:
                ui_button.config(
                    text=get_idle_button_text(),
                    bg="#222629",
                    fg="#f5b041",
                    disabledforeground="#f5b041",
                    state="disabled"
                )

    ui_button.after(0, lambda: _step(0))


def is_workstation_locked():
    """Returns True when the Windows session is locked (WTSSessionInfoEx
    SessionFlags == WTS_SESSIONSTATE_LOCK [0] on Windows 8/10/11), and False
    only when the session is unlocked (WTS_SESSIONSTATE_UNLOCK [1])."""
    try:
        wts = ctypes.windll.wtsapi32
        k32 = ctypes.windll.kernel32
        ppbuf = ctypes.c_void_p()
        bytes_ret = ctypes.c_ulong(0)
        sess_id = k32.WTSGetActiveConsoleSessionId()
        ok = wts.WTSQuerySessionInformationW(
            0, sess_id, 25, ctypes.byref(ppbuf), ctypes.byref(bytes_ret)
        )
        if ok and ppbuf.value and bytes_ret.value >= 20:
            try:
                raw = ctypes.string_at(ppbuf.value, 20)
                _, _, _, _, sflags = struct.unpack("<IIiiI", raw)
                return sflags == 0
            finally:
                wts.WTSFreeMemory(ppbuf)
    except Exception:
        pass
    return False


def _format_exact_remaining_voice_msg(rem_seconds):
    """Formats the exact remaining lockout time for verbal announcement when
    an early screen-unlock attempt is detected and immediately re-locked."""
    rem = max(1, int(round(float(rem_seconds))))
    mins = rem // 60
    secs = rem % 60
    if mins > 0 and secs > 0:
        m_word = "minute" if mins == 1 else "minutes"
        s_word = "second" if secs == 1 else "seconds"
        return f"Lockout still active. {mins} {m_word} and {secs} {s_word} remaining."
    if mins > 0:
        m_word = "minute" if mins == 1 else "minutes"
        return f"Lockout still active. {mins} {m_word} remaining."
    s_word = "second" if secs == 1 else "seconds"
    return f"Lockout still active. {secs} {s_word} remaining."


def _format_exact_remaining_log_str(rem_seconds):
    rem = max(1, int(round(float(rem_seconds))))
    mins = rem // 60
    secs = rem % 60
    return f"{mins}m {secs:02d}s" if mins > 0 else f"{secs}s"


def _format_lock_voice_msg(duration_mins, label_prefix, upgraded=False):
    mins_val = float(duration_mins)
    dur_words = "1 minute" if mins_val == 1.0 else f"{mins_val:g} minutes"
    lp_upper = str(label_prefix).upper()
    is_daily = "DAILY" in lp_upper
    is_tilt = "TILT" in lp_upper or "STREAK" in lp_upper
    if upgraded:
        reason_words = "Upgraded to daily floor breach" if is_daily else "Lockout extended"
    else:
        if is_daily:
            reason_words = "Daily floor breached"
        elif is_tilt:
            reason_words = "Consecutive loss cooldown triggered"
        else:
            reason_words = "Open P and L stop triggered"
    return f"{reason_words}. Locked out for {dur_words}."


def _run_post_lock_watchdog(adapter, ui_button, lock_context="OS LOCK"):
    """Executes a Two-Stage Post-Lock Straggler Watchdog (Stage 1 at T+2.0s and
    Stage 2 at T+15.0s) after Windows OS lock engages, with verbal confirmations."""
    if adapter is None:
        return

    is_one_shot = "ONE-SHOT" in str(lock_context).upper()

    def _check_or_sweep_stage(stage_num, elapsed_tag):
        global cooldown_active
        opt_armed = is_options_flatten_armed(config)
        post_pos = adapter.get_open_equity_positions()
        post_opt = (
            adapter.get_open_option_positions()
            if opt_armed and hasattr(adapter, "get_open_option_positions")
            else []
        )
        if post_pos is None or (opt_armed and post_opt is None):
            log_event(
                "WARNING",
                f"POST-LOCK WATCHDOG STAGE {stage_num} ({elapsed_tag} | {lock_context}): "
                f"Position check returned None; retrying in 1.5s..."
            )
            time.sleep(1.5)
            post_pos = adapter.get_open_equity_positions()
            post_opt = (
                adapter.get_open_option_positions()
                if opt_armed and hasattr(adapter, "get_open_option_positions")
                else []
            )

        eq_ok = (post_pos is not None and len(post_pos) == 0)
        opt_ok = (not opt_armed) or (post_opt is not None and len(post_opt) == 0)

        if eq_ok and opt_ok:
            if stage_num == 1:
                log_event(
                    "GUARDRAIL",
                    f"POST-LOCK WATCHDOG STAGE 1 (2.0s | {lock_context}): "
                    f"Triple-confirmed 0 open equity shares"
                    + (" and 0 open option contracts." if opt_armed else ".")
                )
                if not is_one_shot:
                    time.sleep(1.8)
                speak_async("Initial flat check passed.")
            else:
                log_event(
                    "GUARDRAIL",
                    f"POST-LOCK WATCHDOG STAGE 2 (15.0s | {lock_context}): "
                    f"15-second sweep clear — confirmed 0 open equity shares"
                    + (" and 0 open option contracts." if opt_armed else ".")
                )
                speak_async("15 second sweep clear, account confirmed flat.")
            return True

        straggler_desc = (
            f"Equities={post_pos}, Options={[(x[0], x[1]) for x in (post_opt or [])]}"
            if opt_armed
            else f"{post_pos}"
        )
        log_event(
            "CRITICAL",
            f"POST-LOCK WATCHDOG STAGE {stage_num} ({elapsed_tag} | {lock_context}): "
            f"Straggler positions detected after OS lock: {straggler_desc}! "
            f"Initiating emergency sweep..."
        )
        speak_async("Warning, straggler shares detected, flattening now.", interrupt=True)
        swept_flat = flatten_equities(
            adapter, force_flatten=True, include_options=opt_armed
        )
        if swept_flat:
            log_event(
                "GUARDRAIL",
                f"POST-LOCK WATCHDOG STAGE {stage_num} ({elapsed_tag} | {lock_context}): "
                f"Emergency post-lock sweep confirmed 100% flat."
            )
            speak_async("Emergency flatten complete, account confirmed flat.")
            return True

        log_event(
            "CRITICAL",
            f"POST-LOCK WATCHDOG STAGE {stage_num} ({elapsed_tag} | {lock_context}): "
            f"Post-lock flatten FAILED! Aborting OS lock and sounding emergency siren!"
        )
        cooldown_active = False
        trigger_alarm(
            "POST-LOCK FLATTEN FAILED — CHECK POSITIONS!", ui_button
        )
        return False

    def _watchdog():
        lock_start_ts = time.time()
        try:
            # Stage 1: T + 2.0s initial post-lock verification
            time.sleep(2.0)
            if not is_one_shot and not cooldown_active:
                return
            if not _check_or_sweep_stage(1, "2.0s"):
                return

            # Stage 2: T + 15.0s delayed sweep to catch late ECN/unhalt prints
            rem_wait = max(1.0, 15.0 - (time.time() - lock_start_ts))
            time.sleep(rem_wait)
            if not is_one_shot and not cooldown_active:
                return
            _check_or_sweep_stage(2, "15.0s")
        except Exception as e:
            log_event("ERROR", f"Post-lock watchdog exception: {e}")

    threading.Thread(target=_watchdog, daemon=True).start()


def start_cooldown_lock(
    duration_mins, ui_button, label_prefix="COOL-DOWN LOCK", adapter=None
):
    global cooldown_active, cooldown_end_time, cooldown_label
    global cooldown_30s_announced, cooldown_announced_mins, alarm_active
    duration_sec = max(5, int(round(float(duration_mins) * 60)))
    new_end_time = time.time() + duration_sec
    init_announced_mins = {
        m for m in range(1, (duration_sec // 60) + 3)
        if (m * 60) >= (duration_sec - 10)
    }

    if cooldown_active:
        if new_end_time > cooldown_end_time:
            cooldown_end_time = new_end_time
            cooldown_label = label_prefix
            cooldown_30s_announced = (duration_sec <= 35)
            cooldown_announced_mins = set(init_announced_mins)
            log_event(
                "COOLDOWN",
                f"Upgraded active lock to {label_prefix} for {duration_sec}s "
                f"({duration_mins:g} min). Siren muted."
            )
            speak_async(
                _format_lock_voice_msg(duration_mins, label_prefix, upgraded=True),
                interrupt=True,
            )
            _run_post_lock_watchdog(adapter, ui_button, label_prefix)
        return

    cooldown_active = True
    cooldown_end_time = new_end_time
    cooldown_label = label_prefix
    cooldown_30s_announced = (duration_sec <= 35)
    cooldown_announced_mins = set(init_announced_mins)
    alarm_active = False

    def cooldown_worker():
        global cooldown_active, cooldown_end_time, cooldown_label
        global cooldown_30s_announced, cooldown_announced_mins, alarm_active
        log_event(
            "COOLDOWN",
            f"Persistent {cooldown_label} started for {duration_sec}s "
            f"({duration_mins:g} min). Siren muted."
        )
        try:
            ctypes.windll.user32.LockWorkStation()
        except Exception:
            pass
        time.sleep(0.35)
        speak_async(_format_lock_voice_msg(duration_mins, cooldown_label, upgraded=False))
        watchdog_launched = False
        lock_started_ts = time.time()
        confirmed_locked = is_workstation_locked()
        last_early_unlock_ts = 0.0
        while cooldown_active and time.time() < cooldown_end_time:
            alarm_active = False
            now_ts = time.time()
            rem = max(0, int(round(cooldown_end_time - now_ts)))
            currently_locked = is_workstation_locked()
            if currently_locked:
                confirmed_locked = True
            else:
                try:
                    ctypes.windll.user32.LockWorkStation()
                except Exception:
                    pass
                if (
                    confirmed_locked
                    and (now_ts - lock_started_ts) >= 1.5
                    and rem >= 1
                    and (now_ts - last_early_unlock_ts) >= 2.5
                ):
                    confirmed_locked = False
                    last_early_unlock_ts = now_ts
                    rem_log = _format_exact_remaining_log_str(rem)
                    log_event(
                        "COOLDOWN",
                        f"Early unlock attempt detected during {cooldown_label} "
                        f"({rem_log} remaining) — workstation immediately re-locked."
                    )
                    time.sleep(0.30)
                    rem_voice = max(1, int(round(cooldown_end_time - time.time())))
                    speak_async(
                        _format_exact_remaining_voice_msg(rem_voice),
                        interrupt=True,
                    )
            recent_early_callout = (time.time() - last_early_unlock_ts) < 4.0
            if rem > 35:
                m_mark = (rem + 4) // 60
                if (
                    m_mark >= 1
                    and m_mark not in cooldown_announced_mins
                    and (m_mark * 60) - 5 <= rem <= (m_mark * 60)
                ):
                    cooldown_announced_mins.add(m_mark)
                    if not recent_early_callout:
                        m_word = "minute" if m_mark == 1 else "minutes"
                        speak_async(f"{m_mark} {m_word} remaining until unlock.")
            if not cooldown_30s_announced and 0 < rem <= 30:
                cooldown_30s_announced = True
                if not recent_early_callout:
                    speak_async("30 seconds remaining until unlock.")
            txt = (
                f"🔒 LOCKED: {rem}s"
                if is_compact_hud()
                else f"{cooldown_label} ACTIVE: {rem}s REMAINING (DO NOT REVENGE TRADE)"
            )
            ui_button.after(
                0,
                lambda t=txt: ui_button.config(
                    text=t,
                    bg="#922b21",
                    fg="white",
                    disabledforeground="white",
                    state="disabled"
                )
            )
            if not watchdog_launched:
                watchdog_launched = True
                _run_post_lock_watchdog(adapter, ui_button, cooldown_label)
            time.sleep(0.20)

        if not cooldown_active:
            log_event(
                "COOLDOWN",
                f"{cooldown_label} aborted early by post-lock watchdog."
            )
            return

        was_daily_breach_lock = "DAILY" in str(cooldown_label).upper()
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
                bg="#222629",
                fg="#f5b041",
                disabledforeground="#f5b041",
                state="disabled"
            )
        )
        stop_active_tts()
        play_unlock_chimes()
        if was_daily_breach_lock and is_locked_down:
            ui_button.after(
                350,
                lambda: _prompt_daily_breach_settings_on_unlock(ui_button),
            )

    threading.Thread(target=cooldown_worker, daemon=True).start()


def flatten_equities(adapter, force_flatten=False, include_options=None):
    """Cancels working orders, submits RTH Market or EXT Limit liquidations
    for EQUITIES (and RTH Market liquidations for OPTIONS when the BETA Options
    Auto-Flatten toggle + waiver are active), and double-confirms (with 0.8s
    settlement delay) that 0 open positions remain."""
    alarms_only = config.get("alarms_only_mode", False)
    should_exec = (not alarms_only) and (
        force_flatten or config.get("enable_auto_flatten", False)
    )
    if include_options is None:
        include_options = is_options_flatten_armed(config)
    else:
        include_options = bool(include_options and is_options_flatten_armed(config))

    def _fmt_opt_summary(opt_list):
        if not opt_list:
            return "[]"
        return str([(x[0], x[1]) for x in opt_list])

    try:
        if include_options and not is_market_hours():
            # US equity options only trade during RTH (9:30 AM - 4:00 PM ET).
            # Check if any options are open; if none are open, proceed with
            # standard Extended-Hours equity flatten.
            eh_opt = (
                adapter.get_open_option_positions()
                if hasattr(adapter, "get_open_option_positions")
                else []
            )
            if eh_opt is not None and len(eh_opt) == 0:
                include_options = False
            else:
                # Flatten any open equities first, then return False because
                # options cannot be market-flattened outside RTH.
                flatten_equities(
                    adapter, force_flatten=force_flatten, include_options=False
                )
                log_event(
                    "GUARDRAIL",
                    f"Options Auto-Flatten (BETA) is enabled, but US options "
                    f"market is closed (outside 9:30 AM – 4:00 PM ET). "
                    f"Open options require manual action: {_fmt_opt_summary(eh_opt)}"
                )
                return False

        submitted_close_eq = {}
        submitted_close_opt = {}
        ever_seen_eq = set()
        confirmed_closed_eq = set()
        ever_seen_opt = set()
        confirmed_closed_opt = set()

        def _filter_uncovered_positions(pos_list, submitted_map):
            if not pos_list:
                return []
            preserved_map = getattr(adapter, "last_preserved_close_qty", {}) or {}
            failed_cancels = getattr(adapter, "last_cancel_failed_syms", set()) or set()
            uncovered = []
            for item in pos_list:
                sym = item[0]
                qty = float(item[1])
                abs_q = abs(qty)
                pres_q = float(preserved_map.get(sym, 0.0))
                sub_q = float(submitted_map.get(sym, 0.0))
                if pres_q >= (abs_q - 1e-6) or (
                    is_market_hours()
                    and sub_q >= (abs_q - 1e-6)
                    and sym in failed_cancels
                ):
                    log_event(
                        "FLATTEN",
                        f"Working close order already active for {sym} ({qty:+g}) "
                        f"— preserving queue priority without duplicate submission.",
                    )
                    submitted_map[sym] = max(sub_q, abs_q)
                else:
                    uncovered.append(item)
            return uncovered

        def _filter_stale_replica_resurrections(
            pos_list, confirmed_closed_set, is_opt_flag=False
        ):
            if not pos_list or not confirmed_closed_set:
                return pos_list
            suspect = [x[0] for x in pos_list if x[0] in confirmed_closed_set]
            if not suspect:
                return pos_list
            time.sleep(0.35)
            re_list = (
                adapter.get_open_option_positions()
                if is_opt_flag and hasattr(adapter, "get_open_option_positions")
                else adapter.get_open_equity_positions()
            )
            if re_list is not None:
                re_syms = {x[0] for x in re_list}
                vanished = [s for s in suspect if s not in re_syms]
                if vanished:
                    log_event(
                        "FLATTEN",
                        f"Filtered stale read-replica resurrection of already-closed "
                        f"{'option' if is_opt_flag else 'equity'} position(s): {vanished}",
                    )
                return [x for x in re_list if x[0] not in confirmed_closed_set]
            log_event(
                "FLATTEN",
                f"Filtered stale read-replica resurrection of already-closed "
                f"{'option' if is_opt_flag else 'equity'} position(s): {suspect}",
            )
            return [x for x in pos_list if x[0] not in confirmed_closed_set]

        if should_exec:
            log_event(
                "FLATTEN",
                "Starting emergency flatten sequence (Equities + Options BETA)..."
                if include_options
                else "Starting emergency equity flatten sequence..."
            )
            peek_pos = adapter.get_open_equity_positions()
            peek_opt = (
                adapter.get_open_option_positions()
                if include_options and hasattr(adapter, "get_open_option_positions")
                else []
            )
            init_preserve_map = {}
            for item in (peek_pos or []):
                init_preserve_map[item[0]] = item[1]
            for item in (peek_opt or []):
                init_preserve_map[item[0]] = item[1]

            adapter.cancel_all_working_orders(
                preserve_market_close_map=init_preserve_map
            )

            open_pos = adapter.get_open_equity_positions()
            if open_pos is None and peek_pos is not None:
                open_pos = peek_pos
            open_opt = (
                adapter.get_open_option_positions()
                if include_options and hasattr(adapter, "get_open_option_positions")
                else []
            )
            if include_options and open_opt is None and peek_opt is not None:
                open_opt = peek_opt

            for item in (open_pos or []):
                ever_seen_eq.add(item[0])
            for item in (open_opt or []):
                ever_seen_opt.add(item[0])

            if (
                open_pos is not None
                and len(open_pos) == 0
                and (not include_options or (open_opt is not None and len(open_opt) == 0))
            ):
                log_event(
                    "FLATTEN",
                    "Initial check shows 0 open positions. Running 0.8s "
                    "settlement double-confirm..."
                    if include_options
                    else "Initial check shows 0 open equity shares. Running 0.8s "
                    "settlement double-confirm..."
                )
                time.sleep(0.8)
                open_pos = adapter.get_open_equity_positions()
                open_opt = (
                    adapter.get_open_option_positions()
                    if include_options and hasattr(adapter, "get_open_option_positions")
                    else []
                )
                if (
                    open_pos is not None
                    and len(open_pos) == 0
                    and (not include_options or (open_opt is not None and len(open_opt) == 0))
                ):
                    log_event(
                        "FLATTEN",
                        "Double-confirmed 0 open equities & 0 open options (no flatten order needed)."
                        if include_options
                        else "Double-confirmed 0 open equity shares (no flatten order needed)."
                    )
                    return True

            if open_pos:
                to_sub_eq = _filter_uncovered_positions(
                    open_pos, submitted_close_eq
                )
                if to_sub_eq:
                    log_event("FLATTEN", f"Equity positions to liquidate: {to_sub_eq}")
                    sub_ok = adapter.submit_liquidation_batch(to_sub_eq) or {}
                    submitted_close_eq.update(sub_ok)
            if include_options and open_opt:
                to_sub_opt = _filter_uncovered_positions(
                    open_opt, submitted_close_opt
                )
                if to_sub_opt:
                    log_event(
                        "FLATTEN",
                        f"Option positions to liquidate (BETA): {_fmt_opt_summary(to_sub_opt)}"
                    )
                    sub_opt_ok = (
                        adapter.submit_option_liquidation_batch(to_sub_opt)
                        or {}
                    )
                    submitted_close_opt.update(sub_opt_ok)
            if open_pos is None or (include_options and open_opt is None):
                log_event(
                    "WARNING",
                    "Initial position query failed (None); entering verification polling loop..."
                )
        else:
            open_pos = adapter.get_open_equity_positions()
            open_opt = (
                adapter.get_open_option_positions()
                if include_options and hasattr(adapter, "get_open_option_positions")
                else []
            )
            if (
                open_pos is not None
                and len(open_pos) == 0
                and (not include_options or (open_opt is not None and len(open_opt) == 0))
            ):
                time.sleep(0.8)
                open_pos = adapter.get_open_equity_positions()
                open_opt = (
                    adapter.get_open_option_positions()
                    if include_options and hasattr(adapter, "get_open_option_positions")
                    else []
                )
                if (
                    open_pos is not None
                    and len(open_pos) == 0
                    and (not include_options or (open_opt is not None and len(open_opt) == 0))
                ):
                    return True
            log_event(
                "WARNING",
                f"Auto-Flatten is OFF, and positions remain open (or unverified): "
                f"Equities={open_pos}"
                + (f", Options={_fmt_opt_summary(open_opt)}" if include_options else "")
            )
            return False

        log_event(
            "FLATTEN",
            "Polling broker API to verify 0 open equities & 0 open options..."
            if include_options
            else "Polling broker API to verify 0 open equity shares..."
        )
        start_wait = time.time()
        polls = 0
        while time.time() - start_wait < 15:
            time.sleep(0.5 if polls == 0 else 1.5)
            polls += 1
            rem_pos = adapter.get_open_equity_positions()
            rem_opt = (
                adapter.get_open_option_positions()
                if include_options and hasattr(adapter, "get_open_option_positions")
                else []
            )
            elapsed = time.time() - start_wait
            if rem_pos is None or (include_options and rem_opt is None):
                log_event(
                    "WARNING",
                    f"Check #{polls} ({elapsed:.1f}s): Position query returned None; retrying..."
                )
                continue

            rem_pos = _filter_stale_replica_resurrections(
                rem_pos, confirmed_closed_eq, is_opt_flag=False
            )
            if include_options and rem_opt:
                rem_opt = _filter_stale_replica_resurrections(
                    rem_opt, confirmed_closed_opt, is_opt_flag=True
                )

            curr_eq_syms = {x[0] for x in rem_pos}
            for s in list(ever_seen_eq):
                if s not in curr_eq_syms:
                    confirmed_closed_eq.add(s)
            ever_seen_eq.update(curr_eq_syms)

            if include_options:
                curr_opt_syms = {x[0] for x in (rem_opt or [])}
                for s in list(ever_seen_opt):
                    if s not in curr_opt_syms:
                        confirmed_closed_opt.add(s)
                ever_seen_opt.update(curr_opt_syms)

            if len(rem_pos) == 0 and (not include_options or len(rem_opt) == 0):
                log_event(
                    "FLATTEN",
                    f"Check #{polls} ({elapsed:.1f}s): 0 open positions reported. "
                    f"Running 0.8s settlement double-confirm..."
                    if include_options
                    else f"Check #{polls} ({elapsed:.1f}s): 0 equity shares reported. "
                    f"Running 0.8s settlement double-confirm..."
                )
                time.sleep(0.8)
                rem_confirm = adapter.get_open_equity_positions()
                opt_confirm = (
                    adapter.get_open_option_positions()
                    if include_options and hasattr(adapter, "get_open_option_positions")
                    else []
                )
                elapsed_confirm = time.time() - start_wait
                if (
                    rem_confirm is not None
                    and len(rem_confirm) == 0
                    and (not include_options or (opt_confirm is not None and len(opt_confirm) == 0))
                ):
                    log_event(
                        "FLATTEN",
                        f"SUCCESS: Double-confirmed 0 equities & 0 options in {elapsed_confirm:.1f}s."
                        if include_options
                        else f"SUCCESS: Double-confirmed 0 equity shares in {elapsed_confirm:.1f}s."
                    )
                    return True
                if rem_confirm is None or (include_options and opt_confirm is None):
                    log_event(
                        "WARNING",
                        "0.8s double-confirm query returned None; continuing verification loop..."
                    )
                    continue
                log_event(
                    "FLATTEN",
                    f"Straggler positions detected on 0.8s double-confirm: "
                    f"Equities={rem_confirm}"
                    + (f", Options={_fmt_opt_summary(opt_confirm)}" if include_options else "")
                    + " — sweeping..."
                )
                if should_exec:
                    strag_map = {x[0]: x[1] for x in (rem_confirm or [])}
                    for x in (opt_confirm or []):
                        strag_map[x[0]] = x[1]
                    adapter.cancel_all_working_orders(
                        preserve_market_close_map=strag_map
                    )
                    to_s_eq = _filter_uncovered_positions(
                        rem_confirm, submitted_close_eq
                    )
                    if to_s_eq:
                        sub_ok = adapter.submit_liquidation_batch(to_s_eq) or {}
                        submitted_close_eq.update(sub_ok)
                    if include_options and opt_confirm:
                        to_s_opt = _filter_uncovered_positions(
                            opt_confirm, submitted_close_opt
                        )
                        if to_s_opt:
                            sub_opt_ok = (
                                adapter.submit_option_liquidation_batch(to_s_opt)
                                or {}
                            )
                            submitted_close_opt.update(sub_opt_ok)
                continue

            log_event(
                "FLATTEN",
                f"Check #{polls} ({elapsed:.1f}s): Positions still open: "
                f"Equities={rem_pos}, Options={_fmt_opt_summary(rem_opt)}"
                if include_options
                else f"Check #{polls} ({elapsed:.1f}s): Equities still open: {rem_pos}"
            )

            if should_exec and polls % 2 == 0:
                log_event(
                    "FLATTEN",
                    "Positions still open after 4s — inspecting working orders & sweeping uncovered shares..."
                    if include_options
                    else "Equities still open after 4s — inspecting working orders & sweeping uncovered shares..."
                )
                curr_preserve_map = {x[0]: x[1] for x in (rem_pos or [])}
                for x in (rem_opt or []):
                    curr_preserve_map[x[0]] = x[1]
                adapter.cancel_all_working_orders(
                    preserve_market_close_map=curr_preserve_map
                )
                rem_pos = adapter.get_open_equity_positions()
                rem_opt = (
                    adapter.get_open_option_positions()
                    if include_options and hasattr(adapter, "get_open_option_positions")
                    else []
                )
                if rem_pos is not None:
                    rem_pos = _filter_stale_replica_resurrections(
                        rem_pos, confirmed_closed_eq, is_opt_flag=False
                    )
                    for s in list(ever_seen_eq):
                        if s not in {x[0] for x in rem_pos}:
                            confirmed_closed_eq.add(s)
                if include_options and rem_opt is not None:
                    rem_opt = _filter_stale_replica_resurrections(
                        rem_opt, confirmed_closed_opt, is_opt_flag=True
                    )
                    for s in list(ever_seen_opt):
                        if s not in {x[0] for x in rem_opt}:
                            confirmed_closed_opt.add(s)

                if (
                    rem_pos is not None
                    and len(rem_pos) == 0
                    and (not include_options or (rem_opt is not None and len(rem_opt) == 0))
                ):
                    time.sleep(0.8)
                    rem_confirm = adapter.get_open_equity_positions()
                    opt_confirm = (
                        adapter.get_open_option_positions()
                        if include_options and hasattr(adapter, "get_open_option_positions")
                        else []
                    )
                    if (
                        rem_confirm is not None
                        and len(rem_confirm) == 0
                        and (not include_options or (opt_confirm is not None and len(opt_confirm) == 0))
                    ):
                        log_event(
                            "FLATTEN",
                            f"SUCCESS: Double-confirmed 0 positions after sweep "
                            f"({time.time() - start_wait:.1f}s)."
                            if include_options
                            else f"SUCCESS: Double-confirmed 0 equity shares after sweep "
                            f"({time.time() - start_wait:.1f}s)."
                        )
                        return True
                    rem_pos = rem_confirm
                    rem_opt = opt_confirm

                uncovered_eq = (
                    _filter_uncovered_positions(rem_pos, submitted_close_eq)
                    if rem_pos
                    else []
                )
                uncovered_opt = (
                    _filter_uncovered_positions(rem_opt, submitted_close_opt)
                    if (include_options and rem_opt)
                    else []
                )
                if uncovered_eq:
                    sub_ok = adapter.submit_liquidation_batch(uncovered_eq) or {}
                    submitted_close_eq.update(sub_ok)
                if include_options and uncovered_opt:
                    sub_opt_ok = (
                        adapter.submit_option_liquidation_batch(uncovered_opt)
                        or {}
                    )
                    submitted_close_opt.update(sub_opt_ok)

                if (
                    not uncovered_eq
                    and not uncovered_opt
                    and polls >= 4
                    and (rem_pos or (include_options and rem_opt))
                ):
                    log_event(
                        "FLATTEN",
                        f"All remaining open position(s) {[(x[0], x[1]) for x in (rem_pos or [])]} "
                        f"already have working close order(s) queued at broker (likely LULD / trading halt). "
                        f"Ending active sweep loop to preserve order queue priority.",
                    )
                    break

        log_event(
            "CRITICAL",
            "Flatten 15s timeout reached! Positions (Equities/Options) still open!"
            if include_options
            else "Equity flatten 15s timeout reached! Shares still open!"
        )
        return False

    except Exception as e:
        log_event("ERROR", f"Flatten execution exception: {e}")
        return False


def _close_active_settings_window_on_breach(ui_button=None):
    """If the user has the Settings window open while a live Open PnL Stop,
    Consecutive Loss Cooldown, or Daily Stop breaches in the background,
    automatically closes the Settings modal on the Tk main thread so the HUD
    alarm/lockout is unobstructed."""
    fn = active_preflight_close_fn
    if not settings_win_open or fn is None:
        return
    try:
        if ui_button is not None:
            ui_button.after(0, fn)
        else:
            fn()
    except Exception:
        pass


def _enter_halt_breach_watch(
    breach_type, reason, context_str, has_options, adapter, ui_button
):
    """Transitions an unflattened breach (e.g. a stock stuck in an LULD volatility
    halt with a working Market close order queued, or unflattened options) into
    passive Halt / Unfilled Position Watch so data_loop() does not re-trigger
    15-second cancel/re-submit loops every 2 seconds. As soon as data_loop()
    observes 0 open shares (unhalt fill or manual exit), it completes the
    deferred lockdown/cooldown automatically."""
    global pending_halt_breach
    watched = {}
    try:
        if adapter is not None:
            rem_eq = adapter.get_open_equity_positions()
            for item in (rem_eq or []):
                watched[str(item[0])] = float(item[1])
            if has_options and hasattr(adapter, "get_open_option_positions"):
                rem_opt = adapter.get_open_option_positions()
                for item in (rem_opt or []):
                    watched[f"{item[0]} (OPT)"] = float(item[1])
    except Exception:
        pass
    if not watched and isinstance(prev_pos_snapshot, dict):
        for k, d in prev_pos_snapshot.items():
            q = float(d.get("qty", 0.0))
            if abs(q) > 1e-6:
                watched[str(k)] = q

    prev_type = (
        pending_halt_breach.get("type")
        if isinstance(pending_halt_breach, dict)
        else None
    )
    eff_type = "DAILY" if (prev_type == "DAILY" or breach_type == "DAILY") else breach_type
    eff_reason = (
        pending_halt_breach.get("reason", reason)
        if (prev_type == "DAILY" and breach_type != "DAILY" and isinstance(pending_halt_breach, dict))
        else reason
    )
    pending_halt_breach = {
        "type": eff_type,
        "reason": eff_reason,
        "context_str": context_str,
        "has_options": bool(has_options),
        "watched_positions": watched,
        "started_ts": time.time(),
    }
    syms_label = ", ".join(watched.keys()) if watched else "OPEN SHARES"
    log_event(
        "GUARDRAIL",
        f"Entering Halt / Unfilled Position Watch ({eff_type}): "
        f"{watched or 'unverified open shares'}. Working exit order(s) preserved "
        f"in broker queue; suppressing repeat flatten loops and deferring "
        f"OS Lock / App Kill until 100% flat.",
    )
    fail_reason = (
        f"{eff_reason} — CHECK OPTIONS MANUALLY!"
        if has_options
        else f"{eff_reason} (HALT/UNFILLED: {syms_label})"
    )
    trigger_alarm(fail_reason, ui_button, context_str)


def trigger_open_pnl_flatten(
    adapter, reason, ui_button, has_options=False, context_str=""
):
    global alarm_active, pending_halt_breach
    _close_active_settings_window_on_breach(ui_button)
    cd_on = config.get("enable_open_cooldown", False)
    opt_armed = is_options_flatten_armed(config)

    if has_options and not opt_armed:
        opt_reason = f"{reason} — MANUAL OPTIONS EXIT REQUIRED!"
        log_event(
            "GUARDRAIL",
            f"Open PnL Stop breached with OPTIONS open ({context_str}). "
            f"Options Auto-Flatten (BETA) is OFF; flattening any equities and "
            f"waiting for manual options exit."
        )
        flatten_equities(adapter, force_flatten=True, include_options=False)
        _enter_halt_breach_watch(
            "OPEN_PNL", opt_reason, context_str, True, adapter, ui_button
        )
        return

    if has_options and opt_armed and not is_market_hours():
        opt_reason = f"{reason} — OPTIONS MARKET CLOSED (EXIT MANUALLY!)"
        log_event(
            "GUARDRAIL",
            f"Open PnL Stop breached with OPTIONS open outside RTH ({context_str}). "
            f"Options cannot be market-flattened outside 9:30–16:00 ET; "
            f"flattening any equities and sounding siren."
        )
        flatten_equities(adapter, force_flatten=True, include_options=False)
        _enter_halt_breach_watch(
            "OPEN_PNL", opt_reason, context_str, True, adapter, ui_button
        )
        return

    if not cd_on:
        trigger_alarm(reason, ui_button, context_str)
    else:
        alarm_active = False

    log_event(
        "GUARDRAIL",
        f"OPEN PnL AUTO-FLATTEN {'(EQUITIES + OPTIONS BETA) ' if (has_options and opt_armed) else ''}INITIATED: "
        f"{reason} | {context_str}"
    )
    all_flat = flatten_equities(
        adapter,
        force_flatten=True,
        include_options=(has_options and opt_armed)
    )
    if all_flat:
        pending_halt_breach = None
        log_event(
            "GUARDRAIL",
            "Open PnL bailout (Equities + Options BETA) confirmed 100% flat."
            if (has_options and opt_armed)
            else "Open PnL equity bailout confirmed 100% flat."
        )
        if cd_on:
            alarm_active = False
            cd_mins = config.get("open_cooldown_mins", 1.0)
            start_cooldown_lock(
                cd_mins,
                ui_button,
                label_prefix="PENALTY BOX LOCK",
                adapter=adapter
            )
    else:
        log_event(
            "CRITICAL",
            "Open PnL flatten timed out — Cool-Down Lock DEFERRED until "
            "halted/unfilled shares close!"
        )
        _enter_halt_breach_watch(
            "OPEN_PNL", reason, context_str, has_options, adapter, ui_button
        )


def trigger_consec_loss_cooldown(
    adapter, reason, ui_button, has_options=False, context_str=""
):
    """Executes the Card 1 Consecutive Loss Cooldown ('Tilt Streak Stop'):
    cancels working orders, flattens any open positions (if the trader flipped
    rather than closing flat), verifies 100% flat, and engages the Penalty Box
    OS Lock for open_cooldown_mins."""
    global alarm_active, recent_loss_timestamps, pending_halt_breach
    _close_active_settings_window_on_breach(ui_button)
    recent_loss_timestamps.clear()
    save_session_state()
    if config.get("alarms_only_mode", False):
        trigger_alarm(reason, ui_button, context_str)
        log_event(
            "GUARDRAIL",
            f"Consecutive Loss Stop reached ({reason}), but Alarms Only Mode is ON "
            f"(Observation Mode — Siren Only)."
        )
        return

    cd_on = config.get("enable_open_cooldown", True)
    opt_armed = is_options_flatten_armed(config)

    if has_options and not opt_armed:
        opt_reason = f"{reason} — MANUAL OPTIONS EXIT REQUIRED!"
        log_event(
            "GUARDRAIL",
            f"Consecutive Loss Cooldown triggered with OPTIONS open ({context_str}). "
            f"Options Auto-Flatten (BETA) is OFF; flattening any equities and "
            f"waiting for manual options exit."
        )
        flatten_equities(adapter, force_flatten=True, include_options=False)
        _enter_halt_breach_watch(
            "CONSEC_LOSS", opt_reason, context_str, True, adapter, ui_button
        )
        return

    if has_options and opt_armed and not is_market_hours():
        opt_reason = f"{reason} — OPTIONS MARKET CLOSED (EXIT MANUALLY!)"
        log_event(
            "GUARDRAIL",
            f"Consecutive Loss Cooldown triggered with OPTIONS open outside RTH ({context_str}). "
            f"Options cannot be market-flattened outside 9:30–16:00 ET; "
            f"flattening any equities and sounding siren."
        )
        flatten_equities(adapter, force_flatten=True, include_options=False)
        _enter_halt_breach_watch(
            "CONSEC_LOSS", opt_reason, context_str, True, adapter, ui_button
        )
        return

    if not cd_on:
        trigger_alarm(reason, ui_button, context_str)
    else:
        alarm_active = False

    log_event(
        "GUARDRAIL",
        f"CONSECUTIVE LOSS COOLDOWN TRIGGERED: {reason} | {context_str}"
    )
    all_flat = flatten_equities(
        adapter,
        force_flatten=True,
        include_options=(has_options and opt_armed)
    )
    if all_flat:
        pending_halt_breach = None
        log_event(
            "GUARDRAIL",
            "Consecutive Loss Cooldown confirmed 100% flat."
        )
        if cd_on:
            alarm_active = False
            cd_mins = float(config.get("open_cooldown_mins", 1.0))
            start_cooldown_lock(
                cd_mins,
                ui_button,
                label_prefix="TILT STREAK LOCK",
                adapter=adapter
            )
    else:
        log_event(
            "CRITICAL",
            "Consecutive Loss Cooldown flatten timed out — OS Lock DEFERRED "
            "until halted/unfilled shares close!"
        )
        _enter_halt_breach_watch(
            "CONSEC_LOSS", reason, context_str, has_options, adapter, ui_button
        )


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
    global is_locked_down, alarm_active, pending_halt_breach
    global daily_breach_settings_prompted, recent_loss_timestamps
    if is_locked_down:
        return
    _close_active_settings_window_on_breach(ui_button)

    alarms_only = config.get("alarms_only_mode", False)
    flat_on = (not alarms_only) and config.get("enable_auto_flatten", False)
    opt_armed = flat_on and is_options_flatten_armed(config)
    kill_tos = (not alarms_only) and config.get("enable_kill_tos", False)
    kill_wb = (not alarms_only) and config.get("enable_kill_webull", False)
    lock_on = (not alarms_only) and config.get("enable_lock_os", False)

    if not flat_on and not kill_tos and not kill_wb and not lock_on:
        trigger_alarm(reason, ui_button, context_str)
        mode_desc = (
            "Alarms Only Mode is ON"
            if alarms_only
            else "all enforcement toggles are OFF"
        )
        log_event(
            "GUARDRAIL",
            f"Daily floor breached ({reason}), but {mode_desc} "
            f"(Observation Mode — Siren Only)."
        )
        return

    log_event(
        "LOCKDOWN",
        f"DAILY TERMINATION BREACHED: {reason} | {context_str}"
    )

    opt_exec_now = bool(has_options and opt_armed and is_market_hours())
    all_flat = flatten_equities(adapter, include_options=opt_exec_now)

    if has_options and not opt_exec_now:
        log_event(
            "CRITICAL",
            "OPTIONS ARE STILL OPEN! Holding off on App Kill / OS Lock "
            "until options are manually flattened!"
        )
        _enter_halt_breach_watch(
            "DAILY",
            f"{reason} (CLOSE OPTIONS MANUALLY!)",
            context_str,
            True,
            adapter,
            ui_button,
        )
        return

    if not all_flat:
        log_event(
            "CRITICAL",
            "OS ACTIONS ABORTED: Positions (Equities/Options) still open! "
            "Holding off on App Kill / OS Lock until halted/unfilled shares close!"
            if has_options
            else "OS ACTIONS ABORTED: Equity shares still open (halt / unfilled)! "
            "Holding off on App Kill / OS Lock until shares close!"
        )
        _enter_halt_breach_watch(
            "DAILY", reason, context_str, has_options, adapter, ui_button
        )
        return

    pending_halt_breach = None
    is_locked_down = True
    daily_breach_settings_prompted = False
    recent_loss_timestamps.clear()
    save_session_state()
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
                dl_mins,
                ui_button,
                label_prefix="DAILY BREACH OS LOCK",
                adapter=adapter
            )
        else:
            log_event(
                "LOCKDOWN",
                "Confirmed flat. Muting siren and locking Windows once..."
            )
            ctypes.windll.user32.LockWorkStation()
            _run_post_lock_watchdog(
                adapter, ui_button, "ONE-SHOT DAILY OS LOCK"
            )
            ui_button.after(
                2500,
                lambda: _prompt_daily_breach_settings_on_unlock(ui_button),
            )


# ==========================================
# 7. MAIN POLLING LOOP
# ==========================================
def log_position_transitions(
    pos_details, realized_pnl, open_pnl, net_pnl, session_high_pnl
):
    global prev_pos_snapshot, win_trades, loss_trades, prev_flat_realized_pnl
    global recent_loss_timestamps
    curr_sig_map = {
        s: (d["qty"], round(float(d.get("avg", 0.0)), 4))
        for s, d in pos_details.items()
    }
    prev_sig_map = {
        s: (d["qty"], round(float(d.get("avg", 0.0)), 4))
        for s, d in prev_pos_snapshot.items()
    }

    if curr_sig_map == prev_sig_map:
        return None

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
        return None

    consec_trigger_reason = None
    streak_note = ""
    if completed_round_trip and (len(pos_details) == 0 or any("Re-entry Avg:" in c for c in changes)):
        delta = round(realized_pnl - prev_flat_realized_pnl, 2)
        req_losses = max(
            2, int(round(float(config.get("consec_loss_count", 3))))
        )
        min_loss_mag = abs(
            float(config.get("consec_loss_min_dollars", 25.0))
        )
        win_mins = max(
            0.5, float(config.get("consec_loss_window_mins", 15.0))
        )
        now_ts = time.time()
        recent_loss_timestamps[:] = [
            ts
            for ts in recent_loss_timestamps
            if (now_ts - ts) <= (win_mins * 60.0)
        ]
        if delta > 0.0:
            win_trades += 1
            if recent_loss_timestamps:
                min_win_to_reset = abs(
                    float(config.get("consec_win_reset_dollars", 10.0))
                )
                if delta >= min_win_to_reset:
                    recent_loss_timestamps.clear()
                    if config.get("enable_consec_loss_cooldown", False):
                        streak_note = (
                            f" | TiltStreak: 0/{req_losses} "
                            f"(Reset by {format_dollar(delta)} qualifying win)"
                        )
                elif config.get("enable_consec_loss_cooldown", False):
                    streak_note = (
                        f" | TiltStreak: {len(recent_loss_timestamps)}/{req_losses} "
                        f"(Scratch win {format_dollar(delta)} < +${min_win_to_reset:,.0f} did not reset streak)"
                    )
        elif delta < 0.0:
            loss_trades += 1
            if not first_poll_of_launch:
                if cooldown_active and "DAILY" in str(cooldown_label).upper():
                    recent_loss_timestamps.clear()
                    if config.get("enable_consec_loss_cooldown", False):
                        streak_note = (
                            f" | TiltStreak: 0/{req_losses} "
                            f"(Reset by Daily Breach Lockout)"
                        )
                elif abs(delta) >= min_loss_mag:
                    recent_loss_timestamps.append(now_ts)
                    cur_streak = len(recent_loss_timestamps)
                    if config.get("enable_consec_loss_cooldown", False):
                        streak_note = (
                            f" | TiltStreak: {cur_streak}/{req_losses} "
                            f"(in {win_mins:g}m)"
                        )
                        if cur_streak >= req_losses:
                            recent_loss_timestamps.clear()
                            if cooldown_active:
                                streak_note = (
                                    f" | TiltStreak: {cur_streak}/{req_losses} -> "
                                    f"0/{req_losses} (Penalty Box Lock active)"
                                )
                            else:
                                consec_trigger_reason = (
                                    f"Consecutive Loss Stop ({req_losses} Losses "
                                    f"<= -${min_loss_mag:,.0f} in {win_mins:g}m)"
                                )
                elif config.get("enable_consec_loss_cooldown", False):
                    streak_note = (
                        f" | TiltStreak: {len(recent_loss_timestamps)}/{req_losses} "
                        f"(Scratch {format_dollar(delta)} < -${min_loss_mag:,.0f} ignored)"
                    )
        else:
            if not first_poll_of_launch and config.get("enable_consec_loss_cooldown", False):
                streak_note = (
                    f" | TiltStreak: {len(recent_loss_timestamps)}/{req_losses} "
                    f"($0.00 flat scratch ignored)"
                )
        prev_flat_realized_pnl = realized_pnl
        save_session_state()

    prev_pos_snapshot = pos_details.copy()
    change_str = ", ".join(changes)
    log_event(
        "POS_CHANGE",
        f"{change_str} | Realized: {format_dollar(realized_pnl)} | "
        f"Open: {format_dollar(open_pnl)} | "
        f"Net: {format_dollar(net_pnl)} | "
        f"High: {format_dollar(session_high_pnl)}{streak_note}"
    )
    return consec_trigger_reason


def _stabilize_mid_fill_realized_and_equity(
    current_eq, is_flat, live_open_pnl, pos_details, is_reverify=False
):
    """ Guard against 1-to-2 poll cross-endpoint cash vs. position fill
        desynchronization (e.g. Webull/Schwab deducting cash for a buy fill
        150-350ms before /positions reports the shares, or crediting sale
        proceeds during a multi-lot scale-out before /positions reduces qty). """
    global last_flat_equity, max_equity, daily_max_equity
    global settled_realized_pnl, prev_flat_realized_pnl, flat_desync_streak
    global in_trade_desync_streak, pending_scale_out_tol

    if first_poll_of_launch or settled_realized_pnl is None:
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
            realized_pnl = round((current_eq - start_equity) - open_pnl, 2)
            last_flat_equity = round(start_equity + realized_pnl, 2)
            prev_flat_realized_pnl = realized_pnl
        settled_realized_pnl = realized_pnl
        flat_desync_streak = 0
        in_trade_desync_streak = 0
        pending_scale_out_tol = 0.0
        return current_eq, realized_pnl, open_pnl

    if is_flat:
        open_pnl = 0.0
        raw_flat_realized = round(current_eq - start_equity, 2)
        was_flat_before = (len(prev_pos_snapshot) == 0)

        if was_flat_before:
            if (
                last_flat_equity is not None
                and abs(raw_flat_realized - settled_realized_pnl) > 25.0
                and flat_desync_streak < 2
            ):
                if not is_reverify:
                    flat_desync_streak += 1
                    log_event(
                        "GUARDRAIL",
                        f"Filtered transient pre-position cash desync while flat "
                        f"(Raw Realized: {format_dollar(raw_flat_realized)} vs "
                        f"Settled: {format_dollar(settled_realized_pnl)} | "
                        f"Streak: {flat_desync_streak}/2)."
                    )
                current_eq = last_flat_equity
                realized_pnl = settled_realized_pnl
            else:
                flat_desync_streak = 0
                in_trade_desync_streak = 0
                pending_scale_out_tol = 0.0
                last_flat_equity = current_eq
                if current_eq > max_equity:
                    max_equity = current_eq
                if current_eq > daily_max_equity:
                    daily_max_equity = current_eq
                save_session_state()
                realized_pnl = round(last_flat_equity - start_equity, 2)
                settled_realized_pnl = realized_pnl
        else:
            est_open_sum = sum(
                float(d.get("open_pnl", 0.0))
                for d in prev_pos_snapshot.values()
            )
            expected_flat_realized = round(
                settled_realized_pnl + est_open_sum, 2
            )
            closed_notional = sum(
                abs(float(d.get("qty", 0.0)))
                * float(d.get("last", 0.0))
                * (100.0 if d.get("asset_type") == "OPTION" else 1.0)
                for d in prev_pos_snapshot.values()
            )
            tol = max(100.0, closed_notional * 0.35, pending_scale_out_tol)
            if (
                abs(raw_flat_realized - expected_flat_realized) > tol
                and flat_desync_streak < 1
            ):
                if not is_reverify:
                    flat_desync_streak += 1
                    log_event(
                        "GUARDRAIL",
                        f"Filtered transient exit-settlement cash desync on flat "
                        f"transition (Raw Realized: {format_dollar(raw_flat_realized)} "
                        f"vs Expected: {format_dollar(expected_flat_realized)})."
                    )
                realized_pnl = expected_flat_realized
                settled_realized_pnl = realized_pnl
                current_eq = round(start_equity + realized_pnl, 2)
                last_flat_equity = current_eq
                save_session_state()
            else:
                flat_desync_streak = 0
                in_trade_desync_streak = 0
                pending_scale_out_tol = 0.0
                last_flat_equity = current_eq
                if current_eq > max_equity:
                    max_equity = current_eq
                if current_eq > daily_max_equity:
                    daily_max_equity = current_eq
                save_session_state()
                realized_pnl = round(last_flat_equity - start_equity, 2)
                settled_realized_pnl = realized_pnl

        for k in list(triggered_alarms.keys()):
            if k.startswith("Open PnL -"):
                del triggered_alarms[k]
        return current_eq, realized_pnl, open_pnl

    # Not flat (holding 1 or more open positions)
    flat_desync_streak = 0
    open_pnl = live_open_pnl
    raw_realized_pnl = round((current_eq - start_equity) - open_pnl, 2)

    any_closed_or_reduced = False
    est_closed_delta = 0.0
    closed_notional = 0.0
    all_syms = set(prev_pos_snapshot.keys()) | set(pos_details.keys())
    for sym in all_syms:
        old_d = prev_pos_snapshot.get(sym)
        new_d = pos_details.get(sym)
        old_q = float(old_d.get("qty", 0.0)) if old_d else 0.0
        new_q = float(new_d.get("qty", 0.0)) if new_d else 0.0
        old_avg = (
            float(old_d.get("avg", old_d.get("avg_price", 0.0)))
            if old_d
            else 0.0
        )
        new_avg = (
            float(new_d.get("avg", new_d.get("avg_price", 0.0)))
            if new_d
            else 0.0
        )
        old_open = float(old_d.get("open_pnl", 0.0)) if old_d else 0.0
        old_last = float(old_d.get("last", 0.0)) if old_d else 0.0
        new_last = float(new_d.get("last", old_last)) if new_d else old_last
        mult = (
            100.0
            if ((old_d or new_d or {}).get("asset_type") == "OPTION")
            else 1.0
        )
        if old_q != 0.0 and new_q == 0.0:
            any_closed_or_reduced = True
            est_closed_delta += old_open
            closed_notional += abs(old_q) * (new_last or old_last) * mult
        elif old_q != 0.0 and (old_q * new_q < 0):
            any_closed_or_reduced = True
            est_closed_delta += old_open
            closed_notional += abs(old_q) * (new_last or old_last) * mult
        elif old_q != 0.0 and abs(new_q) < abs(old_q):
            any_closed_or_reduced = True
            closed_shares = abs(old_q) - abs(new_q)
            frac = closed_shares / abs(old_q)
            if new_last > 0 and old_avg > 0:
                if old_q > 0:
                    est_closed_delta += (
                        (new_last - old_avg) * closed_shares * mult
                    )
                else:
                    est_closed_delta += (
                        (old_avg - new_last) * closed_shares * mult
                    )
            else:
                est_closed_delta += old_open * frac
            closed_notional += closed_shares * (new_last or old_last) * mult
        elif (
            old_q != 0.0
            and new_q == old_q
            and abs(new_avg - old_avg) >= 0.0001
        ):
            any_closed_or_reduced = True
            est_closed_delta += old_open
            closed_notional += abs(old_q) * (new_last or old_last) * mult

    qty_changed_now = (
        {k: v.get("qty") for k, v in pos_details.items()}
        != {k: v.get("qty") for k, v in prev_pos_snapshot.items()}
    )

    if not any_closed_or_reduced:
        added_opt_contracts = 0.0
        if qty_changed_now:
            for sym_k, new_d in pos_details.items():
                if new_d.get("asset_type") == "OPTION":
                    old_q = float(
                        (prev_pos_snapshot.get(sym_k) or {}).get("qty", 0.0)
                    )
                    new_q = float(new_d.get("qty", 0.0))
                    if abs(new_q) > abs(old_q):
                        added_opt_contracts += abs(new_q) - abs(old_q)
        fee_tol = max(6.0, added_opt_contracts * 1.50)
        allowed_drift = max(fee_tol, pending_scale_out_tol)
        if (
            abs(raw_realized_pnl - settled_realized_pnl) > allowed_drift
            and (qty_changed_now or in_trade_desync_streak < 2)
        ):
            if not is_reverify:
                if qty_changed_now:
                    in_trade_desync_streak = 0
                else:
                    in_trade_desync_streak += 1
                log_event(
                    "GUARDRAIL",
                    f"Filtered mid-fill cash/position desync on entry/add "
                    f"(Raw Realized: {format_dollar(raw_realized_pnl)} vs "
                    f"Settled: {format_dollar(settled_realized_pnl)} | "
                    f"Open: {format_dollar(open_pnl)})."
                )
            realized_pnl = settled_realized_pnl
            current_eq = round(start_equity + realized_pnl + open_pnl, 2)
        else:
            in_trade_desync_streak = 0
            pending_scale_out_tol = 0.0
            realized_pnl = raw_realized_pnl
            settled_realized_pnl = realized_pnl
    else:
        expected_realized = round(settled_realized_pnl + est_closed_delta, 2)
        tol = max(60.0, closed_notional * 0.30)
        if (
            abs(raw_realized_pnl - expected_realized) > tol
            and (qty_changed_now or in_trade_desync_streak < 2)
        ):
            if not is_reverify:
                if qty_changed_now:
                    in_trade_desync_streak = 0
                else:
                    in_trade_desync_streak += 1
                log_event(
                    "GUARDRAIL",
                    f"Filtered mid-scale-out cash/position desync "
                    f"(Raw Realized: {format_dollar(raw_realized_pnl)} vs "
                    f"Expected: {format_dollar(expected_realized)} | "
                    f"Open: {format_dollar(open_pnl)})."
                )
            pending_scale_out_tol = tol
            realized_pnl = expected_realized
            settled_realized_pnl = realized_pnl
            current_eq = round(start_equity + realized_pnl + open_pnl, 2)
        else:
            in_trade_desync_streak = 0
            pending_scale_out_tol = 0.0
            realized_pnl = raw_realized_pnl
            settled_realized_pnl = realized_pnl

    return current_eq, realized_pnl, open_pnl


def data_loop(ui_labels, mute_btn, settings_btn, close_btn, root):
    global start_equity, max_equity, daily_max_equity, last_flat_equity
    global anchor_cash_flow, _last_logged_unanchored_cash_flow
    global has_reset_at_open, has_reset_at_close, is_locked_down, force_reanchor
    global triggered_alarms, prev_pos_snapshot, current_is_flat
    global active_adapter, first_poll_of_launch
    global current_upside_tier, last_rth_mode
    global win_trades, loss_trades, prev_flat_realized_pnl
    global settled_realized_pnl, flat_desync_streak
    global in_trade_desync_streak, pending_scale_out_tol
    global consecutive_api_failures, api_disconnect_alerted
    global alarm_active, last_alarm_reason, daily_breach_settings_prompted
    global pending_halt_breach

    consecutive_api_failures = 0
    api_disconnect_alerted = False

    while True:
        poll_sec = max(1, int(config.get("poll_interval", 2)))
        try:
            if active_adapter is None or broker_reconfig_in_progress:
                time.sleep(0.5)
                continue

            current_eq, is_flat, live_open_pnl, pos_details, has_options = (
                active_adapter.fetch_account_data()
            )

            if current_eq is not None and current_eq > 0:
                if consecutive_api_failures > 0 or api_disconnect_alerted:
                    recovered_attempts = max(1, consecutive_api_failures)
                    was_alerted = api_disconnect_alerted
                    consecutive_api_failures = 0
                    api_disconnect_alerted = False
                    if was_alerted:
                        if alarm_active and any(
                            k in last_alarm_reason.upper()
                            for k in (
                                "CONNECTION LOST",
                                "DISCONNECTED",
                                "TOKEN EXPIRED",
                            )
                        ):
                            alarm_active = False
                            last_alarm_reason = ""
                        speak_async("Connection restored. Enforcer is back online.")
                        if config.get("enable_upside_chime", True):
                            trigger_upside_tier_glow(
                                mute_btn,
                                "✓ CONNECTION RESTORED — BACK ONLINE",
                                f"Broker API connection restored after {recovered_attempts} attempt(s).",
                                log_tag="SESSION",
                            )
                        else:
                            log_event(
                                "SESSION",
                                f"Broker API connection restored after {recovered_attempts} attempt(s).",
                            )
                            if not alarm_active and not cooldown_active:
                                mute_btn.after(
                                    0,
                                    lambda: mute_btn.config(
                                        text=get_idle_button_text(),
                                        bg="#222629",
                                        fg="#f5b041",
                                        disabledforeground="#f5b041",
                                        state="disabled",
                                    ),
                                )
                    else:
                        log_event(
                            "SESSION",
                            "Broker API poll recovered after 1 retry.",
                        )
                        if not alarm_active and not cooldown_active:
                            mute_btn.after(
                                0,
                                lambda: mute_btn.config(
                                    text=get_idle_button_text(),
                                    bg="#222629",
                                    fg="#f5b041",
                                    disabledforeground="#f5b041",
                                    state="disabled",
                                ),
                            )
                current_is_flat = is_flat

                if (
                    start_equity is None
                    or start_equity <= 0.0
                    or force_reanchor
                ):
                    anchor_eq = round(current_eq - live_open_pnl, 2)
                    start_equity = anchor_eq
                    max_equity = anchor_eq
                    daily_max_equity = max(anchor_eq, current_eq)
                    last_flat_equity = anchor_eq
                    anchor_cash_flow = (
                        active_adapter.get_last_intraday_cash_flow()
                        if active_adapter is not None
                        else 0.0
                    )
                    _last_logged_unanchored_cash_flow = 0.0
                    has_reset_at_open = is_rth() or is_after_hours()
                    has_reset_at_close = is_after_hours()
                    force_reanchor = False
                    is_locked_down = False
                    daily_breach_settings_prompted = False
                    pending_halt_breach = None
                    win_trades = 0
                    loss_trades = 0
                    prev_flat_realized_pnl = 0.0
                    settled_realized_pnl = 0.0
                    flat_desync_streak = 0
                    in_trade_desync_streak = 0
                    pending_scale_out_tol = 0.0
                    recent_loss_timestamps.clear()
                    triggered_alarms.clear()
                    prev_pos_snapshot = {}
                    save_session_state()
                    ig_log_sfx = (
                        f" | IgnoredPreExisting={list(ignored_positions.keys())}"
                        if ignored_positions
                        else ""
                    )
                    log_event(
                        "SESSION",
                        f"Baseline anchored to: ${start_equity:,.2f} "
                        f"({active_adapter.name}){ig_log_sfx}"
                    )

                if daily_max_equity is None:
                    daily_max_equity = max(start_equity, max_equity)

                reset_925 = config.get("reset_at_925", True)
                if is_rth() and not has_reset_at_open:
                    has_reset_at_open = True
                    first_poll_of_launch = True
                    settled_realized_pnl = (
                        round(last_flat_equity - start_equity, 2)
                        if last_flat_equity is not None
                        else 0.0
                    )
                    flat_desync_streak = 0
                    in_trade_desync_streak = 0
                    pending_scale_out_tol = 0.0
                    if reset_925:
                        old_hwm = max_equity - start_equity
                        max_equity = max(start_equity, last_flat_equity)
                        new_hwm = max_equity - start_equity
                        is_locked_down = False
                        daily_breach_settings_prompted = False
                        pending_halt_breach = None
                        recent_loss_timestamps.clear()
                        triggered_alarms.clear()
                        save_session_state()
                        log_event(
                            "SESSION",
                            f"9:30 AM RTH Transition: Rulebook HWM recalibrated "
                            f"from {format_dollar(old_hwm)} to "
                            f"{format_dollar(new_hwm)} (Session High preserved at "
                            f"{format_dollar(daily_max_equity - start_equity)})."
                        )
                    else:
                        save_session_state()
                        log_event(
                            "SESSION",
                            "9:30 AM RTH Transition: Switched from Extended-Hours "
                            "Rulebook to RTH Rulebook."
                        )

                if is_after_hours() and not has_reset_at_close:
                    has_reset_at_open = True
                    has_reset_at_close = True
                    first_poll_of_launch = True
                    settled_realized_pnl = (
                        round(last_flat_equity - start_equity, 2)
                        if last_flat_equity is not None
                        else 0.0
                    )
                    flat_desync_streak = 0
                    in_trade_desync_streak = 0
                    pending_scale_out_tol = 0.0
                    if reset_925:
                        old_hwm = max_equity - start_equity
                        max_equity = max(start_equity, last_flat_equity)
                        new_hwm = max_equity - start_equity
                        is_locked_down = False
                        daily_breach_settings_prompted = False
                        pending_halt_breach = None
                        recent_loss_timestamps.clear()
                        triggered_alarms.clear()
                        save_session_state()
                        log_event(
                            "SESSION",
                            f"4:00 PM Extended-Hours Transition: Rulebook HWM "
                            f"recalibrated from {format_dollar(old_hwm)} to "
                            f"{format_dollar(new_hwm)} (Session High preserved at "
                            f"{format_dollar(daily_max_equity - start_equity)})."
                        )
                    else:
                        save_session_state()
                        log_event(
                            "SESSION",
                            "4:00 PM Extended-Hours Transition: Switched from RTH "
                            "Rulebook to Extended-Hours Rulebook."
                        )

                pre_poll_hwm_profit = round(max_equity - start_equity, 2)

                current_eq, realized_pnl, open_pnl = (
                    _stabilize_mid_fill_realized_and_equity(
                        current_eq, is_flat, live_open_pnl, pos_details
                    )
                )

                net_pnl = round(current_eq - start_equity, 2)
                max_realized_profit = round(max_equity - start_equity, 2)
                session_high_pnl = round(
                    daily_max_equity - start_equity, 2
                )

                alarms_only = config.get("alarms_only_mode", False)
                open_flat_on = (
                    (not alarms_only)
                    and config.get("enable_open_flatten", False)
                )
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

                # Anti-Wick Verification:
                # 1. If the breach is already confirmed across BOTH the live
                #    NBBO Midpoint and the broker's Account position snapshot
                #    (confirmed_open_pnl / confirmed_eq), fire immediately with
                #    0.0s delay!
                # 2. If only the raw trade print breached while the NBBO
                #    Midpoint or Account snapshot did not yet breach (e.g. a
                #    single-order wick or entry-sweep quote lag), do a fast
                #    0.2s re-verification poll before firing enforcement.
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
                        else start_equity + t3_max
                        if (t3_on and max_realized_profit >= t3_trig)
                        else start_equity + t2_max
                        if (t2_on and max_realized_profit >= t2_trig)
                        else start_equity - t1_max
                    )
                )
                warn_floors = []
                if not rth_now:
                    if (
                        pm_w1_on
                        and f"Ext-Hours -${pm_w1:,.0f} Warn 1"
                        not in triggered_alarms
                    ):
                        warn_floors.append(start_equity - pm_w1)
                    if (
                        pm_w2_on
                        and f"Ext-Hours -${pm_w2:,.0f} Warn 2"
                        not in triggered_alarms
                    ):
                        warn_floors.append(start_equity - pm_w2)
                else:
                    if t4_on and max_realized_profit >= t4_trig:
                        pass
                    elif t3_on and max_realized_profit >= t3_trig:
                        if (
                            t3_max < 0
                            and "Hit $0 (Tier 3)" not in triggered_alarms
                        ):
                            warn_floors.append(start_equity)
                    elif t2_on and max_realized_profit >= t2_trig:
                        if (
                            t2_max < 0
                            and "Hit $0 (Tier 2)" not in triggered_alarms
                        ):
                            warn_floors.append(start_equity)
                    else:
                        if (
                            t1_w1_on
                            and f"Hit -${t1_w1:,.0f} (Tier 1)"
                            not in triggered_alarms
                        ):
                            warn_floors.append(start_equity - t1_w1)
                        if (
                            t1_w2_on
                            and f"Hit -${t1_w2:,.0f} (Tier 1)"
                            not in triggered_alarms
                        ):
                            warn_floors.append(start_equity - t1_w2)
                active_warn_floor_now = (
                    max(warn_floors) if warn_floors else None
                )
                floor_breach_cand = (
                    not is_locked_down
                    and pending_halt_breach is None
                    and current_eq <= active_floor_now
                )
                open_breach_cand = (
                    open_flat_on
                    and pending_halt_breach is None
                    and not is_flat
                    and open_pnl <= -open_max
                )
                warn_breach_cand = (
                    active_warn_floor_now is not None
                    and pending_halt_breach is None
                    and current_eq <= active_warn_floor_now
                )
                if (
                    not first_poll_of_launch
                    and (
                        floor_breach_cand
                        or open_breach_cand
                        or warn_breach_cand
                    )
                ):
                    conf_open_pnl = round(
                        sum(
                            d.get("confirmed_open_pnl", d.get("open_pnl", 0.0))
                            for d in pos_details.values()
                        ),
                        2
                    )
                    conf_eq = round(
                        current_eq + (conf_open_pnl - open_pnl), 2
                    )
                    book_confirms_floor = (
                        floor_breach_cand
                        and not is_flat
                        and conf_eq <= active_floor_now
                    )
                    book_confirms_open = (
                        open_breach_cand
                        and not is_flat
                        and conf_open_pnl <= -open_max
                    )
                    book_confirms_warn = (
                        warn_breach_cand
                        and not is_flat
                        and active_warn_floor_now is not None
                        and conf_eq <= active_warn_floor_now
                    )
                    qty_just_changed = (
                        {k: v.get("qty") for k, v in pos_details.items()}
                        != {k: v.get("qty") for k, v in prev_pos_snapshot.items()}
                    )
                    spike_ctx = (
                        f"Realized={format_dollar(realized_pnl)}, "
                        f"Open={format_dollar(open_pnl)}, "
                        f"Net={format_dollar(net_pnl)}"
                    )
                    if (
                        (
                            book_confirms_floor
                            or book_confirms_open
                            or book_confirms_warn
                        )
                        and not is_flat
                        and not qty_just_changed
                        and not has_options
                    ):
                        if floor_breach_cand or open_breach_cand:
                            log_event(
                                "GUARDRAIL",
                                f"Breach confirmed immediately by NBBO book & "
                                f"account snapshot (0s delay | {spike_ctx})."
                            )
                    else:
                        time.sleep(
                            0.35 if (qty_just_changed or is_flat) else 0.2
                        )
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
                            current_eq, realized_pnl, open_pnl = (
                                _stabilize_mid_fill_realized_and_equity(
                                    current_eq,
                                    is_flat,
                                    live_open_pnl,
                                    pos_details,
                                    is_reverify=True,
                                )
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
                            still_warn = (
                                active_warn_floor_now is not None
                                and current_eq <= active_warn_floor_now
                            )
                            if (
                                not still_floor
                                and not still_open
                                and not still_warn
                            ):
                                log_event(
                                    "GUARDRAIL",
                                    f"Filtered transient single-order wick "
                                    f"(Spike: {spike_ctx} -> Re-verified 0.2s later: "
                                    f"{v_ctx}). No flatten triggered."
                                )
                            elif floor_breach_cand or open_breach_cand:
                                log_event(
                                    "GUARDRAIL",
                                    f"Breach confirmed after 0.2s anti-wick check "
                                    f"(Initial: {spike_ctx} -> Verified: {v_ctx})."
                                )

                consec_reason = log_position_transitions(
                    pos_details,
                    realized_pnl,
                    open_pnl,
                    net_pnl,
                    session_high_pnl
                )

                # Prevent immediate siren blast or flat re-lock on startup,
                # at the 9:30 AM / 4:00 PM transitions, or right after saving Settings
                if first_poll_of_launch or last_rth_mode != rth_now:
                    is_mode_switch = (
                        last_rth_mode is not None and last_rth_mode != rth_now
                    )
                    if is_mode_switch:
                        first_poll_of_launch = True
                    last_rth_mode = rth_now
                    # Use pre_poll_hwm_profit on launch/resume so if a new profit
                    # tier was reached while Enforcer was closed or in Pre-Flight,
                    # the [RATCHET] log, upside chime, and emerald HUD banner
                    # still fire on the first poll.
                    ref_hwm_for_init = (
                        max_realized_profit
                        if is_mode_switch
                        else pre_poll_hwm_profit
                    )
                    current_upside_tier = compute_upside_tier(
                        rth_now, ref_hwm_for_init, config
                    )

                if first_poll_of_launch and is_flat:
                    first_poll_of_launch = False
                    if pm_w1_on and net_pnl <= -pm_w1:
                        triggered_alarms[f"Ext-Hours -${pm_w1:,.0f} Warn 1"] = time.time()
                    if pm_w2_on and net_pnl <= -pm_w2:
                        triggered_alarms[f"Ext-Hours -${pm_w2:,.0f} Warn 2"] = time.time()
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
                         start_equity + t3_max if (t3_on and max_realized_profit >= t3_trig) else
                         start_equity + t2_max if (t2_on and max_realized_profit >= t2_trig) else
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

                if pending_halt_breach is not None:
                    hb = pending_halt_breach
                    hb_type = hb.get("type", "DAILY")
                    hb_reason = hb.get("reason", "Daily Stop Breach")
                    watched = hb.get("watched_positions") or {}

                    if is_flat:
                        pending_halt_breach = None
                        log_event(
                            "GUARDRAIL",
                            f"Halt / Unfilled Position Watch resolved: account is now "
                            f"100% FLAT ({list(watched.keys())}). Completing deferred "
                            f"{hb_type} enforcement ({hb_reason})...",
                        )
                        if hb_type == "DAILY":
                            if not is_locked_down and current_eq <= active_floor_now:
                                trigger_lockdown(
                                    active_adapter,
                                    hb_reason,
                                    mute_btn,
                                    has_options,
                                    ctx,
                                )
                            else:
                                alarm_active = False
                                log_event(
                                    "SESSION",
                                    f"Deferred Daily Stop watch cleared while flat "
                                    f"(Net PnL {format_dollar(net_pnl)} is above active floor "
                                    f"{format_dollar(round(active_floor_now - start_equity, 2))}).",
                                )
                                if not cooldown_active:
                                    mute_btn.after(
                                        0,
                                        lambda: mute_btn.config(
                                            text=get_idle_button_text(),
                                            bg="#222629",
                                            fg="#f5b041",
                                            disabledforeground="#f5b041",
                                            state="disabled",
                                        ),
                                    )
                        elif hb_type == "OPEN_PNL":
                            if config.get("enable_open_cooldown", False):
                                alarm_active = False
                                cd_mins = float(
                                    config.get("open_cooldown_mins", 1.0)
                                )
                                start_cooldown_lock(
                                    cd_mins,
                                    mute_btn,
                                    label_prefix="PENALTY BOX LOCK",
                                    adapter=active_adapter,
                                )
                            elif not alarm_active and not cooldown_active:
                                mute_btn.after(
                                    0,
                                    lambda: mute_btn.config(
                                        text=get_idle_button_text(),
                                        bg="#222629",
                                        fg="#f5b041",
                                        disabledforeground="#f5b041",
                                        state="disabled",
                                    ),
                                )
                        elif hb_type == "CONSEC_LOSS":
                            if config.get("enable_open_cooldown", True):
                                alarm_active = False
                                cd_mins = float(
                                    config.get("open_cooldown_mins", 1.0)
                                )
                                start_cooldown_lock(
                                    cd_mins,
                                    mute_btn,
                                    label_prefix="TILT STREAK LOCK",
                                    adapter=active_adapter,
                                )
                            elif not alarm_active and not cooldown_active:
                                mute_btn.after(
                                    0,
                                    lambda: mute_btn.config(
                                        text=get_idle_button_text(),
                                        bg="#222629",
                                        fg="#f5b041",
                                        disabledforeground="#f5b041",
                                        state="disabled",
                                    ),
                                )
                    else:
                        if (
                            hb_type != "DAILY"
                            and not is_locked_down
                            and current_eq <= active_floor_now
                        ):
                            _, _, _, tier_short_u, _, _ = describe_active_floor(
                                config, rth_now
                            )
                            hb["type"] = "DAILY"
                            hb["reason"] = (
                                f"Breached {tier_short_u} "
                                f"({format_dollar(round(active_floor_now - start_equity, 2))})"
                            )
                            log_event(
                                "LOCKDOWN",
                                f"Upgraded active Halt Watch from {hb_type} to "
                                f"DAILY ({hb['reason']}) | {ctx}",
                            )

                        unauthorized = []
                        new_watched = {}
                        for sym_k, d_k in pos_details.items():
                            curr_q = float(d_k.get("qty", 0.0))
                            if abs(curr_q) < 1e-6:
                                continue
                            w_q = float(watched.get(sym_k, 0.0))
                            if (
                                sym_k not in watched
                                or abs(curr_q) > (abs(w_q) + 1e-6)
                                or (abs(w_q) > 1e-6 and (curr_q * w_q) < 0)
                            ):
                                unauthorized.append((sym_k, curr_q))
                            new_watched[sym_k] = curr_q
                        hb["watched_positions"] = new_watched

                        if unauthorized:
                            log_event(
                                "GUARDRAIL",
                                f"New/increased position detected during Halt Watch: "
                                f"{unauthorized}! Flattening unauthorized shares while "
                                f"preserving halted exit order(s)...",
                            )
                            flatten_equities(
                                active_adapter,
                                force_flatten=True,
                                include_options=(
                                    has_options
                                    and is_options_flatten_armed(config)
                                    and is_market_hours()
                                ),
                            )
                            refreshed_w = {}
                            try:
                                r_eq = active_adapter.get_open_equity_positions()
                                for item in (r_eq or []):
                                    refreshed_w[str(item[0])] = float(item[1])
                            except Exception:
                                pass
                            if refreshed_w:
                                hb["watched_positions"] = refreshed_w

                if not is_rth():
                    r_pm_max = f"Ext-Hours -${pm_max:,.0f} Breach"
                    r_pm_w2 = f"Ext-Hours -${pm_w2:,.0f} Warn 2"
                    r_pm_w1 = f"Ext-Hours -${pm_w1:,.0f} Warn 1"
                    r_pm_tr = "Ext-Hours Trailing Floor Breach"

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

                    if pending_halt_breach is not None:
                        pass
                    elif (
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
                    elif not is_locked_down and pm_w2_on and net_pnl <= -pm_w2:
                        triggered_alarms.setdefault(r_pm_w1, time.time())
                        trigger_alarm(r_pm_w2, mute_btn, ctx)
                    elif not is_locked_down and pm_w1_on and net_pnl <= -pm_w1:
                        trigger_alarm(r_pm_w1, mute_btn, ctx)

                else:
                    if t4_on and max_realized_profit >= t4_trig:
                        floor_equity = max_equity - t4_trail
                        if pending_halt_breach is not None:
                            pass
                        elif not is_locked_down and current_eq <= floor_equity:
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
                        floor_equity = start_equity + t3_max
                        r_t3 = "Hit $0 (Tier 3)"
                        if t3_max < 0:
                            check_alarm_rearm(r_t3, current_eq, start_equity)
                        if pending_halt_breach is not None:
                            pass
                        elif not is_locked_down and current_eq <= floor_equity:
                            msg = f"Breached Tier 3 Stop ({format_dollar(t3_max)})"
                            trigger_lockdown(
                                active_adapter, msg, mute_btn, has_options, ctx
                            )
                        elif (
                            open_flat_on
                            and not is_flat
                            and open_pnl <= -open_max
                        ):
                            if t3_max < 0 and current_eq <= start_equity:
                                triggered_alarms.setdefault(r_t3, time.time())
                            r_open = f"Open PnL -${open_max:,.0f} Stop"
                            trigger_open_pnl_flatten(
                                active_adapter,
                                r_open,
                                mute_btn,
                                has_options,
                                ctx
                            )
                        elif (
                            not is_locked_down
                            and t3_max < 0
                            and current_eq <= start_equity
                        ):
                            trigger_alarm(r_t3, mute_btn, ctx)

                    elif t2_on and max_realized_profit >= t2_trig:
                        floor_equity = start_equity + t2_max
                        r_t2 = "Hit $0 (Tier 2)"
                        if t2_max < 0:
                            check_alarm_rearm(r_t2, current_eq, start_equity)
                        if pending_halt_breach is not None:
                            pass
                        elif not is_locked_down and current_eq <= floor_equity:
                            msg = f"Breached Tier 2 Stop ({format_dollar(t2_max)})"
                            trigger_lockdown(
                                active_adapter, msg, mute_btn, has_options, ctx
                            )
                        elif (
                            open_flat_on
                            and not is_flat
                            and open_pnl <= -open_max
                        ):
                            if t2_max < 0 and current_eq <= start_equity:
                                triggered_alarms.setdefault(r_t2, time.time())
                            r_open = f"Open PnL -${open_max:,.0f} Stop"
                            trigger_open_pnl_flatten(
                                active_adapter,
                                r_open,
                                mute_btn,
                                has_options,
                                ctx
                            )
                        elif (
                            not is_locked_down
                            and t2_max < 0
                            and current_eq <= start_equity
                        ):
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

                        if pending_halt_breach is not None:
                            pass
                        elif not is_locked_down and current_eq <= floor_equity:
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
                        elif (
                            not is_locked_down
                            and t1_w2_on
                            and current_eq <= (start_equity - t1_w2)
                        ):
                            triggered_alarms.setdefault(
                                r_t1_w1, time.time()
                            )
                            trigger_alarm(r_t1_w2, mute_btn, ctx)
                        elif (
                            not is_locked_down
                            and t1_w1_on
                            and current_eq <= (start_equity - t1_w1)
                        ):
                            trigger_alarm(r_t1_w1, mute_btn, ctx)

                if (
                    consec_reason
                    and not cooldown_active
                    and pending_halt_breach is None
                ):
                    trigger_consec_loss_cooldown(
                        active_adapter, consec_reason, mute_btn, has_options, ctx
                    )

                if (
                    is_locked_down
                    and is_flat
                    and current_eq >= (floor_equity + RECOVERY_BUFFER_DOLLARS)
                ):
                    is_locked_down = False
                    daily_breach_settings_prompted = False
                    log_event(
                        "SESSION",
                        f"Daily Stop RE-ARMED after flat recovery above floor + "
                        f"${RECOVERY_BUFFER_DOLLARS:,.0f} buffer "
                        f"(Net PnL: {format_dollar(net_pnl)} vs "
                        f"Daily Stop: {format_dollar(round(floor_equity - start_equity, 2))})."
                    )
                    if not alarm_active and not cooldown_active:
                        mute_btn.after(
                            0,
                            lambda: mute_btn.config(text=get_idle_button_text())
                        )

                terminate_pnl_level = round(floor_equity - start_equity, 2)
                distance_to_terminate = round(current_eq - floor_equity, 2)

                if not rth_now:
                    full_leash = (
                        max(1.0, float(pm_trail))
                        if (pm_lock_on and max_realized_profit >= pm_trig)
                        else max(1.0, float(pm_max))
                    )
                else:
                    if t4_on and max_realized_profit >= t4_trig:
                        full_leash = max(1.0, float(t4_trail))
                    elif t3_on and max_realized_profit >= t3_trig:
                        full_leash = max(
                            1.0,
                            float(max_realized_profit - t3_max),
                            float(t1_max)
                        )
                    elif t2_on and max_realized_profit >= t2_trig:
                        full_leash = max(
                            1.0,
                            float(max_realized_profit - t2_max),
                            float(t1_max)
                        )
                    else:
                        full_leash = max(1.0, float(t1_max))
                leash_pct = (
                    0.0
                    if is_locked_down
                    else max(0.0, min(1.0, distance_to_terminate / full_leash))
                )

                new_upside_tier = compute_upside_tier(
                    rth_now, max_realized_profit, config
                )
                if is_flat and new_upside_tier > current_upside_tier:
                    current_upside_tier = new_upside_tier
                    fl_str = format_dollar(terminate_pnl_level)
                    if not rth_now:
                        banner_txt = (
                            f"★ EXT-HOURS PROFIT LOCK UNLOCKED — "
                            f"FLOOR RAISED TO {fl_str} ★"
                        )
                        log_txt = (
                            f"Extended-Hours Profit Lock unlocked at "
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
                    "#b03a2e" if (is_locked_down or distance_to_terminate <= 0)
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
                    "dist_to_term": (
                        format_dist_to_stop_hud(
                            distance_to_terminate, is_locked_down
                        ),
                        c4_bg,
                    ),
                    "session_high": (format_dollar(session_high_pnl), c5_bg),
                    "from_high": (format_dollar(giveback_val), fh_bg),
                    "trades_wl": (
                        format_trades_wl_multiline(win_trades, loss_trades),
                        wl_bg
                    ),
                    "loss_streak": format_loss_streak_multiline(),
                }
                active_cols = get_active_hud_columns(config)
                col_data = [
                    all_col_values.get(cid, ("---", "#2c3e50"))
                    for cid in active_cols
                ]

                root.after(
                    0,
                    lambda d=col_data, f=is_flat, lp=leash_pct: update_gui(
                        ui_labels, d, f, settings_btn, close_btn, leash_pct=lp
                    )
                )
            else:
                consecutive_api_failures += 1
                raw_err = str(
                    getattr(active_adapter, "last_error", "")
                    or "Network / socket timeout"
                ).strip()
                err_lower = raw_err.lower()
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
                if consecutive_api_failures == 1 and not is_tok_exp:
                    log_event(
                        "WARN",
                        f"Broker API poll failed (Attempt #1: {raw_err[:90]}) — "
                        f"retrying automatically...",
                    )
                    if not alarm_active and not cooldown_active:
                        retry_1_txt = (
                            "⚠️ RETRYING API (#1)..."
                            if is_compact_hud()
                            else "⚠️ CONNECTION HICCUP — RETRYING BROKER API (ATTEMPT #1)..."
                        )
                        mute_btn.after(
                            0,
                            lambda t=retry_1_txt: mute_btn.config(
                                text=t,
                                bg="#78350f",
                                fg="#fde68a",
                                disabledforeground="#fde68a",
                                state="disabled",
                            ),
                        )
                elif is_tok_exp or consecutive_api_failures >= 2:
                    current_is_flat = True
                    if not is_tok_exp and hasattr(active_adapter, "reconnect_session"):
                        if (
                            consecutive_api_failures == 2
                            or consecutive_api_failures % 3 == 0
                        ):
                            try:
                                active_adapter.reconnect_session()
                            except Exception:
                                pass
                    lbl_1 = "TOKEN" if is_tok_exp else "OFFLINE"
                    lbl_2 = (
                        "EXPIRED"
                        if is_tok_exp
                        else f"RETRY #{consecutive_api_failures}"
                    )
                    col_2_bg = "#7b241c" if is_tok_exp else "#92400e"
                    n_cols = max(1, len(get_active_hud_columns(config)))
                    err_cols = []
                    for idx in range(n_cols):
                        if idx == 0:
                            err_cols.append((lbl_1, "#7b241c"))
                        elif idx == 1:
                            err_cols.append((lbl_2, col_2_bg))
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
                            else f"CONNECTION LOST — AUTO-RECONNECTING (ATTEMPT #{consecutive_api_failures})"
                        )
                        v_msg = (
                            "Warning. Broker token expired. Please restart Enforcer to log in."
                            if is_tok_exp
                            else "Warning. Connection lost. Attempting to reconnect automatically."
                        )
                        log_event(
                            "WARN",
                            f"Connection lost ({active_adapter.name}: {raw_err[:90]}). "
                            f"Auto-reconnecting (Attempt #{consecutive_api_failures})...",
                        )
                        speak_async(v_msg)
                        trigger_alarm(
                            r_msg,
                            mute_btn,
                            raw_err[:80],
                        )
                    else:
                        att = consecutive_api_failures
                        if att % 5 == 0:
                            log_event(
                                "WARN",
                                f"Still offline — auto-reconnect attempt #{att} "
                                f"({raw_err[:80]})...",
                            )
                        if not is_tok_exp:
                            if alarm_active:
                                last_alarm_reason = (
                                    f"CONNECTION LOST — AUTO-RECONNECTING (ATTEMPT #{att})"
                                )
                                al_btn_txt = (
                                    f"🔔 RECONNECTING (#{att}) (MUTE)"
                                    if is_compact_hud()
                                    else f"🔔 CONNECTION LOST — RECONNECTING (ATTEMPT #{att}) (CLICK TO MUTE)"
                                )
                                mute_btn.after(
                                    0,
                                    lambda t=al_btn_txt: mute_btn.config(
                                        text=t,
                                        bg="#eab308",
                                        fg="#090d16",
                                        disabledforeground="#090d16",
                                        state="normal",
                                    ),
                                )
                            elif not cooldown_active:
                                re_btn_txt = (
                                    f"🔄 RECONNECTING (#{att})..."
                                    if is_compact_hud()
                                    else f"🔄 CONNECTION LOST — AUTO-RECONNECTING (ATTEMPT #{att})..."
                                )
                                mute_btn.after(
                                    0,
                                    lambda t=re_btn_txt: mute_btn.config(
                                        text=t,
                                        bg="#78350f",
                                        fg="#fde68a",
                                        disabledforeground="#fde68a",
                                        state="disabled",
                                    ),
                                )

        except Exception as e:
            log_event("ERROR", f"Main data_loop error: {e}")

        time.sleep(poll_sec)


# ==========================================
# 8. SPACIOUS WIDESCREEN PRE-FLIGHT WINDOW
# ==========================================
def show_preflight_window(
    parent=None, mute_btn=None, post_daily_breach_prompt=False
):
    global settings_win_open, triggered_alarms, active_preflight_close_fn
    global active_preflight_win, last_preflight_pos
    global force_reanchor, is_locked_down, current_is_flat
    global active_adapter, start_equity, daily_breach_settings_prompted

    if parent is not None:
        if settings_win_open:
            return False
        if cooldown_active or dry_run_lock_active:
            log_event(
                "GUARDRAIL",
                "BLOCKED: Attempted to open Settings during an active lockout cooldown!",
            )
            return False
        if not current_is_flat:
            log_event(
                "SESSION",
                "Opened Settings while in an active daytrade (Enforcement & Rulebook Cards 1, 2, 4, 5 Tamper-Locked).",
            )
    else:
        load_config()

    launched = {"status": False}
    pf_timer_state = {
        "rulebook_after_id": None,
        "streak_after_id": None,
        "closing": False,
    }

    if parent is None:
        pf = tk.Tk()
    else:
        settings_win_open = True
        pf = tk.Toplevel(parent)
        pf.grab_set()
    pf.withdraw()
    active_preflight_win = pf

    pf.title(f"PnL Enforcer Beta v{APP_VERSION} — Pre-Flight & Risk Rulebook")
    pf.config(bg="#0d1117", padx=24, pady=16)
    pf.resizable(False, False)
    pf.attributes("-topmost", True)

    _prefs_modal_refs = {
        "dlg": None,
        "cb_reset925": None,
        "cb_ignore_prepos": None,
        "lbl_session_lock": None,
        "btn_test_audio": None,
        "btn_done": None,
        "cleanup_fn": None,
    }

    def _remember_pf_pos():
        global last_preflight_pos
        try:
            if pf.winfo_exists() and pf.winfo_width() > 200:
                last_preflight_pos = (
                    int(pf.winfo_rootx()),
                    int(pf.winfo_rooty()),
                )
        except Exception:
            pass

    def _cancel_pf_timers():
        pf_timer_state["closing"] = True
        for k_id in ("rulebook_after_id", "streak_after_id"):
            aid = pf_timer_state.get(k_id)
            if aid is not None:
                pf_timer_state[k_id] = None
                try:
                    pf.after_cancel(aid)
                except Exception:
                    pass
        cleanup_fn = _prefs_modal_refs.get("cleanup_fn")
        if callable(cleanup_fn):
            try:
                cleanup_fn()
            except Exception:
                pass

    def on_close(event=None, force=False):
        global settings_win_open, first_poll_of_launch
        global active_preflight_close_fn, active_preflight_win
        if (dry_run_lock_active or cooldown_active) and not force:
            log_event(
                "GUARDRAIL",
                "BLOCKED: Attempted to close Pre-Flight Settings window during an active lockout!",
            )
            return "break"
        _remember_pf_pos()
        _cancel_pf_timers()
        active_preflight_close_fn = None
        active_preflight_win = None
        if parent is None or current_is_flat:
            first_poll_of_launch = True
        settings_win_open = False
        try:
            pf.destroy()
        except Exception:
            pass

    if parent is not None:
        active_preflight_close_fn = lambda: on_close(force=True)
    pf.protocol("WM_DELETE_WINDOW", on_close)
    pf.bind("<Alt-F4>", on_close)

    def _normalize_tooltip_paragraphs(raw_text):
        lines = [
            ln.strip() for ln in str(raw_text).strip().splitlines() if ln.strip()
        ]
        if not lines:
            return []
        paragraphs = [lines[0]]
        new_para_prefixes = (
            "•",
            "- ",
            "* ",
            "(Example",
            "(Options",
            "(Note",
            "Left-Click:",
            "Right-Click:",
            "Uncheck ",
        )
        for ln in lines[1:]:
            prev = paragraphs[-1]
            if prev.endswith(":") or ln.startswith(new_para_prefixes):
                paragraphs.append(ln)
            else:
                paragraphs[-1] = f"{prev} {ln}"
        return paragraphs

    _all_hide_tip_callbacks = []

    def hide_all_tooltips(_event=None):
        for fn in _all_hide_tip_callbacks:
            try:
                fn()
            except Exception:
                pass

    def attach_tooltip(widget, text):
        """Attaches a clean dark-themed hover tooltip card to any widget."""
        tip_state = {"win": None, "after_id": None}
        paragraphs = _normalize_tooltip_paragraphs(text)

        def show_tip():
            tip_state["after_id"] = None
            if (
                tip_state["win"] is not None
                or not widget.winfo_exists()
                or getattr(widget, "_menu_open", False)
            ):
                return
            try:
                host_win = widget.winfo_toplevel() or pf
                tw = tk.Toplevel(host_win)
                tw.withdraw()
                tw.wm_overrideredirect(True)
                tw.attributes("-topmost", True)
                tw.config(bg="#5dade2", padx=1, pady=1)
                inner = tk.Frame(tw, bg="#1b2631", padx=12, pady=8)
                inner.pack(fill="both", expand=True)
                for p_idx, para in enumerate(paragraphs):
                    is_hdr = (p_idx == 0 and para.endswith(":"))
                    is_bullet = para.startswith("•")
                    fg_col = (
                        "#aed6f1" if is_hdr
                        else ("#f5cba7" if para.startswith("• IMPORTANT:") else "#f2f2f2")
                    )
                    fnt = ("Arial", 9, "bold") if is_hdr else ("Arial", 9)
                    top_pad = 0 if p_idx == 0 else (4 if is_bullet or para.startswith(("Uncheck ", "(Example")) else 2)
                    bot_pad = 3 if is_hdr else 0
                    tk.Label(
                        inner,
                        text=para,
                        font=fnt,
                        fg=fg_col,
                        bg="#1b2631",
                        justify="left",
                        anchor="w",
                        wraplength=420,
                    ).pack(fill="x", pady=(top_pad, bot_pad))
                tw.update_idletasks()
                tip_w = tw.winfo_reqwidth()
                tip_h = tw.winfo_reqheight()
                wx = int(widget.winfo_rootx())
                wy = int(widget.winfo_rooty())
                m_left, m_top, m_right, m_bottom = get_monitor_work_area(
                    wx, wy, widget=widget
                )
                if host_win is pf:
                    bound_left = max(m_left + 8, pf.winfo_rootx() + 8)
                    bound_right = min(
                        m_right - 8,
                        pf.winfo_rootx() + max(pf.winfo_width(), 900) + 20,
                    )
                    bound_bottom = min(
                        m_bottom - 8,
                        pf.winfo_rooty() + max(pf.winfo_height(), 600) + 40,
                    )
                else:
                    bound_left = m_left + 8
                    bound_right = m_right - 8
                    bound_bottom = m_bottom - 8
                x = wx + 16
                y = wy + widget.winfo_height() + 6
                if x + tip_w > bound_right:
                    x = max(bound_left, bound_right - tip_w)
                if y + tip_h > bound_bottom:
                    y = max(m_top + 8, wy - tip_h - 6)
                tw.wm_geometry(f"+{int(x)}+{int(y)}")
                tw.deiconify()
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
            if getattr(widget, "_menu_open", False):
                return
            try:
                tip_state["after_id"] = widget.after(320, show_tip)
            except Exception:
                pass

        _all_hide_tip_callbacks.append(hide_tip)
        widget._hide_tooltip_fn = hide_tip
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
    var_tilt_cd = tk.BooleanVar(
        value=config.get("enable_consec_loss_cooldown", False)
    )
    var_tilt_count = tk.StringVar(
        value=str(max(2, int(round(float(config.get("consec_loss_count", 3))))))
    )
    var_tilt_window = tk.StringVar(
        value=f"{config.get('consec_loss_window_mins', 15.0):g}"
    )
    _tilt_cd_popup_guard = {"suppress": False}
    var_open_cd = tk.BooleanVar(
        value=config.get("enable_open_cooldown", False)
    )
    var_cd_mins = tk.StringVar(
        value=f"{config.get('open_cooldown_mins', 1.0):g}"
    )

    var_alarms_only = tk.BooleanVar(
        value=config.get("alarms_only_mode", False)
    )
    var_flatten = tk.BooleanVar(value=config["enable_auto_flatten"])
    var_flatten_options = tk.BooleanVar(
        value=bool(
            config.get("enable_flatten_options", False)
            and is_options_waiver_verified(config)
        )
    )
    _opt_waiver_guard = {"suppress": False}
    var_kill_tos = tk.BooleanVar(value=config.get("enable_kill_tos", False))
    var_kill_wb = tk.BooleanVar(value=config.get("enable_kill_webull", False))
    var_lock_os = tk.BooleanVar(value=config["enable_lock_os"])
    var_daily_lock_mins = tk.StringVar(
        value=f"{config.get('daily_lock_mins', 15.0):g}"
    )

    var_reset925 = tk.BooleanVar(value=config["reset_at_925"])
    var_ignore_preexisting = tk.BooleanVar(
        value=bool(config.get("ignore_preexisting_positions", True))
    )
    _ignore_prepos_guard = {"suppress": False}
    _preexisting_state = {
        "broker": None,
        "acct_id": None,
        "had_saved": False,
        "initial_ignored_tags": set(),
        "raw_eq": None,
        "reviewed": False,
        "reanchor_reviewed": False,
    }
    btn_review_ignored = None
    var_reanchor = tk.BooleanVar(value=False)
    var_auto_share_logs = tk.BooleanVar(
        value=bool(config.get("auto_share_sanitized_logs", False))
    )
    _auto_share_guard = {"suppress": False}
    var_voice_cues = tk.BooleanVar(
        value=config.get("enable_voice_cues", True)
    )
    init_voice_id = config.get("tts_voice", "Zira")
    var_tts_voice = tk.StringVar(
        value=TTS_ID_TO_LABEL.get(init_voice_id, "Zira (Female)")
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
        "consec_loss_min_dollars",
        "consec_win_reset_dollars",
        "pm_warn_1", "pm_warn_2", "pm_max_loss",
        "pm_lock_trigger", "pm_trail_cushion",
        "t1_warn_1", "t1_warn_2", "t1_max_loss",
        "t2_trigger", "t2_max_loss",
        "t3_trigger", "t3_max_loss",
        "t4_trigger", "t4_trail"
    ]
    loss_display_keys = {
        "open_max_loss",
        "consec_loss_min_dollars",
        "pm_warn_1", "pm_warn_2", "pm_max_loss",
        "t1_warn_1", "t1_warn_2", "t1_max_loss",
    }

    def _fmt_ui_dollar(key, val):
        v = float(val)
        if key in loss_display_keys:
            mag = abs(v)
            return f"-{mag:.0f}" if mag > 0 else "0"
        return f"{v:.0f}"

    dollar_vars = {
        k: tk.StringVar(value=_fmt_ui_dollar(k, config.get(k, DEFAULT_CONFIG[k])))
        for k in dollar_keys
    }

    def _bind_loss_sign_normalizer(var_obj):
        def _on_focus_out(_event=None):
            try:
                mag = abs(float(var_obj.get().strip()))
                var_obj.set(f"-{mag:.0f}" if mag > 0 else "0")
            except ValueError:
                pass
        return _on_focus_out

    def _render_baseline_telemetry_spans(spans):
        """Renders multi-color inline telemetry spans inside base_sub_lbl frame."""
        if base_sub_lbl is None or not base_sub_lbl.winfo_exists():
            return
        for child in base_sub_lbl.winfo_children():
            child.destroy()
        base_tip = (
            "Shows today's anchored starting account equity ($0.00 PnL reference point),\n"
            "remaining Schwab 7-day token lifetime (click Token to renew), and today's completed Win/Loss trade count."
        )
        in_tr_lk = is_in_trade_tamper_locked()
        for span_item in spans:
            seg_txt = span_item[0]
            seg_col = span_item[1]
            act_key = span_item[2] if len(span_item) > 2 else None
            seg_tip = (
                span_item[3]
                if (len(span_item) > 3 and span_item[3])
                else base_tip
            )
            is_clickable = bool(act_key == "edit_api_keys" and not in_tr_lk)
            lbl = tk.Label(
                base_sub_lbl,
                text=seg_txt,
                font=("Arial", 9, "bold"),
                fg=seg_col,
                bg="#131922",
                bd=0,
                padx=0,
                pady=0,
                anchor="w",
                cursor="hand2" if is_clickable else "arrow",
            )
            lbl.pack(side="left")
            if is_clickable:
                lbl.bind(
                    "<Enter>",
                    lambda _e, w=lbl: w.config(
                        fg="#fde68a", font=("Arial", 9, "bold underline")
                    ),
                )
                lbl.bind(
                    "<Leave>",
                    lambda _e, w=lbl, c=seg_col: w.config(
                        fg=c, font=("Arial", 9, "bold")
                    ),
                )
                lbl.bind(
                    "<Button-1>",
                    lambda _e: edit_api_keys(),
                )
            attach_tooltip(lbl, seg_tip)

    _card3_base_cache = {
        "connected": False,
        "b_name": "SCHWAB",
        "eq_str": "Will anchor on first API poll",
        "last_spans": None,
    }

    def is_tilt_streak_tamper_locked():
        """Returns True if the trader currently has an active Consecutive Loss
        Streak (> 0 losses on the rolling clock) with Consecutive Loss Cooldown
        enabled in config, locking those settings against mid-streak tampering."""
        cur_s, _req_l, _next_s, _full_s, _is_en = get_loss_streak_status()
        return bool(
            cur_s > 0 and config.get("enable_consec_loss_cooldown", False)
        )

    def is_in_trade_tamper_locked():
        """Returns True when the Settings window is opened from the live HUD
        while an active tracked daytrade position is open (`not current_is_flat`),
        locking all enforcement and rulebook settings across Cards 1, 2, 4, and 5
        (plus baseline/position-filter switches) while keeping HUD Columns, Logs,
        Bug Reports, and Audio/System settings accessible."""
        return bool(parent is not None and not current_is_flat)

    def _render_card3_telemetry_live(force=False):
        if base_sub_lbl is None:
            return
        in_tr_lk = is_in_trade_tamper_locked()
        if not _card3_base_cache["connected"]:
            spans = [
                (
                    "⚠️ No broker connected — click here or open BROKER ▾ to set up API Keys ↻",
                    "#f5b041",
                    "edit_api_keys",
                    "Click to open the API Credential Setup Wizard to connect your Schwab or Webull account.",
                )
            ]
            if force or spans != _card3_base_cache["last_spans"]:
                _card3_base_cache["last_spans"] = spans
                _render_baseline_telemetry_spans(spans)
            return

        b_name = _card3_base_cache["b_name"]
        eq_str = _card3_base_cache["eq_str"]
        spans = [
            (f"Baseline ({b_name}): ", "#94a3b8"),
            (eq_str, "#7dd3fc"),
        ]
        if b_name == "SCHWAB":
            rem_h = get_schwab_token_remaining_hours()
            tok_tip = (
                "🔒 Token renewal is locked while a daytrade is open."
                if in_tr_lk
                else "Click to open the Schwab API Wizard & renew your 7-day security token."
            )
            spans.append((" | ", "#475569"))
            if rem_h is not None and rem_h > 0:
                rem_d = rem_h / 24.0
                tok_col = "#fbbf24" if rem_d < 1.5 else "#4ade80"
                tok_sfx = "" if in_tr_lk else " ↻"
                spans.append(
                    (
                        f"Token: {rem_d:.1f}d{tok_sfx}",
                        tok_col,
                        "edit_api_keys",
                        tok_tip,
                    )
                )
            else:
                spans.append(
                    (
                        "Token: EXPIRED (Renew ↻)",
                        "#f87171",
                        "edit_api_keys",
                        tok_tip,
                    )
                )

        tot_t = int(win_trades) + int(loss_trades)
        w_pct = (win_trades / tot_t * 100.0) if tot_t > 0 else 0.0
        l_pct = (loss_trades / tot_t * 100.0) if tot_t > 0 else 0.0
        spans.append((" | ", "#475569"))
        spans.append((f"W: {win_trades} ({w_pct:.1f}%)", "#58d68d"))
        spans.append((" | ", "#475569"))
        spans.append((f"L: {loss_trades} ({l_pct:.1f}%)", "#e07a7a"))
        cur_s, req_l, next_s, _full_s, is_en = get_loss_streak_status()
        if is_en or cur_s > 0 or bool(var_tilt_cd.get()):
            spans.append((" | ", "#475569"))
            if cur_s > 0:
                s_col = "#f87171" if cur_s >= (req_l - 1) else "#fbbf24"
                spans.append(
                    (
                        f"Streak: {cur_s}/{req_l} ({_format_countdown_mm_ss(next_s)})",
                        s_col,
                    )
                )
            else:
                spans.append((f"Streak: 0/{req_l}", "#94a3b8"))
        if bool(var_ignore_preexisting.get()) and ignored_positions:
            spans.append((" | ", "#475569"))
            spans.append((f"Ignored: {len(ignored_positions)}", "#6ee7b7"))
        if force or spans != _card3_base_cache["last_spans"]:
            _card3_base_cache["last_spans"] = spans
            _render_baseline_telemetry_spans(spans)

    def _refresh_ignored_positions_pill(*_):
        if btn_review_ignored is None:
            return
        try:
            if not btn_review_ignored.winfo_exists():
                return
        except Exception:
            return
        raw_pos = (
            active_adapter.get_last_raw_pos_details()
            if active_adapter is not None
            else {}
        )
        ig_cnt = len(ignored_positions) if var_ignore_preexisting.get() else 0
        open_cnt = len(raw_pos)
        if ig_cnt > 0:
            btn_review_ignored.config(
                text=f"🛡️ Ignored ({ig_cnt}) ▸",
                fill_color="#0d2e22",
                fill_top_color="#144332",
                border_color="#10b981",
                hover_fill="#113b2c",
                hover_fill_top="#19543f",
                hover_border="#34d399",
                fg="#6ee7b7",
            )
        elif open_cnt > 0:
            btn_review_ignored.config(
                text=f"⚡ Tracked ({open_cnt}) ▸",
                fill_color="#0f213a",
                fill_top_color="#163052",
                border_color="#38bdf8",
                hover_fill="#132a48",
                hover_fill_top="#1c3b63",
                hover_border="#7dd3fc",
                fg="#7dd3fc",
            )
        else:
            btn_review_ignored.config(
                text="🛡️ Positions (0)",
                fill_color="#141820",
                fill_top_color="#1c212b",
                border_color="#2e3746",
                hover_fill="#181e28",
                hover_fill_top="#232a36",
                hover_border="#475569",
                fg="#94a3b8",
            )

    def _apply_preexisting_selection(chosen_ignored_tags, mark_reviewed=True):
        global start_equity, last_flat_equity, max_equity, daily_max_equity
        global force_reanchor
        raw_pos = (
            active_adapter.get_last_raw_pos_details()
            if active_adapter is not None
            else {}
        )
        is_mid_session = bool(
            _preexisting_state["had_saved"]
            and not force_reanchor
            and not var_reanchor.get()
            and start_equity is not None
            and start_equity > 0
        )
        if not is_mid_session:
            ignored_positions.clear()
            for tag in chosen_ignored_tags:
                if tag in raw_pos:
                    ignored_positions[tag] = build_ignored_position_entry(
                        tag, raw_pos[tag], lock_existing_open_pnl=False
                    )
            raw_eq_now = _preexisting_state.get("raw_eq")
            if raw_eq_now is not None and raw_eq_now > 0:
                tracked_opnl = round(
                    sum(
                        float(d.get("open_pnl", 0.0))
                        for t, d in raw_pos.items()
                        if t not in chosen_ignored_tags
                    ),
                    2,
                )
                start_equity = round(raw_eq_now - tracked_opnl, 2)
                _card3_base_cache["eq_str"] = f"${start_equity:,.2f} (Live)"
        else:
            for tag in list(ignored_positions.keys()):
                if tag not in chosen_ignored_tags:
                    old_ig = ignored_positions.pop(tag, None)
                    if tag in raw_pos and isinstance(old_ig, dict):
                        d = raw_pos[tag]
                        mult = (
                            100.0
                            if str(old_ig.get("asset_type", "EQUITY")).upper()
                            == "OPTION"
                            else 1.0
                        )
                        lp = float(d.get("last", 0.0))
                        qty = float(d.get("qty", 0.0))
                        ref_p = float(old_ig.get("ref_price", lp))
                        locked_imp = float(old_ig.get("locked_impact", 0.0))
                        old_impact = locked_imp + (
                            (lp - ref_p) * qty * mult if lp > 0 else 0.0
                        )
                        d_open = float(d.get("open_pnl", 0.0))
                        delta_base = round(old_impact - d_open, 2)
                        if abs(delta_base) >= 0.01:
                            start_equity = round(start_equity + delta_base, 2)
                            last_flat_equity = round(
                                (
                                    last_flat_equity
                                    if last_flat_equity is not None
                                    else start_equity
                                )
                                + delta_base,
                                2,
                            )
                            max_equity = round(
                                (
                                    max_equity
                                    if max_equity is not None
                                    else start_equity
                                )
                                + delta_base,
                                2,
                            )
                            daily_max_equity = round(
                                (
                                    daily_max_equity
                                    if daily_max_equity is not None
                                    else max_equity
                                )
                                + delta_base,
                                2,
                            )
                            _card3_base_cache["eq_str"] = (
                                f"${start_equity:,.2f} (Saved)"
                            )
            newly_ignored_igs = []
            for tag in chosen_ignored_tags:
                if tag not in ignored_positions and tag in raw_pos:
                    ig_entry = build_ignored_position_entry(
                        tag, raw_pos[tag], lock_existing_open_pnl=True
                    )
                    ignored_positions[tag] = ig_entry
                    newly_ignored_igs.append(ig_entry)
            raw_eq_now = _preexisting_state.get("raw_eq")
            ref_flat_eq = (
                last_flat_equity
                if last_flat_equity is not None
                else start_equity
            )
            if (
                newly_ignored_igs
                and raw_eq_now is not None
                and float(raw_eq_now) > 0.0
                and ref_flat_eq is not None
                and float(ref_flat_eq) > 0.0
            ):
                tracked_opnl = round(
                    sum(
                        float(d.get("open_pnl", 0.0))
                        for t, d in raw_pos.items()
                        if t not in chosen_ignored_tags
                    ),
                    2,
                )
                cur_ig_sum = 0.0
                for t_ig, ig_d in ignored_positions.items():
                    if not isinstance(ig_d, dict):
                        continue
                    r_d = raw_pos.get(t_ig)
                    l_imp = float(ig_d.get("locked_impact", 0.0))
                    if r_d is not None:
                        m_ig = (
                            100.0
                            if str(ig_d.get("asset_type", "EQUITY")).upper()
                            == "OPTION"
                            else 1.0
                        )
                        q_ig = float(r_d.get("qty", 0.0))
                        lp_ig = float(r_d.get("last", 0.0))
                        rp_ig = float(ig_d.get("ref_price", lp_ig))
                        cur_ig_sum += l_imp + q_ig * (lp_ig - rp_ig) * m_ig
                    else:
                        cur_ig_sum += l_imp
                target_ig_sum = round(
                    (float(raw_eq_now) - tracked_opnl) - float(ref_flat_eq), 2
                )
                ig_drift = round(target_ig_sum - cur_ig_sum, 2)
                if abs(ig_drift) >= 0.01 and abs(ig_drift) <= 50000.0:
                    newly_ignored_igs[-1]["locked_impact"] = round(
                        float(newly_ignored_igs[-1].get("locked_impact", 0.0))
                        + ig_drift,
                        2,
                    )
            save_session_state()

        if chosen_ignored_tags and not var_ignore_preexisting.get():
            _ignore_prepos_guard["suppress"] = True
            try:
                var_ignore_preexisting.set(True)
            finally:
                _ignore_prepos_guard["suppress"] = False
        config["ignore_preexisting_positions"] = bool(
            var_ignore_preexisting.get()
        )
        if mark_reviewed:
            _preexisting_state["reviewed"] = True
            _preexisting_state["reanchor_reviewed"] = bool(var_reanchor.get())
        _refresh_ignored_positions_pill()
        _render_card3_telemetry_live(force=True)

    def refresh_baseline_preview(force_restore=False):
        """Updates the Active Baseline multi-color telemetry strip in Card 3 to
        match the currently selected Broker + Account."""
        global start_equity, last_flat_equity, prev_flat_realized_pnl
        global settled_realized_pnl, anchor_cash_flow, force_reanchor
        if base_sub_lbl is None:
            return
        if active_adapter is None or not active_adapter.account_id:
            _card3_base_cache["connected"] = False
            _refresh_ignored_positions_pill()
            _render_card3_telemetry_live(force=True)
            return

        b_name = active_adapter.name
        acct_id = active_adapter.account_id
        if (
            parent is not None
            and not force_restore
            and start_equity is not None
            and start_equity > 0
        ):
            # Live HUD session is already actively running for this broker/account:
            # preserve live in-memory session state without re-running restore_account_session
            _preexisting_state["broker"] = b_name
            _preexisting_state["acct_id"] = acct_id
            _preexisting_state["had_saved"] = True
            _preexisting_state["initial_ignored_tags"] = set(
                ignored_positions.keys()
            )
            _preexisting_state["reviewed"] = True
            _preexisting_state["reanchor_reviewed"] = False
            eq_str = f"${start_equity:,.2f} (Saved)"
        else:
            had_saved = restore_account_session(
                b_name, acct_id, log_restore=False
            )
            _preexisting_state["broker"] = b_name
            _preexisting_state["acct_id"] = acct_id
            _preexisting_state["had_saved"] = had_saved
            _preexisting_state["initial_ignored_tags"] = set(
                ignored_positions.keys()
            )
            _preexisting_state["reviewed"] = False
            _preexisting_state["reanchor_reviewed"] = False

            if had_saved and start_equity is not None and start_equity > 0:
                force_reanchor = False
                if (
                    parent is None
                    or not active_adapter.get_last_raw_pos_details()
                ):
                    eq_now, is_fl_now, _, _, _ = (
                        active_adapter.fetch_account_data()
                    )
                    if (
                        parent is None
                        and eq_now is not None
                        and eq_now > 0
                        and is_fl_now
                    ):
                        last_flat_equity = round(float(eq_now), 2)
                        prev_flat_realized_pnl = round(
                            last_flat_equity - start_equity, 2
                        )
                        settled_realized_pnl = prev_flat_realized_pnl
                        save_session_state()
                eq_str = f"${start_equity:,.2f} (Saved)"
            else:
                eq, _, live_opnl, _, _ = active_adapter.fetch_account_data()
                _preexisting_state["raw_eq"] = eq
                raw_pos = active_adapter.get_last_raw_pos_details()
                if var_ignore_preexisting.get() and raw_pos:
                    ignored_positions.clear()
                    for tag, d in raw_pos.items():
                        ignored_positions[tag] = build_ignored_position_entry(
                            tag, d, lock_existing_open_pnl=False
                        )
                    live_opnl = 0.0
                if eq is not None and eq > 0:
                    start_equity = round(eq - live_opnl, 2)
                    anchor_cash_flow = (
                        active_adapter.get_last_intraday_cash_flow()
                    )
                    force_reanchor = True
                    eq_str = f"${start_equity:,.2f} (Live)"
                else:
                    eq_str = "Will anchor on first API poll"

        _card3_base_cache["connected"] = True
        _card3_base_cache["b_name"] = b_name
        _card3_base_cache["eq_str"] = eq_str
        _refresh_ignored_positions_pill()
        _render_card3_telemetry_live(force=True)

    def _on_toggle_ignore_preexisting(*_):
        if _ignore_prepos_guard["suppress"] or is_in_trade_tamper_locked():
            return
        raw_pos = (
            active_adapter.get_last_raw_pos_details()
            if active_adapter is not None
            else {}
        )
        if var_ignore_preexisting.get():
            _apply_preexisting_selection(
                set(raw_pos.keys()), mark_reviewed=False
            )
        else:
            _apply_preexisting_selection(set(), mark_reviewed=True)

    var_ignore_preexisting.trace_add("write", _on_toggle_ignore_preexisting)

    def show_preexisting_positions_dialog(from_launch=False):
        """Displays a dark-glass modal dialog listing pre-existing / open
        positions in the account so the trader can keep swing/long-term holdings
        Ignored (default) or toggle specific positions to Track as Active
        Daytrades."""
        read_only = is_in_trade_tamper_locked()
        if active_adapter is not None and not from_launch and not read_only:
            try:
                active_adapter.fetch_account_data()
            except Exception:
                pass
        raw_pos = (
            active_adapter.get_last_raw_pos_details()
            if active_adapter is not None
            else {}
        )
        all_tags = list(raw_pos.keys()) + [
            t for t in ignored_positions.keys() if t not in raw_pos
        ]
        if from_launch and not all_tags:
            return True

        decision = {"ok": False}
        dlg = tk.Toplevel(pf)
        dlg.withdraw()
        dlg.grab_set()
        if os.path.exists(ICON_PATH):
            try:
                dlg.iconbitmap(ICON_PATH)
            except Exception:
                pass
        apply_dark_title_bar(dlg)
        dlg.title(
            "PnL Enforcer — Open & Ignored Positions (In-Trade Read-Only View)"
            if read_only
            else "PnL Enforcer — Pre-Existing Positions & Daytrade Filter"
        )
        dlg.config(bg="#0d1117", padx=24, pady=18)
        dlg.resizable(False, False)
        dlg.transient(pf)
        dlg.attributes("-topmost", True)

        def on_cancel():
            decision["ok"] = False
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", on_cancel)
        dlg.bind("<Escape>", lambda _e: on_cancel())

        init_tags = _preexisting_state.get("initial_ignored_tags", set())
        had_svd = bool(_preexisting_state.get("had_saved", False))
        is_rezero = bool(var_reanchor.get())
        new_today_tags = (
            [t for t in raw_pos.keys() if t not in init_tags]
            if (had_svd and not is_rezero)
            else []
        )
        # List new intraday positions first when re-opening mid-day
        if new_today_tags:
            all_tags = (
                list(new_today_tags)
                + [t for t in raw_pos.keys() if t in init_tags]
                + [t for t in ignored_positions.keys() if t not in raw_pos]
            )

        hdr_row = tk.Frame(dlg, bg="#0d1117")
        hdr_row.pack(fill="x", pady=(0, 4))
        if read_only:
            hdr_title = "▶  🔒 OPEN & IGNORED POSITIONS — IN-TRADE READ-ONLY VIEW"
            hdr_fg = "#fbbf24"
        elif new_today_tags:
            hdr_title = "▶  ⚡ NEW POSITION(S) FOUND TODAY — DAYTRADE OR SWING?"
            hdr_fg = "#38bdf8"
        elif all_tags:
            hdr_title = "▶  🛡️ PRE-EXISTING POSITIONS DETECTED IN ACCOUNT"
            hdr_fg = "#4ec994"
        else:
            hdr_title = "▶  🛡️ PRE-EXISTING & IGNORED POSITIONS MANAGER"
            hdr_fg = "#4ec994"

        tk.Label(
            hdr_row,
            text=hdr_title,
            font=("Arial", 12, "bold"),
            fg=hdr_fg,
            bg="#0d1117",
            anchor="w",
        ).pack(side="left")

        b_lbl = (
            active_adapter.name
            if active_adapter is not None
            else config.get("active_broker", "SCHWAB")
        )
        badge_hdr_txt = (
            f"🔒 IN TRADE · {len(raw_pos)} OPEN"
            if read_only
            else (
                f"{b_lbl} · {len(new_today_tags)} NEW TODAY / {len(raw_pos)} OPEN"
                if new_today_tags
                else f"{b_lbl} · {len(raw_pos)} OPEN POSITION{'S' if len(raw_pos) != 1 else ''}"
            )
        )
        tk.Label(
            hdr_row,
            text=badge_hdr_txt,
            font=("Arial", 8, "bold"),
            fg="#fde68a" if (read_only or new_today_tags) else "#7dd3fc",
            bg="#33220c" if (read_only or new_today_tags) else "#142334",
            padx=8,
            pady=3,
        ).pack(side="right", padx=(12, 0))

        if read_only:
            sub_txt = (
                "An active daytrade is currently open. Position tracking & ignore status are locked in Read-Only mode\n"
                "so an active daytrade cannot be switched to Ignored mid-trade. Flatten your daytrade to modify."
            )
        elif new_today_tags:
            sub_txt = (
                f"Detected {len(new_today_tags)} new position{'s' if len(new_today_tags) != 1 else ''} "
                f"({', '.join(new_today_tags[:3])}) opened since your session started today.\n"
                "New positions default to ⚡ TRACK AS DAYTRADE, while your earlier swing positions stay 🛡️ IGNORED."
            )
        else:
            sub_txt = (
                "PnL Enforcer regulates intraday trades. Positions marked IGNORED are treated as swing / long-term holdings:\n"
                "they never lock enforcement settings or HUD Close, never trigger Open or Daily Stops, and are never auto-flattened."
            )
        tk.Label(
            dlg,
            text=sub_txt,
            font=("Arial", 9),
            fg="#94a3b8",
            bg="#0d1117",
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        list_outer = tk.Frame(
            dlg,
            bg="#131922",
            bd=0,
            highlightthickness=1,
            highlightbackground="#243040",
        )
        list_outer.pack(fill="both", expand=True, pady=(0, 10))
        NeonBarCanvas(
            list_outer,
            core_color="#38bdf8" if new_today_tags else "#10b981",
            card_bg="#131922",
            glow_on=True,
        ).pack(side="left", fill="y")

        if len(all_tags) > 6:
            scroll_wrap = tk.Frame(list_outer, bg="#131922")
            scroll_wrap.pack(side="left", fill="both", expand=True)
            cvs = tk.Canvas(
                scroll_wrap,
                bg="#131922",
                bd=0,
                highlightthickness=0,
                width=740,
                height=264,
            )
            sb = tk.Scrollbar(
                scroll_wrap, orient="vertical", command=cvs.yview
            )
            list_frame = tk.Frame(cvs, bg="#131922", padx=14, pady=10)
            list_frame.bind(
                "<Configure>",
                lambda _e: cvs.configure(scrollregion=cvs.bbox("all")),
            )
            cvs.create_window((0, 0), window=list_frame, anchor="nw", width=740)
            cvs.configure(yscrollcommand=sb.set)
            cvs.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
        else:
            list_frame = tk.Frame(list_outer, bg="#131922", padx=14, pady=10)
            list_frame.pack(side="left", fill="both", expand=True)

        row_vars = {}

        if not all_tags:
            tk.Label(
                list_frame,
                text=(
                    "✓ Your account is currently 100% flat (0 open positions).\n\n"
                    "When 'Ignore Pre-Existing Positions on Launch' is checked, any swing or long-term positions\n"
                    "open in your account when you launch PnL Enforcer will appear here and default to Ignored."
                ),
                font=("Arial", 10),
                fg="#cbd5e1",
                bg="#131922",
                justify="left",
                anchor="w",
                padx=8,
                pady=12,
            ).pack(fill="x")
        else:
            for idx, tag in enumerate(all_tags):
                d = raw_pos.get(tag)
                ig_saved = ignored_positions.get(tag, {})
                is_closed_today = d is None
                if _preexisting_state["reviewed"]:
                    default_ig = tag in ignored_positions
                elif not var_ignore_preexisting.get():
                    default_ig = tag in ignored_positions
                elif had_svd and not is_rezero:
                    # Mid-day relaunch: keep earlier swing positions Ignored,
                    # default brand-new intraday positions to Track as Daytrade
                    default_ig = (tag in init_tags) or is_closed_today
                else:
                    default_ig = True
                rv = tk.BooleanVar(value=bool(default_ig))
                row_vars[tag] = rv

                if idx > 0:
                    tk.Frame(list_frame, bg="#1f2937", height=1).pack(
                        fill="x", pady=5
                    )

                r_f = tk.Frame(list_frame, bg="#131922")
                r_f.pack(fill="x", pady=2)

                left_info = tk.Frame(r_f, bg="#131922")
                left_info.pack(side="left", fill="x", expand=True)

                top_line = tk.Frame(left_info, bg="#131922")
                top_line.pack(fill="x")

                a_type = str(
                    (d or ig_saved).get("asset_type", "EQUITY")
                ).upper()
                tk.Label(
                    top_line,
                    text=tag,
                    font=("Consolas", 11, "bold"),
                    fg="#f8fafc",
                    bg="#131922",
                ).pack(side="left", padx=(0, 8))

                tk.Label(
                    top_line,
                    text=a_type,
                    font=("Arial", 8, "bold"),
                    fg="#fbbf24" if a_type == "OPTION" else "#38bdf8",
                    bg="#33220c" if a_type == "OPTION" else "#142334",
                    padx=6,
                    pady=1,
                ).pack(side="left", padx=(0, 8))

                if is_closed_today:
                    b_txt, b_fg, b_bg = (
                        "CLOSED TODAY — LOCKED AT $0 IMPACT",
                        "#94a3b8",
                        "#1e293b",
                    )
                elif tag in init_tags and not is_rezero:
                    b_txt, b_fg, b_bg = (
                        "🛡️ ALREADY IGNORED (SWING)",
                        "#6ee7b7",
                        "#132a22",
                    )
                elif had_svd and not is_rezero:
                    b_txt, b_fg, b_bg = (
                        "⚡ NEW POSITION TODAY",
                        "#fde68a",
                        "#33220c",
                    )
                else:
                    b_txt, b_fg, b_bg = (
                        "PRE-EXISTING AT LAUNCH",
                        "#7dd3fc",
                        "#1a2636",
                    )

                tk.Label(
                    top_line,
                    text=b_txt,
                    font=("Arial", 8, "bold"),
                    fg=b_fg,
                    bg=b_bg,
                    padx=6,
                    pady=1,
                ).pack(side="left")

                bot_line = tk.Frame(left_info, bg="#131922")
                bot_line.pack(fill="x", pady=(2, 0))
                if is_closed_today:
                    init_q = float(ig_saved.get("init_qty", 0.0))
                    init_p = float(ig_saved.get("init_price", 0.0))
                    tk.Label(
                        bot_line,
                        text=f"Started at Qty: {init_q:+g}  ·  Ref Price: ${init_p:,.2f}  ·  Closed earlier today",
                        font=("Consolas", 9),
                        fg="#94a3b8",
                        bg="#131922",
                    ).pack(side="left")
                else:
                    qty = float(d.get("qty", 0.0))
                    avg = float(d.get("avg", 0.0))
                    last = float(d.get("last", 0.0))
                    opnl = float(d.get("open_pnl", 0.0))
                    tk.Label(
                        bot_line,
                        text=f"Qty: {qty:+g}   ·   Avg: ${avg:,.2f}   ·   Last: ${last:,.2f}   ·   Open PnL: ",
                        font=("Consolas", 9),
                        fg="#cbd5e1",
                        bg="#131922",
                    ).pack(side="left")
                    opnl_col = (
                        "#4ade80"
                        if opnl > 0.005
                        else ("#f87171" if opnl < -0.005 else "#94a3b8")
                    )
                    tk.Label(
                        bot_line,
                        text=format_dollar(opnl),
                        font=("Consolas", 9, "bold"),
                        fg=opnl_col,
                        bg="#131922",
                    ).pack(side="left")

                def _make_row_toggle(t_var):
                    btn = make_stadium_button(
                        r_f,
                        text="🛡️ IGNORE (Swing / Hold)",
                        font=("Arial", 9, "bold"),
                        fill_color="#0d2e22",
                        fill_top_color="#144332",
                        border_color="#10b981",
                        hover_fill="#113b2c",
                        hover_fill_top="#19543f",
                        hover_border="#34d399",
                        fg="#6ee7b7",
                        canvas_bg="#131922",
                        width=226,
                        height=30,
                        auto_width=False,
                        command=lambda: (
                            None
                            if read_only
                            else t_var.set(not bool(t_var.get()))
                        ),
                    )
                    btn.pack(side="right", padx=(14, 0))

                    def _sync_btn(*_):
                        if t_var.get():
                            btn.config(
                                text=(
                                    "🔒 IGNORED (Swing / Hold)"
                                    if read_only
                                    else "🛡️ IGNORE (Swing / Hold)"
                                ),
                                fill_color="#0d2e22",
                                fill_top_color="#144332",
                                border_color="#10b981",
                                hover_fill="#113b2c",
                                hover_fill_top="#19543f",
                                hover_border="#34d399",
                                fg="#6ee7b7",
                                disabledforeground="#6ee7b7",
                                state="disabled" if read_only else "normal",
                            )
                        else:
                            btn.config(
                                text=(
                                    "🔒 TRACKED DAYTRADE"
                                    if read_only
                                    else "⚡ TRACK AS DAYTRADE"
                                ),
                                fill_color="#33220c" if read_only else "#0f213a",
                                fill_top_color=(
                                    "#473010" if read_only else "#163052"
                                ),
                                border_color=(
                                    "#f59e0b" if read_only else "#38bdf8"
                                ),
                                hover_fill="#132a48",
                                hover_fill_top="#1c3b63",
                                hover_border="#7dd3fc",
                                fg="#fde68a" if read_only else "#ffffff",
                                disabledforeground=(
                                    "#fde68a" if read_only else "#ffffff"
                                ),
                                state="disabled" if read_only else "normal",
                            )
                        _update_summary_strip()

                    t_var.trace_add("write", _sync_btn)
                    return _sync_btn

                row_sync = _make_row_toggle(rv)
                r_f._sync_fn = row_sync

        summary_lbl = tk.Label(
            dlg,
            text="",
            font=("Arial", 9, "bold"),
            fg="#6ee7b7",
            bg="#111822",
            padx=12,
            pady=6,
            anchor="w",
        )
        summary_lbl.pack(fill="x", pady=(0, 8))

        def _update_summary_strip():
            if not row_vars:
                summary_lbl.config(
                    text="🛡️ 0 Pre-Existing Positions Currently Open",
                    fg="#94a3b8",
                )
                return
            ig_c = sum(1 for v in row_vars.values() if v.get())
            tr_c = len(row_vars) - ig_c
            summary_lbl.config(
                text=(
                    f"Selection Summary:   🛡️ {ig_c} Ignored ($0.00 Daytrade Impact, Never Auto-Flattened)   ·   "
                    f"⚡ {tr_c} Tracked as Active Daytrade{'s' if tr_c != 1 else ''}"
                ),
                fg="#6ee7b7" if ig_c > 0 else "#7dd3fc",
            )

        for w_child in list_frame.winfo_children():
            if hasattr(w_child, "_sync_fn"):
                w_child._sync_fn()
        _update_summary_strip()

        rules_box = tk.Frame(
            dlg,
            bg="#11161f",
            bd=0,
            highlightthickness=1,
            highlightbackground="#1e293b",
            padx=14,
            pady=8,
        )
        rules_box.pack(fill="x", pady=(0, 12))
        tk.Label(
            rules_box,
            text=(
                "• 🛡️ Ignored Ticker Rule: Price swings, adding shares, trimming, or closing an Ignored ticker has $0.00 impact on your\n"
                "  daytrade Realized/Open/Net PnL, never locks Settings/Close, and is skipped by Auto-Flatten & Order Cancellation.\n"
                "• ⚡ Tracked Daytrade Rule: Monitored live for Open PnL, Daily Stop, and Auto-Flatten (starting at $0.00 Realized PnL)."
            ),
            font=("Arial", 8),
            fg="#94a3b8",
            bg="#11161f",
            justify="left",
            anchor="w",
        ).pack(fill="x")

        btn_bar = tk.Frame(dlg, bg="#0d1117")
        btn_bar.pack(fill="x")

        if read_only:
            tk.Label(
                btn_bar,
                text="🔒 Position tracking cannot be modified while an active daytrade is open.",
                font=("Arial", 9, "bold"),
                fg="#fbbf24",
                bg="#0d1117",
                anchor="w",
            ).pack(side="left")
            make_stadium_button(
                btn_bar,
                text="Close",
                font=("Arial", 10, "bold"),
                fill_color="#181e26",
                border_color="#4a5568",
                hover_fill="#232c38",
                hover_border="#718096",
                fg="#d1d5db",
                canvas_bg="#0d1117",
                width=116,
                height=36,
                auto_width=False,
                command=on_cancel,
            ).pack(side="right")
        else:
            if row_vars:
                def _set_all_rows(val):
                    for v in row_vars.values():
                        v.set(val)

                if new_today_tags and init_tags:
                    def _set_new_daytrade_swings_ignored():
                        for t, v in row_vars.items():
                            v.set((t in init_tags) or (t not in raw_pos))

                    make_stadium_button(
                        btn_bar,
                        text="Track New & Ignore Swings (Default)",
                        font=("Arial", 9, "bold"),
                        fill_color="#141820",
                        fill_top_color="#1c212b",
                        border_color="#2e3746",
                        hover_fill="#181e28",
                        hover_fill_top="#232a36",
                        hover_border="#38bdf8",
                        fg="#7dd3fc",
                        canvas_bg="#0d1117",
                        width=226,
                        height=34,
                        auto_width=False,
                        command=_set_new_daytrade_swings_ignored,
                    ).pack(side="left", padx=(0, 8))

                make_stadium_button(
                    btn_bar,
                    text=(
                        "Ignore All"
                        if new_today_tags
                        else "Ignore All (Default)"
                    ),
                    font=("Arial", 9, "bold"),
                    fill_color="#141820",
                    fill_top_color="#1c212b",
                    border_color="#2e3746",
                    hover_fill="#181e28",
                    hover_fill_top="#232a36",
                    hover_border="#10b981",
                    fg="#6ee7b7",
                    canvas_bg="#0d1117",
                    width=112 if new_today_tags else 148,
                    height=34,
                    auto_width=False,
                    command=lambda: _set_all_rows(True),
                ).pack(side="left", padx=(0, 8))

                make_stadium_button(
                    btn_bar,
                    text=(
                        "Track All"
                        if new_today_tags
                        else "Track All as Daytrades"
                    ),
                    font=("Arial", 9, "bold"),
                    fill_color="#141820",
                    fill_top_color="#1c212b",
                    border_color="#2e3746",
                    hover_fill="#181e28",
                    hover_fill_top="#232a36",
                    hover_border="#38bdf8",
                    fg="#7dd3fc",
                    canvas_bg="#0d1117",
                    width=108 if new_today_tags else 168,
                    height=34,
                    auto_width=False,
                    command=lambda: _set_all_rows(False),
                ).pack(side="left")

            def on_apply():
                chosen_ig = {t for t, v in row_vars.items() if v.get()}
                _apply_preexisting_selection(chosen_ig, mark_reviewed=True)
                log_event(
                    "SESSION",
                    f"Pre-Existing Position Filter applied: "
                    f"Ignored={sorted(chosen_ig)} | "
                    f"Tracked={sorted(t for t in row_vars if t not in chosen_ig)}",
                )
                decision["ok"] = True
                dlg.destroy()

            confirm_lbl = (
                "✔ Apply & Launch Enforcer >>"
                if (from_launch and parent is None)
                else (
                    "✔ Apply & Save >>"
                    if from_launch
                    else "✔ Apply Selection"
                )
            )
            make_stadium_button(
                btn_bar,
                text=confirm_lbl,
                font=("Arial", 10, "bold"),
                fill_color="#0d3b20",
                fill_top_color="#14532d",
                border_color="#10b981",
                hover_fill="#114b29",
                hover_fill_top="#196638",
                hover_border="#34d399",
                fg="#ffffff",
                canvas_bg="#0d1117",
                width=236 if from_launch else 174,
                height=36,
                auto_width=False,
                command=on_apply,
            ).pack(side="right")

            make_stadium_button(
                btn_bar,
                text="Cancel",
                font=("Arial", 10, "bold"),
                fill_color="#181e26",
                border_color="#4a5568",
                hover_fill="#232c38",
                hover_border="#718096",
                fg="#d1d5db",
                canvas_bg="#0d1117",
                width=104,
                height=36,
                auto_width=False,
                command=on_cancel,
            ).pack(side="right", padx=(0, 8))

        dlg.update_idletasks()
        w_req = max(760, dlg.winfo_reqwidth())
        h_req = dlg.winfo_reqheight()
        center_dialog_over_parent(dlg, parent=pf, width=w_req, height=h_req)

        pf.wait_window(dlg)
        return decision["ok"]

    # --- TOP BAR: UNIFIED BROKER/ACCOUNT CAPSULE, UTILITY PILLS & PRESETS ---
    top_bar = tk.Frame(
        pf,
        bg="#11161f",
        bd=0,
        highlightthickness=1,
        highlightbackground="#222d3d",
        padx=10,
        pady=7,
    )
    top_bar.pack(fill="x", pady=(0, 12))

    # 1. Unified Broker & Account Frosted Glass Stadium Bar (Single Un-Nested Bar)
    broker_acct_capsule = tk.Canvas(
        top_bar,
        bg="#11161f",
        width=408,
        height=32,
        bd=0,
        highlightthickness=0,
        cursor="hand2",
    )
    broker_acct_capsule.pack(side="left", padx=(0, 6))

    broker_dropdown = DarkDropdownMenu(
        pf,
        tearoff=0,
        font=("Arial", 9, "bold"),
        bg="#141820",
        fg="#e2e8f0",
        activebackground="#1e293b",
        activeforeground="#ffffff",
    )

    def rebuild_broker_dropdown():
        broker_dropdown.delete(0, "end")
        cur_b = str(var_broker.get() or "SCHWAB").upper()
        for b_opt in ("SCHWAB", "WEBULL"):
            chk = "✓ " if b_opt == cur_b else "   "
            broker_dropdown.add_command(
                label=f"{chk}{b_opt}",
                command=lambda b=b_opt: var_broker.set(b),
                fg="#7dd3fc" if b_opt == cur_b else "#e2e8f0",
                activeforeground="#ffffff",
            )
        broker_dropdown.add_separator()
        if cur_b == "SCHWAB":
            broker_dropdown.add_command(
                label="🔑 API Keys & Renew 7-Day Token...",
                command=lambda: edit_api_keys(),
                fg="#f5b041",
                activeforeground="#fde68a",
            )
        else:
            broker_dropdown.add_command(
                label="🔑 Configure Webull API Keys...",
                command=lambda: edit_api_keys(),
                fg="#f5b041",
                activeforeground="#fde68a",
            )

    acct_dropdown = DarkDropdownMenu(
        pf,
        tearoff=0,
        font=("Arial", 9, "bold"),
        bg="#141820",
        fg="#e2e8f0",
        activebackground="#1e293b",
        activeforeground="#ffffff",
    )

    _capsule_state = {
        "bg_photo": None,
        "dot_photo": None,
        "hover_zone": None,
        "divider_x": 165,
        "broker_x": 74,
        "acct_x": 248,
        "connected": True,
    }

    def _measure_canvas_txt(cvs, txt, fnt):
        pid = cvs.create_text(0, 0, text=txt, font=fnt, anchor="nw")
        bb = cvs.bbox(pid)
        cvs.delete(pid)
        return (bb[2] - bb[0]) if bb else 0

    def _redraw_broker_acct_capsule(_event=None):
        broker_acct_capsule.delete("all")
        fnt_lbl = ("Arial", 9, "bold")
        fnt_val = ("Arial", 9, "bold")
        b_val = var_broker.get() or "SCHWAB"
        a_val = var_account_label.get() or "Loading..."

        w_b_lbl = _measure_canvas_txt(broker_acct_capsule, "BROKER:", fnt_lbl)
        w_b_val = _measure_canvas_txt(broker_acct_capsule, b_val, fnt_val)
        w_a_lbl = _measure_canvas_txt(broker_acct_capsule, "ACCOUNT:", fnt_lbl)
        w_a_val = _measure_canvas_txt(broker_acct_capsule, a_val, fnt_val)

        pad_l = 16
        x_b_lbl = pad_l
        x_b_val = x_b_lbl + w_b_lbl + 7
        x_b_chev = x_b_val + w_b_val + 6
        x_div = x_b_chev + 18
        x_dot = x_div + 4
        x_a_lbl = x_dot + 19
        x_a_val = x_a_lbl + w_a_lbl + 7
        x_a_chev = x_a_val + w_a_val + 6
        total_w = max(360, int(x_a_chev + 20))
        h = 32
        cy = h // 2

        _capsule_state["divider_x"] = x_div
        _capsule_state["broker_x"] = x_b_val - 4
        _capsule_state["acct_x"] = x_a_val - 4

        if abs(int(broker_acct_capsule["width"]) - total_w) > 1:
            broker_acct_capsule.configure(width=total_w, height=h)

        hz = _capsule_state["hover_zone"]
        _capsule_state["bg_photo"] = _get_glass_pill_photo(
            broker_acct_capsule,
            total_w,
            h,
            bg_hex="#11161f",
            fill_hex="#141820",
            fill_top_hex="#1c212b",
            border_hex="#2e3746" if hz is None else "#475569",
            hover=(hz is not None),
            corner_radius=6,
        )
        broker_acct_capsule.create_image(
            0, 0, image=_capsule_state["bg_photo"], anchor="nw"
        )

        # Subtle hover highlight directly on the surface when hovering a selector
        if hz == "broker":
            broker_acct_capsule.create_rectangle(
                x_b_val - 5,
                5,
                x_b_chev + 10,
                h - 5,
                fill="#1f2735",
                outline="#3b495e",
                width=1,
            )
        elif hz == "account":
            broker_acct_capsule.create_rectangle(
                x_a_val - 5,
                5,
                x_a_chev + 10,
                h - 5,
                fill="#1f2735",
                outline="#3b495e",
                width=1,
            )

        broker_acct_capsule.create_text(
            x_b_lbl, cy, text="BROKER:", font=fnt_lbl, fill="#60a5fa", anchor="w"
        )
        broker_acct_capsule.create_text(
            x_b_val,
            cy,
            text=b_val,
            font=fnt_val,
            fill="#ffffff" if hz == "broker" else "#f8fafc",
            anchor="w",
        )
        broker_acct_capsule.create_text(
            x_b_chev,
            cy,
            text="▾",
            font=fnt_val,
            fill="#7dd3fc" if hz == "broker" else "#38bdf8",
            anchor="w",
        )

        dot_c = "#00e676" if _capsule_state["connected"] else "#fbbf24"
        _capsule_state["dot_photo"] = _get_glow_dot_photo(
            broker_acct_capsule, bg_hex="#171c25", dot_hex=dot_c, size=18
        )
        broker_acct_capsule.create_image(
            x_dot + 7, cy, image=_capsule_state["dot_photo"], anchor="center"
        )

        broker_acct_capsule.create_text(
            x_a_lbl, cy, text="ACCOUNT:", font=fnt_lbl, fill="#94a3b8", anchor="w"
        )
        broker_acct_capsule.create_text(
            x_a_val,
            cy,
            text=a_val,
            font=fnt_val,
            fill="#ffffff" if hz == "account" else "#f8fafc",
            anchor="w",
        )
        broker_acct_capsule.create_text(
            x_a_chev,
            cy,
            text="▾",
            font=fnt_val,
            fill="#69f0ae" if hz == "account" else "#00e676",
            anchor="w",
        )

    def _on_capsule_motion(event):
        if is_in_trade_tamper_locked():
            if _capsule_state["hover_zone"] is not None:
                _capsule_state["hover_zone"] = None
                _redraw_broker_acct_capsule()
            return
        new_z = "broker" if event.x < _capsule_state["divider_x"] else "account"
        if new_z != _capsule_state["hover_zone"]:
            _capsule_state["hover_zone"] = new_z
            _redraw_broker_acct_capsule()

    def _on_capsule_leave(_event):
        if _capsule_state["hover_zone"] is not None:
            _capsule_state["hover_zone"] = None
            _redraw_broker_acct_capsule()

    def _on_capsule_click(event):
        hide_all_tooltips()
        if is_in_trade_tamper_locked():
            if default_status_lbl is not None:
                default_status_lbl.config(
                    text="🔒 Broker & Account selection are locked while a daytrade is open.",
                    fg="#fbbf24",
                )
            return
        root_x = broker_acct_capsule.winfo_rootx()
        root_y = (
            broker_acct_capsule.winfo_rooty()
            + broker_acct_capsule.winfo_height()
            + 2
        )

        def _after_capsule_menu_close():
            hide_all_tooltips()
            _capsule_state["hover_zone"] = None
            _redraw_broker_acct_capsule()

        if event.x < _capsule_state["divider_x"]:
            rebuild_broker_dropdown()
            broker_dropdown.tk_popup(
                root_x + int(_capsule_state["broker_x"]),
                root_y,
                min_width=92,
                owner=broker_acct_capsule,
                on_close=_after_capsule_menu_close,
            )
        else:
            acct_dropdown.tk_popup(
                root_x + int(_capsule_state["acct_x"]),
                root_y,
                min_width=155,
                owner=broker_acct_capsule,
                on_close=_after_capsule_menu_close,
            )

    broker_acct_capsule.bind("<Configure>", _redraw_broker_acct_capsule, add="+")
    broker_acct_capsule.bind("<Motion>", _on_capsule_motion, add="+")
    broker_acct_capsule.bind("<Leave>", _on_capsule_leave, add="+")
    broker_acct_capsule.bind("<Button-1>", _on_capsule_click, add="+")

    attach_tooltip(
        broker_acct_capsule,
        "Click BROKER (left) to switch between Charles Schwab / Thinkorswim and Webull,\n"
        "or to open the API Credential Setup Wizard & renew your 7-day Schwab token.\n"
        "Click ACCOUNT (right) to choose which sub-account to monitor.\n"
        "Each broker and account tracks its own separate daily baseline and session history."
    )

    def _sync_broker_acct_pills(*_):
        _capsule_state["connected"] = bool(
            active_adapter and active_adapter.accounts
        )
        rebuild_broker_dropdown()
        _redraw_broker_acct_capsule()

    var_account_label.trace_add("write", _sync_broker_acct_pills)

    def on_account_select(chosen_lbl):
        if is_in_trade_tamper_locked():
            return
        var_account_label.set(chosen_lbl)
        if active_adapter is not None:
            chosen_id = account_label_to_id.get(chosen_lbl)
            if chosen_id and chosen_id != active_adapter.account_id:
                active_adapter.account_id = chosen_id
                config["brokers"][active_adapter.name]["selected_account_id"] = chosen_id
                refresh_baseline_preview(force_restore=True)

    def populate_account_dropdown():
        account_label_to_id.clear()
        acct_dropdown.delete(0, "end")
        if active_adapter and active_adapter.accounts:
            selected_lbl = active_adapter.accounts[0]["label"]
            for acc in active_adapter.accounts:
                lbl = acc["label"]
                aid = acc["id"]
                account_label_to_id[lbl] = aid
                acct_dropdown.add_command(
                    label=lbl,
                    command=lambda v=lbl: on_account_select(v)
                )
                if aid == active_adapter.account_id:
                    selected_lbl = lbl
            var_account_label.set(selected_lbl)
        else:
            var_account_label.set("No Account Connected")
        _sync_broker_acct_pills()

    def on_broker_change(*_):
        global active_adapter, broker_reconfig_in_progress
        if is_in_trade_tamper_locked():
            if active_adapter is not None and var_broker.get() != active_adapter.name:
                var_broker.set(active_adapter.name)
            return
        chosen = var_broker.get()
        _sync_broker_acct_pills()
        if active_adapter is None or active_adapter.name != chosen:
            broker_reconfig_in_progress = True
            try:
                new_ad = connect_broker_adapter(
                    chosen, parent=pf, force_wizard=False
                )
            finally:
                broker_reconfig_in_progress = False
            if new_ad is not None:
                active_adapter = new_ad
                config["active_broker"] = chosen
                populate_account_dropdown()
                refresh_baseline_preview(force_restore=True)
            else:
                if active_adapter is not None:
                    var_broker.set(active_adapter.name)
                    _sync_broker_acct_pills()

    def edit_api_keys():
        global active_adapter, broker_reconfig_in_progress
        if is_in_trade_tamper_locked():
            return
        chosen = var_broker.get()
        broker_reconfig_in_progress = True
        try:
            new_ad = connect_broker_adapter(
                chosen, parent=pf, force_wizard=True
            )
        finally:
            broker_reconfig_in_progress = False
        if new_ad is not None:
            active_adapter = new_ad
            config["active_broker"] = chosen
            populate_account_dropdown()
            refresh_baseline_preview(force_restore=True)

    def open_hud_columns_dialog():
        dlg = tk.Toplevel(pf)
        dlg.withdraw()
        dlg.title("Customize HUD Columns & Order")
        dlg.config(bg="#0d1117", padx=22, pady=16)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.grab_set()

        tk.Label(
            dlg,
            text="📊 CUSTOMIZE HUD COLUMNS & DISPLAY ORDER",
            font=("Arial", 11, "bold"),
            fg="#5dade2",
            bg="#0d1117",
            anchor="w"
        ).pack(fill="x")
        tk.Label(
            dlg,
            text=(
                "Check the columns you want on your HUD and use ▲ / ▼ to arrange their left-to-right order.\n"
                "• Small HUD Mode: Selecting 3 (or fewer) columns shrinks the HUD and uses a compact hover-over status pill."
            ),
            font=("Arial", 9),
            fg="#94a3b8",
            bg="#0d1117",
            justify="left",
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

        list_outer = tk.Frame(
            dlg, bg="#131922", bd=0, highlightthickness=1, highlightbackground="#243040"
        )
        list_outer.pack(fill="both", expand=True)
        NeonBarCanvas(
            list_outer, core_color="#38bdf8", card_bg="#131922", glow_on=True
        ).pack(side="left", fill="y")
        list_frame = tk.Frame(list_outer, bg="#131922", padx=14, pady=10)
        list_frame.pack(side="left", fill="both", expand=True)

        def render_rows():
            for w in list_frame.winfo_children():
                w.destroy()
            for idx, cid in enumerate(ordered_ids):
                hdr, desc = desc_map[cid]
                row = tk.Frame(list_frame, bg="#131922", pady=3)
                row.pack(fill="x")

                make_glass_checkbutton(
                    row,
                    text=f"{idx + 1}. {hdr}",
                    variable=checked_vars[cid],
                    font=("Arial", 10, "bold"),
                    fg="#dce4ee",
                    bg="#131922",
                    width=180,
                    anchor="w"
                ).pack(side="left")

                tk.Label(
                    row,
                    text=desc,
                    font=("Arial", 9),
                    fg="#8b9bb0",
                    bg="#131922",
                    anchor="w",
                    width=42
                ).pack(side="left", padx=(8, 12))

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

                make_stadium_button(
                    row,
                    text="▼",
                    font=("Arial", 8, "bold"),
                    fill_color="#182434",
                    border_color="#475b73",
                    hover_fill="#22344a",
                    hover_border="#38bdf8",
                    fg="#e2e8f0",
                    canvas_bg="#131922",
                    width=36,
                    height=24,
                    auto_width=False,
                    glow_strength=0.35,
                    command=move_down,
                ).pack(side="right", padx=2)
                make_stadium_button(
                    row,
                    text="▲",
                    font=("Arial", 8, "bold"),
                    fill_color="#182434",
                    border_color="#475b73",
                    hover_fill="#22344a",
                    hover_border="#38bdf8",
                    fg="#e2e8f0",
                    canvas_bg="#131922",
                    width=36,
                    height=24,
                    auto_width=False,
                    glow_strength=0.35,
                    command=move_up,
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

        def apply_small_3():
            ordered_ids.clear()
            ordered_ids.extend(
                list(COMPACT_HUD_COLUMNS)
                + [c for c in all_ids if c not in COMPACT_HUD_COLUMNS]
            )
            for c in all_ids:
                checked_vars[c].set(c in COMPACT_HUD_COLUMNS)
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
            hud_cols_btn.config(text=format_hud_cols_btn_label(chosen))
            dlg.destroy()

        b_bar = tk.Frame(dlg, bg="#0d1117", pady=12)
        b_bar.pack(fill="x")
        btn_std_5 = make_stadium_button(
            b_bar,
            text="Standard 5-Col",
            font=("Arial", 9, "bold"),
            fill_color="#141820",
            fill_top_color="#1c212b",
            border_color="#2e3746",
            hover_fill="#181e28",
            hover_fill_top="#232a36",
            hover_border="#475569",
            fg="#94a3b8",
            canvas_bg="#0d1117",
            width=148,
            height=34,
            auto_width=False,
            command=reset_standard_5,
        )
        btn_std_5.pack(side="left", padx=(0, 8))
        btn_small_3 = make_stadium_button(
            b_bar,
            text="Small 3-Col (Compact)",
            font=("Arial", 9, "bold"),
            fill_color="#141820",
            fill_top_color="#1c212b",
            border_color="#2e3746",
            hover_fill="#181e28",
            hover_fill_top="#232a36",
            hover_border="#475569",
            fg="#94a3b8",
            canvas_bg="#0d1117",
            width=184,
            height=34,
            auto_width=False,
            command=apply_small_3,
        )
        btn_small_3.pack(side="left")

        def refresh_hud_preset_highlight(*_):
            curr_chosen = [c for c in ordered_ids if checked_vars[c].get()]
            is_small_active = (len(curr_chosen) == 3)
            is_std_active = (len(curr_chosen) == 5)
            if is_std_active:
                btn_std_5.config(
                    text="✓ Standard 5-Col",
                    fill_color="#0f213a",
                    fill_top_color="#163052",
                    border_color="#38bdf8",
                    hover_fill="#132a48",
                    hover_fill_top="#1c3b63",
                    hover_border="#7dd3fc",
                    fg="#ffffff",
                )
            else:
                btn_std_5.config(
                    text="Standard 5-Col",
                    fill_color="#141820",
                    fill_top_color="#1c212b",
                    border_color="#2e3746",
                    hover_fill="#181e28",
                    hover_fill_top="#232a36",
                    hover_border="#475569",
                    fg="#94a3b8",
                )
            if is_small_active:
                btn_small_3.config(
                    text="✓ Small 3-Col (Compact)",
                    fill_color="#0f213a",
                    fill_top_color="#163052",
                    border_color="#38bdf8",
                    hover_fill="#132a48",
                    hover_fill_top="#1c3b63",
                    hover_border="#7dd3fc",
                    fg="#ffffff",
                )
            else:
                btn_small_3.config(
                    text="Small 3-Col (Compact)",
                    fill_color="#141820",
                    fill_top_color="#1c212b",
                    border_color="#2e3746",
                    hover_fill="#181e28",
                    hover_fill_top="#232a36",
                    hover_border="#475569",
                    fg="#94a3b8",
                )

        for cv in checked_vars.values():
            cv.trace_add("write", refresh_hud_preset_highlight)
        refresh_hud_preset_highlight()

        make_stadium_button(
            b_bar,
            text="Done ✓",
            font=("Arial", 9, "bold"),
            fill_color="#0d3b20",
            fill_top_color="#14532d",
            border_color="#10b981",
            hover_fill="#114b29",
            hover_fill_top="#196638",
            hover_border="#34d399",
            fg="#ffffff",
            canvas_bg="#0d1117",
            width=126,
            height=34,
            pad_x=28,
            command=apply_and_close,
        ).pack(side="right")

        center_dialog_over_parent(dlg, parent=pf)
        pf.wait_window(dlg)

    hud_cols_btn = make_stadium_button(
        top_bar,
        text=format_hud_cols_btn_label(selected_hud_columns),
        font=("Arial", 9, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#475569",
        fg="#e2e8f0",
        canvas_bg="#11161f",
        width=142,
        height=32,
        auto_width=False,
        command=open_hud_columns_dialog,
    )
    hud_cols_btn.pack(side="left", padx=(0, 5))
    attach_tooltip(
        hud_cols_btn,
        "Choose which metrics appear on your live HUD bar (or switch between Standard 5-Col\n"
        "and Small 3-Col Compact HUD mode) and reorder them."
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

    def open_log_archive_folder(event=None):
        try:
            os.makedirs(LOG_ARCHIVE_DIR, exist_ok=True)
            os.startfile(LOG_ARCHIVE_DIR)
        except Exception as e:
            messagebox.showinfo(
                "Log Archive Folder",
                f"Your 90-day log archive folder is located at:\n{LOG_ARCHIVE_DIR}\n\n({e})",
                parent=pf
            )

    def open_sanitized_archive_folder(event=None):
        try:
            _sync_sanitized_log_archive()
            os.startfile(SANITIZED_ARCHIVE_DIR)
        except Exception as e:
            messagebox.showinfo(
                "Safe Log Archive Folder",
                f"Your 90-day balance-redacted log archive folder is located at:\n{SANITIZED_ARCHIVE_DIR}\n\n({e})",
                parent=pf
            )

    def _prepare_sanitized_log():
        """Generates ~/enforcer_log_sanitized.txt (and a convenience copy in
        ~/Downloads if present) and copies the sanitized text to the clipboard."""
        if not os.path.exists(LOG_PATH):
            init_daily_log()
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            raw_txt = f.read()
        sanitized_txt = sanitize_log_for_export(raw_txt)
        with open(SANITIZED_LOG_PATH, "w", encoding="utf-8") as sf:
            sf.write(sanitized_txt)
        try:
            dl_dir = os.path.join(USER_HOME, "Downloads")
            if os.path.isdir(dl_dir):
                dl_copy = os.path.join(dl_dir, "enforcer_log_sanitized.txt")
                with open(dl_copy, "w", encoding="utf-8") as df:
                    df.write(sanitized_txt)
        except Exception:
            pass
        try:
            pf.clipboard_clear()
            pf.clipboard_append(sanitized_txt)
            pf.update()
        except Exception:
            pass
        return SANITIZED_LOG_PATH

    def export_sanitized_log_action():
        try:
            out_path = _prepare_sanitized_log()
            if default_status_lbl is not None:
                default_status_lbl.config(
                    text=(
                        "✓ Safe log copied to clipboard & saved to "
                        f"{_mask_user_path(out_path)} (Account balances redacted)."
                    ),
                    fg="#58d68d",
                )
            try:
                os.startfile(out_path)
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror(
                "Export Sanitized Log Error",
                f"Could not export sanitized log:\n{e}",
                parent=pf,
            )

    def report_bug_action():
        try:
            out_path = _prepare_sanitized_log()
            if default_status_lbl is not None:
                default_status_lbl.config(
                    text=(
                        "✓ Safe log copied to clipboard & highlighted in Explorer "
                        "— Opening Bug Report form..."
                    ),
                    fg="#f5cba7",
                )
            try:
                subprocess.Popen(
                    ["explorer", f"/select,{os.path.normpath(out_path)}"]
                )
            except Exception:
                pass
            webbrowser.open(BUG_REPORT_FORM_URL)
        except Exception as e:
            messagebox.showerror(
                "Bug Report Error",
                f"Could not prepare sanitized log for bug report:\n{e}",
                parent=pf,
            )

    def preview_most_recent_safe_log():
        try:
            _sync_sanitized_log_archive()
            _, prior_path = _find_most_recent_prior_sanitized_log()
            target_path = prior_path if prior_path else _prepare_sanitized_log()
            os.startfile(target_path)
        except Exception as e:
            messagebox.showerror(
                "Preview Safe Log Error",
                f"Could not open sanitized log preview:\n{e}",
                parent=pf,
            )

    def show_telemetry_upload_result_dialog(ok, tester_id):
        try:
            if not pf.winfo_exists():
                return
        except Exception:
            return
        dlg = tk.Toplevel(pf)
        dlg.withdraw()
        dlg.grab_set()
        if os.path.exists(ICON_PATH):
            try:
                dlg.iconbitmap(ICON_PATH)
            except Exception:
                pass
        apply_dark_title_bar(dlg)
        dlg.title(
            "PnL Enforcer — Safe Log Uploaded"
            if ok
            else "PnL Enforcer — Safe Log Upload Failed"
        )
        dlg.config(bg="#0d1117", padx=24, pady=18)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)

        bar_col = "#10b981" if ok else "#f59e0b"
        rim_col = "#1f4d3a" if ok else "#5c3d1e"
        hdr_txt = (
            "✅ Safe Log Sent!"
            if ok
            else "⚠️ Upload Failed"
        )
        body_txt = (
            f"✅ Safe Log Sent! Your balance-redacted session log "
            f"(Tester ID: {tester_id}) was uploaded directly to the beta diagnostic drive."
            if ok
            else "⚠️ Upload Failed: Could not reach the telemetry endpoint. "
            "You can still use Export Safe Log or Report Bug."
        )

        tk.Label(
            dlg,
            text=hdr_txt,
            font=("Arial", 12, "bold"),
            fg="#69f0ae" if ok else "#fbbf24",
            bg="#0d1117",
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        card_outer = tk.Frame(
            dlg,
            bg="#131922",
            bd=0,
            highlightthickness=1,
            highlightbackground=rim_col,
        )
        card_outer.pack(fill="x", pady=(0, 14))
        NeonBarCanvas(
            card_outer, core_color=bar_col, card_bg="#131922", glow_on=True
        ).pack(side="left", fill="y")
        tk.Label(
            card_outer,
            text=body_txt,
            font=("Arial", 10),
            fg="#e2e8f0",
            bg="#131922",
            justify="left",
            anchor="w",
            wraplength=480,
            padx=18,
            pady=14,
        ).pack(side="left", fill="both", expand=True)

        btn_row = tk.Frame(dlg, bg="#0d1117")
        btn_row.pack(fill="x")
        make_stadium_button(
            btn_row,
            text="OK",
            font=("Arial", 10, "bold"),
            fill_color="#0d3b20" if ok else "#141820",
            fill_top_color="#14532d" if ok else "#1c212b",
            border_color="#10b981" if ok else "#475569",
            hover_fill="#114b29" if ok else "#181e28",
            hover_fill_top="#196638" if ok else "#232a36",
            hover_border="#34d399" if ok else "#64748b",
            fg="#ffffff",
            canvas_bg="#0d1117",
            width=110,
            height=34,
            auto_width=False,
            command=dlg.destroy,
        ).pack(side="right")

        center_dialog_over_parent(dlg, parent=pf)

    def send_today_safe_log_now():
        try:
            if not os.path.exists(LOG_PATH):
                init_daily_log()
            with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                raw_txt = f.read()
            sanitized_txt = sanitize_log_for_export(raw_txt)
            tester_id = str(config.get("anonymous_tester_id", "") or "").strip()
            if not tester_id:
                tester_id = uuid.uuid4().hex[:6]
                config["anonymous_tester_id"] = tester_id
                save_config(config)
            active_b = str(
                var_broker.get() or config.get("active_broker", "SCHWAB")
            )
            upload_fname = f"enforcer_log_{get_today_str()}_manual_sanitized.txt"

            if default_status_lbl is not None:
                default_status_lbl.config(
                    text=(
                        f"⏳ Uploading today's Safe Log (Tester ID: {tester_id}) "
                        "to beta diagnostic drive..."
                    ),
                    fg="#38bdf8",
                )

            def _worker():
                ok = _upload_sanitized_log_to_drive(
                    upload_fname, sanitized_txt, active_b, tester_id
                )

                def _finish():
                    if ok:
                        log_event(
                            "TELEMETRY",
                            f"Manually uploaded today's sanitized log "
                            f"({upload_fname}, Tester ID: {tester_id})",
                        )
                        if default_status_lbl is not None:
                            default_status_lbl.config(
                                text=(
                                    f"✓ Safe Log Sent! Uploaded {upload_fname} "
                                    f"(Tester ID: {tester_id})."
                                ),
                                fg="#58d68d",
                            )
                    else:
                        if default_status_lbl is not None:
                            default_status_lbl.config(
                                text="⚠️ Safe Log upload failed (telemetry endpoint unreachable).",
                                fg="#f5b041",
                            )
                    show_telemetry_upload_result_dialog(ok, tester_id)

                try:
                    pf.after(0, _finish)
                except Exception:
                    pass

            threading.Thread(target=_worker, daemon=True).start()
        except Exception as e:
            messagebox.showerror(
                "Safe Log Upload Error",
                f"Could not prepare today's sanitized log for upload:\n{e}",
                parent=pf,
            )

    def show_auto_share_consent_dialog():
        tester_id = str(config.get("anonymous_tester_id", "") or "").strip()
        if not tester_id:
            tester_id = uuid.uuid4().hex[:6]
            config["anonymous_tester_id"] = tester_id
            save_config(config)

        decision = {"ok": False}
        active_parent = _prefs_modal_refs.get("dlg")
        try:
            if active_parent is None or not active_parent.winfo_exists():
                active_parent = pf
        except Exception:
            active_parent = pf
        dlg = tk.Toplevel(active_parent)
        dlg.withdraw()
        if os.path.exists(ICON_PATH):
            try:
                dlg.iconbitmap(ICON_PATH)
            except Exception:
                pass
        apply_dark_title_bar(dlg)
        dlg.title("PnL Enforcer — Auto-Share Daily Safe Logs (Beta Opt-In)")
        dlg.config(bg="#0d1117", padx=26, pady=20)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.transient(active_parent)

        def on_cancel():
            decision["ok"] = False
            dlg.destroy()

        def on_enable():
            decision["ok"] = True
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", on_cancel)
        dlg.bind("<Escape>", lambda _e: on_cancel())

        tk.Label(
            dlg,
            text="▶  📤 AUTO-SHARE DAILY SAFE LOGS (BETA OPT-IN)",
            font=("Arial", 12, "bold"),
            fg="#38bdf8",
            bg="#0d1117",
            anchor="w",
        ).pack(fill="x", pady=(0, 12))

        card_outer = tk.Frame(
            dlg,
            bg="#131922",
            bd=0,
            highlightthickness=1,
            highlightbackground="#243040",
        )
        card_outer.pack(fill="x", pady=(0, 16))
        NeonBarCanvas(
            card_outer, core_color="#38bdf8", card_bg="#131922", glow_on=True
        ).pack(side="left", fill="y")

        msg_txt = (
            "When enabled, PnL Enforcer will automatically upload yesterday's "
            "balance-redacted log (enforcer_log_YYYY-MM-DD_sanitized.txt) in the "
            "background when you launch the app. All account balances ($[REDACTED]), "
            "Windows usernames (~), and order IDs are scrubbed, and your log is "
            f"tagged only with an anonymous 6-character Tester ID ({tester_id}). "
            "You can turn this off anytime."
        )
        tk.Label(
            card_outer,
            text=msg_txt,
            font=("Arial", 10),
            fg="#e2e8f0",
            bg="#131922",
            justify="left",
            anchor="w",
            wraplength=560,
            padx=20,
            pady=16,
        ).pack(side="left", fill="both", expand=True)

        btn_row = tk.Frame(dlg, bg="#0d1117")
        btn_row.pack(fill="x")

        make_stadium_button(
            btn_row,
            text="Preview Safe Log",
            font=("Arial", 9, "bold"),
            fill_color="#141820",
            fill_top_color="#1c212b",
            border_color="#2e3746",
            hover_fill="#181e28",
            hover_fill_top="#232a36",
            hover_border="#38bdf8",
            fg="#7dd3fc",
            canvas_bg="#0d1117",
            width=154,
            height=34,
            auto_width=False,
            command=preview_most_recent_safe_log,
        ).pack(side="left")

        make_stadium_button(
            btn_row,
            text="Enable Auto-Share",
            font=("Arial", 10, "bold"),
            fill_color="#0d3b20",
            fill_top_color="#14532d",
            border_color="#10b981",
            hover_fill="#114b29",
            hover_fill_top="#196638",
            hover_border="#34d399",
            fg="#ffffff",
            canvas_bg="#0d1117",
            width=174,
            height=34,
            auto_width=False,
            command=on_enable,
        ).pack(side="right")

        make_stadium_button(
            btn_row,
            text="Cancel",
            font=("Arial", 10, "bold"),
            fill_color="#3b1520",
            border_color="#f43f5e",
            hover_fill="#4f1c2b",
            hover_border="#fb7185",
            fg="#ffe4e6",
            canvas_bg="#0d1117",
            width=108,
            height=34,
            auto_width=False,
            command=on_cancel,
        ).pack(side="right", padx=(0, 8))

        dlg.update_idletasks()
        center_dialog_over_parent(dlg, parent=active_parent)
        dlg.grab_set()
        dlg.focus_set()
        active_parent.wait_window(dlg)
        if active_parent is not pf:
            try:
                if active_parent.winfo_exists():
                    active_parent.lift()
                    active_parent.grab_set()
                    active_parent.focus_force()
            except Exception:
                pass
        return decision["ok"]

    logs_dropdown = DarkDropdownMenu(
        pf,
        tearoff=0,
        font=("Arial", 9, "bold"),
        bg="#141820",
        fg="#e2e8f0",
        activebackground="#1e293b",
        activeforeground="#ffffff"
    )

    def _toggle_auto_share_from_menu():
        var_auto_share_logs.set(not bool(var_auto_share_logs.get()))

    def rebuild_logs_dropdown():
        logs_dropdown.delete(0, "end")
        logs_dropdown.add_command(
            label="📤 Send Today's Safe Log Now",
            command=send_today_safe_log_now,
        )
        chk_mark = "☑" if var_auto_share_logs.get() else "☐"
        logs_dropdown.add_command(
            label=f"{chk_mark} Auto-Share Daily Safe Logs (Beta Opt-In)",
            command=_toggle_auto_share_from_menu,
        )
        logs_dropdown.add_separator()
        logs_dropdown.add_command(
            label="📄 View Today's Log",
            command=open_log_file,
        )
        logs_dropdown.add_command(
            label="🔒 Export Today's Safe Log (Balances Redacted)",
            command=export_sanitized_log_action,
        )
        logs_dropdown.add_separator()
        logs_dropdown.add_command(
            label=f"🔒 Open Safe Archived Logs ({LOG_RETENTION_DAYS}-Day Redacted)",
            command=open_sanitized_archive_folder,
        )
        logs_dropdown.add_command(
            label=f"📁 Open Raw Archived Logs ({LOG_RETENTION_DAYS}-Day Full)",
            command=open_log_archive_folder,
        )

    def _on_toggle_auto_share_logs(*_):
        if _auto_share_guard["suppress"]:
            return
        if var_auto_share_logs.get():
            if not show_auto_share_consent_dialog():
                _auto_share_guard["suppress"] = True
                try:
                    var_auto_share_logs.set(False)
                finally:
                    _auto_share_guard["suppress"] = False
                rebuild_logs_dropdown()
                return
            config["auto_share_sanitized_logs"] = True
            save_config(config)
            tester_id = config.get("anonymous_tester_id", "")
            log_event(
                "TELEMETRY",
                f"User enabled Auto-Share Daily Safe Logs (Tester ID: {tester_id}).",
            )
            rebuild_logs_dropdown()
            _maybe_upload_prior_day_sanitized_log()
        else:
            config["auto_share_sanitized_logs"] = False
            save_config(config)
            log_event(
                "TELEMETRY",
                "User disabled Auto-Share Daily Safe Logs in Pre-Flight.",
            )
            rebuild_logs_dropdown()

    var_auto_share_logs.trace_add("write", _on_toggle_auto_share_logs)
    rebuild_logs_dropdown()

    btn_logs_menu = make_stadium_button(
        top_bar,
        text="📜 Logs ▾",
        font=("Arial", 9, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#475569",
        fg="#e2e8f0",
        canvas_bg="#11161f",
        width=88,
        height=32,
        pad_x=22,
        menu=logs_dropdown,
    )
    btn_logs_menu.pack(side="left", padx=(0, 5))
    attach_tooltip(
        btn_logs_menu,
        "Session & Audit Logs Menu:\n"
        "• Send Today's Safe Log Now: Uploads today's balance-redacted log directly to the beta diagnostic drive\n"
        "• Auto-Share Daily Safe Logs (Beta Opt-In): Automatically uploads yesterday's redacted log on startup\n"
        f"• View Today's Log: Opens your local audit log in Notepad ({_mask_user_path(LOG_PATH)})\n"
        "• Export Today's Safe Log: Creates a privacy-scrubbed copy with total account balances redacted ($[REDACTED]) and copies it to clipboard\n"
        f"• Open Safe Archived Logs: Opens your {LOG_RETENTION_DAYS}-day redacted log archive ({_mask_user_path(SANITIZED_ARCHIVE_DIR)})\n"
        f"• Open Raw Archived Logs: Opens your {LOG_RETENTION_DAYS}-day full local log archive ({_mask_user_path(LOG_ARCHIVE_DIR)})"
    )

    btn_report_bug = make_stadium_button(
        top_bar,
        text="🐞 Report Bug",
        font=("Arial", 9, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#5c2836",
        hover_fill="#1f161c",
        hover_fill_top="#2a1d25",
        hover_border="#9f3a56",
        fg="#f4d6de",
        canvas_bg="#11161f",
        width=108,
        height=32,
        pad_x=22,
        command=report_bug_action,
    )
    btn_report_bug.pack(side="left", padx=(0, 6))
    attach_tooltip(
        btn_report_bug,
        "One-Click Bug Report & Safe Log Prep:\n"
        "Automatically prepares your sanitized log and opens the Bug Report portal in your browser.\n"
        "• Copies your privacy-scrubbed log straight to your clipboard (ready to Ctrl+V)\n"
        "• Saves enforcer_log_sanitized.txt (in ~ and ~/Downloads) and highlights it in Windows Explorer so you can drag-and-drop it straight into the form\n"
        "• Redacts all total account balances ($[REDACTED]), Windows usernames (~), and order IDs (...1234)."
    )

    populate_account_dropdown()
    var_broker.trace_add("write", on_broker_change)

    def _get_preset_target_dicts():
        base_src = config.get("user_defaults") or DEFAULT_CONFIG
        full_d = {}
        half_d = {}
        for k in dollar_keys:
            fv = float(base_src.get(k, DEFAULT_CONFIG[k]))
            full_d[k] = round(fv) if k in SIGNED_DOLLAR_KEYS else round(abs(fv))
            if k in SIGNED_DOLLAR_KEYS:
                half_d[k] = round(fv * 0.5)
            else:
                half_d[k] = round(abs(fv) * 0.5) if fv != 0 else 0.0
        return full_d, half_d

    def refresh_preset_buttons_highlight(*_):
        try:
            full_d, half_d = _get_preset_target_dicts()
            curr_d = {}
            for k in dollar_keys:
                raw_v = float(dollar_vars[k].get().strip())
                curr_d[k] = (
                    round(raw_v)
                    if k in SIGNED_DOLLAR_KEYS
                    else round(abs(raw_v))
                )
            tamper_lk = is_tilt_streak_tamper_locked()
            cmp_keys = [
                k
                for k in dollar_keys
                if not (
                    tamper_lk
                    and k
                    in ("consec_loss_min_dollars", "consec_win_reset_dollars")
                )
            ]
            is_full = all(abs(curr_d[k] - full_d[k]) < 0.5 for k in cmp_keys)
            is_half = (
                not is_full
                and all(abs(curr_d[k] - half_d[k]) < 0.5 for k in cmp_keys)
            )
        except Exception:
            is_full = False
            is_half = False

        if is_full:
            btn_full_risk.config(
                text="✓ Standard Full Risk",
                fill_color="#0f213a",
                fill_top_color="#163052",
                border_color="#38bdf8",
                hover_fill="#132a48",
                hover_fill_top="#1c3b63",
                hover_border="#7dd3fc",
                fg="#ffffff",
            )
            btn_half_risk.config(
                text="50% Low Energy",
                fill_color="#141820",
                fill_top_color="#1c212b",
                border_color="#2e3746",
                hover_fill="#181e28",
                hover_fill_top="#232a36",
                hover_border="#475569",
                fg="#94a3b8",
            )
        elif is_half:
            btn_full_risk.config(
                text="Standard Full Risk",
                fill_color="#141820",
                fill_top_color="#1c212b",
                border_color="#2e3746",
                hover_fill="#181e28",
                hover_fill_top="#232a36",
                hover_border="#475569",
                fg="#94a3b8",
            )
            btn_half_risk.config(
                text="✓ 50% Low Energy",
                fill_color="#0d2e22",
                fill_top_color="#144332",
                border_color="#10b981",
                hover_fill="#113b2c",
                hover_fill_top="#19543f",
                hover_border="#34d399",
                fg="#ffffff",
            )
        else:
            btn_full_risk.config(
                text="Standard Full Risk",
                fill_color="#141820",
                fill_top_color="#1c212b",
                border_color="#2e3746",
                hover_fill="#181e28",
                hover_fill_top="#232a36",
                hover_border="#475569",
                fg="#94a3b8",
            )
            btn_half_risk.config(
                text="50% Low Energy",
                fill_color="#141820",
                fill_top_color="#1c212b",
                border_color="#2e3746",
                hover_fill="#181e28",
                hover_fill_top="#232a36",
                hover_border="#475569",
                fg="#94a3b8",
            )

    def apply_dollar_preset(preset_dict):
        if is_in_trade_tamper_locked():
            return
        tamper_lk = is_tilt_streak_tamper_locked()
        for k, val in preset_dict.items():
            if k in dollar_vars:
                if tamper_lk and k in (
                    "consec_loss_min_dollars",
                    "consec_win_reset_dollars",
                ):
                    continue
                dollar_vars[k].set(_fmt_ui_dollar(k, val))
        refresh_preset_buttons_highlight()

    def apply_half_risk_preset():
        if is_in_trade_tamper_locked():
            return
        _, half_dict = _get_preset_target_dicts()
        apply_dollar_preset(half_dict)
        if default_status_lbl is not None:
            src_name = "your saved Default" if config.get("user_defaults") else "Factory Default"
            lk_note = (
                " (🔒 Active Loss Streak settings stayed locked)"
                if is_tilt_streak_tamper_locked()
                else ""
            )
            default_status_lbl.config(
                text=f"⚡ Applied 50% Low Energy preset (50% of {src_name}){lk_note}.",
                fg="#f5b041"
            )

    def apply_standard_full_preset():
        if is_in_trade_tamper_locked():
            return
        base_src = config.get("user_defaults") or DEFAULT_CONFIG
        apply_dollar_preset(base_src)
        if default_status_lbl is not None:
            src_name = "your saved Default" if config.get("user_defaults") else "Factory Default"
            lk_note = (
                " (🔒 Active Loss Streak settings stayed locked)"
                if is_tilt_streak_tamper_locked()
                else ""
            )
            default_status_lbl.config(
                text=f"✓ Applied Standard Full Risk preset (100% of {src_name}){lk_note}.",
                fg="#5dade2"
            )

    btn_half_risk = make_stadium_button(
        top_bar,
        text="50% Low Energy",
        font=("Arial", 9, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#475569",
        fg="#94a3b8",
        canvas_bg="#11161f",
        width=122,
        height=32,
        pad_x=22,
        command=apply_half_risk_preset,
    )
    btn_half_risk.pack(side="right", padx=(3, 0))
    attach_tooltip(
        btn_half_risk,
        "Cuts all dollar risk thresholds, warning alarms, and tier triggers in half (50%)\n"
        "relative to your saved Default settings (or Factory Defaults if none saved yet).\n"
        "Ideal for choppy markets, B-setup days, or low-energy sessions."
    )

    btn_full_risk = make_stadium_button(
        top_bar,
        text="Standard Full Risk",
        font=("Arial", 9, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#475569",
        fg="#94a3b8",
        canvas_bg="#11161f",
        width=142,
        height=32,
        pad_x=22,
        command=apply_standard_full_preset,
    )
    btn_full_risk.pack(side="right", padx=3)
    attach_tooltip(
        btn_full_risk,
        "Restores 100% of your saved Default dollar thresholds\n"
        "(or Factory Default dollar thresholds if you haven't clicked 'Save as Default' yet)."
    )

    for dv in dollar_vars.values():
        dv.trace_add("write", refresh_preset_buttons_highlight)
    refresh_preset_buttons_highlight()

    tk.Label(
        top_bar,
        text="PRESETS:",
        font=("Arial", 9, "bold"),
        fg="#94a3b8",
        bg="#11161f"
    ).pack(side="right", padx=(4, 3))

    default_status_lbl = None
    btn_restore_def = None
    btn_save_def = None
    btn_alarms_only = None
    btn_launch = None

    def restore_factory_defaults():
        if is_in_trade_tamper_locked():
            return
        src = config.get("user_defaults") or DEFAULT_CONFIG
        tamper_lk = is_tilt_streak_tamper_locked()
        var_open_flat.set(
            src.get("enable_open_flatten", DEFAULT_CONFIG["enable_open_flatten"])
        )
        if not tamper_lk:
            _tilt_cd_popup_guard["suppress"] = True
            try:
                var_tilt_cd.set(
                    src.get(
                        "enable_consec_loss_cooldown",
                        DEFAULT_CONFIG["enable_consec_loss_cooldown"],
                    )
                )
            finally:
                _tilt_cd_popup_guard["suppress"] = False
            var_tilt_count.set(
                str(
                    max(
                        2,
                        int(
                            round(
                                float(
                                    src.get(
                                        "consec_loss_count",
                                        DEFAULT_CONFIG["consec_loss_count"],
                                    )
                                )
                            )
                        ),
                    )
                )
            )
            var_tilt_window.set(
                f"{src.get('consec_loss_window_mins', DEFAULT_CONFIG['consec_loss_window_mins']):g}"
            )
        if not (tamper_lk and config.get("enable_open_cooldown", False)):
            var_open_cd.set(
                src.get("enable_open_cooldown", DEFAULT_CONFIG["enable_open_cooldown"])
            )
            var_cd_mins.set(
                f"{src.get('open_cooldown_mins', DEFAULT_CONFIG['open_cooldown_mins']):g}"
            )
        if not tamper_lk:
            var_alarms_only.set(
                src.get("alarms_only_mode", DEFAULT_CONFIG["alarms_only_mode"])
            )
        var_flatten.set(
            src.get("enable_auto_flatten", DEFAULT_CONFIG["enable_auto_flatten"])
        )
        _opt_waiver_guard["suppress"] = True
        try:
            var_flatten_options.set(
                bool(
                    src.get(
                        "enable_flatten_options",
                        DEFAULT_CONFIG["enable_flatten_options"],
                    )
                    and is_options_waiver_verified(config)
                )
            )
        finally:
            _opt_waiver_guard["suppress"] = False
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
        var_ignore_preexisting.set(
            bool(
                src.get(
                    "ignore_preexisting_positions",
                    DEFAULT_CONFIG["ignore_preexisting_positions"],
                )
            )
        )
        _auto_share_guard["suppress"] = True
        try:
            restored_auto_share = bool(
                src.get(
                    "auto_share_sanitized_logs",
                    DEFAULT_CONFIG["auto_share_sanitized_logs"],
                )
                and config.get("auto_share_sanitized_logs", False)
            )
            var_auto_share_logs.set(restored_auto_share)
            config["auto_share_sanitized_logs"] = restored_auto_share
        finally:
            _auto_share_guard["suppress"] = False
        rebuild_logs_dropdown()
        var_voice_cues.set(
            src.get("enable_voice_cues", DEFAULT_CONFIG["enable_voice_cues"])
        )
        restored_vid = src.get("tts_voice", DEFAULT_CONFIG["tts_voice"])
        var_tts_voice.set(TTS_ID_TO_LABEL.get(restored_vid, "Zira (Female)"))
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
            text=format_hud_cols_btn_label(selected_hud_columns)
        )
        var_reanchor.set(False)
        var_poll.set(
            str(int(src.get("poll_interval", DEFAULT_CONFIG["poll_interval"])))
        )
        apply_dollar_preset(src)
        refresh_smart_dimming()
        if default_status_lbl is not None:
            lk_note = (
                " (🔒 Active Loss Streak settings stayed locked)"
                if tamper_lk
                else ""
            )
            msg = (
                f"↺ Restored your saved defaults{lk_note}."
                if config.get("user_defaults")
                else f"↺ Restored factory defaults{lk_note}."
            )
            default_status_lbl.config(text=msg, fg="#5dade2")

    def save_as_user_defaults():
        if is_in_trade_tamper_locked():
            return
        try:
            custom_def = {
                "alarms_only_mode": bool(var_alarms_only.get()),
                "enable_open_flatten": bool(var_open_flat.get()),
                "enable_consec_loss_cooldown": bool(var_tilt_cd.get()),
                "consec_loss_count": max(2, int(round(abs(float(var_tilt_count.get()))))),
                "consec_loss_window_mins": max(0.5, abs(float(var_tilt_window.get()))),
                "enable_open_cooldown": bool(var_open_cd.get()),
                "open_cooldown_mins": max(0.1, abs(float(var_cd_mins.get()))),
                "enable_auto_flatten": bool(var_flatten.get()),
                "enable_flatten_options": bool(var_flatten_options.get()),
                "enable_kill_tos": bool(var_kill_tos.get()),
                "enable_kill_webull": bool(var_kill_wb.get()),
                "enable_lock_os": bool(var_lock_os.get()),
                "daily_lock_mins": max(0.0, abs(float(var_daily_lock_mins.get()))),
                "reset_at_925": bool(var_reset925.get()),
                "ignore_preexisting_positions": bool(var_ignore_preexisting.get()),
                "auto_share_sanitized_logs": bool(var_auto_share_logs.get()),
                "enable_voice_cues": bool(var_voice_cues.get()),
                "tts_voice": TTS_LABEL_TO_ID.get(var_tts_voice.get(), "Zira"),
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
                raw_v = float(dollar_vars[k].get())
                custom_def[k] = (
                    raw_v if k in SIGNED_DOLLAR_KEYS else abs(raw_v)
                )
                dollar_vars[k].set(_fmt_ui_dollar(k, custom_def[k]))

            config["user_defaults"] = custom_def
            config["signed_tier_stops"] = True
            save_config(config)
            refresh_preset_buttons_highlight()
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
        global active_preflight_close_fn

        if dry_run_lock_active or cooldown_active:
            log_event(
                "GUARDRAIL",
                "BLOCKED: Attempted to save/close Pre-Flight during an active lockout!",
            )
            return

        if active_adapter is None:
            messagebox.showerror(
                "Broker Not Connected",
                "Please connect a valid Schwab or Webull account first.",
                parent=pf
            )
            return

        if is_in_trade_tamper_locked():
            try:
                new_poll = max(1, int(float(var_poll.get())))
            except ValueError:
                messagebox.showerror(
                    "Invalid Input",
                    "Please enter a valid number for API Poll Interval (s).",
                    parent=pf,
                )
                return
            new_cfg = json.loads(json.dumps(config))
            new_cfg["hud_columns"] = list(selected_hud_columns)
            new_cfg["poll_interval"] = new_poll
            new_cfg["enable_voice_cues"] = bool(var_voice_cues.get())
            new_cfg["tts_voice"] = TTS_LABEL_TO_ID.get(
                var_tts_voice.get(), "Zira"
            )
            new_cfg["enable_upside_chime"] = bool(var_upside_chime.get())
            new_cfg["auto_share_sanitized_logs"] = bool(
                var_auto_share_logs.get()
            )
            save_config(new_cfg)
            log_event(
                "CONFIG",
                "Saved HUD/Audio/System settings while in an active daytrade "
                "(Enforcement & Rulebook Cards 1, 2, 4, 5 stayed locked).",
            )
            rebuild_hud_columns()
            if mute_btn is not None:
                if alarm_active and not cooldown_active:
                    mute_btn.config(
                        text=format_alarm_button_text(
                            last_alarm_reason or "Active Alarm"
                        )
                    )
                elif not cooldown_active:
                    mute_btn.config(text=get_idle_button_text())
            launched["status"] = True
            _remember_pf_pos()
            active_preflight_close_fn = None
            active_preflight_win = None
            settings_win_open = False
            _cancel_pf_timers()
            pf.destroy()
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

            if (chosen_b, active_adapter.account_id) != (
                _preexisting_state.get("broker"),
                _preexisting_state.get("acct_id"),
            ):
                refresh_baseline_preview()
            had_saved = bool(_preexisting_state.get("had_saved", False))
            if not had_saved:
                force_reanchor = True

            if var_flatten_options.get() and not is_options_waiver_verified(config):
                if not show_options_flatten_beta_waiver(
                    parent=pf, force_prompt=True
                ):
                    _opt_waiver_guard["suppress"] = True
                    try:
                        var_flatten_options.set(False)
                    finally:
                        _opt_waiver_guard["suppress"] = False
                    refresh_smart_dimming()
                    return

            if var_ignore_preexisting.get():
                raw_pos_now = (
                    active_adapter.get_last_raw_pos_details()
                    if active_adapter is not None
                    else {}
                )
                needs_prepos_prompt = False
                if raw_pos_now:
                    init_ig_tags = _preexisting_state.get(
                        "initial_ignored_tags", set()
                    )
                    has_new_today = any(
                        t not in init_ig_tags for t in raw_pos_now.keys()
                    )
                    if (
                        var_reanchor.get()
                        and not is_tilt_streak_tamper_locked()
                        and not _preexisting_state["reanchor_reviewed"]
                    ):
                        needs_prepos_prompt = True
                    elif not had_saved and not _preexisting_state["reviewed"]:
                        needs_prepos_prompt = True
                    elif (
                        had_saved
                        and has_new_today
                        and not _preexisting_state["reviewed"]
                    ):
                        needs_prepos_prompt = True
                if needs_prepos_prompt:
                    if not show_preexisting_positions_dialog(from_launch=True):
                        return
            else:
                _apply_preexisting_selection(set(), mark_reviewed=True)

            new_cfg["alarms_only_mode"] = bool(var_alarms_only.get())
            new_cfg["enable_open_flatten"] = bool(var_open_flat.get())
            if is_tilt_streak_tamper_locked():
                new_cfg["enable_consec_loss_cooldown"] = True
                new_cfg["consec_loss_count"] = max(
                    2, int(round(float(config.get("consec_loss_count", 3))))
                )
                new_cfg["consec_loss_window_mins"] = max(
                    0.5, float(config.get("consec_loss_window_mins", 15.0))
                )
                if config.get("enable_open_cooldown", False):
                    new_cfg["enable_open_cooldown"] = True
                    new_cfg["open_cooldown_mins"] = max(
                        0.1, float(config.get("open_cooldown_mins", 1.0))
                    )
                else:
                    new_cfg["enable_open_cooldown"] = bool(var_open_cd.get())
                    new_cfg["open_cooldown_mins"] = max(
                        0.1, abs(float(var_cd_mins.get()))
                    )
                if not config.get("alarms_only_mode", False):
                    new_cfg["alarms_only_mode"] = False
            else:
                new_cfg["enable_consec_loss_cooldown"] = bool(var_tilt_cd.get())
                new_cfg["consec_loss_count"] = max(
                    2, int(round(abs(float(var_tilt_count.get()))))
                )
                new_cfg["consec_loss_window_mins"] = max(
                    0.5, abs(float(var_tilt_window.get()))
                )
                new_cfg["enable_open_cooldown"] = bool(var_open_cd.get())
                new_cfg["open_cooldown_mins"] = max(
                    0.1, abs(float(var_cd_mins.get()))
                )
            new_cfg["enable_auto_flatten"] = bool(var_flatten.get())
            new_cfg["enable_flatten_options"] = bool(var_flatten_options.get())
            for _ow_k in (
                "options_waiver_accepted",
                "options_waiver_version",
                "options_waiver_accepted_at",
                "options_waiver_sha256",
            ):
                new_cfg[_ow_k] = config.get(_ow_k, DEFAULT_CONFIG[_ow_k])
            new_cfg["enable_kill_tos"] = bool(var_kill_tos.get())
            new_cfg["enable_kill_webull"] = bool(var_kill_wb.get())
            new_cfg["enable_lock_os"] = bool(var_lock_os.get())
            new_cfg["daily_lock_mins"] = max(
                0.0, abs(float(var_daily_lock_mins.get()))
            )
            new_cfg["reset_at_925"] = bool(var_reset925.get())
            new_cfg["ignore_preexisting_positions"] = bool(
                var_ignore_preexisting.get()
            )
            new_cfg["auto_share_sanitized_logs"] = bool(
                var_auto_share_logs.get()
            )
            new_cfg["last_uploaded_sanitized_log"] = config.get(
                "last_uploaded_sanitized_log", ""
            )
            new_cfg["anonymous_tester_id"] = config.get(
                "anonymous_tester_id", ""
            )
            new_cfg["enable_voice_cues"] = bool(var_voice_cues.get())
            new_cfg["tts_voice"] = TTS_LABEL_TO_ID.get(
                var_tts_voice.get(), "Zira"
            )
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
                raw_v = float(dollar_vars[k].get())
                new_cfg[k] = (
                    raw_v if k in SIGNED_DOLLAR_KEYS else abs(raw_v)
                )
            if is_tilt_streak_tamper_locked():
                new_cfg["consec_loss_min_dollars"] = abs(
                    float(config.get("consec_loss_min_dollars", 25.0))
                )
                new_cfg["consec_win_reset_dollars"] = abs(
                    float(config.get("consec_win_reset_dollars", 10.0))
                )
            new_cfg["signed_tier_stops"] = True

            first_poll_of_launch = True

            if var_reanchor.get() and not is_tilt_streak_tamper_locked():
                force_reanchor = True
                is_locked_down = False
                daily_breach_settings_prompted = False
                recent_loss_timestamps.clear()
                triggered_alarms.clear()
                if active_adapter is not None:
                    reanchor_ignored_positions_to_live(
                        active_adapter.get_last_raw_pos_details()
                    )
                s_key = get_session_key(chosen_b, active_adapter.account_id)
                if s_key and s_key in new_cfg.get("account_sessions", {}):
                    del new_cfg["account_sessions"][s_key]
                new_cfg["saved_start_equity"] = None
                new_cfg["saved_daily_max_equity"] = None
                log_event("CONFIG", "User checked Force Re-Anchor Baseline.")
            else:
                s_key = get_session_key(chosen_b, active_adapter.account_id)
                if (
                    s_key
                    and isinstance(new_cfg.get("account_sessions"), dict)
                    and s_key in new_cfg["account_sessions"]
                ):
                    s_entry = new_cfg["account_sessions"][s_key]
                    s_entry["start_equity"] = start_equity
                    s_entry["max_equity"] = max_equity
                    s_entry["daily_max_equity"] = daily_max_equity
                    s_entry["last_flat_equity"] = last_flat_equity
                    s_entry["anchor_cash_flow"] = round(
                        float(anchor_cash_flow or 0.0), 2
                    )
                    s_entry["win_trades"] = win_trades
                    s_entry["loss_trades"] = loss_trades
                    s_entry["loss_timestamps"] = [
                        round(float(t), 2) for t in recent_loss_timestamps
                    ]
                    s_entry["ignored_positions"] = json.loads(
                        json.dumps(ignored_positions)
                    )
                new_cfg["saved_win_trades"] = win_trades
                new_cfg["saved_loss_trades"] = loss_trades
                ref_eq = (
                    last_flat_equity
                    if last_flat_equity is not None
                    else start_equity
                )
                new_floor, _, _, new_tier_short, _, _ = describe_active_floor(
                    new_cfg
                )
                if (
                    ref_eq is not None
                    and new_floor is not None
                    and ref_eq <= new_floor
                ):
                    is_locked_down = True
                    log_event(
                        "GUARDRAIL",
                        f"Daily Stop remains BREACHED / DISARMED after Settings save "
                        f"(Net PnL {format_dollar(round(ref_eq - start_equity, 2))} <= "
                        f"Daily Stop {format_dollar(round(new_floor - start_equity, 2))} "
                        f"[{new_tier_short}]). "
                        f"Card 1 Trade/Tilt Stops remain active."
                    )
                else:
                    was_ld = is_locked_down
                    is_locked_down = False
                    daily_breach_settings_prompted = False
                    if (
                        was_ld
                        and ref_eq is not None
                        and new_floor is not None
                    ):
                        log_event(
                            "SESSION",
                            f"Daily Stop RE-ARMED at "
                            f"{format_dollar(round(new_floor - start_equity, 2))} "
                            f"[{new_tier_short}] "
                            f"({format_dollar(round(ref_eq - new_floor, 2))} buffer to stop)."
                        )

            save_config(new_cfg)
            log_event("CONFIG", format_config_summary(new_cfg))
            rebuild_hud_columns()

            if mute_btn is not None:
                if alarm_active and not cooldown_active:
                    mute_btn.config(
                        text=format_alarm_button_text(
                            last_alarm_reason or "Active Alarm"
                        )
                    )
                elif not cooldown_active:
                    mute_btn.config(text=get_idle_button_text())

            launched["status"] = True
            _remember_pf_pos()
            active_preflight_close_fn = None
            active_preflight_win = None
            settings_win_open = False
            _cancel_pf_timers()
            pf.destroy()
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Please ensure all fields contain valid numbers.",
                parent=pf
            )

    # --- SPACIOUS 2-COLUMN BODY CONTAINER ---
    body_frame = tk.Frame(pf, bg="#0d1117")
    body_frame.pack(fill="both", expand=True)
    body_frame.columnconfigure(0, weight=1, minsize=520)
    body_frame.columnconfigure(1, weight=1, minsize=520)

    left_col = tk.Frame(body_frame, bg="#0d1117")
    left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

    right_col = tk.Frame(body_frame, bg="#0d1117")
    right_col.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

    def make_card(
        parent_col,
        title,
        subtitle,
        accent="#5dade2",
        bar_color=None,
        expand=False,
        return_parts=False
    ):
        core_c = bar_color or accent
        halo0 = tk.Frame(
            parent_col,
            bg="#151d28",
            padx=1,
            pady=1
        )
        halo0.pack(fill="both", expand=expand, pady=4)
        outer = tk.Frame(
            halo0,
            bg="#131922",
            bd=0,
            highlightthickness=1,
            highlightbackground="#243040"
        )
        outer.pack(fill="both", expand=True)
        accent_bar = NeonBarCanvas(
            outer, core_color=core_c, card_bg="#131922", glow_on=True
        )
        accent_bar.pack(side="left", fill="y")
        card = tk.Frame(
            outer, bg="#131922", padx=14, pady=11
        )
        card.pack(side="left", fill="both", expand=True)
        hdr_row = tk.Frame(card, bg="#131922")
        hdr_row.pack(fill="x")
        card._hdr_row = hdr_row
        title_lbl = tk.Label(
            hdr_row,
            text=title,
            font=("Arial", 11, "bold"),
            fg=accent,
            bg="#131922",
            anchor="w"
        )
        title_lbl.pack(side="left", fill="x", expand=True)
        badge_pill = None
        if return_parts:
            badge_pill = RulebookPillBadge(hdr_row, card_bg="#131922")
            badge_pill.pack(side="right", padx=(6, 0))
        if subtitle:
            tk.Label(
                card,
                text=subtitle,
                font=("Arial", 9),
                fg="#8b9bb0",
                bg="#131922",
                anchor="w"
            ).pack(fill="x", pady=(2, 6))
        tk.Frame(card, bg="#222d3d", height=1).pack(fill="x", pady=(0, 6))
        if return_parts:
            return (
                card,
                (halo0, outer),
                accent_bar,
                title_lbl,
                badge_pill
            )
        return card

    loss_var_ids = {id(dollar_vars[k]) for k in loss_display_keys}
    green_var_ids = {
        id(dollar_vars[k])
        for k in (
            "consec_win_reset_dollars",
            "pm_lock_trigger",
            "pm_trail_cushion",
            "t4_trigger",
            "t4_trail",
        )
        if k in dollar_vars
    }

    def make_entry(parent_w, var, width=8):
        vid = id(var)
        if vid in loss_var_ids:
            e_bg = "#24141a"
            e_rim = "#632d3b"
            e_focus = "#f43f5e"
            e_fg = "#f8e4e7"
        elif vid in green_var_ids:
            e_bg = "#10261e"
            e_rim = "#266149"
            e_focus = "#10b981"
            e_fg = "#e2f7ec"
        else:
            e_bg = "#132333"
            e_rim = "#2e526e"
            e_focus = "#38bdf8"
            e_fg = "#e6eef8"
        ent = tk.Entry(
            parent_w,
            textvariable=var,
            font=("Consolas", 11, "bold"),
            width=width,
            bg=e_bg,
            fg=e_fg,
            disabledbackground="#11161e",
            disabledforeground="#475569",
            insertbackground="#f1f5f9",
            justify="center",
            bd=0,
            highlightthickness=1,
            highlightbackground=e_rim,
            highlightcolor=e_focus
        )
        ent._orig_rim = e_rim
        if vid in loss_var_ids:
            ent.bind("<FocusOut>", _bind_loss_sign_normalizer(var))
        return ent

    def make_dual_field_row(
        parent_w,
        lbl1,
        var1,
        lbl2=None,
        var2=None,
        cb_var1=None,
        cb_var2=None,
        tip1=None,
        tip2=None,
        fg1="#dce4ee",
        fg2="#dce4ee"
    ):
        row = tk.Frame(parent_w, bg="#131922")
        row.pack(fill="x", pady=4)
        row.columnconfigure(0, weight=1, uniform="dual_lbl")
        row.columnconfigure(1, weight=0, minsize=108)
        row.columnconfigure(2, weight=1, uniform="dual_lbl")
        row.columnconfigure(3, weight=0, minsize=84)

        if cb_var1 is not None:
            w1 = make_glass_checkbutton(
                row,
                text=lbl1,
                variable=cb_var1,
                font=("Arial", 10, "bold"),
                fg=fg1,
                bg="#131922",
                anchor="w"
            )
        else:
            w1 = tk.Label(
                row,
                text=lbl1,
                font=("Arial", 10, "bold"),
                fg=fg1,
                bg="#131922",
                anchor="w"
            )
        w1.grid(row=0, column=0, sticky="w", padx=(0, 8))
        e1 = make_entry(row, var1, width=8)
        e1.grid(row=0, column=1, sticky="e", padx=(0, 24))
        if tip1:
            attach_tooltip(w1, tip1)
            attach_tooltip(e1, tip1)

        w2, e2 = None, None
        if lbl2 and var2 is not None:
            if cb_var2 is not None:
                w2 = make_glass_checkbutton(
                    row,
                    text=lbl2,
                    variable=cb_var2,
                    font=("Arial", 10, "bold"),
                    fg=fg2,
                    bg="#131922",
                    anchor="w"
                )
            else:
                w2 = tk.Label(
                    row,
                    text=lbl2,
                    font=("Arial", 10, "bold"),
                    fg=fg2,
                    bg="#131922",
                    anchor="w"
                )
            w2.grid(row=0, column=2, sticky="w", padx=(0, 8))
            e2 = make_entry(row, var2, width=8)
            e2.grid(row=0, column=3, sticky="e")
            if tip2:
                attach_tooltip(w2, tip2)
                attach_tooltip(e2, tip2)
        return w1, e1, w2, e2

    # ==========================================================
    # LEFT COLUMN: 1. TRADE & TILT STOPS, 2. DAILY ACTIONS, 3. SYSTEM
    # ==========================================================
    c1 = make_card(
        left_col,
        "▶  1. TRADE & TILT STOPS (Intraday Penalty Box)",
        "Stops single-trade blowups and rapid loss streaks without ending your trading day.",
        accent="#5dade2",
        bar_color="#38bdf8"
    )
    c1_tamper_lbl = tk.Label(
        c1._hdr_row,
        text="🔒 Locks on active streak",
        font=("Arial", 8, "bold"),
        fg="#7dd3fc",
        bg="#142334",
        padx=7,
        pady=2,
    )
    c1_tamper_lbl.pack(side="right", padx=(6, 0))
    c1_tamper_tip = (
        "Anti-Tilt Tamper Lock (Consecutive Loss Cooldown):\n"
        "• Transparent Upfront Rule: While your Loss Streak is 0/X (CLEAR), you can freely adjust\n"
        "  your Consecutive Loss Cooldown settings (Losses, Min Loss $, Win Reset $, In Mins, and Lock Duration).\n"
        "• Locked During Active Streak: As soon as you have at least 1 qualifying loss on the rolling\n"
        "  clock (e.g. Streak 1/5 or 3/5), these controls LOCK automatically so you cannot raise your limit,\n"
        "  lower your Win Reset threshold, or disable the cooldown mid-streak.\n"
        "• How It Unlocks: Unlocks automatically when the rolling countdown timer reaches 00:00 or when\n"
        "  you close a qualifying winning trade (>= +Win Reset $)."
    )
    attach_tooltip(c1_tamper_lbl, c1_tamper_tip)

    r_open1 = tk.Frame(c1, bg="#131922")
    r_open1.pack(fill="x", pady=3)
    cb_open_flat = make_glass_checkbutton(
        r_open1,
        text="Enable Open PnL Auto-Flatten (Equities)",
        variable=var_open_flat,
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#131922",
        anchor="w"
    )
    cb_open_flat.pack(side="left")
    ent_open_loss = make_entry(r_open1, dollar_vars["open_max_loss"], width=8)
    ent_open_loss.pack(side="right")
    lbl_open_loss = tk.Label(
        r_open1,
        text="Max Open Loss ($):",
        font=("Arial", 10, "bold"),
        fg="#dc6d72",
        bg="#131922"
    )
    lbl_open_loss.pack(side="right", padx=(16, 8))
    open_stop_tip = (
        "Single-Trade Open PnL Stop:\n"
        "If your combined unrealized Open PnL drops to or below -Max Open Loss ($),\n"
        "Enforcer cancels working orders and flattens open EQUITY shares immediately\n"
        "(Market order in RTH 9:30–4:00 ET; marketable GTC_EXT limit order in Extended Hours).\n"
        "• Does NOT end your trading day.\n"
        "• Option contracts are Siren-Only by default unless 'Include Options in Auto-Flatten (BETA)'\n"
        "  is explicitly enabled in Card 2 (RTH 9:30 AM – 4:00 PM ET Market orders only)."
    )
    attach_tooltip(cb_open_flat, open_stop_tip)
    attach_tooltip(lbl_open_loss, open_stop_tip)
    attach_tooltip(ent_open_loss, open_stop_tip)

    r_tilt = tk.Frame(c1, bg="#131922")
    r_tilt.pack(fill="x", pady=3)
    cb_tilt_cd = make_glass_checkbutton(
        r_tilt,
        text="Consecutive Loss Cooldown",
        variable=var_tilt_cd,
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#131922",
        anchor="w"
    )
    cb_tilt_cd.pack(side="left")

    ent_tilt_window = make_entry(r_tilt, var_tilt_window, width=5)
    ent_tilt_window.pack(side="right")
    lbl_tilt_window = tk.Label(
        r_tilt,
        text="In (Mins):",
        font=("Arial", 10, "bold"),
        fg="#97a7b9",
        bg="#131922"
    )
    lbl_tilt_window.pack(side="right", padx=(14, 6))

    lbl_tilt_losses = tk.Label(
        r_tilt,
        text="Losses",
        font=("Arial", 10, "bold"),
        fg="#97a7b9",
        bg="#131922"
    )
    lbl_tilt_losses.pack(side="right", padx=(6, 0))
    ent_tilt_count = make_entry(r_tilt, var_tilt_count, width=4)
    ent_tilt_count.pack(side="right")

    def _fmt_signed_dollar_token(val, neg=False):
        try:
            num = abs(float(val))
        except Exception:
            num = 0.0
        sign = "-" if neg else "+"
        num_str = str(int(num)) if num.is_integer() else f"{num:g}"
        return f"{sign}${num_str}"

    def _format_tilt_filter_pill_text(locked=False):
        m_txt = _fmt_signed_dollar_token(
            dollar_vars["consec_loss_min_dollars"].get(), neg=True
        )
        w_txt = _fmt_signed_dollar_token(
            dollar_vars["consec_win_reset_dollars"].get(), neg=False
        )
        prefix = "🔒 Filter" if locked else "⚙ Filter"
        return f"{prefix} ({m_txt} / {w_txt}) ▸"

    def open_tilt_filter_dialog():
        is_locked = is_in_trade_tamper_locked() or is_tilt_streak_tamper_locked()
        dlg = tk.Toplevel(pf)
        dlg.withdraw()
        if os.path.exists(ICON_PATH):
            try:
                dlg.iconbitmap(ICON_PATH)
            except Exception:
                pass
        apply_dark_title_bar(dlg)
        dlg.title("PnL Enforcer — Qualifying Trade Filter")
        dlg.config(bg="#0d1117", padx=20, pady=16)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.transient(pf)

        hdr = tk.Frame(dlg, bg="#0d1117")
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(
            hdr,
            text="⚙  QUALIFYING TRADE FILTER",
            font=("Arial", 11, "bold"),
            fg="#5dade2",
            bg="#0d1117",
            anchor="w",
        ).pack(side="left")

        if is_locked:
            lock_reason = (
                "🔒 Locked In Trade"
                if is_in_trade_tamper_locked()
                else "🔒 Active Loss Streak"
            )
            tk.Label(
                hdr,
                text=lock_reason,
                font=("Arial", 8, "bold"),
                fg="#fbbf24",
                bg="#2b2112",
                padx=8,
                pady=2,
            ).pack(side="right")

        card_outer = tk.Frame(
            dlg,
            bg="#131922",
            bd=0,
            highlightthickness=1,
            highlightbackground="#243040",
        )
        card_outer.pack(fill="x", pady=(0, 12))
        NeonBarCanvas(
            card_outer,
            core_color="#f59e0b" if is_locked else "#38bdf8",
            card_bg="#131922",
            glow_on=True,
        ).pack(side="left", fill="y")
        card_body = tk.Frame(card_outer, bg="#131922", padx=16, pady=12)
        card_body.pack(side="left", fill="both", expand=True)

        tk.Label(
            card_body,
            text=(
                "Controls which closed round-trip trades count toward or reset your\n"
                "Consecutive Loss Cooldown streak (ignores tiny micro-scratches)."
            ),
            font=("Arial", 9),
            fg="#94a3b8",
            bg="#131922",
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        tmp_min = tk.StringVar(value=dollar_vars["consec_loss_min_dollars"].get())
        tmp_win = tk.StringVar(value=dollar_vars["consec_win_reset_dollars"].get())

        row1 = tk.Frame(card_body, bg="#131922")
        row1.pack(fill="x", pady=4)
        tk.Label(
            row1,
            text="Min Loss to Count ($):",
            font=("Arial", 10, "bold"),
            fg="#fbbf24" if is_locked else "#dc6d72",
            bg="#131922",
            anchor="w",
        ).pack(side="left", padx=(0, 16))
        ent_m = tk.Entry(
            row1,
            textvariable=tmp_min,
            font=("Consolas", 11, "bold"),
            width=8,
            bg="#24141a",
            fg="#f8e4e7",
            disabledbackground="#11161e",
            disabledforeground="#fde68a" if is_locked else "#475569",
            insertbackground="#f1f5f9",
            justify="center",
            bd=0,
            highlightthickness=1,
            highlightbackground="#b45309" if is_locked else "#632d3b",
            highlightcolor="#f43f5e",
        )
        ent_m.pack(side="right")
        ent_m.bind("<FocusOut>", _bind_loss_sign_normalizer(tmp_min))

        row2 = tk.Frame(card_body, bg="#131922")
        row2.pack(fill="x", pady=4)
        tk.Label(
            row2,
            text="Min Win to Reset Streak ($):",
            font=("Arial", 10, "bold"),
            fg="#fbbf24" if is_locked else "#4ec994",
            bg="#131922",
            anchor="w",
        ).pack(side="left", padx=(0, 16))
        ent_w = tk.Entry(
            row2,
            textvariable=tmp_win,
            font=("Consolas", 11, "bold"),
            width=8,
            bg="#10261e",
            fg="#e2f7ec",
            disabledbackground="#11161e",
            disabledforeground="#fde68a" if is_locked else "#475569",
            insertbackground="#f1f5f9",
            justify="center",
            bd=0,
            highlightthickness=1,
            highlightbackground="#b45309" if is_locked else "#266149",
            highlightcolor="#10b981",
        )
        ent_w.pack(side="right")

        err_lbl = tk.Label(
            card_body,
            text="",
            font=("Arial", 8, "bold"),
            fg="#f87171",
            bg="#131922",
            anchor="w",
        )
        err_lbl.pack(fill="x", pady=(6, 0))

        if is_locked:
            ent_m.config(state="disabled")
            ent_w.config(state="disabled")
            err_lbl.config(
                text="Read-only while a daytrade is open or a loss streak is active.",
                fg="#fbbf24",
            )

        def _on_cancel():
            dlg.destroy()

        def _on_apply(*_):
            if is_locked:
                dlg.destroy()
                return
            try:
                m_val = abs(float(tmp_min.get().strip()))
                w_val = abs(float(tmp_win.get().strip()))
            except Exception:
                err_lbl.config(
                    text="Please enter valid numbers for Min Loss and Win Reset.",
                    fg="#f87171",
                )
                return
            m_fmt = f"-{int(m_val)}" if m_val.is_integer() else f"-{m_val:g}"
            w_fmt = f"{int(w_val)}" if w_val.is_integer() else f"{w_val:g}"
            dollar_vars["consec_loss_min_dollars"].set(m_fmt)
            dollar_vars["consec_win_reset_dollars"].set(w_fmt)
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", _on_cancel)
        dlg.bind("<Escape>", lambda _e: _on_cancel())
        if not is_locked:
            dlg.bind("<Return>", _on_apply)

        btn_row = tk.Frame(dlg, bg="#0d1117")
        btn_row.pack(fill="x")
        if is_locked:
            make_stadium_button(
                btn_row,
                text="Close",
                font=("Arial", 9, "bold"),
                fill_color="#141820",
                fill_top_color="#1c212b",
                border_color="#475569",
                hover_fill="#1e293b",
                hover_border="#64748b",
                fg="#e2e8f0",
                canvas_bg="#0d1117",
                width=110,
                height=32,
                auto_width=False,
                command=_on_cancel,
            ).pack(side="right")
        else:
            make_stadium_button(
                btn_row,
                text="Done ✓",
                font=("Arial", 9, "bold"),
                fill_color="#0d3b20",
                fill_top_color="#14532d",
                border_color="#10b981",
                hover_fill="#114b29",
                hover_fill_top="#196638",
                hover_border="#34d399",
                fg="#ffffff",
                canvas_bg="#0d1117",
                width=110,
                height=32,
                auto_width=False,
                command=_on_apply,
            ).pack(side="right", padx=(8, 0))
            make_stadium_button(
                btn_row,
                text="Cancel",
                font=("Arial", 9, "bold"),
                fill_color="#141820",
                fill_top_color="#1c212b",
                border_color="#2e3746",
                hover_fill="#1e293b",
                hover_border="#475569",
                fg="#94a3b8",
                canvas_bg="#0d1117",
                width=96,
                height=32,
                auto_width=False,
                command=_on_cancel,
            ).pack(side="right")

        center_dialog_over_parent(dlg, parent=pf)
        dlg.grab_set()
        if not is_locked:
            try:
                ent_m.focus_set()
                ent_m.selection_range(0, "end")
            except Exception:
                pass
        else:
            try:
                dlg.focus_set()
            except Exception:
                pass
        pf.wait_window(dlg)

    r_tilt_sub = tk.Frame(c1, bg="#131922")
    r_tilt_sub.pack(fill="x", pady=2)
    lbl_tilt_filter = tk.Label(
        r_tilt_sub,
        text="└─ Qualifying Trade Filter:",
        font=("Arial", 9, "bold"),
        fg="#97a7b9",
        bg="#131922",
        anchor="w",
    )
    lbl_tilt_filter.pack(side="left", padx=(18, 0))

    btn_tilt_filter = make_stadium_button(
        r_tilt_sub,
        text=_format_tilt_filter_pill_text(),
        font=("Arial", 8, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#38bdf8",
        fg="#cbd5e1",
        canvas_bg="#131922",
        width=182,
        height=24,
        pad_x=18,
        command=open_tilt_filter_dialog,
    )
    btn_tilt_filter.pack(side="right")

    def _refresh_tilt_filter_pill(*_):
        try:
            if not pf.winfo_exists():
                return
        except Exception:
            return
        is_t_locked = (
            is_in_trade_tamper_locked() or is_tilt_streak_tamper_locked()
        )
        btn_tilt_filter.config(
            text=_format_tilt_filter_pill_text(locked=is_t_locked)
        )

    dollar_vars["consec_loss_min_dollars"].trace_add(
        "write", _refresh_tilt_filter_pill
    )
    dollar_vars["consec_win_reset_dollars"].trace_add(
        "write", _refresh_tilt_filter_pill
    )

    tilt_tip = (
        "Consecutive Loss Cooldown ('Tilt Streak Stop'):\n"
        "Tracks completed losing round-trip trades inside a rolling time window.\n"
        "If you close X consecutive losing trades (each at least 'Min Loss ($)') within 'In (Mins)' minutes,\n"
        "Enforcer cancels working orders and triggers the Penalty Box OS Lock Cooldown below.\n"
        "• Min Loss ($): Ignores tiny scratch losses smaller than '-Min Loss ($)' (e.g. -$5 when Min Loss is -$25)\n"
        "  so disciplined micro-scratches are never penalized toward a loss streak.\n"
        "• Win Reset ($): Sets the minimum green trade required to reset an active loss streak early\n"
        "  (e.g. +$10 means a +$0.30 scratch 'win' will NOT wipe out a 4/5 loss streak, while a +$10+ win resets it to 0).\n"
        "• Anti-Tilt Tamper Lock: While you have an active loss streak (> 0 losses on the clock), these settings\n"
        "  lock automatically and cannot be disabled or loosened in Settings until the streak clears."
    )
    for _tw in (
        cb_tilt_cd,
        ent_tilt_count,
        lbl_tilt_losses,
        lbl_tilt_filter,
        btn_tilt_filter,
        lbl_tilt_window,
        ent_tilt_window,
    ):
        attach_tooltip(_tw, tilt_tip)

    def show_tilt_cooldown_lock_notice():
        """Displays a friendly dark-glass reminder popup when the user enables
        Consecutive Loss Cooldown so they know upfront that the settings lock
        automatically during an active loss streak."""
        decision = {"ok": False}
        dlg = tk.Toplevel(pf)
        dlg.withdraw()
        dlg.title("PnL Enforcer — Consecutive Loss Cooldown")
        dlg.configure(bg="#0d1117", padx=24, pady=20)
        dlg.resizable(False, False)
        dlg.transient(pf)

        def on_cancel():
            decision["ok"] = False
            dlg.destroy()

        def on_confirm():
            decision["ok"] = True
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", on_cancel)
        dlg.bind("<Escape>", lambda _e: on_cancel())

        hdr_row = tk.Frame(dlg, bg="#0d1117")
        hdr_row.pack(fill="x", pady=(0, 4))

        tk.Label(
            hdr_row,
            text="▶  CONSECUTIVE LOSS COOLDOWN — ANTI-TILT LOCK",
            font=("Arial", 12, "bold"),
            fg="#38bdf8",
            bg="#0d1117",
            anchor="w",
        ).pack(side="left")

        tk.Label(
            hdr_row,
            text="🔒 LOCKS ON ACTIVE STREAK",
            font=("Arial", 8, "bold"),
            fg="#fde68a",
            bg="#451a03",
            padx=8,
            pady=3,
        ).pack(side="right", padx=(12, 0))

        tk.Label(
            dlg,
            text="Friendly heads-up on how your streak settings behave once a losing streak starts:",
            font=("Arial", 9),
            fg="#94a3b8",
            bg="#0d1117",
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        card_outer = tk.Frame(
            dlg,
            bg="#131922",
            bd=0,
            highlightthickness=1,
            highlightbackground="#243040",
        )
        card_outer.pack(fill="x", pady=(0, 16))
        NeonBarCanvas(
            card_outer, core_color="#f59e0b", card_bg="#131922", glow_on=True
        ).pack(side="left", fill="y")

        txt_box = tk.Text(
            card_outer,
            width=86,
            height=15,
            bg="#131922",
            fg="#dce4ee",
            font=("Segoe UI", 10),
            wrap="none",
            bd=0,
            highlightthickness=0,
            padx=18,
            pady=14,
            cursor="arrow",
        )
        txt_box.pack(side="left", fill="both", expand=True)

        txt_box.tag_configure(
            "hdr_green",
            font=("Segoe UI", 10, "bold"),
            foreground="#4ade80",
            spacing1=0,
            spacing3=4,
        )
        txt_box.tag_configure(
            "hdr_amber",
            font=("Segoe UI", 10, "bold"),
            foreground="#fbbf24",
            spacing1=2,
            spacing3=4,
        )
        txt_box.tag_configure(
            "hdr_blue",
            font=("Segoe UI", 10, "bold"),
            foreground="#38bdf8",
            spacing1=2,
            spacing3=4,
        )
        txt_box.tag_configure(
            "body",
            font=("Segoe UI", 10),
            foreground="#dce4ee",
            spacing1=1,
            spacing3=2,
        )
        txt_box.tag_configure(
            "pill_blue",
            font=("Consolas", 9, "bold"),
            foreground="#7dd3fc",
            background="#1a2636",
        )
        txt_box.tag_configure(
            "pill_red",
            font=("Consolas", 9, "bold"),
            foreground="#fda4af",
            background="#2c151d",
        )
        txt_box.tag_configure(
            "pill_green",
            font=("Consolas", 9, "bold"),
            foreground="#6ee7b7",
            background="#112a20",
        )
        txt_box.tag_configure(
            "pill_amber",
            font=("Consolas", 9, "bold"),
            foreground="#fde68a",
            background="#3b2106",
        )
        txt_box.tag_configure(
            "div_line",
            font=("Consolas", 8),
            foreground="#222d3d",
            spacing1=5,
            spacing3=5,
        )

        # Section 1: Clear state
        txt_box.insert(
            "end",
            "✓  1. FREELY ADJUSTABLE WHEN CLEAR  (Streak: 0 / X)\n",
            "hdr_green",
        )
        s1_spans = [
            ("    While your Loss Streak is ", ("body",)),
            (" 0 / X ", ("body", "pill_green")),
            (", you can freely tune your ", ("body",)),
            (" Losses ", ("body", "pill_blue")),
            (" count,\n", ("body",)),
            ("    ", ("body",)),
            (" Min Loss ($) ", ("body", "pill_red")),
            (", ", ("body",)),
            (" Win Reset ($) ", ("body", "pill_green")),
            (", ", ("body",)),
            (" In (Mins) ", ("body", "pill_blue")),
            (" window, and ", ("body",)),
            (" Penalty Box Lock Duration ", ("body", "pill_blue")),
            (".\n", ("body",)),
        ]
        for s_txt, s_tags in s1_spans:
            txt_box.insert("end", s_txt, s_tags)

        txt_box.insert("end", "─" * 76 + "\n", "div_line")

        # Section 2: Active streak lock
        txt_box.insert(
            "end",
            "🔒  2. LOCKED DURING AN ACTIVE STREAK  (Streak: 1 / X or Higher)\n",
            "hdr_amber",
        )
        s2_spans = [
            ("    Once you have ", ("body",)),
            (" 1 qualifying loss ", ("body", "pill_amber")),
            (" on the rolling clock, these controls switch to ", ("body",)),
            (" 🔒 LOCKED ", ("body", "pill_amber")),
            ("\n", ("body",)),
            ("    (and ignore ", ("body",)),
            (" Restore Defaults ", ("body", "pill_blue")),
            (", ", ("body",)),
            (" Standard Full Risk ", ("body", "pill_blue")),
            (", and ", ("body",)),
            (" 50% Low Energy ", ("body", "pill_blue")),
            (") so you\n", ("body",)),
            ("    cannot raise your limit, lower ", ("body",)),
            (" Win Reset ($) ", ("body", "pill_green")),
            (", or turn off the cooldown mid-streak.\n", ("body",)),
        ]
        for s_txt, s_tags in s2_spans:
            txt_box.insert("end", s_txt, s_tags)

        txt_box.insert("end", "─" * 76 + "\n", "div_line")

        # Section 3: Unlock conditions
        txt_box.insert(
            "end",
            "⏱  3. AUTOMATIC UNLOCK CONDITIONS\n",
            "hdr_blue",
        )
        s3_spans = [
            ("    The lock clears automatically as soon as your rolling streak countdown reaches ", ("body",)),
            (" 00:00 ", ("body", "pill_blue")),
            ("\n", ("body",)),
            ("    or when you close a qualifying winning trade (", ("body",)),
            (" >= +Win Reset ($) ", ("body", "pill_green")),
            (").", ("body",)),
        ]
        for s_txt, s_tags in s3_spans:
            txt_box.insert("end", s_txt, s_tags)

        txt_box.config(state="disabled")

        btn_row = tk.Frame(dlg, bg="#0d1117")
        btn_row.pack(fill="x")

        make_stadium_button(
            btn_row,
            text="Got It — Arm Cooldown ✓",
            font=("Arial", 10, "bold"),
            fill_color="#0d3b20",
            fill_top_color="#14532d",
            border_color="#10b981",
            hover_fill="#114b29",
            hover_fill_top="#196638",
            hover_border="#34d399",
            fg="#ffffff",
            canvas_bg="#0d1117",
            width=210,
            height=34,
            auto_width=False,
            command=on_confirm,
        ).pack(side="right")

        make_stadium_button(
            btn_row,
            text="Cancel",
            font=("Arial", 10, "bold"),
            fill_color="#3b1520",
            border_color="#f43f5e",
            hover_fill="#4f1c2b",
            hover_border="#fb7185",
            fg="#ffe4e6",
            canvas_bg="#0d1117",
            width=104,
            height=34,
            auto_width=False,
            command=on_cancel,
        ).pack(side="right", padx=(0, 8))

        dlg.update_idletasks()
        center_dialog_over_parent(dlg, parent=pf)
        dlg.grab_set()
        pf.wait_window(dlg)
        return decision["ok"]

    def _on_toggle_tilt_cd(*_):
        if _tilt_cd_popup_guard["suppress"] or _tamper_sync_guard["busy"]:
            return
        if var_tilt_cd.get():
            if not show_tilt_cooldown_lock_notice():
                _tilt_cd_popup_guard["suppress"] = True
                try:
                    var_tilt_cd.set(False)
                finally:
                    _tilt_cd_popup_guard["suppress"] = False
                refresh_smart_dimming()
                return
            if not var_open_cd.get():
                var_open_cd.set(True)
        refresh_smart_dimming()

    r_open2 = tk.Frame(c1, bg="#131922")
    r_open2.pack(fill="x", pady=3)
    cb_open_cd = make_glass_checkbutton(
        r_open2,
        text="Penalty Box OS Lock Cooldown",
        variable=var_open_cd,
        font=("Arial", 10, "bold"),
        fg="#c8d4e0",
        bg="#131922",
        anchor="w"
    )
    cb_open_cd.pack(side="left")
    ent_cd_mins = make_entry(r_open2, var_cd_mins, width=8)
    ent_cd_mins.pack(side="right")
    lbl_cd_mins = tk.Label(
        r_open2,
        text="Lock Duration (Mins):",
        font=("Arial", 10, "bold"),
        fg="#97a7b9",
        bg="#131922"
    )
    lbl_cd_mins.pack(side="right", padx=(16, 8))
    open_cd_tip = (
        "Penalty Box Cooldown Lock (Shared by Open PnL Stop & Consecutive Loss Cooldown):\n"
        "Locks your Windows screen for the set duration (supports decimals like 0.5 for 30s)\n"
        "after an Open PnL Stop or Consecutive Loss Cooldown triggers so you cannot revenge-trade.\n"
        "• SAFETY GUARANTEE: The app ALWAYS confirms with the broker API that 100% of open\n"
        "  positions are closed (flat) before locking your computer — it will never lock you\n"
        "  out while a position is still open."
    )
    attach_tooltip(cb_open_cd, open_cd_tip)
    attach_tooltip(lbl_cd_mins, open_cd_tip)
    attach_tooltip(ent_cd_mins, open_cd_tip)

    # --- CARD 2: DAILY STOP ACTIONS (MAX LOSS & PROFIT LOCK) ---
    c2 = make_card(
        left_col,
        "▶  2. DAILY STOP ACTIONS (Max Loss & Profit Lock)",
        "Fires when Net PnL hits your active Max Loss or Profit Lock in Rulebook 4 or 5.",
        accent="#f5b041",
        bar_color="#fbbf24"
    )
    c2_tamper_lbl = tk.Label(
        c2._hdr_row,
        text="",
        font=("Arial", 8, "bold"),
        fg="#64748b",
        bg="#131922",
        padx=7,
        pady=2,
    )
    c2_tamper_lbl.pack(side="right", padx=(6, 0))

    r_day_top = tk.Frame(c2, bg="#131922")
    r_day_top.pack(fill="x", pady=3)
    cb_day_flat = make_glass_checkbutton(
        r_day_top,
        text="Auto-Flatten Equities on Max Loss / Profit Stop",
        variable=var_flatten,
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#131922",
        anchor="w"
    )
    cb_day_flat.pack(side="left")
    attach_tooltip(
        cb_day_flat,
        "Auto-Flatten on Daily Stop (Max Loss or Profit Lock):\n"
        "When your total Net PnL (Realized + Open) hits your active Daily Stop in Rulebook 4 or 5\n"
        "(whether that is your Starting Max Loss, a tightened Tier 2/3 Max Loss, or a green\n"
        "Trailing Profit Lock), Enforcer cancels working orders and liquidates open Equity shares.\n"
        "• Option contracts are Siren-Only by default unless 'Include Options in Auto-Flatten (BETA)'\n"
        "  is enabled below; if options remain open, the siren blares until you close them."
    )

    r_opt_flat = tk.Frame(c2, bg="#131922")
    r_opt_flat.pack(fill="x", pady=2)
    cb_opt_flat = make_glass_checkbutton(
        r_opt_flat,
        text="└─ Include Options in Auto-Flatten (BETA — RTH Market Orders)",
        variable=var_flatten_options,
        font=("Arial", 10, "bold"),
        fg="#f5b041",
        bg="#131922",
        accent_hex="#d97706",
        check_hex="#fbbf24",
        anchor="w"
    )
    cb_opt_flat.pack(side="left", padx=(18, 0))
    opt_flat_tip = (
        "EXPERIMENTAL BETA — Options Auto-Flatten (RTH 9:30 AM – 4:00 PM ET Only):\n"
        "When checked (and after accepting the BETA Options Risk Waiver), Enforcer will also submit\n"
        "single-leg RTH MARKET orders (BUY_TO_CLOSE for short legs first, SELL_TO_CLOSE for long legs)\n"
        "to liquidate open equity option contracts during Card 1 Open PnL stops and Card 2 Daily Stops.\n"
        "• WIDE SPREAD WARNING: Option Market orders fill at the live Bid/Ask and can suffer severe\n"
        "  slippage far beyond your stop threshold on wide-spread or fast-moving contracts.\n"
        "• MULTI-LEG SPREADS: Liquidated leg-by-leg as individual Market orders (short legs first).\n"
        "• RTH ONLY: Options cannot be auto-flattened outside 9:30 AM – 4:00 PM ET (sounds siren instead)."
    )
    attach_tooltip(cb_opt_flat, opt_flat_tip)

    def _on_toggle_flatten_options(*_):
        if _opt_waiver_guard["suppress"]:
            return
        if var_flatten_options.get():
            accepted = show_options_flatten_beta_waiver(
                parent=pf, force_prompt=True
            )
            if not accepted:
                _opt_waiver_guard["suppress"] = True
                try:
                    var_flatten_options.set(False)
                finally:
                    _opt_waiver_guard["suppress"] = False
        else:
            log_event(
                "WAIVER",
                "User unchecked BETA Options Auto-Flatten toggle in Pre-Flight.",
            )
        refresh_smart_dimming()

    var_flatten_options.trace_add("write", _on_toggle_flatten_options)

    r_kill = tk.Frame(c2, bg="#131922")
    r_kill.pack(fill="x", pady=3)
    lbl_kill = tk.Label(
        r_kill,
        text="Kill Apps (When Flat):",
        font=("Arial", 10, "bold"),
        fg="#97a7b9",
        bg="#131922"
    )
    lbl_kill.pack(side="left", padx=(0, 10))
    cb_kill_tos = make_glass_checkbutton(
        r_kill,
        text="Thinkorswim",
        variable=var_kill_tos,
        font=("Arial", 10, "bold"),
        fg="#dc6d72",
        bg="#131922"
    )
    cb_kill_tos.pack(side="left", padx=(0, 12))
    cb_kill_wb = make_glass_checkbutton(
        r_kill,
        text="Webull Desktop",
        variable=var_kill_wb,
        font=("Arial", 10, "bold"),
        fg="#dc6d72",
        bg="#131922"
    )
    cb_kill_wb.pack(side="left")
    kill_tip = (
        "Platform Kill-Switch (When Flat):\n"
        "Force-closes your desktop trading platform (thinkorswim.exe and/or Webull Desktop) "
        "when your active Max Loss or Profit Lock is hit.\n"
        "• SAFETY GUARANTEE: Only closes the app AFTER confirming your account is 100% flat."
    )
    attach_tooltip(lbl_kill, kill_tip)
    attach_tooltip(cb_kill_tos, kill_tip)
    attach_tooltip(cb_kill_wb, kill_tip)

    r_day_lock = tk.Frame(c2, bg="#131922")
    r_day_lock.pack(fill="x", pady=3)
    cb_lock_os = make_glass_checkbutton(
        r_day_lock,
        text="Lock Windows OS on Max Loss / Profit Stop",
        variable=var_lock_os,
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#131922",
        anchor="w"
    )
    cb_lock_os.pack(side="left")
    ent_daily_lock_mins = make_entry(r_day_lock, var_daily_lock_mins, width=8)
    ent_daily_lock_mins.pack(side="right")
    lbl_daily_lock_mins = tk.Label(
        r_day_lock,
        text="Lock Duration (Mins):",
        font=("Arial", 10, "bold"),
        fg="#97a7b9",
        bg="#131922"
    )
    lbl_daily_lock_mins.pack(side="right", padx=(12, 8))
    day_lock_tip = (
        "Windows OS Lockout on Max Loss / Profit Stop:\n"
        "Locks your Windows workstation for this duration whenever your active Max Loss, "
        "Tier 2/3 Ratchet, or Trailing Profit Lock is hit.\n"
        "• 0 = Locks Windows one single time (1x).\n"
        "• > 0 (e.g. 15) = Persistent lockout timer that re-locks Windows every few seconds if you log back in early.\n"
        "• SAFETY GUARANTEE: Always confirms with the broker API that 100% of open positions are flat before locking."
    )
    attach_tooltip(cb_lock_os, day_lock_tip)
    attach_tooltip(lbl_daily_lock_mins, day_lock_tip)
    attach_tooltip(ent_daily_lock_mins, day_lock_tip)

    # --- CARD 3: TODAY'S SESSION & BASELINE (WITH MULTI-COLOR TELEMETRY STRIP) ---
    c3_core = "#10b981"
    c3_h0 = tk.Frame(
        left_col,
        bg="#151d28",
        padx=1,
        pady=1
    )
    c3_h0.pack(fill="both", expand=True, pady=4)
    c3_outer = tk.Frame(
        c3_h0,
        bg="#131922",
        bd=0,
        highlightthickness=1,
        highlightbackground="#243040"
    )
    c3_outer.pack(fill="both", expand=True)
    c3_bar = NeonBarCanvas(
        c3_outer, core_color=c3_core, card_bg="#131922", glow_on=True
    )
    c3_bar.pack(side="left", fill="y")
    c3 = tk.Frame(c3_outer, bg="#131922", padx=14, pady=11)
    c3.pack(side="left", fill="both", expand=True)
    c3_hdr_row = tk.Frame(c3, bg="#131922")
    c3_hdr_row.pack(fill="x")
    tk.Label(
        c3_hdr_row,
        text="▶  3. TODAY'S SESSION & BASELINE",
        font=("Arial", 11, "bold"),
        fg="#4ec994",
        bg="#131922",
        anchor="w"
    ).pack(side="left")

    def _on_click_reanchor_pill():
        if is_in_trade_tamper_locked():
            messagebox.showwarning(
                "Locked During Active Trade",
                "Baseline Re-Zero is locked while an active daytrade position is open.\n\n"
                "Flatten your open daytrade first to re-zero your baseline.",
                parent=pf,
            )
            var_reanchor.set(False)
            return
        if is_tilt_streak_tamper_locked():
            cur_s, req_l, next_s, _full_s, _is_en = get_loss_streak_status()
            messagebox.showwarning(
                "Locked During Active Loss Streak",
                f"Baseline Re-Zero is locked while an active Consecutive Loss Streak "
                f"({cur_s}/{req_l} — resets in {_format_countdown_mm_ss(next_s)}) is running.\n\n"
                f"Wait for the streak countdown to reach 00:00 or close a qualifying win to unlock.",
                parent=pf,
            )
            var_reanchor.set(False)
            return
        var_reanchor.set(not bool(var_reanchor.get()))

    btn_reanchor_pill = make_stadium_button(
        c3_hdr_row,
        text="↺ Re-Zero Baseline",
        font=("Arial", 8, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#3b2f1e",
        hover_fill="#1e1b16",
        hover_fill_top="#29231a",
        hover_border="#f59e0b",
        fg="#f5b041",
        canvas_bg="#131922",
        width=124,
        height=22,
        pad_x=16,
        command=_on_click_reanchor_pill,
    )
    btn_reanchor_pill.pack(side="right")
    attach_tooltip(
        btn_reanchor_pill,
        "One-Time Baseline Reset (Re-Zero):\n"
        "Click to arm a one-time baseline reset, then click 'SAVE & APPLY CHANGES'.\n"
        "Re-anchors today's starting baseline equity to your current account balance right now\n"
        "(resetting today's Realized PnL, Session High, Consecutive Loss Streak, and W/L counter to 0).\n"
        "Useful after a deposit/withdrawal or if starting a fresh afternoon session."
    )

    def _refresh_reanchor_pill(*_):
        if is_in_trade_tamper_locked():
            btn_reanchor_pill.config(
                text="🔒 In Trade",
                fill_color="#1e2228",
                fill_top_color="#262a30",
                border_color="#6b5b3e",
                fg="#94a3b8",
                disabledforeground="#94a3b8",
                state="disabled",
            )
        elif var_reanchor.get():
            btn_reanchor_pill.config(
                text="✓ Re-Zero Armed",
                fill_color="#33220c",
                fill_top_color="#473010",
                border_color="#f59e0b",
                hover_fill="#3f2a0f",
                hover_fill_top="#543813",
                hover_border="#fbbf24",
                fg="#fde68a",
                state="normal",
            )
        else:
            btn_reanchor_pill.config(
                text="↺ Re-Zero Baseline",
                fill_color="#141820",
                fill_top_color="#1c212b",
                border_color="#3b2f1e",
                hover_fill="#1e1b16",
                hover_fill_top="#29231a",
                hover_border="#f59e0b",
                fg="#f5b041",
                state="normal",
            )

    var_reanchor.trace_add("write", _refresh_reanchor_pill)

    base_sub_lbl = tk.Frame(c3, bg="#131922")
    base_sub_lbl.pack(fill="x", pady=(2, 6))
    tk.Frame(c3, bg="#222d3d", height=1).pack(fill="x", pady=(0, 6))
    refresh_baseline_preview()
    attach_tooltip(
        base_sub_lbl,
        "Shows today's anchored starting account equity ($0.00 PnL reference point),\n"
        "remaining Schwab 7-day token lifetime, and today's completed Win/Loss trade count."
    )

    prepos_tip = (
        "Pre-Existing Swing / Long-Term Position Filter (ON by Default):\n"
        "When enabled, any positions already open in your account when PnL Enforcer starts\n"
        "are prompted for review and default to IGNORED:\n"
        "• Never locks enforcement settings or HUD Close as '🔒 IN TRADE'.\n"
        "• Excluded from Open PnL, Realized PnL, Net PnL, and Daily Stop calculations.\n"
        "• Never auto-flattened and its working GTC orders are never canceled.\n"
        "• Adding to, trimming, or closing an ignored ticker has $0.00 impact on daytrade PnL.\n"
        "Click the pill button on the left anytime to review or toggle Ignored vs. Tracked positions."
    )
    audio_choices = [
        "Warning Siren (Short Preview)",
        "Connection Lost Tone (2-Tone)",
        "Upside Tier Chime",
        "Voice: Lockout Alert",
        "Voice: 15s Sweep Clear",
        "Voice: 1m Warning",
        "Voice: 30s Warning",
        "Unlock Chime (3-Tone)",
        "Full 10s Dry-Run Lockout",
    ]
    for _mk in list(_prefs_modal_refs.keys()):
        _prefs_modal_refs[_mk] = None

    def _sync_prefs_modal_state(*_):
        dlg = _prefs_modal_refs.get("dlg")
        if dlg is None:
            return
        try:
            if not dlg.winfo_exists():
                return
        except Exception:
            return
        in_tr_lk = is_in_trade_tamper_locked()
        cb_r925 = _prefs_modal_refs.get("cb_reset925")
        if cb_r925 is not None:
            try:
                cb_r925.config(
                    state="disabled" if in_tr_lk else "normal",
                    disabledforeground="#94a3b8" if var_reset925.get() else "#526070",
                )
            except Exception:
                pass
        cb_ig = _prefs_modal_refs.get("cb_ignore_prepos")
        if cb_ig is not None:
            try:
                cb_ig.config(
                    state="disabled" if in_tr_lk else "normal",
                    disabledforeground=(
                        "#94a3b8" if var_ignore_preexisting.get() else "#526070"
                    ),
                )
            except Exception:
                pass
        lbl_sl = _prefs_modal_refs.get("lbl_session_lock")
        if lbl_sl is not None:
            try:
                lbl_sl.config(text="🔒 Locked In Trade" if in_tr_lk else "")
            except Exception:
                pass
        btn_ta = _prefs_modal_refs.get("btn_test_audio")
        if btn_ta is not None:
            try:
                if dry_run_lock_active or cooldown_active:
                    btn_ta.config(text="🔒 10s", state="disabled")
                else:
                    btn_ta.config(text="🔊 Test", state="normal")
            except Exception:
                pass
        btn_dn = _prefs_modal_refs.get("btn_done")
        if btn_dn is not None:
            try:
                btn_dn.config(
                    state="disabled"
                    if (dry_run_lock_active or cooldown_active)
                    else "normal"
                )
            except Exception:
                pass

    def _confirm_dry_run_lockout():
        decision = {"ok": False}
        active_parent = _prefs_modal_refs.get("dlg")
        try:
            if active_parent is None or not active_parent.winfo_exists():
                active_parent = pf
        except Exception:
            active_parent = pf
        dlg = tk.Toplevel(active_parent)
        dlg.withdraw()
        if os.path.exists(ICON_PATH):
            try:
                dlg.iconbitmap(ICON_PATH)
            except Exception:
                pass
        apply_dark_title_bar(dlg)
        dlg.title("PnL Enforcer — 10-Second Dry-Run OS Lockout Test")
        dlg.config(bg="#0d1117", padx=26, pady=20)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.transient(active_parent)

        def on_cancel():
            decision["ok"] = False
            dlg.destroy()

        def on_start():
            decision["ok"] = True
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", on_cancel)
        dlg.bind("<Escape>", lambda _e: on_cancel())

        tk.Label(
            dlg,
            text="▶  🧪 10-SECOND DRY-RUN OS LOCKOUT TEST",
            font=("Arial", 12, "bold"),
            fg="#fbbf24",
            bg="#0d1117",
            anchor="w",
        ).pack(fill="x", pady=(0, 12))

        card_outer = tk.Frame(
            dlg,
            bg="#131922",
            bd=0,
            highlightthickness=1,
            highlightbackground="#243040",
        )
        card_outer.pack(fill="x", pady=(0, 16))
        NeonBarCanvas(
            card_outer, core_color="#fbbf24", card_bg="#131922", glow_on=True
        ).pack(side="left", fill="y")

        msg_txt = (
            "Run a 10-second simulated lockout sequence now?\n\n"
            "• Plays the warning siren & verbal lockout voice announcement\n"
            "• Locks your Windows screen (LockWorkStation) for 10 seconds\n"
            "• Plays the 3-tone unlock chime & voice confirmation when finished\n\n"
            "No orders are placed or canceled, and your session baseline and W/L stats remain untouched."
        )
        tk.Label(
            card_outer,
            text=msg_txt,
            font=("Arial", 10, "bold"),
            fg="#e2e8f0",
            bg="#131922",
            justify="left",
            anchor="w",
            wraplength=540,
            padx=20,
            pady=16,
        ).pack(side="left", fill="both", expand=True)

        btn_row = tk.Frame(dlg, bg="#0d1117")
        btn_row.pack(fill="x")

        make_stadium_button(
            btn_row,
            text="Cancel",
            font=("Arial", 10, "bold"),
            fill_color="#181e26",
            border_color="#4a5568",
            hover_fill="#232c38",
            hover_border="#718096",
            fg="#e2e8f0",
            hover_fg="#ffffff",
            canvas_bg="#0d1117",
            width=120,
            height=34,
            auto_width=False,
            command=on_cancel,
        ).pack(side="right", padx=(10, 0))

        make_stadium_button(
            btn_row,
            text="▶ Start 10s Dry-Run Lock",
            font=("Arial", 10, "bold"),
            fill_color="#78350f",
            fill_top_color="#92400e",
            border_color="#f59e0b",
            hover_fill="#92400e",
            hover_fill_top="#b45309",
            hover_border="#fbbf24",
            fg="#fef3c7",
            hover_fg="#ffffff",
            canvas_bg="#0d1117",
            width=220,
            height=34,
            auto_width=False,
            command=on_start,
        ).pack(side="right")

        dlg.update_idletasks()
        w = dlg.winfo_reqwidth()
        h = dlg.winfo_reqheight()
        center_dialog_over_parent(dlg, parent=active_parent, width=w, height=h)
        dlg.grab_set()
        dlg.focus_set()
        active_parent.wait_window(dlg)
        if active_parent is not pf:
            try:
                if active_parent.winfo_exists():
                    active_parent.lift()
                    active_parent.grab_set()
                    active_parent.focus_force()
            except Exception:
                pass
        return decision["ok"]

    def play_selected_test_audio():
        choice = var_audio_test.get()
        sel_voice_id = TTS_LABEL_TO_ID.get(var_tts_voice.get(), "Zira")
        active_parent = _prefs_modal_refs.get("dlg")
        try:
            if active_parent is None or not active_parent.winfo_exists():
                active_parent = pf
        except Exception:
            active_parent = pf
        if choice == "Warning Siren (Short Preview)":
            def _siren_sample():
                try:
                    for _ in range(4):
                        winsound.Beep(2600, 180)
                        time.sleep(0.04)
                except Exception:
                    pass
            threading.Thread(target=_siren_sample, daemon=True).start()
        elif choice == "Connection Lost Tone (2-Tone)":
            threading.Thread(
                target=play_disconnect_tone_once, daemon=True
            ).start()
        elif choice == "Upside Tier Chime":
            play_upside_tier_chime()
        elif choice == "Voice: Lockout Alert":
            speak_async(
                "Open P and L stop triggered. Locked out for 2 minutes. Initial flat check passed.",
                force=True,
                voice_override=sel_voice_id,
                interrupt=True,
            )
        elif choice == "Voice: 15s Sweep Clear":
            speak_async(
                "15 second sweep clear, account confirmed flat.",
                force=True,
                voice_override=sel_voice_id,
                interrupt=True,
            )
        elif choice == "Voice: 1m Warning":
            speak_async(
                "1 minute remaining until unlock.",
                force=True,
                voice_override=sel_voice_id,
                interrupt=True,
            )
        elif choice == "Voice: 30s Warning":
            speak_async(
                "30 seconds remaining until unlock.",
                force=True,
                voice_override=sel_voice_id,
                interrupt=True,
            )
        elif choice == "Unlock Chime (3-Tone)":
            threading.Thread(target=play_unlock_chimes, daemon=True).start()
        elif choice == "Full 10s Dry-Run Lockout":
            if dry_run_lock_active or cooldown_active:
                return
            if is_in_trade_tamper_locked():
                messagebox.showwarning(
                    "In Trade — Dry-Run Disabled",
                    "Dry-Run OS Lockout is disabled while an active daytrade is open.\n\n"
                    "Close your trade first so you are 100% flat before testing an OS lockout.",
                    parent=active_parent,
                )
                return
            if not _confirm_dry_run_lockout():
                return
            log_event(
                "SESSION",
                "User triggered 10-second Dry-Run OS Lockout test from Pre-Flight.",
            )

            def _dry_run_seq():
                global dry_run_lock_active
                dry_run_lock_active = True
                try:
                    pf.after(
                        0,
                        lambda: (
                            _sync_prefs_modal_state(),
                            refresh_smart_dimming(),
                        ),
                    )
                except Exception:
                    pass
                try:
                    for _ in range(4):
                        winsound.Beep(2600, 180)
                        time.sleep(0.04)
                    try:
                        ctypes.windll.user32.LockWorkStation()
                    except Exception:
                        pass
                    time.sleep(0.35)
                    speak_async(
                        "Dry run lockout test started. Locked out for 10 seconds.",
                        force=True,
                        voice_override=sel_voice_id,
                        interrupt=True,
                    )
                    lock_started_ts = time.time()
                    end_t = lock_started_ts + 10.0
                    confirmed_locked = is_workstation_locked()
                    last_early_unlock_ts = 0.0
                    while time.time() < end_t:
                        now_ts = time.time()
                        rem = max(0, int(round(end_t - now_ts)))
                        currently_locked = is_workstation_locked()
                        if currently_locked:
                            confirmed_locked = True
                        else:
                            try:
                                ctypes.windll.user32.LockWorkStation()
                            except Exception:
                                pass
                            if (
                                confirmed_locked
                                and (now_ts - lock_started_ts) >= 1.5
                                and rem >= 1
                                and (now_ts - last_early_unlock_ts) >= 2.0
                            ):
                                confirmed_locked = False
                                last_early_unlock_ts = now_ts
                                log_event(
                                    "SESSION",
                                    f"Early unlock attempt detected during 10s Dry-Run Lockout "
                                    f"({rem}s remaining) — workstation immediately re-locked.",
                                )
                                time.sleep(0.30)
                                rem_voice = max(1, int(round(end_t - time.time())))
                                speak_async(
                                    _format_exact_remaining_voice_msg(rem_voice),
                                    force=True,
                                    voice_override=sel_voice_id,
                                    interrupt=True,
                                )
                        time.sleep(0.20)
                    stop_active_tts()
                    play_unlock_chimes()
                    speak_async(
                        "Dry run lockout complete. You may unlock your screen.",
                        force=True,
                        voice_override=sel_voice_id,
                        interrupt=True,
                    )
                    log_event(
                        "SESSION",
                        "10-second Dry-Run OS Lockout test completed cleanly.",
                    )
                except Exception:
                    pass
                finally:
                    dry_run_lock_active = False
                    try:
                        pf.after(
                            0,
                            lambda: (
                                _sync_prefs_modal_state(),
                                refresh_smart_dimming(),
                            ),
                        )
                    except Exception:
                        pass

            threading.Thread(target=_dry_run_seq, daemon=True).start()

    def open_preferences_audio_dialog():
        existing_dlg = _prefs_modal_refs.get("dlg")
        if existing_dlg is not None:
            try:
                if existing_dlg.winfo_exists():
                    existing_dlg.lift()
                    existing_dlg.focus_set()
                    return
            except Exception:
                pass

        try:
            initial_poll_str = str(max(1, int(float(str(var_poll.get()).strip()))))
        except Exception:
            initial_poll_str = str(max(1, int(config.get("poll_interval", 2))))

        dlg = tk.Toplevel(pf)
        dlg.withdraw()
        if os.path.exists(ICON_PATH):
            try:
                dlg.iconbitmap(ICON_PATH)
            except Exception:
                pass
        apply_dark_title_bar(dlg)
        dlg.title("PnL Enforcer — Preferences & Audio")
        dlg.config(bg="#0d1117", padx=20, pady=16)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.transient(pf)
        _prefs_modal_refs["dlg"] = dlg

        tk.Label(
            dlg,
            text="⚙  PREFERENCES & AUDIO SETTINGS",
            font=("Arial", 11, "bold"),
            fg="#5dade2",
            bg="#0d1117",
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        def _make_prefs_section(sec_title, bar_col):
            outer = tk.Frame(
                dlg,
                bg="#131922",
                bd=0,
                highlightthickness=1,
                highlightbackground="#243040",
            )
            outer.pack(fill="x", pady=(0, 10))
            NeonBarCanvas(
                outer, core_color=bar_col, card_bg="#131922", glow_on=True
            ).pack(side="left", fill="y")
            body = tk.Frame(outer, bg="#131922", padx=14, pady=10)
            body.pack(side="left", fill="both", expand=True)
            hdr_r = tk.Frame(body, bg="#131922")
            hdr_r.pack(fill="x", pady=(0, 4))
            tk.Label(
                hdr_r,
                text=sec_title,
                font=("Arial", 9, "bold"),
                fg="#8ec5fc",
                bg="#131922",
                anchor="w",
            ).pack(side="left")
            tk.Frame(body, bg="#222d3d", height=1).pack(fill="x", pady=(0, 6))
            return body, hdr_r

        # Section 1: Session Behavior
        sec1, sec1_hdr = _make_prefs_section("SESSION BEHAVIOR", "#38bdf8")
        lbl_session_lock = tk.Label(
            sec1_hdr,
            text="",
            font=("Arial", 8, "bold"),
            fg="#fbbf24",
            bg="#131922",
        )
        lbl_session_lock.pack(side="right")
        _prefs_modal_refs["lbl_session_lock"] = lbl_session_lock

        cb_reset925 = make_glass_checkbutton(
            sec1,
            text="Start Fresh on Rulebook Switch (9:30 AM & 4:00 PM)",
            variable=var_reset925,
            font=("Arial", 10, "bold"),
            fg="#dce4ee",
            bg="#131922",
            anchor="w",
        )
        cb_reset925.pack(fill="x", pady=2)
        attach_tooltip(
            cb_reset925,
            "If checked, at 9:30 AM ET (RTH Open) and 4:00 PM ET (After-Hours Open) your active Rulebook\n"
            "starts fresh from current flat equity so an earlier session's profit peak won't immediately\n"
            "trigger a tier ratchet or trailing stop. (Your SESSION HIGH column still preserves your full-day peak.)"
        )
        _prefs_modal_refs["cb_reset925"] = cb_reset925

        cb_ignore_prepos = make_glass_checkbutton(
            sec1,
            text="Ignore Pre-Existing Positions on Launch",
            variable=var_ignore_preexisting,
            font=("Arial", 10, "bold"),
            fg="#dce4ee",
            bg="#131922",
            anchor="w",
        )
        cb_ignore_prepos.pack(fill="x", pady=2)
        attach_tooltip(cb_ignore_prepos, prepos_tip)
        _prefs_modal_refs["cb_ignore_prepos"] = cb_ignore_prepos

        # Section 2: Audio & Voice Cues
        sec2, _sec2_hdr = _make_prefs_section("AUDIO & VOICE CUES", "#10b981")
        r_audio = tk.Frame(sec2, bg="#131922")
        r_audio.pack(fill="x", pady=2)
        cb_voice = make_glass_checkbutton(
            r_audio,
            text="Verbal Lockout Voice Cues",
            variable=var_voice_cues,
            font=("Arial", 10, "bold"),
            fg="#dce4ee",
            bg="#131922",
            anchor="w",
        )
        cb_voice.pack(side="left", padx=(0, 18))
        attach_tooltip(
            cb_voice,
            "Uses Windows Speech Synthesis to speak the lockout reason, duration, and 2s/15s\n"
            "post-lock flat check confirmations out loud when a Penalty Box or Daily Lockout triggers,\n"
            "plus whole-minute / 30-second countdown reminders and an exact remaining time callout\n"
            "whenever an early screen-unlock attempt is detected and immediately re-locked."
        )

        cb_chime = make_glass_checkbutton(
            r_audio,
            text="Upside Tier Chime & Glow",
            variable=var_upside_chime,
            font=("Arial", 10, "bold"),
            fg="#4ec994",
            bg="#131922",
            anchor="w",
        )
        cb_chime.pack(side="left")
        attach_tooltip(
            cb_chime,
            "When you close a winning trade (100% flat) that unlocks a higher profit ratchet tier\n"
            "(Extended-Hours Profit Lock or RTH Tier 2 / 3 / 4), plays a pleasant 4-note ascending chime\n"
            "and glows the HUD status bar emerald green for 3 seconds."
        )

        r_test_audio = tk.Frame(sec2, bg="#131922")
        r_test_audio.pack(fill="x", pady=(6, 2))
        lbl_preview_audio = tk.Label(
            r_test_audio,
            text="Voice / Cue:",
            font=("Arial", 9, "bold"),
            fg="#97a7b9",
            bg="#131922",
            anchor="w",
        )
        lbl_preview_audio.pack(side="left", padx=(0, 6))

        voice_choices = [lbl for lbl, _ in TTS_VOICE_CATALOG]
        voice_dropdown = DarkDropdownMenu(
            dlg,
            tearoff=0,
            font=("Arial", 9, "bold"),
            bg="#141820",
            fg="#e2e8f0",
            activebackground="#1e293b",
            activeforeground="#ffffff",
        )
        for v_lbl in voice_choices:
            voice_dropdown.add_command(
                label=v_lbl, command=lambda v=v_lbl: var_tts_voice.set(v)
            )
        voice_menu = make_stadium_button(
            r_test_audio,
            text=var_tts_voice.get(),
            chevron="▾",
            chevron_color="#64748b",
            font=("Arial", 9, "bold"),
            fill_color="#141820",
            fill_top_color="#1c212b",
            border_color="#2e3746",
            hover_fill="#181e28",
            hover_fill_top="#232a36",
            hover_border="#475569",
            fg="#cbd5e1",
            canvas_bg="#131922",
            width=124,
            height=26,
            pad_x=20,
            menu=voice_dropdown,
        )
        voice_menu.pack(side="left", padx=(0, 6))
        attach_tooltip(
            voice_menu,
            "Choose the Windows Speech voice used for Verbal Lockout Voice Cues:\n"
            "• Zira (Female) — Clear female voice (Default)\n"
            "• Mark (Male) — Natural Windows OneCore male voice\n"
            "• David (Male) — Deep classic male voice"
        )

        audio_dropdown = DarkDropdownMenu(
            dlg,
            tearoff=0,
            font=("Arial", 9, "bold"),
            bg="#141820",
            fg="#e2e8f0",
            activebackground="#1e293b",
            activeforeground="#ffffff",
        )
        for a_lbl in audio_choices:
            audio_dropdown.add_command(
                label=a_lbl, command=lambda a=a_lbl: var_audio_test.set(a)
            )
        audio_menu = make_stadium_button(
            r_test_audio,
            text=var_audio_test.get(),
            chevron="▾",
            chevron_color="#64748b",
            font=("Arial", 9, "bold"),
            fill_color="#141820",
            fill_top_color="#1c212b",
            border_color="#2e3746",
            hover_fill="#181e28",
            hover_fill_top="#232a36",
            hover_border="#475569",
            fg="#cbd5e1",
            canvas_bg="#131922",
            width=222,
            height=26,
            pad_x=22,
            menu=audio_dropdown,
        )
        audio_menu.pack(side="left", padx=(0, 6))

        btn_test_audio = make_stadium_button(
            r_test_audio,
            text="🔊 Test",
            font=("Arial", 9, "bold"),
            fill_color="#141820",
            fill_top_color="#1c212b",
            border_color="#2e3746",
            hover_fill="#181e28",
            hover_fill_top="#232a36",
            hover_border="#475569",
            fg="#dce4ee",
            canvas_bg="#131922",
            width=76,
            height=26,
            pad_x=16,
            command=play_selected_test_audio,
        )
        btn_test_audio.pack(side="left")
        _prefs_modal_refs["btn_test_audio"] = btn_test_audio
        audio_test_tip = (
            "Select a voice and any sound or voice announcement from the dropdown, then click '🔊 Test'\n"
            "to preview how it sounds at your current speaker/headset volume."
        )
        attach_tooltip(lbl_preview_audio, audio_test_tip)
        attach_tooltip(audio_menu, audio_test_tip)
        attach_tooltip(btn_test_audio, audio_test_tip)

        # Section 3: System & Telemetry
        sec3, _sec3_hdr = _make_prefs_section("SYSTEM & TELEMETRY", "#5dade2")
        r_poll = tk.Frame(sec3, bg="#131922")
        r_poll.pack(fill="x", pady=2)
        lbl_poll = tk.Label(
            r_poll,
            text="API Poll Interval (s):",
            font=("Arial", 10, "bold"),
            fg="#97a7b9",
            bg="#131922",
            anchor="w",
        )
        lbl_poll.pack(side="left", padx=(0, 8))
        ent_poll = make_entry(r_poll, var_poll, width=5)
        ent_poll.pack(side="left")
        poll_tip = (
            "How often (in seconds) Enforcer polls your broker API for live equity and positions.\n"
            "Recommended: 2 seconds (30 requests/min — well within Schwab & Webull rate limits)."
        )
        attach_tooltip(lbl_poll, poll_tip)
        attach_tooltip(ent_poll, poll_tip)

        cb_auto_share = make_glass_checkbutton(
            r_poll,
            text="Auto-Share Safe Logs (Beta Opt-In)",
            variable=var_auto_share_logs,
            font=("Arial", 10, "bold"),
            fg="#7dd3fc",
            bg="#131922",
            accent_hex="#0284c7",
            check_hex="#38bdf8",
            anchor="e",
        )
        cb_auto_share.pack(side="right", padx=(24, 0))
        attach_tooltip(
            cb_auto_share,
            "Beta Diagnostic Telemetry (Strictly Opt-In — OFF by Default):\n"
            "When enabled, PnL Enforcer automatically uploads yesterday's balance-redacted log\n"
            "(enforcer_log_YYYY-MM-DD_sanitized.txt) in the background when you launch the app.\n"
            "• All total account balances ($[REDACTED]), Windows usernames (~), and order IDs are scrubbed.\n"
            f"• Tagged only with your anonymous 6-character Tester ID ({config.get('anonymous_tester_id', '')})."
        )

        lbl_poll_err = tk.Label(
            sec3,
            text="",
            font=("Arial", 8, "bold"),
            fg="#f87171",
            bg="#131922",
            anchor="w",
        )

        trace_v_id = var_tts_voice.trace_add(
            "write", lambda *_: voice_menu.config(text=var_tts_voice.get())
        )
        trace_a_id = var_audio_test.trace_add(
            "write", lambda *_: audio_menu.config(text=var_audio_test.get())
        )

        _prefs_cleaned = {"done": False}

        def _cleanup_prefs_modal(restore_invalid_poll=True):
            if _prefs_cleaned["done"]:
                return
            _prefs_cleaned["done"] = True
            if restore_invalid_poll:
                raw_p = str(var_poll.get()).strip()
                try:
                    p_chk = float(raw_p)
                    if not raw_p or p_chk < 1.0:
                        var_poll.set(initial_poll_str)
                except Exception:
                    var_poll.set(initial_poll_str)
            for _var_obj, _tid in (
                (var_tts_voice, trace_v_id),
                (var_audio_test, trace_a_id),
            ):
                try:
                    _var_obj.trace_remove("write", _tid)
                except Exception:
                    pass
            for k in list(_prefs_modal_refs.keys()):
                _prefs_modal_refs[k] = None
            try:
                dlg.grab_release()
            except Exception:
                pass
            try:
                if dlg.winfo_exists():
                    dlg.destroy()
            except Exception:
                pass

        _prefs_modal_refs["cleanup_fn"] = lambda: _cleanup_prefs_modal(
            restore_invalid_poll=True
        )

        def _on_apply_prefs(*_):
            if dry_run_lock_active or cooldown_active:
                return "break"
            raw_p = str(var_poll.get()).strip()
            try:
                if not raw_p:
                    raise ValueError("empty")
                p_num = float(raw_p)
                if p_num < 1.0:
                    raise ValueError("lt1")
                p_val = int(p_num)
            except Exception:
                lbl_poll_err.config(
                    text="API Poll Interval must be a number >= 1 second."
                )
                if not lbl_poll_err.winfo_manager():
                    lbl_poll_err.pack(fill="x", pady=(4, 0))
                    try:
                        dlg.update_idletasks()
                    except Exception:
                        pass
                try:
                    ent_poll.focus_set()
                    ent_poll.select_range(0, "end")
                except Exception:
                    pass
                return "break"
            var_poll.set(str(p_val))
            _cleanup_prefs_modal(restore_invalid_poll=False)
            return "break"

        def _on_cancel_prefs(*_):
            if dry_run_lock_active or cooldown_active:
                return "break"
            _cleanup_prefs_modal(restore_invalid_poll=True)
            return "break"

        def _on_dlg_destroy(event):
            if event.widget is dlg and not _prefs_cleaned["done"]:
                _cleanup_prefs_modal(restore_invalid_poll=True)

        dlg.bind("<Destroy>", _on_dlg_destroy)

        b_row = tk.Frame(dlg, bg="#0d1117")
        b_row.pack(fill="x", pady=(2, 0))
        tk.Label(
            b_row,
            text="Click 'SAVE & LAUNCH / SAVE CHANGES' on main screen to apply to disk.",
            font=("Arial", 8),
            fg="#64748b",
            bg="#0d1117",
            anchor="w",
        ).pack(side="left", padx=(0, 14))
        btn_done = make_stadium_button(
            b_row,
            text="Done ✓",
            font=("Arial", 9, "bold"),
            fill_color="#0d3b20",
            fill_top_color="#14532d",
            border_color="#10b981",
            hover_fill="#114b29",
            hover_fill_top="#196638",
            hover_border="#34d399",
            fg="#ffffff",
            canvas_bg="#0d1117",
            width=116,
            height=34,
            auto_width=False,
            command=_on_apply_prefs,
        )
        btn_done.pack(side="right")
        _prefs_modal_refs["btn_done"] = btn_done

        dlg.protocol("WM_DELETE_WINDOW", _on_cancel_prefs)
        dlg.bind("<Escape>", _on_cancel_prefs)
        dlg.bind("<Return>", _on_apply_prefs)
        _sync_prefs_modal_state()
        center_dialog_over_parent(dlg, parent=pf)
        dlg.grab_set()
        dlg.focus_set()
        pf.wait_window(dlg)

    lbl_prefs_summary = tk.Label(
        c3,
        text="",
        font=("Arial", 9, "bold"),
        fg="#94a3b8",
        bg="#131922",
        anchor="w",
    )
    lbl_prefs_summary.pack(fill="x", pady=(0, 4))

    def _refresh_card3_prefs_summary(*_):
        if pf_timer_state.get("closing"):
            return
        try:
            if not pf.winfo_exists() or not lbl_prefs_summary.winfo_exists():
                return
        except Exception:
            return
        sw_txt = "Reset" if var_reset925.get() else "Carry"
        pos_txt = "Ignored" if var_ignore_preexisting.get() else "Tracked"
        vc_txt = "ON" if var_voice_cues.get() else "OFF"
        raw_p = str(var_poll.get()).strip()
        try:
            p_sec = max(1, int(float(raw_p))) if raw_p else "?"
        except Exception:
            p_sec = "?"
        log_txt = "ON" if var_auto_share_logs.get() else "OFF"
        try:
            lbl_prefs_summary.config(
                text=(
                    f"Rulebook Switch: {sw_txt} · Swings: {pos_txt} · "
                    f"Voice: {vc_txt} · Poll: {p_sec}s · Safe Logs: {log_txt}"
                )
            )
        except Exception:
            pass

    for _pv in (
        var_reset925,
        var_ignore_preexisting,
        var_voice_cues,
        var_upside_chime,
        var_poll,
        var_auto_share_logs,
    ):
        _pv.trace_add("write", _refresh_card3_prefs_summary)
    _refresh_card3_prefs_summary()
    attach_tooltip(
        lbl_prefs_summary,
        "Quick summary of active Session Behavior, Voice Cue, Poll Rate, and Beta Log preferences.\n"
        "Click '⚙ Preferences & Audio...' below to customize them."
    )

    r_c3_actions = tk.Frame(c3, bg="#131922")
    r_c3_actions.pack(fill="x", pady=(4, 0))
    btn_review_ignored = make_stadium_button(
        r_c3_actions,
        text="🛡️ Positions (0)",
        font=("Arial", 8, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#475569",
        fg="#94a3b8",
        canvas_bg="#131922",
        width=136,
        height=24,
        pad_x=14,
        command=lambda: show_preexisting_positions_dialog(from_launch=False),
    )
    btn_review_ignored.pack(side="left")
    attach_tooltip(btn_review_ignored, prepos_tip)
    _refresh_ignored_positions_pill()

    btn_prefs_card3 = make_stadium_button(
        r_c3_actions,
        text="⚙ Preferences & Audio...",
        font=("Arial", 8, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#38bdf8",
        fg="#cbd5e1",
        canvas_bg="#131922",
        width=176,
        height=24,
        pad_x=16,
        command=open_preferences_audio_dialog,
    )
    btn_prefs_card3.pack(side="right")
    attach_tooltip(
        btn_prefs_card3,
        "Open Preferences & Audio Settings:\n"
        "• Session Behavior: Start Fresh on Rulebook Switch & Ignore Pre-Existing Positions\n"
        "• Audio & Voice Cues: Voice Cues, Upside Chime, Voice Selector & Sound/Dry-Run Tester\n"
        "• System & Telemetry: API Poll Interval (s) & Auto-Share Safe Logs (Beta Opt-In)"
    )

    # ==========================================================
    # RIGHT COLUMN: 4. EXTENDED HOURS RULEBOOK, 5. REGULAR HOURS RULEBOOK
    # ==========================================================
    c4, c4_halos, c4_bar, c4_title_lbl, c4_badge_pill = make_card(
        right_col,
        "▶  4. EXTENDED HOURS RULEBOOK (Pre-Market & After-Hours)",
        "Active before 9:30 AM and after 4:00 PM ET. Hitting your Max Loss "
        "or Profit Lock triggers Card 2.",
        accent="#5dade2",
        bar_color="#10b981",
        return_parts=True
    )

    def _accentuate_max_loss_row(lbl_w, ent_w):
        """Visually elevates Starting Max Loss fields above soft warning alarms."""
        lbl_w.config(font=("Arial", 11, "bold"), fg="#f87171")
        ent_w.config(
            font=("Consolas", 12, "bold"),
            bg="#35141d",
            fg="#ffffff",
            highlightbackground="#dc2626",
            highlightcolor="#f87171",
            highlightthickness=2,
        )
        ent_w._orig_rim = "#dc2626"

    lbl_pm_max, ent_pm_max, _, _ = make_dual_field_row(
        c4,
        "Starting Max Loss ($):",
        dollar_vars["pm_max_loss"],
        None,
        None,
        fg1="#f87171",
        tip1=(
            "Extended-Hours Starting Max Loss:\n"
            "Your initial worst-case Extended-Hours loss limit before Profit Lock is triggered.\n"
            "If Extended-Hours Net PnL reaches this loss, it immediately triggers your Card 2\n"
            "Daily Stop Actions (Auto-Flatten Equities via Extended-Hours limit order,\n"
            "Kill Apps, and Windows OS Lock for the duration set in Card 2)."
        )
    )
    _accentuate_max_loss_row(lbl_pm_max, ent_pm_max)
    cb_pm_w1, ent_pm_w1, cb_pm_w2, ent_pm_w2 = make_dual_field_row(
        c4,
        "Warning Alarm 1 ($):",
        dollar_vars["pm_warn_1"],
        "Warning Alarm 2 ($):",
        dollar_vars["pm_warn_2"],
        cb_var1=var_pm_w1_on,
        cb_var2=var_pm_w2_on,
        tip1=(
            "Extended-Hours Warning Alarm 1:\n"
            "Sounds a warning siren (no flatten) when Extended-Hours Net PnL reaches this loss.\n"
            "Uncheck to disable Warning Alarm 1."
        ),
        tip2=(
            "Extended-Hours Warning Alarm 2:\n"
            "Sounds a second warning siren when Extended-Hours Net PnL reaches this deeper loss.\n"
            "Uncheck if you only want a single warning alarm before your Starting Max Loss."
        )
    )
    tk.Frame(c4, bg="#222d3d", height=1).pack(fill="x", pady=7)

    tk.Label(
        c4,
        text="PROFIT LOCK (Raises Daily Stop)",
        font=("Arial", 10, "bold"),
        fg="#8ec5fc",
        bg="#131922",
        anchor="w",
    ).pack(fill="x", pady=(0, 4))

    pm_tbl = tk.Frame(c4, bg="#131922")
    pm_tbl.pack(fill="x")
    pm_tbl.columnconfigure(0, weight=1, minsize=184)
    pm_tbl.columnconfigure(1, weight=0, minsize=86)
    pm_tbl.columnconfigure(2, weight=0)
    pm_tbl.columnconfigure(3, weight=0, minsize=24)
    pm_tbl.columnconfigure(4, weight=0, minsize=196)

    cb_pm_lock = make_glass_checkbutton(
        pm_tbl,
        text="Trailing Profit Lock",
        variable=var_pm_lock_on,
        font=("Arial", 10, "bold"),
        fg="#4ec994",
        bg="#131922",
        anchor="w",
    )
    cb_pm_lock.grid(row=0, column=0, sticky="w", pady=3)
    lbl_pm_trig = tk.Label(
        pm_tbl,
        text="At Profit ($):",
        font=("Arial", 10, "bold"),
        fg="#97a7b9",
        bg="#131922",
        anchor="e",
    )
    lbl_pm_trig.grid(row=0, column=1, sticky="e", padx=(4, 6), pady=3)
    ent_pm_trig = make_entry(pm_tbl, dollar_vars["pm_lock_trigger"], width=8)
    ent_pm_trig.grid(row=0, column=2, pady=3)
    lbl_pm_arrow = tk.Label(
        pm_tbl,
        text="→",
        font=("Arial", 11, "bold"),
        fg="#64748b",
        bg="#131922",
    )
    lbl_pm_arrow.grid(row=0, column=3, padx=4, pady=3)

    pm_fl_cell = tk.Frame(pm_tbl, bg="#131922")
    pm_fl_cell.grid(row=0, column=4, sticky="e", pady=3)
    lbl_pm_trail = tk.Label(
        pm_fl_cell,
        text="Trail Peak By ($):",
        font=("Arial", 10, "bold"),
        fg="#97a7b9",
        bg="#131922",
    )
    lbl_pm_trail.pack(side="left", padx=(0, 6))
    ent_pm_trail = make_entry(pm_fl_cell, dollar_vars["pm_trail_cushion"], width=8)
    ent_pm_trail.pack(side="right")

    pm_trig_tip = (
        "Extended-Hours Trailing Profit Lock:\n"
        "Once your closed Extended-Hours Realized PnL reaches +At Profit ($),\n"
        "this trailing stop replaces your Starting Max Loss as your active Daily Stop.\n"
        "• IMPORTANT: If Net PnL pulls back and touches this trailed stop, it triggers the\n"
        "  exact same Card 2 Daily Stop Actions (Auto-Flatten, Kill Apps, and OS Lock\n"
        "  for your Card 2 lock duration).\n"
        "Uncheck to disable Extended-Hours profit trailing."
    )
    pm_trail_tip = (
        "Extended-Hours Trailing Cushion ($):\n"
        "Once At Profit ($) is reached, your active Daily Stop trails behind\n"
        "your highest closed Realized PnL by this dollar amount.\n"
        "(Example: Trigger +$500 with $500 Trail locks your stop at $0.00 breakeven\n"
        "at +$500, and raises it to +$200 if you reach +$700.)\n"
        "• Hitting this trailed stop triggers your Card 2 Daily Stop Actions & OS Lock timer."
    )
    for _pmw in (cb_pm_lock, lbl_pm_trig, ent_pm_trig, lbl_pm_arrow):
        attach_tooltip(_pmw, pm_trig_tip)
    attach_tooltip(lbl_pm_trail, pm_trail_tip)
    attach_tooltip(ent_pm_trail, pm_trail_tip)

    c5, c5_halos, c5_bar, c5_title_lbl, c5_badge_pill = make_card(
        right_col,
        "▶  5. REGULAR HOURS RULEBOOK (9:30 AM – 4:00 PM)",
        "Starts at Base Tier 1 and ratchets your stop upward "
        "as realized profit grows. Hitting your stop triggers Card 2.",
        accent="#5dade2",
        bar_color="#34495e",
        expand=True,
        return_parts=True
    )

    def _apply_rulebook_aura(halos, bar_cv, title_w, badge_w, is_active):
        h0, outer_w = halos
        in_tr_lk = is_in_trade_tamper_locked()
        if is_active:
            h0.config(bg="#132e24", padx=1, pady=1)
            outer_w.config(highlightbackground="#1f5c43", highlightthickness=1)
            bar_cv.set_neon("#00e676", glow_on=True)
            title_w.config(fg="#4ade80")
            if badge_w is not None:
                badge_w.set_active(True, locked=in_tr_lk)
        else:
            h0.config(bg="#151d28", padx=1, pady=1)
            outer_w.config(highlightbackground="#243040", highlightthickness=1)
            bar_cv.set_neon("#334459", glow_on=False)
            title_w.config(fg="#7f8fa3")
            if badge_w is not None:
                badge_w.set_active(False, locked=in_tr_lk)

    def refresh_active_rulebook_highlight():
        pf_timer_state["rulebook_after_id"] = None
        if pf_timer_state["closing"]:
            return
        try:
            if not pf.winfo_exists():
                return
        except Exception:
            return
        rth_now = is_rth()
        _apply_rulebook_aura(
            c5_halos, c5_bar, c5_title_lbl, c5_badge_pill, is_active=rth_now
        )
        _apply_rulebook_aura(
            c4_halos, c4_bar, c4_title_lbl, c4_badge_pill, is_active=(not rth_now)
        )
        if not pf_timer_state["closing"]:
            try:
                pf_timer_state["rulebook_after_id"] = pf.after(
                    5000, refresh_active_rulebook_highlight
                )
            except Exception:
                pass

    refresh_active_rulebook_highlight()

    tk.Label(
        c5,
        text="BASE TIER 1 — Starting Daily Stop",
        font=("Arial", 10, "bold"),
        fg="#8ec5fc",
        bg="#131922",
        anchor="w"
    ).pack(fill="x", pady=(2, 4))

    lbl_t1_max, ent_t1_max, _, _ = make_dual_field_row(
        c5,
        "Starting Max Loss ($):",
        dollar_vars["t1_max_loss"],
        None,
        None,
        fg1="#f87171",
        tip1=(
            "RTH Base Tier 1 — Starting Max Loss:\n"
            "Your initial worst-case RTH loss limit before any profit ratchet tiers are unlocked.\n"
            "If Net PnL reaches this loss, it triggers your Card 2 Daily Stop Actions\n"
            "(Auto-Flatten Equities, Kill Apps, and Windows OS Lock for the duration set in Card 2)."
        )
    )
    _accentuate_max_loss_row(lbl_t1_max, ent_t1_max)
    cb_t1_w1, ent_t1_w1, cb_t1_w2, ent_t1_w2 = make_dual_field_row(
        c5,
        "Warning Alarm 1 ($):",
        dollar_vars["t1_warn_1"],
        "Warning Alarm 2 ($):",
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
            "Uncheck if you only want 1 warning alarm before your Starting Max Loss."
        )
    )

    tk.Frame(c5, bg="#222d3d", height=1).pack(fill="x", pady=8)

    tk.Label(
        c5,
        text="PROFIT RATCHET TIERS (Raises Daily Stop)",
        font=("Arial", 10, "bold"),
        fg="#8ec5fc",
        bg="#131922",
        anchor="w",
    ).pack(fill="x", pady=(0, 6))

    tbl = tk.Frame(c5, bg="#131922")
    tbl.pack(fill="x")
    tbl.columnconfigure(0, weight=1, minsize=184)
    tbl.columnconfigure(1, weight=0, minsize=86)
    tbl.columnconfigure(2, weight=0)
    tbl.columnconfigure(3, weight=0, minsize=24)
    tbl.columnconfigure(4, weight=0, minsize=196)

    tier_rows = [
        (
            "Tier 2 — Fixed Stop",
            var_t2_on,
            dollar_vars["t2_trigger"],
            "Stop Level ($):",
            dollar_vars["t2_max_loss"],
            "#dce4ee",
            (
                "RTH Tier 2 — Fixed Daily Stop Ratchet:\n"
                "Once your closed Realized PnL reaches 'At Profit ($)', your active Daily Stop\n"
                "moves to 'Stop Level ($)' — supports negative, zero, or positive PnL levels!\n"
                "• Examples: Enter -1000 for a -$1,000 tightened stop, 0 for breakeven, or 250 for a +$250 profit lock.\n"
                "• If 'Stop Level ($)' is below $0, a warning siren sounds if PnL pulls back to $0.00.\n"
                "• Hitting 'Stop Level ($)' triggers your Card 2 Daily Stop Actions.\n"
                "Uncheck to skip Tier 2."
            )
        ),
        (
            "Tier 3 — Fixed Stop",
            var_t3_on,
            dollar_vars["t3_trigger"],
            "Stop Level ($):",
            dollar_vars["t3_max_loss"],
            "#dce4ee",
            (
                "RTH Tier 3 — Fixed Daily Stop Ratchet:\n"
                "Once your closed Realized PnL reaches 'At Profit ($)', your active Daily Stop\n"
                "moves to 'Stop Level ($)' — supports negative, zero, or positive PnL levels!\n"
                "• Examples: Enter -500 for a -$500 tightened stop, 0 for $0.00 breakeven, or 250 for a +$250 locked profit stop.\n"
                "• If 'Stop Level ($)' is below $0, a warning siren sounds if PnL pulls back to $0.00.\n"
                "• Hitting 'Stop Level ($)' triggers your Card 2 Daily Stop Actions.\n"
                "Uncheck to skip Tier 3."
            )
        ),
        (
            "Tier 4 — Trailing Lock",
            var_t4_on,
            dollar_vars["t4_trigger"],
            "Trail Peak By ($):",
            dollar_vars["t4_trail"],
            "#4ec994",
            (
                "RTH Tier 4 — Dynamic Trailing Profit Stop:\n"
                "Once your closed Realized PnL reaches 'At Profit ($)', your active Daily Stop\n"
                "locks in green and trails behind your highest realized PnL peak by 'Trail Peak By ($)'.\n"
                "(Example: At Profit +$1,000 with $500 Trail locks in +$500 minimum, and ratchets\n"
                "to +$900 if your closed Realized PnL reaches +$1,400.)\n"
                "• IMPORTANT: If Net PnL pulls back and touches this trailed stop, it triggers the\n"
                "  exact same Card 2 Daily Stop Actions (Auto-Flatten, Kill Apps, and OS Lock\n"
                "  for your Card 2 lock duration).\n"
                "Uncheck to disable Tier 4."
            )
        )
    ]

    tier_widget_refs = []
    for idx, (
        t_name, t_cb_var, trig_var, fl_lbl, fl_var, cb_fg_col, t_tip
    ) in enumerate(tier_rows):
        cb_t = make_glass_checkbutton(
            tbl,
            text=t_name,
            variable=t_cb_var,
            font=("Arial", 10, "bold"),
            fg=cb_fg_col,
            bg="#131922",
            anchor="w"
        )
        cb_t.grid(row=idx, column=0, sticky="w", pady=4)

        lbl_trig = tk.Label(
            tbl,
            text="At Profit ($):",
            font=("Arial", 10, "bold"),
            fg="#97a7b9",
            bg="#131922",
            anchor="e",
        )
        lbl_trig.grid(row=idx, column=1, sticky="e", padx=(4, 6), pady=4)

        ent_trig = make_entry(tbl, trig_var, width=8)
        ent_trig.grid(row=idx, column=2, pady=4)

        lbl_arrow = tk.Label(
            tbl,
            text="→",
            font=("Arial", 11, "bold"),
            fg="#64748b",
            bg="#131922",
        )
        lbl_arrow.grid(row=idx, column=3, padx=4, pady=4)

        fl_cell = tk.Frame(tbl, bg="#131922")
        fl_cell.grid(row=idx, column=4, pady=4, sticky="e")
        lbl_fl = tk.Label(
            fl_cell,
            text=fl_lbl,
            font=("Arial", 10, "bold"),
            fg="#97a7b9",
            bg="#131922"
        )
        lbl_fl.pack(side="left", padx=(0, 6))
        ent_fl = make_entry(fl_cell, fl_var, width=8)
        ent_fl.pack(side="right")

        attach_tooltip(cb_t, t_tip)
        attach_tooltip(lbl_trig, t_tip)
        attach_tooltip(ent_trig, t_tip)
        attach_tooltip(lbl_arrow, t_tip)
        attach_tooltip(lbl_fl, t_tip)
        attach_tooltip(ent_fl, t_tip)
        tier_widget_refs.append(
            (t_cb_var, cb_t, lbl_trig, ent_trig, lbl_arrow, lbl_fl, ent_fl, cb_fg_col)
        )

    # --- INTERACTIVE SMART DIMMING LOGIC ---
    _tamper_sync_guard = {"busy": False}

    def _refresh_c1_tamper_badge():
        cur_s, req_l, next_s, _full_s, _is_en = get_loss_streak_status()
        in_tr = is_in_trade_tamper_locked()
        if in_tr and cur_s > 0 and config.get("enable_consec_loss_cooldown", False):
            t_str = f"🔒 IN TRADE & STREAK {cur_s}/{req_l} — LOCKED"
            fg_c = "#fecaca" if cur_s >= (req_l - 1) else "#fde68a"
            bg_c = "#5c1919" if cur_s >= (req_l - 1) else "#451a03"
        elif in_tr:
            t_str = "🔒 IN TRADE — LOCKED"
            fg_c = "#fde68a"
            bg_c = "#451a03"
        elif cur_s > 0 and config.get("enable_consec_loss_cooldown", False):
            t_str = f"🔒 STREAK {cur_s}/{req_l} ({_format_countdown_mm_ss(next_s)}) — LOCKED"
            fg_c = "#fecaca" if cur_s >= (req_l - 1) else "#fde68a"
            bg_c = "#5c1919" if cur_s >= (req_l - 1) else "#451a03"
        elif var_tilt_cd.get():
            t_str = "🔒 Locks on active streak"
            fg_c = "#7dd3fc"
            bg_c = "#142334"
        else:
            t_str = "🔒 Locks on active streak"
            fg_c = "#64748b"
            bg_c = "#131922"
        if (
            c1_tamper_lbl.cget("text") != t_str
            or c1_tamper_lbl.cget("fg") != fg_c
            or c1_tamper_lbl.cget("bg") != bg_c
        ):
            c1_tamper_lbl.config(text=t_str, fg=fg_c, bg=bg_c)

        c2_txt = "🔒 IN TRADE — LOCKED" if in_tr else ""
        c2_fg = "#fde68a" if in_tr else "#64748b"
        c2_bg = "#451a03" if in_tr else "#131922"
        if (
            c2_tamper_lbl.cget("text") != c2_txt
            or c2_tamper_lbl.cget("fg") != c2_fg
            or c2_tamper_lbl.cget("bg") != c2_bg
        ):
            c2_tamper_lbl.config(text=c2_txt, fg=c2_fg, bg=c2_bg)

    def _style_locked_entry(ent, is_armed):
        if is_armed:
            ent.config(
                state="disabled",
                disabledforeground="#fde68a",
                highlightbackground="#b45309",
            )
        else:
            ent.config(
                state="disabled",
                disabledforeground="#475569",
                highlightbackground=getattr(ent, "_orig_rim", "#2e526e"),
            )

    def _restore_entry_rim(ent):
        ent.config(
            disabledforeground="#475569",
            highlightbackground=getattr(ent, "_orig_rim", "#2e526e"),
        )

    def refresh_smart_dimming(*_):
        if _tamper_sync_guard["busy"]:
            return
        in_trade_locked = is_in_trade_tamper_locked()
        tamper_locked = is_tilt_streak_tamper_locked()

        if in_trade_locked:
            _tamper_sync_guard["busy"] = True
            try:
                var_alarms_only.set(bool(config.get("alarms_only_mode", False)))
                var_open_flat.set(
                    bool(config.get("enable_open_flatten", False))
                )
                _tilt_cd_popup_guard["suppress"] = True
                try:
                    var_tilt_cd.set(
                        bool(config.get("enable_consec_loss_cooldown", False))
                    )
                finally:
                    _tilt_cd_popup_guard["suppress"] = False
                var_tilt_count.set(
                    str(
                        max(
                            2,
                            int(round(float(config.get("consec_loss_count", 3)))),
                        )
                    )
                )
                var_tilt_window.set(
                    f"{config.get('consec_loss_window_mins', 15.0):g}"
                )
                var_open_cd.set(bool(config.get("enable_open_cooldown", False)))
                var_cd_mins.set(f"{config.get('open_cooldown_mins', 1.0):g}")
                var_flatten.set(bool(config.get("enable_auto_flatten", False)))
                _opt_waiver_guard["suppress"] = True
                try:
                    var_flatten_options.set(
                        bool(
                            config.get("enable_flatten_options", False)
                            and is_options_waiver_verified(config)
                        )
                    )
                finally:
                    _opt_waiver_guard["suppress"] = False
                var_kill_tos.set(bool(config.get("enable_kill_tos", False)))
                var_kill_wb.set(bool(config.get("enable_kill_webull", False)))
                var_lock_os.set(bool(config.get("enable_lock_os", False)))
                var_daily_lock_mins.set(
                    f"{config.get('daily_lock_mins', 15.0):g}"
                )
                var_reset925.set(bool(config.get("reset_at_925", True)))
                _ignore_prepos_guard["suppress"] = True
                try:
                    var_ignore_preexisting.set(
                        bool(config.get("ignore_preexisting_positions", True))
                    )
                finally:
                    _ignore_prepos_guard["suppress"] = False
                var_reanchor.set(False)
                var_pm_w1_on.set(bool(config.get("enable_pm_warn_1", True)))
                var_pm_w2_on.set(bool(config.get("enable_pm_warn_2", True)))
                var_pm_lock_on.set(bool(config.get("enable_pm_lock", True)))
                var_t1_w1_on.set(bool(config.get("enable_t1_warn_1", True)))
                var_t1_w2_on.set(bool(config.get("enable_t1_warn_2", True)))
                var_t2_on.set(bool(config.get("enable_t2", True)))
                var_t3_on.set(bool(config.get("enable_t3", True)))
                var_t4_on.set(bool(config.get("enable_t4", True)))
                for k in dollar_keys:
                    dollar_vars[k].set(
                        _fmt_ui_dollar(k, config.get(k, DEFAULT_CONFIG[k]))
                    )
            finally:
                _tamper_sync_guard["busy"] = False
        elif tamper_locked:
            _tamper_sync_guard["busy"] = True
            try:
                if not config.get("alarms_only_mode", False) and var_alarms_only.get():
                    var_alarms_only.set(False)
                if not var_tilt_cd.get():
                    var_tilt_cd.set(True)
                var_tilt_count.set(
                    str(max(2, int(round(float(config.get("consec_loss_count", 3))))))
                )
                dollar_vars["consec_loss_min_dollars"].set(
                    _fmt_ui_dollar(
                        "consec_loss_min_dollars",
                        config.get("consec_loss_min_dollars", 25.0),
                    )
                )
                dollar_vars["consec_win_reset_dollars"].set(
                    _fmt_ui_dollar(
                        "consec_win_reset_dollars",
                        config.get("consec_win_reset_dollars", 10.0),
                    )
                )
                var_tilt_window.set(
                    f"{config.get('consec_loss_window_mins', 15.0):g}"
                )
                if config.get("enable_open_cooldown", False):
                    if not var_open_cd.get():
                        var_open_cd.set(True)
                    var_cd_mins.set(
                        f"{config.get('open_cooldown_mins', 1.0):g}"
                    )
                if var_reanchor.get():
                    var_reanchor.set(False)
            finally:
                _tamper_sync_guard["busy"] = False

        _refresh_c1_tamper_badge()
        _refresh_reanchor_pill()
        _refresh_ignored_positions_pill()
        _render_card3_telemetry_live()
        rth_now = is_rth()
        _apply_rulebook_aura(
            c5_halos, c5_bar, c5_title_lbl, c5_badge_pill, is_active=rth_now
        )
        _apply_rulebook_aura(
            c4_halos,
            c4_bar,
            c4_title_lbl,
            c4_badge_pill,
            is_active=(not rth_now),
        )

        broker_acct_capsule.configure(
            cursor="arrow" if in_trade_locked else "hand2"
        )
        btn_full_risk.config(state="disabled" if in_trade_locked else "normal")
        btn_half_risk.config(state="disabled" if in_trade_locked else "normal")
        _refresh_reanchor_pill()
        _refresh_tilt_filter_pill()
        _sync_prefs_modal_state()
        if btn_restore_def is not None:
            btn_restore_def.config(
                state="disabled" if in_trade_locked else "normal"
            )
        if btn_save_def is not None:
            btn_save_def.config(
                state="disabled" if in_trade_locked else "normal"
            )
        if btn_alarms_only is not None:
            ao_on_btn = bool(var_alarms_only.get())
            ao_locked_btn = in_trade_locked or (tamper_locked and not ao_on_btn)
            if ao_on_btn:
                btn_alarms_only.config(
                    text=(
                        "🔒 🔔 Alarms Only: ON"
                        if ao_locked_btn
                        else "🔔 Alarms Only: ON"
                    ),
                    fill_color="#78350f",
                    fill_top_color="#92400e",
                    border_color="#f59e0b",
                    hover_fill="#92400e",
                    hover_fill_top="#b45309",
                    hover_border="#fbbf24",
                    fg="#fef3c7",
                    disabledforeground="#fde68a",
                    state="disabled" if ao_locked_btn else "normal",
                )
            else:
                btn_alarms_only.config(
                    text=(
                        "🔒 🔔 Alarms Only: OFF"
                        if ao_locked_btn
                        else "🔔 Alarms Only: OFF"
                    ),
                    fill_color="#141820",
                    fill_top_color="#1c212b",
                    border_color="#475569",
                    hover_fill="#261f14",
                    hover_fill_top="#362b1a",
                    hover_border="#f59e0b",
                    fg="#cbd5e1",
                    disabledforeground="#526070",
                    state="disabled" if ao_locked_btn else "normal",
                )
        if btn_launch is not None:
            if dry_run_lock_active or cooldown_active:
                btn_launch.config(
                    text="🔒 DRY-RUN LOCKOUT ACTIVE...",
                    fill_color="#33220c",
                    fill_top_color="#473010",
                    border_color="#b45309",
                    hover_fill="#33220c",
                    hover_fill_top="#473010",
                    hover_border="#b45309",
                    fg="#fde68a",
                    disabledforeground="#fde68a",
                    state="disabled",
                )
            elif in_trade_locked:
                btn_launch.config(
                    text="💾 SAVE HUD & AUDIO >>",
                    fill_color="#0d3b20",
                    fill_top_color="#14532d",
                    border_color="#10b981",
                    hover_fill="#114b29",
                    hover_fill_top="#196638",
                    hover_border="#34d399",
                    fg="#ffffff",
                    state="normal",
                )
            elif var_alarms_only.get():
                btn_launch.config(
                    text=(
                        "🔔 SAVE & LAUNCH (ALARMS ONLY) >>"
                        if parent is None
                        else "🔔 SAVE & APPLY (ALARMS ONLY) >>"
                    ),
                    fill_color="#78350f",
                    fill_top_color="#92400e",
                    border_color="#f59e0b",
                    hover_fill="#92400e",
                    hover_fill_top="#b45309",
                    hover_border="#fbbf24",
                    fg="#fef3c7",
                    state="normal",
                )
            else:
                btn_launch.config(
                    text=(
                        "🚀 SAVE & LAUNCH ENFORCER >>"
                        if parent is None
                        else "🚀 SAVE & APPLY CHANGES >>"
                    ),
                    fill_color="#0d3b20",
                    fill_top_color="#14532d",
                    border_color="#10b981",
                    hover_fill="#114b29",
                    hover_fill_top="#196638",
                    hover_border="#34d399",
                    fg="#ffffff",
                    state="normal",
                )

        if in_trade_locked:
            ao_on = bool(var_alarms_only.get())
            cb_open_flat.config(
                state="disabled",
                text=(
                    "Enable Open PnL Auto-Flatten (Eq + Opt BETA)"
                    if var_flatten_options.get()
                    else "Enable Open PnL Auto-Flatten (Equities)"
                ),
                disabledforeground=(
                    "#fde68a"
                    if (not ao_on and var_open_flat.get())
                    else "#526070"
                ),
            )
            _style_locked_entry(
                ent_open_loss, not ao_on and var_open_flat.get()
            )
            lbl_open_loss.config(
                fg="#fbbf24"
                if (not ao_on and var_open_flat.get())
                else "#526070"
            )

            t_on = not ao_on and bool(var_tilt_cd.get())
            cb_tilt_cd.config(
                state="disabled",
                disabledforeground="#fde68a" if t_on else "#526070",
            )
            _style_locked_entry(ent_tilt_count, t_on)
            _style_locked_entry(ent_tilt_window, t_on)
            lbl_tilt_losses.config(fg="#fbbf24" if t_on else "#526070")
            lbl_tilt_filter.config(fg="#fbbf24" if t_on else "#526070")
            lbl_tilt_window.config(fg="#fbbf24" if t_on else "#526070")
            if t_on:
                btn_tilt_filter.config(
                    state="normal",
                    fill_color="#2a1f10",
                    fill_top_color="#382814",
                    border_color="#b45309",
                    hover_fill="#332512",
                    hover_fill_top="#443016",
                    hover_border="#f59e0b",
                    fg="#fde68a",
                )
            else:
                btn_tilt_filter.config(
                    state="disabled",
                    fill_color="#11161e",
                    fill_top_color="#161c26",
                    border_color="#222d3d",
                    fg="#526070",
                    disabledforeground="#526070",
                )

            cd_armed = (
                not ao_on
                and (var_open_flat.get() or var_tilt_cd.get())
                and var_open_cd.get()
            )
            cb_open_cd.config(
                state="disabled",
                disabledforeground="#fde68a" if cd_armed else "#526070",
            )
            _style_locked_entry(ent_cd_mins, cd_armed)
            lbl_cd_mins.config(fg="#fbbf24" if cd_armed else "#526070")

            cb_day_flat.config(
                state="disabled",
                disabledforeground=(
                    "#fde68a"
                    if (not ao_on and var_flatten.get())
                    else "#526070"
                ),
            )
            opt_armed = (
                not ao_on
                and (
                    var_open_flat.get()
                    or var_tilt_cd.get()
                    or var_flatten.get()
                )
                and var_flatten_options.get()
            )
            cb_opt_flat.config(
                state="disabled",
                disabledforeground="#fde68a" if opt_armed else "#526070",
            )
            lbl_kill.config(
                fg="#fbbf24"
                if (not ao_on and (var_kill_tos.get() or var_kill_wb.get()))
                else "#526070"
            )
            cb_kill_tos.config(
                state="disabled",
                disabledforeground=(
                    "#fde68a"
                    if (not ao_on and var_kill_tos.get())
                    else "#526070"
                ),
            )
            cb_kill_wb.config(
                state="disabled",
                disabledforeground=(
                    "#fde68a"
                    if (not ao_on and var_kill_wb.get())
                    else "#526070"
                ),
            )
            lk_armed = not ao_on and bool(var_lock_os.get())
            cb_lock_os.config(
                state="disabled",
                disabledforeground="#fde68a" if lk_armed else "#526070",
            )
            _style_locked_entry(ent_daily_lock_mins, lk_armed)
            lbl_daily_lock_mins.config(
                fg="#fbbf24" if lk_armed else "#526070"
            )

            # Card 4 (Extended Hours Rulebook) — Locked in trade
            cb_pm_w1.config(
                state="disabled",
                disabledforeground=(
                    "#fde68a" if var_pm_w1_on.get() else "#526070"
                ),
            )
            _style_locked_entry(ent_pm_w1, bool(var_pm_w1_on.get()))
            cb_pm_w2.config(
                state="disabled",
                disabledforeground=(
                    "#fde68a" if var_pm_w2_on.get() else "#526070"
                ),
            )
            _style_locked_entry(ent_pm_w2, bool(var_pm_w2_on.get()))
            lbl_pm_max.config(fg="#fbbf24")
            _style_locked_entry(ent_pm_max, True)
            cb_pm_lock.config(
                state="disabled",
                disabledforeground=(
                    "#fde68a" if var_pm_lock_on.get() else "#526070"
                ),
            )
            lbl_pm_trig.config(
                fg="#fbbf24" if var_pm_lock_on.get() else "#526070"
            )
            _style_locked_entry(ent_pm_trig, bool(var_pm_lock_on.get()))
            lbl_pm_arrow.config(
                fg="#fbbf24" if var_pm_lock_on.get() else "#526070"
            )
            lbl_pm_trail.config(
                fg="#fbbf24" if var_pm_lock_on.get() else "#526070"
            )
            _style_locked_entry(ent_pm_trail, bool(var_pm_lock_on.get()))

            # Card 5 (RTH Rulebook) — Locked in trade
            cb_t1_w1.config(
                state="disabled",
                disabledforeground=(
                    "#fde68a" if var_t1_w1_on.get() else "#526070"
                ),
            )
            _style_locked_entry(ent_t1_w1, bool(var_t1_w1_on.get()))
            cb_t1_w2.config(
                state="disabled",
                disabledforeground=(
                    "#fde68a" if var_t1_w2_on.get() else "#526070"
                ),
            )
            _style_locked_entry(ent_t1_w2, bool(var_t1_w2_on.get()))
            lbl_t1_max.config(fg="#fbbf24")
            _style_locked_entry(ent_t1_max, True)
            for (
                t_cb_var,
                cb_t,
                lbl_trig,
                ent_trig,
                lbl_arrow,
                lbl_fl,
                ent_fl,
                _cb_fg_col,
            ) in tier_widget_refs:
                t_en = bool(t_cb_var.get())
                cb_t.config(
                    state="disabled",
                    disabledforeground="#fde68a" if t_en else "#526070",
                )
                lbl_trig.config(fg="#fbbf24" if t_en else "#526070")
                _style_locked_entry(ent_trig, t_en)
                lbl_arrow.config(fg="#fbbf24" if t_en else "#526070")
                lbl_fl.config(fg="#fbbf24" if t_en else "#526070")
                _style_locked_entry(ent_fl, t_en)
            return

        # Restore default disabledforeground & entry rims when flat
        for _cb_w in (
            cb_open_flat,
            cb_tilt_cd,
            cb_open_cd,
            cb_day_flat,
            cb_opt_flat,
            cb_kill_tos,
            cb_kill_wb,
            cb_lock_os,
            cb_pm_w1,
            cb_pm_w2,
            cb_pm_lock,
            cb_t1_w1,
            cb_t1_w2,
        ):
            _cb_w.config(disabledforeground="#526070")
        for _ent_w in (
            ent_open_loss,
            ent_daily_lock_mins,
            ent_pm_w1,
            ent_pm_w2,
            ent_pm_max,
            ent_pm_trig,
            ent_pm_trail,
            ent_t1_w1,
            ent_t1_w2,
            ent_t1_max,
        ):
            _restore_entry_rim(_ent_w)
        lbl_pm_max.config(fg="#f87171")
        ent_pm_max.config(state="normal")
        lbl_t1_max.config(fg="#f87171")
        ent_t1_max.config(state="normal")
        for (
            _t_cb_var,
            cb_t,
            _lbl_trig,
            ent_trig,
            _lbl_arrow,
            _lbl_fl,
            ent_fl,
            _cb_fg_col,
        ) in tier_widget_refs:
            cb_t.config(state="normal", disabledforeground="#526070")
            _restore_entry_rim(ent_trig)
            _restore_entry_rim(ent_fl)

        if var_alarms_only.get():
            cb_open_flat.config(state="disabled")
            ent_open_loss.config(state="disabled")
            lbl_open_loss.config(fg="#526070")
            cb_tilt_cd.config(state="disabled")
            ent_tilt_count.config(state="disabled")
            lbl_tilt_losses.config(fg="#526070")
            lbl_tilt_filter.config(fg="#526070")
            btn_tilt_filter.config(
                state="disabled",
                fill_color="#11161e",
                fill_top_color="#161c26",
                border_color="#222d3d",
                fg="#526070",
                disabledforeground="#526070",
            )
            lbl_tilt_window.config(fg="#526070")
            ent_tilt_window.config(state="disabled")
            cb_open_cd.config(state="disabled")
            ent_cd_mins.config(state="disabled")
            lbl_cd_mins.config(fg="#526070")

            cb_day_flat.config(state="disabled")
            cb_opt_flat.config(state="disabled")
            lbl_kill.config(fg="#526070")
            cb_kill_tos.config(state="disabled")
            cb_kill_wb.config(state="disabled")
            cb_lock_os.config(state="disabled")
            ent_daily_lock_mins.config(state="disabled")
            lbl_daily_lock_mins.config(fg="#526070")
        else:
            cb_open_flat.config(
                state="normal",
                text=(
                    "Enable Open PnL Auto-Flatten (Eq + Opt BETA)"
                    if var_flatten_options.get()
                    else "Enable Open PnL Auto-Flatten (Equities)"
                ),
            )
            if var_open_flat.get():
                ent_open_loss.config(state="normal")
                lbl_open_loss.config(fg="#dc6d72")
            else:
                ent_open_loss.config(state="disabled")
                lbl_open_loss.config(fg="#526070")

            if tamper_locked:
                cb_tilt_cd.config(
                    state="disabled",
                    fg="#fde68a",
                    disabledforeground="#fde68a",
                )
                ent_tilt_count.config(
                    state="disabled",
                    disabledforeground="#fde68a",
                    highlightbackground="#b45309",
                )
                lbl_tilt_losses.config(fg="#fbbf24")
                lbl_tilt_filter.config(fg="#fbbf24")
                btn_tilt_filter.config(
                    state="normal",
                    fill_color="#2a1f10",
                    fill_top_color="#382814",
                    border_color="#b45309",
                    hover_fill="#332512",
                    hover_fill_top="#443016",
                    hover_border="#f59e0b",
                    fg="#fde68a",
                )
                lbl_tilt_window.config(fg="#fbbf24")
                ent_tilt_window.config(
                    state="disabled",
                    disabledforeground="#fde68a",
                    highlightbackground="#b45309",
                )
            else:
                cb_tilt_cd.config(state="normal", fg="#dce4ee")
                ent_tilt_count.config(
                    disabledforeground="#475569",
                    highlightbackground="#2e526e",
                )
                ent_tilt_window.config(
                    disabledforeground="#475569",
                    highlightbackground="#2e526e",
                )
                if var_tilt_cd.get():
                    ent_tilt_count.config(state="normal")
                    lbl_tilt_losses.config(fg="#97a7b9")
                    lbl_tilt_filter.config(fg="#97a7b9")
                    btn_tilt_filter.config(
                        state="normal",
                        fill_color="#141820",
                        fill_top_color="#1c212b",
                        border_color="#2e3746",
                        hover_fill="#181e28",
                        hover_fill_top="#232a36",
                        hover_border="#38bdf8",
                        fg="#cbd5e1",
                    )
                    lbl_tilt_window.config(fg="#97a7b9")
                    ent_tilt_window.config(state="normal")
                else:
                    ent_tilt_count.config(state="disabled")
                    lbl_tilt_losses.config(fg="#526070")
                    lbl_tilt_filter.config(fg="#526070")
                    btn_tilt_filter.config(
                        state="disabled",
                        fill_color="#11161e",
                        fill_top_color="#161c26",
                        border_color="#222d3d",
                        fg="#526070",
                        disabledforeground="#526070",
                    )
                    lbl_tilt_window.config(fg="#526070")
                    ent_tilt_window.config(state="disabled")

            if tamper_locked and config.get("enable_open_cooldown", False):
                cb_open_cd.config(
                    state="disabled",
                    fg="#fde68a",
                    disabledforeground="#fde68a",
                )
                ent_cd_mins.config(
                    state="disabled",
                    disabledforeground="#fde68a",
                    highlightbackground="#b45309",
                )
                lbl_cd_mins.config(fg="#fbbf24")
            else:
                cb_open_cd.config(fg="#c8d4e0")
                ent_cd_mins.config(
                    disabledforeground="#475569",
                    highlightbackground="#2e526e",
                )
                if var_open_flat.get() or var_tilt_cd.get():
                    cb_open_cd.config(state="normal")
                    if var_open_cd.get():
                        ent_cd_mins.config(state="normal")
                        lbl_cd_mins.config(fg="#97a7b9")
                    else:
                        ent_cd_mins.config(state="disabled")
                        lbl_cd_mins.config(fg="#526070")
                else:
                    cb_open_cd.config(state="disabled")
                    ent_cd_mins.config(state="disabled")
                    lbl_cd_mins.config(fg="#526070")

            cb_day_flat.config(state="normal")
            if var_open_flat.get() or var_tilt_cd.get() or var_flatten.get():
                cb_opt_flat.config(
                    state="normal",
                    fg="#f5b041" if var_flatten_options.get() else "#c8d4e0",
                )
            else:
                cb_opt_flat.config(state="disabled")
            lbl_kill.config(fg="#97a7b9")
            cb_kill_tos.config(state="normal")
            cb_kill_wb.config(state="normal")
            cb_lock_os.config(state="normal")
            if var_lock_os.get():
                ent_daily_lock_mins.config(state="normal")
                lbl_daily_lock_mins.config(fg="#97a7b9")
            else:
                ent_daily_lock_mins.config(state="disabled")
                lbl_daily_lock_mins.config(fg="#526070")

        # Card 4: Pre-Market Warning Alarms & Profit Lock
        cb_pm_w1.config(
            state="normal",
            fg="#dce4ee" if var_pm_w1_on.get() else "#526070",
        )
        ent_pm_w1.config(state="normal" if var_pm_w1_on.get() else "disabled")
        cb_pm_w2.config(
            state="normal",
            fg="#dce4ee" if var_pm_w2_on.get() else "#526070",
        )
        ent_pm_w2.config(state="normal" if var_pm_w2_on.get() else "disabled")
        cb_pm_lock.config(state="normal")
        if var_pm_lock_on.get():
            cb_pm_lock.config(fg="#4ec994")
            lbl_pm_trig.config(fg="#97a7b9")
            ent_pm_trig.config(state="normal")
            lbl_pm_arrow.config(fg="#64748b")
            lbl_pm_trail.config(fg="#97a7b9")
            ent_pm_trail.config(state="normal")
        else:
            cb_pm_lock.config(fg="#526070")
            lbl_pm_trig.config(fg="#526070")
            ent_pm_trig.config(state="disabled")
            lbl_pm_arrow.config(fg="#3b4756")
            lbl_pm_trail.config(fg="#526070")
            ent_pm_trail.config(state="disabled")

        # Card 5: RTH Tier 1 Warning Alarms & Profit Ratchet Tiers 2-4
        cb_t1_w1.config(
            state="normal",
            fg="#dce4ee" if var_t1_w1_on.get() else "#526070",
        )
        ent_t1_w1.config(state="normal" if var_t1_w1_on.get() else "disabled")
        cb_t1_w2.config(
            state="normal",
            fg="#dce4ee" if var_t1_w2_on.get() else "#526070",
        )
        ent_t1_w2.config(state="normal" if var_t1_w2_on.get() else "disabled")
        for (
            t_cb_var, cb_t, lbl_trig, ent_trig, lbl_arrow, lbl_fl, ent_fl, cb_fg_col
        ) in tier_widget_refs:
            if t_cb_var.get():
                cb_t.config(fg=cb_fg_col)
                lbl_trig.config(fg="#97a7b9")
                ent_trig.config(state="normal")
                lbl_arrow.config(fg="#64748b")
                lbl_fl.config(fg="#97a7b9")
                ent_fl.config(state="normal")
            else:
                cb_t.config(fg="#526070")
                lbl_trig.config(fg="#526070")
                ent_trig.config(state="disabled")
                lbl_arrow.config(fg="#3b4756")
                lbl_fl.config(fg="#526070")
                ent_fl.config(state="disabled")

    var_tilt_cd.trace_add("write", _on_toggle_tilt_cd)
    for trace_var in (
        var_alarms_only,
        var_open_flat, var_open_cd, var_flatten, var_lock_os,
        var_pm_w1_on, var_pm_w2_on, var_pm_lock_on,
        var_t1_w1_on, var_t1_w2_on, var_t2_on, var_t3_on, var_t4_on
    ):
        trace_var.trace_add("write", refresh_smart_dimming)
    refresh_smart_dimming()

    _pf_streak_prev_locked = {
        "val": is_tilt_streak_tamper_locked(),
        "in_trade": is_in_trade_tamper_locked(),
    }

    def _tick_preflight_streak():
        pf_timer_state["streak_after_id"] = None
        if pf_timer_state["closing"]:
            return
        try:
            if not pf.winfo_exists():
                return
            prev_cnt = len(recent_loss_timestamps)
            now_locked = is_tilt_streak_tamper_locked()
            now_in_trade = is_in_trade_tamper_locked()
            if (
                now_locked != _pf_streak_prev_locked["val"]
                or now_in_trade != _pf_streak_prev_locked["in_trade"]
            ):
                was_in_trade = _pf_streak_prev_locked["in_trade"]
                _pf_streak_prev_locked["val"] = now_locked
                _pf_streak_prev_locked["in_trade"] = now_in_trade
                refresh_smart_dimming()
                _refresh_ignored_positions_pill()
                _render_card3_telemetry_live(force=True)
                if was_in_trade and not now_in_trade:
                    log_event(
                        "SESSION",
                        "Settings auto-unlocked: active daytrade closed flat while Settings window was open.",
                    )
                elif not was_in_trade and now_in_trade:
                    log_event(
                        "SESSION",
                        "Settings auto-locked: new daytrade opened while Settings window was open.",
                    )
                if default_status_lbl is not None:
                    if now_in_trade:
                        default_status_lbl.config(
                            text="🔒 In Trade: Risk & Rulebook cards (1, 2, 4, 5) are locked. HUD Columns, Logs & Audio remain editable.",
                            fg="#fbbf24",
                        )
                    elif was_in_trade and not now_in_trade:
                        default_status_lbl.config(
                            text="✓ Position closed (100% flat) — Risk & Rulebook settings unlocked.",
                            fg="#58d68d",
                        )
            else:
                _refresh_c1_tamper_badge()
                _refresh_ignored_positions_pill()
                _render_card3_telemetry_live()
            if len(recent_loss_timestamps) != prev_cnt:
                save_session_state()
        except Exception:
            pass
        if not pf_timer_state["closing"]:
            delay_ms = (
                200
                if (len(recent_loss_timestamps) > 0 or parent is not None)
                else 1000
            )
            try:
                pf_timer_state["streak_after_id"] = pf.after(
                    delay_ms, _tick_preflight_streak
                )
            except Exception:
                pass

    _tick_preflight_streak()

    # --- BOTTOM ACTION BAR (GLASSMORPHIC STADIUMS) ---
    btn_frame = tk.Frame(pf, bg="#0d1117")
    btn_frame.pack(fill="x", pady=(10, 2))

    btn_restore_def = make_stadium_button(
        btn_frame,
        text="Restore Defaults",
        font=("Arial", 10, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#475569",
        fg="#e2e8f0",
        canvas_bg="#0d1117",
        width=148,
        height=38,
        pad_x=30,
        command=restore_factory_defaults,
    )
    btn_restore_def.pack(side="left")
    attach_tooltip(
        btn_restore_def,
        "Resets all checkboxes, HUD columns, and dollar values on this screen\n"
        "back to your saved Default settings (or Factory Defaults if none saved yet)."
    )

    btn_save_def = make_stadium_button(
        btn_frame,
        text="Save as Default",
        font=("Arial", 10, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#475569",
        fg="#cbd5e1",
        canvas_bg="#0d1117",
        width=148,
        height=38,
        pad_x=30,
        command=save_as_user_defaults,
    )
    btn_save_def.pack(side="left", padx=(10, 0))
    attach_tooltip(
        btn_save_def,
        "Saves every setting and dollar threshold currently on this screen as your personal\n"
        "Default profile (used by 'Restore Defaults', 'Standard Full Risk', and '50% Low Energy')."
    )

    def _on_toggle_alarms_only():
        if is_in_trade_tamper_locked():
            return
        if is_tilt_streak_tamper_locked() and not config.get(
            "alarms_only_mode", False
        ):
            return
        var_alarms_only.set(not bool(var_alarms_only.get()))

    launch_txt = (
        "💾 SAVE HUD & AUDIO >>"
        if is_in_trade_tamper_locked()
        else (
            "🚀 SAVE & LAUNCH ENFORCER >>"
            if parent is None
            else "🚀 SAVE & APPLY CHANGES >>"
        )
    )
    btn_launch = make_stadium_button(
        btn_frame,
        text=launch_txt,
        font=("Arial", 10, "bold"),
        fill_color="#0d3b20",
        fill_top_color="#14532d",
        border_color="#10b981",
        hover_fill="#114b29",
        hover_fill_top="#196638",
        hover_border="#34d399",
        fg="#ffffff",
        canvas_bg="#0d1117",
        width=312,
        height=38,
        pad_x=28,
        auto_width=False,
        command=save_and_launch,
    )
    btn_launch.pack(side="right")

    btn_alarms_only = make_stadium_button(
        btn_frame,
        text="🔔 Alarms Only: OFF",
        font=("Arial", 10, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#475569",
        hover_fill="#261f14",
        hover_fill_top="#362b1a",
        hover_border="#f59e0b",
        fg="#cbd5e1",
        canvas_bg="#0d1117",
        width=188,
        height=38,
        pad_x=22,
        auto_width=False,
        command=_on_toggle_alarms_only,
    )
    btn_alarms_only.pack(side="right", padx=(0, 12))
    attach_tooltip(
        btn_alarms_only,
        "Alarms Only Mode (Global Passive Observation / Siren Mode):\n"
        "When toggled ON, all automated broker order execution, platform kill-switches, and Windows OS\n"
        "lockouts across BOTH Cards 1 & 2 are completely disabled and greyed out.\n"
        "• Tracks your live Realized, Open, and Net PnL, Session High, and Profit Ratchet Tiers normally.\n"
        "• Sounds audible warning sirens and breach alarms at every configured threshold.\n"
        "• NEVER submits flatten orders, closes trading apps, or locks your Windows screen.\n"
        "• Toggling OFF immediately restores your saved Auto-Flatten and OS Lock checkmarks."
    )

    ver_outer = tk.Frame(pf, bg="#0d1117")
    ver_outer.pack(fill="x", pady=(6, 0))

    if is_in_trade_tamper_locked():
        init_def_txt = "🔒 In Trade: Risk & Rulebook cards (1, 2, 4, 5) are locked. HUD Columns, Logs & Audio remain editable."
        init_def_fg = "#fbbf24"
    elif config.get("user_defaults"):
        init_def_txt = "Custom defaults saved ✓"
        init_def_fg = "#8b9bb0"
    else:
        init_def_txt = "No custom default saved yet"
        init_def_fg = "#8b9bb0"
    default_status_lbl = tk.Label(
        ver_outer,
        text=init_def_txt,
        font=("Arial", 9, "bold"),
        fg=init_def_fg,
        bg="#0d1117",
        anchor="w",
    )
    default_status_lbl.pack(side="left")

    refresh_smart_dimming()

    ver_frame = tk.Frame(ver_outer, bg="#0d1117")
    ver_frame.pack(side="right")

    tk.Label(
        ver_frame,
        text=f"Version v{APP_VERSION}   ·",
        font=("Arial", 9, "bold"),
        fg="#64748b",
        bg="#0d1117",
    ).pack(side="left", padx=(0, 6))

    rel_notes_lbl = tk.Label(
        ver_frame,
        text="View Release Notes",
        font=("Arial", 9, "bold underline"),
        fg="#5dade2",
        bg="#0d1117",
        cursor="hand2",
    )
    rel_notes_lbl.pack(side="left")
    rel_notes_lbl.bind(
        "<Enter>", lambda e: rel_notes_lbl.config(fg="#85c1e9")
    )
    rel_notes_lbl.bind(
        "<Leave>", lambda e: rel_notes_lbl.config(fg="#5dade2")
    )
    rel_notes_lbl.bind(
        "<Button-1>", lambda e: show_release_notes_dialog(parent=pf)
    )
    attach_tooltip(
        rel_notes_lbl,
        "View the PnL Enforcer Beta Changelog and version release history."
    )

    def show_daily_breach_return_notice():
        """Displays a friendly dark-glass notice after a Daily Stop breach
        lockout finishes (or siren is muted), reminding the trader to raise
        their Daily Stop or Re-Zero Baseline if they want an active Daily Stop,
        or leave it as-is in BREACHED (DISARMED) mode so a new trade does not
        immediately stop them out on entry."""
        if not pf.winfo_exists():
            return
        ref_eq = (
            last_flat_equity if last_flat_equity is not None else start_equity
        )
        (
            act_fl,
            _,
            _,
            tier_short_label,
            tier_full_desc,
            setting_field_hint,
        ) = describe_active_floor(config)
        if (
            ref_eq is not None
            and start_equity is not None
            and act_fl is not None
        ):
            cur_net_str = format_dollar(round(ref_eq - start_equity, 2))
            stop_lvl_str = format_dollar(round(act_fl - start_equity, 2))
            over_val = abs(round(ref_eq - act_fl, 2))
            over_str = f"-${over_val:,.2f} OVER"
        else:
            cur_net_str = "below floor"
            stop_lvl_str = "Daily Stop"
            over_str = "BREACHED"

        dlg = tk.Toplevel(pf)
        dlg.withdraw()
        dlg.title("PnL Enforcer — Daily Stop Breached")
        dlg.configure(bg="#0d1117", padx=24, pady=20)
        dlg.resizable(False, False)
        dlg.transient(pf)
        dlg.grab_set()

        def on_keep_watching():
            dlg.destroy()

        def on_close_keep_as_is():
            dlg.destroy()
            on_close()

        def on_arm_rezero():
            if not is_tilt_streak_tamper_locked():
                var_reanchor.set(True)
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", on_keep_watching)

        hdr_row = tk.Frame(dlg, bg="#0d1117")
        hdr_row.pack(fill="x", pady=(0, 4))

        tk.Label(
            hdr_row,
            text="▶  DAILY STOP BREACHED — REVIEW OR ADJUST YOUR LIMITS",
            font=("Arial", 12, "bold"),
            fg="#f87171",
            bg="#0d1117",
            anchor="w",
        ).pack(side="left")

        tk.Label(
            hdr_row,
            text="⚠️ DAILY STOP DISARMED",
            font=("Arial", 8, "bold"),
            fg="#fecdd3",
            bg="#4c0519",
            padx=8,
            pady=3,
        ).pack(side="right", padx=(12, 0))

        tk.Label(
            dlg,
            text="Your Daily Stop lockout has finished. Before placing another trade, please review your Daily Stop:",
            font=("Arial", 9),
            fg="#94a3b8",
            bg="#0d1117",
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        card_outer = tk.Frame(
            dlg,
            bg="#131922",
            bd=0,
            highlightthickness=1,
            highlightbackground="#243040",
        )
        card_outer.pack(fill="x", pady=(0, 16))
        NeonBarCanvas(
            card_outer, core_color="#ef4444", card_bg="#131922", glow_on=True
        ).pack(side="left", fill="y")

        txt_box = tk.Text(
            card_outer,
            width=88,
            height=20,
            bg="#131922",
            fg="#dce4ee",
            font=("Segoe UI", 10),
            wrap="none",
            bd=0,
            highlightthickness=0,
            padx=18,
            pady=14,
            cursor="arrow",
        )
        txt_box.pack(side="left", fill="both", expand=True)

        txt_box.tag_configure(
            "hdr_red",
            font=("Segoe UI", 10, "bold"),
            foreground="#f87171",
            spacing1=0,
            spacing3=4,
        )
        txt_box.tag_configure(
            "hdr_green",
            font=("Segoe UI", 10, "bold"),
            foreground="#4ade80",
            spacing1=2,
            spacing3=4,
        )
        txt_box.tag_configure(
            "hdr_amber",
            font=("Segoe UI", 10, "bold"),
            foreground="#fbbf24",
            spacing1=2,
            spacing3=4,
        )
        txt_box.tag_configure(
            "body",
            font=("Segoe UI", 10),
            foreground="#dce4ee",
            spacing1=1,
            spacing3=2,
        )
        txt_box.tag_configure(
            "pill_blue",
            font=("Consolas", 9, "bold"),
            foreground="#7dd3fc",
            background="#1a2636",
        )
        txt_box.tag_configure(
            "pill_red",
            font=("Consolas", 9, "bold"),
            foreground="#fca5a5",
            background="#311820",
        )
        txt_box.tag_configure(
            "pill_green",
            font=("Consolas", 9, "bold"),
            foreground="#6ee7b7",
            background="#132a22",
        )
        txt_box.tag_configure(
            "pill_amber",
            font=("Consolas", 9, "bold"),
            foreground="#fde68a",
            background="#33220c",
        )
        txt_box.tag_configure(
            "div_line",
            font=("Consolas", 8),
            foreground="#223042",
            spacing1=5,
            spacing3=5,
        )

        txt_box.insert(
            "end",
            "⚠️  1. YOUR DAILY STOP WAS BREACHED\n",
            "hdr_red",
        )
        s1_spans = [
            ("    Your Net PnL (", ("body",)),
            (f" {cur_net_str} ", ("body", "pill_red")),
            (") is past your active Daily Stop (", ("body",)),
            (f" {stop_lvl_str} · {tier_short_label} ", ("body", "pill_blue")),
            (", ", ("body",)),
            (f" {over_str} ", ("body", "pill_red")),
            (").\n", ("body",)),
            ("    Active Rule: ", ("body",)),
            (f" {tier_full_desc} ", ("body", "pill_amber")),
            ("\n", ("body",)),
            ("    To prevent an instant stop-out on your next entry, your Daily Stop is held in\n", ("body",)),
            ("    ", ("body",)),
            (" DAY STOP: BREACHED (DISARMED) ", ("body", "pill_red")),
            (" mode until you adjust it or recover above the floor.\n", ("body",)),
        ]
        for s_txt, s_tags in s1_spans:
            txt_box.insert("end", s_txt, s_tags)

        txt_box.insert("end", "─" * 78 + "\n", "div_line")

        txt_box.insert(
            "end",
            "✔  2. TO RE-ARM YOUR DAILY STOP FOR THE REST OF TODAY\n",
            "hdr_green",
        )
        s2_spans = [
            ("    • Adjust ", ("body",)),
            (f" {setting_field_hint} ", ("body", "pill_red")),
            (" to give yourself\n", ("body",)),
            ("      room below ", ("body",)),
            (f" {cur_net_str} ", ("body", "pill_red")),
            (" and click ", ("body",)),
            (" SAVE & APPLY CHANGES >> ", ("body", "pill_green")),
            (", OR\n", ("body",)),
            ("    • Click ", ("body",)),
            (" ↺ Arm Re-Zero Baseline ($0.00) ", ("body", "pill_amber")),
            (" below to start a fresh $0.00 session baseline.\n", ("body",)),
        ]
        for s_txt, s_tags in s2_spans:
            txt_box.insert("end", s_txt, s_tags)

        txt_box.insert("end", "─" * 78 + "\n", "div_line")

        txt_box.insert(
            "end",
            "🛡️  3. IF YOU KEEP TRADING WITHOUT CHANGING IT\n",
            "hdr_amber",
        )
        s3_spans = [
            ("    • If you close Settings or save without raising your limit, the HUD displays ", ("body",)),
            (" BREACHED ", ("body", "pill_red")),
            ("\n", ("body",)),
            ("      in ", ("body",)),
            (" $ TO STOP ", ("body", "pill_blue")),
            (" and ", ("body",)),
            (" DAY STOP: BREACHED ", ("body", "pill_amber")),
            (" in the status pill.\n", ("body",)),
            ("    • New trades will NOT immediately flatten on the old Daily Stop, while Card 1\n", ("body",)),
            ("      (", ("body",)),
            (" Open PnL Auto-Flatten ", ("body", "pill_blue")),
            (" & ", ("body",)),
            (" Consecutive Loss Cooldown ", ("body", "pill_blue")),
            (") stays 100% active.", ("body",)),
        ]
        for s_txt, s_tags in s3_spans:
            txt_box.insert("end", s_txt, s_tags)

        txt_box.config(state="disabled")

        btn_row = tk.Frame(dlg, bg="#0d1117")
        btn_row.pack(fill="x")

        make_stadium_button(
            btn_row,
            text="Keep As-Is (Close Settings)",
            font=("Arial", 10, "bold"),
            fill_color="#141820",
            fill_top_color="#1c212b",
            border_color="#2e3746",
            hover_fill="#181e28",
            hover_fill_top="#232a36",
            hover_border="#475569",
            fg="#cbd5e1",
            canvas_bg="#0d1117",
            width=214,
            height=34,
            auto_width=False,
            command=on_close_keep_as_is,
        ).pack(side="left")

        make_stadium_button(
            btn_row,
            text="Review & Edit Limits ✓",
            font=("Arial", 10, "bold"),
            fill_color="#0d3b20",
            fill_top_color="#14532d",
            border_color="#10b981",
            hover_fill="#114b29",
            hover_fill_top="#196638",
            hover_border="#34d399",
            fg="#ffffff",
            canvas_bg="#0d1117",
            width=200,
            height=34,
            auto_width=False,
            command=on_keep_watching,
        ).pack(side="right")

        if not is_tilt_streak_tamper_locked():
            make_stadium_button(
                btn_row,
                text="↺ Arm Re-Zero Baseline ($0.00)",
                font=("Arial", 10, "bold"),
                fill_color="#33220c",
                fill_top_color="#473010",
                border_color="#f59e0b",
                hover_fill="#3f2a0f",
                hover_fill_top="#543813",
                hover_border="#fbbf24",
                fg="#fde68a",
                canvas_bg="#0d1117",
                width=236,
                height=34,
                auto_width=False,
                command=on_arm_rezero,
            ).pack(side="right", padx=(0, 8))

        center_dialog_over_parent(dlg, parent=pf)

        pf.wait_window(dlg)

    try:
        pf.update_idletasks()
        pf_w = int(pf.winfo_reqwidth())
        pf_h = int(pf.winfo_reqheight())
        saved_pf_pos = globals().get("last_preflight_pos")
        if (
            isinstance(saved_pf_pos, (tuple, list))
            and len(saved_pf_pos) == 2
        ):
            sx, sy = int(saved_pf_pos[0]), int(saved_pf_pos[1])
            m_left, m_top, m_right, m_bottom = get_monitor_work_area(
                sx + pf_w // 2, sy + pf_h // 2, widget=pf
            )
            px = max(m_left + 8, min(sx, m_right - pf_w - 8))
            py = max(m_top + 8, min(sy, m_bottom - pf_h - 8))
            pf.geometry(f"+{int(px)}+{int(py)}")
            apply_dark_title_bar(pf)
            pf.deiconify()
            pf.lift()
            if parent is not None:
                try:
                    pf.grab_set()
                except Exception:
                    pass
        else:
            center_dialog_over_parent(pf, parent=parent)
    except Exception:
        try:
            pf.deiconify()
        except Exception:
            pass

    if post_daily_breach_prompt:
        pf.after(150, show_daily_breach_return_notice)

    if parent is None:
        pf.mainloop()
        return launched["status"]
    return True


# ==========================================
# 9. DYNAMIC MULTI-COLUMN HUD SETUP
# ==========================================
acct_badge_mode = 0  # 0 = W/L, 1 = STREAK, 2 = FLAT, 3 = BASE
acct_badge_lbl = None
hud_root = None
hud_grid_frame = None
hud_ui_labels = []
hud_leash_bar = None
hud_leash_col_frame = None
hud_leash_idx = None
hud_last_leash_pct = 1.0
hud_last_leash_bg = "#262a2e"
hud_start_move_fn = None
hud_do_move_fn = None


def refresh_acct_badge():
    """Updates the clickable left account badge (W/L -> STREAK -> FLAT -> BASE)."""
    if acct_badge_lbl is None:
        return

    if acct_badge_mode == 1:
        cur_s, req_l, _next_s, _full_s, is_en = get_loss_streak_status()
        txt = format_loss_streak_inline()
        if cur_s > 0 and is_en and cur_s >= (req_l - 1):
            fg_col = "#fca5a5"
        elif cur_s > 0:
            fg_col = "#fbbf24"
        else:
            fg_col = "#a3e4d7" if is_en else "#94a3b8"
    elif acct_badge_mode == 2:
        val = last_flat_equity if last_flat_equity is not None else start_equity
        txt = f"FLAT: ${val:,.2f}" if (val is not None and val > 0) else "FLAT: ---"
        fg_col = "#ffffff"
    elif acct_badge_mode == 3:
        val = start_equity
        txt = f"BASE: ${val:,.2f}" if (val is not None and val > 0) else "BASE: ---"
        fg_col = "#aed6f1"
    else:
        txt = format_trades_wl_inline(win_trades, loss_trades)
        fg_col = "#e5e8e8"

    if (
        getattr(acct_badge_lbl, "_text", "") != txt
        or getattr(acct_badge_lbl, "_fg", "") != fg_col
    ):
        acct_badge_lbl.config(text=txt, fg=fg_col)


def toggle_acct_badge(event=None):
    global acct_badge_mode
    acct_badge_mode = (acct_badge_mode + 1) % 4
    refresh_acct_badge()


def _redraw_hud_leash_canvas(event=None):
    """Draws the glowing neon '$ TO STOP' progress bar with an upward bloom."""
    if hud_leash_bar is None:
        return
    try:
        hud_leash_bar.delete("all")
        w = hud_leash_bar.winfo_width()
        h = hud_leash_bar.winfo_height()
        if w <= 4:
            w = 156
        if h <= 3:
            h = 5
        lp = max(0.0, min(1.0, float(hud_last_leash_pct)))
        bg_c = hud_last_leash_bg
        if lp > 0.50:
            core_col = "#00e676"
            spec_col = "#b9f6ca"
        elif lp >= 0.25:
            core_col = "#ffab00"
            spec_col = "#ffe57f"
        else:
            core_col = "#ff1744"
            spec_col = "#ff8a80"

        bar_w = int(round(w * lp))
        # Top 1px (y = 0): Subtle neon glow bloom into the column background
        bloom_col = _blend_hex(bg_c, core_col, 0.38)
        if bar_w > 0:
            hud_leash_bar.create_line(0, 0, bar_w, 0, fill=bloom_col)
        if bar_w < w:
            hud_leash_bar.create_line(bar_w, 0, w, 0, fill=bg_c)

        # Dark recessed trough for the bottom 4px (y = 1..4)
        hud_leash_bar.create_rectangle(0, 1, w, h, fill="#16181b", outline="")

        # Filled neon bar with 1px bright specular top highlight
        if bar_w > 0:
            hud_leash_bar.create_line(0, 1, bar_w, 1, fill=spec_col)
            hud_leash_bar.create_rectangle(
                0, 2, bar_w, h, fill=core_col, outline=""
            )

        if hud_leash_col_frame is not None:
            rim_col = _blend_hex("#34393f", core_col, 0.55)
            hud_leash_col_frame.config(highlightbackground=rim_col)
    except Exception:
        pass


def rebuild_hud_columns():
    """Dynamically builds or rebuilds the HUD columns inside hud_grid_frame
    and adjusts the HUD window width while preserving screen position."""
    global hud_ui_labels, hud_leash_bar, hud_leash_col_frame, hud_leash_idx
    if hud_grid_frame is None or hud_root is None:
        return

    for child in hud_grid_frame.winfo_children():
        child.destroy()

    hud_grid_frame.rowconfigure(0, weight=1)
    for c_idx in range(12):
        hud_grid_frame.columnconfigure(c_idx, weight=0, uniform="")

    active_cols = get_active_hud_columns(config)
    hud_ui_labels.clear()
    hud_leash_bar = None
    hud_leash_col_frame = None
    hud_leash_idx = None

    for i, col_id in enumerate(active_cols):
        title = HUD_COL_HEADERS.get(col_id, col_id.upper())
        hud_grid_frame.columnconfigure(i, weight=1, uniform="col")

        col_frame = tk.Frame(
            hud_grid_frame,
            bg="#262a2e",
            bd=0,
            highlightthickness=1,
            highlightbackground="#34393f"
        )
        col_frame.grid(row=0, column=i, sticky="nsew", padx=2, pady=(2, 1))

        if col_id == "terminate_lvl":
            _, _, hud_tag, _, _, _ = describe_active_floor(config)
            title = f"DAILY STOP ({hud_tag})"
            hdr_fg = (
                "#6ee7b7"
                if hud_tag in ("T2", "T3", "T4", "EXT LOCK")
                else "#cccccc"
            )
        else:
            hdr_fg = "#cccccc"

        hdr_lbl = tk.Label(
            col_frame,
            text=title,
            font=("Arial", 8, "bold"),
            fg=hdr_fg,
            bg="#1b1e22",
            pady=3
        )
        hdr_lbl.pack(fill="x")

        val_font = (
            ("Arial", 9, "bold")
            if col_id in ("trades_wl", "loss_streak")
            else ("Arial", 12, "bold")
        )
        val_lbl = tk.Label(
            col_frame,
            text="---",
            font=val_font,
            fg="white",
            bg="#262a2e",
            justify="center"
        )
        val_lbl._hdr_lbl = hdr_lbl
        val_lbl.pack(fill="both", expand=True)

        if col_id == "dist_to_term":
            hud_leash_idx = i
            hud_leash_col_frame = col_frame
            hud_leash_bar = tk.Canvas(
                col_frame,
                bg="#262a2e",
                height=5,
                bd=0,
                highlightthickness=0
            )
            hud_leash_bar.place(
                relx=0.0, rely=1.0, relwidth=1.0, anchor="sw", height=5
            )
            hud_leash_bar.bind("<Configure>", _redraw_hud_leash_canvas)

        if hud_start_move_fn and hud_do_move_fn:
            bind_list = [col_frame, hdr_lbl, val_lbl]
            if col_id == "dist_to_term" and hud_leash_bar is not None:
                bind_list.append(hud_leash_bar)
            for widget in bind_list:
                widget.bind("<Button-1>", hud_start_move_fn)
                widget.bind("<B1-Motion>", hud_do_move_fn)

        hud_ui_labels.append(val_lbl)

    w_px = compute_hud_width(len(active_cols))
    try:
        hud_root.update_idletasks()
        cur_x = hud_root.winfo_x()
        cur_y = hud_root.winfo_y()
        if cur_x <= 0 and cur_y <= 0:
            cur_x, cur_y = 50, 50
        hud_root.geometry(f"{w_px}x88+{cur_x}+{cur_y}")
    except Exception:
        hud_root.geometry(f"{w_px}x88+50+50")


def update_gui(
    ui_labels, col_data, is_flat, settings_btn, close_btn, leash_pct=None
):
    global hud_last_leash_pct, hud_last_leash_bg
    active_cols = get_active_hud_columns(config)
    for i, (text_val, bg_col) in enumerate(col_data):
        if i < len(active_cols) and active_cols[i] == "loss_streak":
            text_val, bg_col = format_loss_streak_multiline()
        disp_bg = "#262a2e" if bg_col in ("#2c3e50", "#1f538d") else bg_col
        if i < len(ui_labels):
            target_font = (
                ("Arial", 9, "bold")
                if "\n" in str(text_val)
                else ("Arial", 12, "bold")
            )
            if (
                ui_labels[i].cget("text") != text_val
                or ui_labels[i].cget("bg") != disp_bg
                or ui_labels[i].cget("font") != target_font
            ):
                ui_labels[i].config(
                    text=text_val, bg=disp_bg, font=target_font
                )
            if i < len(active_cols) and active_cols[i] == "terminate_lvl":
                hdr_w = getattr(ui_labels[i], "_hdr_lbl", None)
                if hdr_w is not None and hdr_w.winfo_exists():
                    _, _, hud_tag, _, _, _ = describe_active_floor(config)
                    new_hdr_txt = f"DAILY STOP ({hud_tag})"
                    new_hdr_fg = (
                        "#6ee7b7"
                        if hud_tag in ("T2", "T3", "T4", "EXT LOCK")
                        else "#cccccc"
                    )
                    if (
                        hdr_w.cget("text") != new_hdr_txt
                        or hdr_w.cget("fg") != new_hdr_fg
                    ):
                        hdr_w.config(text=new_hdr_txt, fg=new_hdr_fg)
        if i == hud_leash_idx:
            hud_last_leash_bg = disp_bg

    if hud_leash_bar is not None and leash_pct is not None:
        hud_last_leash_pct = max(0.0, min(1.0, float(leash_pct)))
        _redraw_hud_leash_canvas()

    refresh_acct_badge()

    if cooldown_active:
        settings_btn.config(
            text="🔒 LOCKED",
            fill_color="#1e2228",
            fill_top_color="#262a30",
            border_color="#4b5563",
            fg="#9ca3af",
            disabledforeground="#9ca3af",
            state="disabled",
        )
        close_btn.config(
            text="🔒",
            fill_color="#1e2228",
            fill_top_color="#262a30",
            border_color="#4b5563",
            fg="#9ca3af",
            disabledforeground="#9ca3af",
            state="disabled",
        )
    elif is_flat:
        settings_btn.config(
            text="⚙ SETTINGS",
            fill_color="#141922",
            fill_top_color="#1c2430",
            border_color="#2e3d4f",
            hover_fill="#1e293b",
            hover_fill_top="#293548",
            hover_border="#38bdf8",
            fg="#e2e8f0",
            state="normal",
        )
        close_btn.config(
            text="✕",
            fill_color="#180f13",
            fill_top_color="#24161c",
            border_color="#5c2836",
            fg="#fda4af",
            state="normal",
        )
    else:
        settings_btn.config(
            text="🔒 IN TRADE ⚙",
            fill_color="#291d0e",
            fill_top_color="#382813",
            border_color="#b45309",
            hover_fill="#362612",
            hover_fill_top="#473218",
            hover_border="#f59e0b",
            fg="#fde68a",
            state="normal",
        )
        close_btn.config(
            text="🔒",
            fill_color="#1e2228",
            fill_top_color="#262a30",
            border_color="#4b5563",
            fg="#9ca3af",
            disabledforeground="#9ca3af",
            state="disabled",
        )

    if not settings_win_open and ui_labels:
        top = ui_labels[0].winfo_toplevel()
        top.attributes("-topmost", True)
        top.lift()


def attach_hud_mute_tooltip(widget, hud_win):
    """Attaches a live dark-slate hover tooltip to the HUD's middle Armed/Alarm
    capsule pill so users in Small/Compact HUD mode (or Standard mode) can
    hover to inspect the full armed configuration and active alarm details."""
    tip_state = {"win": None, "after_id": None}

    def show_tip():
        tip_state["after_id"] = None
        if (
            tip_state["win"] is not None
            or not widget.winfo_exists()
            or settings_win_open
        ):
            return
        try:
            tw = tk.Toplevel(hud_win)
            tw.wm_overrideredirect(True)
            tw.attributes("-topmost", True)
            tw.config(bg="#334155", padx=1, pady=1)
            inner = tk.Frame(tw, bg="#141820", padx=12, pady=8)
            inner.pack(fill="both", expand=True)

            if consecutive_api_failures > 0 or api_disconnect_alerted:
                err_snip = str(
                    getattr(active_adapter, "last_error", "")
                    or "Network / socket timeout"
                )[:70]
                conn_txt = (
                    f"📡 CONNECTION LOST: Auto-reconnecting (Attempt #{max(1, consecutive_api_failures)})  ·  "
                    f"Last Error: {err_snip}"
                )
                tk.Label(
                    inner,
                    text=conn_txt,
                    font=("Arial", 9, "bold"),
                    fg="#fca5a5" if consecutive_api_failures >= 2 else "#fde68a",
                    bg="#141820",
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 4))

            if alarm_active:
                al_txt = (
                    f"🔔 ACTIVE ALARM: {last_alarm_reason or 'Warning Siren'} "
                    f"— Click button to acknowledge & mute"
                )
                tk.Label(
                    inner,
                    text=al_txt,
                    font=("Arial", 9, "bold"),
                    fg="#facc15",
                    bg="#141820",
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 4))
            elif cooldown_active:
                rem_s = max(0, int(round(cooldown_end_time - time.time())))
                cd_txt = (
                    f"🔒 {cooldown_label} ACTIVE: {rem_s}s remaining "
                    f"(Do Not Revenge Trade)"
                )
                tk.Label(
                    inner,
                    text=cd_txt,
                    font=("Arial", 9, "bold"),
                    fg="#fca5a5",
                    bg="#141820",
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 4))

            _, st_pnl, _, tier_short_tip, _, hint_tip = describe_active_floor(
                config
            )
            if is_locked_down:
                ld_txt = (
                    f"⚠️ DAILY STOP BREACHED ({format_dollar(st_pnl)} · {tier_short_tip} — DISARMED): "
                    f"Adjust {hint_tip} or Re-Zero Baseline in Settings (Card 1 Trade/Tilt Stops remain active)."
                )
                tk.Label(
                    inner,
                    text=ld_txt,
                    font=("Arial", 9, "bold"),
                    fg="#fca5a5",
                    bg="#141820",
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 4))

            tk.Label(
                inner,
                text=get_full_idle_button_text(),
                font=("Arial", 9, "bold"),
                fg="#ffca58",
                bg="#141820",
                justify="left",
                anchor="w",
            ).pack(fill="x")

            cur_s, req_l, next_s, full_s, is_en = get_loss_streak_status()
            if is_en or cur_s > 0:
                min_mag = abs(float(config.get("consec_loss_min_dollars", 25.0)))
                min_win_rst = abs(
                    float(config.get("consec_win_reset_dollars", 10.0))
                )
                win_m = float(config.get("consec_loss_window_mins", 15.0))
                if cur_s > 0:
                    st_txt = (
                        f"⏱ Loss Streak: {cur_s} / {req_l}  "
                        f"(Next -1 in {_format_countdown_mm_ss(next_s)}  ·  "
                        f"Full clear in {_format_countdown_mm_ss(full_s)}  ·  "
                        f"Min loss -${min_mag:,.0f} / Win reset +${min_win_rst:,.0f}  ·  🔒 Tamper-Locked)"
                    )
                    st_col = "#fca5a5" if cur_s >= (req_l - 1) else "#fbbf24"
                else:
                    st_txt = (
                        f"⏱ Loss Streak: 0 / {req_l} (CLEAR)  ·  "
                        f"Window: {win_m:g}m  ·  Min Loss: -${min_mag:,.0f} (Win Reset: +${min_win_rst:,.0f})"
                    )
                    st_col = "#a3e4d7"
                tk.Label(
                    inner,
                    text=st_txt,
                    font=("Arial", 8, "bold"),
                    fg=st_col,
                    bg="#141820",
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(3, 0))

            r_mode = (
                "Regular Hours (9:30 AM – 4:00 PM ET)"
                if is_rth()
                else "Extended Hours (Pre-Market & After-Hours)"
            )
            sub_txt = (
                f"Active Rulebook: {r_mode}   ·   "
                f"Active Floor: {format_dollar(st_pnl)} ({tier_short_tip})   ·   "
                f"Poll Interval: {config.get('poll_interval', 2)}s"
            )
            tk.Label(
                inner,
                text=sub_txt,
                font=("Arial", 8, "bold"),
                fg="#94a3b8",
                bg="#141820",
                justify="left",
                anchor="w",
            ).pack(fill="x", pady=(3, 0))

            tw.update_idletasks()
            tip_w = tw.winfo_reqwidth()
            tip_h = tw.winfo_reqheight()
            wx = int(widget.winfo_rootx())
            wy = int(widget.winfo_rooty())
            ww = int(widget.winfo_width())
            wh = int(widget.winfo_height())
            m_left, m_top, m_right, m_bottom = get_monitor_work_area(
                wx + ww // 2, wy + wh // 2, widget=widget
            )
            x = wx + (ww - tip_w) // 2
            x = max(m_left + 8, min(x, m_right - tip_w - 8))
            y = wy + wh + 5
            if (y + tip_h) > (m_bottom - 20):
                y = max(m_top + 8, int(hud_win.winfo_rooty()) - tip_h - 5)
            tw.wm_geometry(f"+{int(x)}+{int(y)}")
            tw.deiconify()
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
            tip_state["after_id"] = widget.after(200, show_tip)
        except Exception:
            pass

    widget._hide_tooltip_fn = hide_tip
    widget.bind("<Enter>", schedule_tip, add="+")
    widget.bind("<Leave>", hide_tip, add="+")
    widget.bind("<ButtonPress>", hide_tip, add="+")


def start_gui():
    global acct_badge_lbl, hud_root, hud_grid_frame
    global hud_ui_labels, hud_start_move_fn, hud_do_move_fn
    root = tk.Tk()
    hud_root = root
    root.title(f"PnL Enforcer v{APP_VERSION}")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    w_init = compute_hud_width(len(get_active_hud_columns(config)))
    root.geometry(f"{w_init}x88+50+50")
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
        if cooldown_active or dry_run_lock_active:
            log_event(
                "GUARDRAIL",
                "BLOCKED: Attempted to close HUD during an active lockout cooldown!",
            )
            return "break"
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

    bottom_bar = tk.Frame(root, bg="#1a1a1a", pady=1)
    bottom_bar.pack(fill="x", side="bottom")

    # Rounded Stadium Capsule Left Badge (Toggles between W/L, FLAT, and BASE)
    acct_badge_lbl = HudCapsulePill(
        bottom_bar,
        text=format_trades_wl_inline(win_trades, loss_trades),
        font=("Arial", 8, "bold"),
        bg="#282c31",
        fg="#e5e8e8",
        rim="#6c757d",
        glow="#343a40",
        width=124,
        height=24,
        state="normal",
        command=toggle_acct_badge,
        cursor="hand2",
        auto_width=True,
        pad_x=22
    )
    acct_badge_lbl.pack(side="left", padx=(2, 4))
    refresh_acct_badge()

    close_btn = make_stadium_button(
        bottom_bar,
        text="✕",
        font=("Arial", 9, "bold"),
        fill_color="#180f13",
        fill_top_color="#24161c",
        border_color="#5c2836",
        hover_fill="#28161e",
        hover_fill_top="#361e29",
        hover_border="#f43f5e",
        fg="#fda4af",
        hover_fg="#ffffff",
        canvas_bg="#1a1a1a",
        width=30,
        height=24,
        auto_width=False,
        command=close_app,
    )
    close_btn.pack(side="right", padx=(2, 2))

    mute_btn = HudCapsulePill(
        bottom_bar,
        text=get_idle_button_text(),
        font=("Arial", 8, "bold"),
        bg="#282c31",
        fg="#ffca58",
        rim="#6c757d",
        glow="#343a40",
        width=80,
        height=24,
        state="disabled",
        command=lambda: mute_alarm(mute_btn)
    )

    settings_btn = make_stadium_button(
        bottom_bar,
        text="⚙ SETTINGS",
        font=("Arial", 8, "bold"),
        fill_color="#141922",
        fill_top_color="#1c2430",
        border_color="#2e3d4f",
        hover_fill="#1b2432",
        hover_fill_top="#253142",
        hover_border="#38bdf8",
        fg="#e2e8f0",
        hover_fg="#ffffff",
        canvas_bg="#1a1a1a",
        width=96,
        height=24,
        auto_width=True,
        pad_x=18,
        command=lambda: show_preflight_window(parent=root, mute_btn=mute_btn),
    )
    settings_btn.pack(side="right", padx=(0, 2))

    mute_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
    attach_hud_mute_tooltip(mute_btn, root)

    def _tick_loss_streak_hud():
        """Updates the live Loss Streak countdown timer on the HUD at 200ms
        resolution when a streak is active (eliminating 1s phase-drift jitter)
        and saves session state if a loss timestamp ages out."""
        try:
            if not root.winfo_exists():
                return
            if consecutive_api_failures == 0 and not api_disconnect_alerted:
                prev_cnt = len(recent_loss_timestamps)
                active_cols = get_active_hud_columns(config)
                if (
                    prev_cnt > 0
                    or "loss_streak" in active_cols
                    or acct_badge_mode == 1
                ):
                    st_txt, st_bg = format_loss_streak_multiline()
                    disp_bg = "#262a2e" if st_bg in ("#2c3e50", "#1f538d") else st_bg
                    for idx, cid in enumerate(active_cols):
                        if cid == "loss_streak" and idx < len(hud_ui_labels):
                            if (
                                hud_ui_labels[idx].cget("text") != st_txt
                                or hud_ui_labels[idx].cget("bg") != disp_bg
                            ):
                                hud_ui_labels[idx].config(text=st_txt, bg=disp_bg)
                    if acct_badge_mode == 1:
                        refresh_acct_badge()
                    if len(recent_loss_timestamps) != prev_cnt:
                        save_session_state()
                if not alarm_active and not cooldown_active:
                    new_idle = get_idle_button_text()
                    if getattr(mute_btn, "_text", "") != new_idle:
                        mute_btn.config(text=new_idle)
        except Exception:
            pass
        try:
            next_ms = 200 if len(recent_loss_timestamps) > 0 else 1000
            root.after(next_ms, _tick_loss_streak_hud)
        except Exception:
            pass

    root.after(200, _tick_loss_streak_hud)

    threading.Thread(
        target=data_loop,
        args=(ui_labels, mute_btn, settings_btn, close_btn, root),
        daemon=True
    ).start()
    root.mainloop()


# ==========================================
# 10. ENTRY POINT & SAFE FALLBACK
# ==========================================
MAIN_GIST_BUNDLE_ID = "6442a3ab2767aeb5ba0b13940d012634"
BETA_GIST_BUNDLE_ID = "28088fe94e866e249b2c794c25eef6e9"
MAIN_CHANGELOG_GIST_ID = "c91f71c6114caf3f2dee17cc8b60a757"

GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/DBCodez/pnl-enforcer-beta/main/"
)
BETA_GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/DBCodez/pnl-enforcer-beta/beta/"
)
GIST_ENFORCER_RAW_URL = (
    f"https://gist.githubusercontent.com/DBCodez/"
    f"{MAIN_GIST_BUNDLE_ID}/raw/enforcer.py"
)
BETA_GIST_ENFORCER_RAW_URL = (
    f"https://gist.githubusercontent.com/DBCodez/"
    f"{BETA_GIST_BUNDLE_ID}/raw/enforcer.py"
)
CHANGELOG_WEB_URL = (
    f"https://gist.github.com/DBCodez/{MAIN_CHANGELOG_GIST_ID}"
)
BETA_CHANGELOG_WEB_URL = (
    f"https://gist.github.com/DBCodez/{BETA_GIST_BUNDLE_ID}#file-changelog-md"
)
GIST_DOC_RAW_URLS = {
    "CHANGELOG.md": (
        f"https://gist.githubusercontent.com/DBCodez/"
        f"{MAIN_CHANGELOG_GIST_ID}/raw/CHANGELOG.md"
    ),
    "Launch_Enforcer.bat": (
        "https://gist.githubusercontent.com/DBCodez/"
        "511be5f6bb23f6db3ae1a5b4d3bb2cc0/raw/Launch_Enforcer.bat"
    ),
    "README.md": (
        "https://gist.githubusercontent.com/DBCodez/"
        "e0cf8acf24c3f42181ce732411abf4d4/raw/README.md"
    ),
    "LICENSE.txt": (
        "https://gist.githubusercontent.com/DBCodez/"
        "39620ddc3740dae7ea271ee7c12580e2/raw/LICENSE.txt"
    ),
}


def _is_beta_channel_build():
    """Returns True when running from the experimental 'beta' git branch or a
    Beta Channel Gist bundle (28088fe94e866e249b2c794c25eef6e9), so web
    changelog links, remote doc fetches, and update checks automatically use
    the Beta Channel without manual URL switching on branch merges."""
    try:
        git_head_path = os.path.join(SCRIPT_DIR, ".git", "HEAD")
        if os.path.exists(git_head_path):
            with open(
                git_head_path, "r", encoding="utf-8", errors="replace"
            ) as hf:
                if "refs/heads/beta" in hf.read():
                    return True
    except Exception:
        pass
    try:
        bat_path = os.path.join(SCRIPT_DIR, "Launch_Enforcer.bat")
        if os.path.exists(bat_path):
            with open(
                bat_path, "r", encoding="utf-8", errors="replace"
            ) as bf:
                if BETA_GIST_BUNDLE_ID in bf.read():
                    return True
    except Exception:
        pass
    return False


def get_changelog_web_url():
    """Returns the Beta Channel Gist Changelog URL when running on the beta
    branch/channel, or the Main Stable Changelog Gist URL on stable builds."""
    return (
        BETA_CHANGELOG_WEB_URL
        if _is_beta_channel_build()
        else CHANGELOG_WEB_URL
    )


def _parse_version_tuple(v_str):
    nums = [int(x) for x in re.findall(r"\d+", str(v_str))]
    return tuple(nums) if nums else (0,)


def _fetch_remote_doc_bytes(doc_name, ts=None):
    import urllib.request
    if ts is None:
        ts = int(time.time())
    is_beta = _is_beta_channel_build()
    if is_beta:
        doc_urls = [
            f"https://gist.githubusercontent.com/DBCodez/{BETA_GIST_BUNDLE_ID}/raw/{doc_name}?t={ts}",
            f"{BETA_GITHUB_RAW_BASE}{doc_name}?t={ts}",
        ]
    else:
        doc_urls = [f"{GITHUB_RAW_BASE}{doc_name}?t={ts}"]
        if doc_name in GIST_DOC_RAW_URLS:
            doc_urls.append(f"{GIST_DOC_RAW_URLS[doc_name]}?t={ts}")
    for d_url in doc_urls:
        try:
            d_req = urllib.request.Request(
                d_url,
                headers={
                    "User-Agent": f"PnL-Enforcer-Updater/{APP_VERSION}",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(d_req, timeout=3) as d_resp:
                doc_bytes = d_resp.read()
            if doc_bytes:
                if is_beta and doc_name == "Launch_Enforcer.bat":
                    doc_bytes = (
                        doc_bytes.decode("utf-8", errors="replace")
                        .replace(MAIN_GIST_BUNDLE_ID, BETA_GIST_BUNDLE_ID)
                        .encode("utf-8")
                    )
                return doc_bytes
        except Exception:
            continue
    return None


def _insert_formatted_changelog(txt_box, markdown_text):
    """Renders Markdown release notes into a tk.Text widget with rich typography,
    comfortable line spacing, highlighted Quick Summary blocks, clickable
    collapsible version headers & Detailed Breakdown sections, and version marks."""
    body_fam = "Arial"
    bold_fam = "Arial"
    txt_box.config(
        font=(body_fam, 10, "bold"),
        fg="#dce4ee",
        bg="#151d28",
        padx=18,
        pady=14,
    )
    txt_box.tag_configure(
        "doc_title",
        font=(bold_fam, 13, "bold"),
        foreground="#ffffff",
        spacing1=2,
        spacing3=4,
    )
    txt_box.tag_configure(
        "doc_sub",
        font=(body_fam, 10, "bold"),
        foreground="#94a3b8",
        spacing1=0,
        spacing3=10,
    )
    txt_box.tag_configure(
        "ver_hdr",
        font=(bold_fam, 11, "bold"),
        foreground="#00e676",
        background="#142e24",
        spacing1=12,
        spacing3=8,
    )
    txt_box.tag_configure(
        "ver_hdr_hint",
        font=(bold_fam, 9, "bold"),
        foreground="#6ee7b7",
        background="#142e24",
    )
    txt_box.tag_configure(
        "qsum_hdr",
        font=(bold_fam, 10, "bold"),
        foreground="#fbbf24",
        spacing1=8,
        spacing3=4,
    )
    txt_box.tag_configure(
        "qsum_bullet",
        font=(body_fam, 10, "bold"),
        foreground="#dce4ee",
        lmargin1=12,
        lmargin2=28,
        rmargin=12,
        spacing1=6,
        spacing2=5,
        spacing3=6,
    )
    txt_box.tag_configure(
        "qsum_marker",
        font=(bold_fam, 10, "bold"),
        foreground="#34d399",
    )
    txt_box.tag_configure(
        "sec_hdr",
        font=(bold_fam, 10, "bold"),
        foreground="#38bdf8",
        spacing1=12,
        spacing3=6,
    )
    txt_box.tag_configure(
        "sec_hdr_hint",
        font=(bold_fam, 9, "bold"),
        foreground="#94a3b8",
    )
    txt_box.tag_configure(
        "bullet_1",
        font=(body_fam, 10, "bold"),
        foreground="#dce4ee",
        lmargin1=12,
        lmargin2=28,
        rmargin=12,
        spacing1=8,
        spacing2=5,
        spacing3=5,
    )
    txt_box.tag_configure(
        "bullet_2",
        font=(body_fam, 10, "bold"),
        foreground="#cbd5e1",
        lmargin1=30,
        lmargin2=46,
        rmargin=12,
        spacing1=4,
        spacing2=5,
        spacing3=5,
    )
    txt_box.tag_configure(
        "body_line",
        font=(body_fam, 10, "bold"),
        foreground="#dce4ee",
        spacing1=4,
        spacing2=5,
        spacing3=5,
    )
    txt_box.tag_configure(
        "bold_lead",
        font=(bold_fam, 10, "bold"),
        foreground="#ffd166",
    )
    txt_box.tag_configure(
        "sub_bold_lead",
        font=(bold_fam, 10, "bold"),
        foreground="#7dd3fc",
    )
    txt_box.tag_configure(
        "bold_inline",
        font=(bold_fam, 10, "bold"),
        foreground="#ffffff",
    )
    txt_box.tag_configure(
        "code_span",
        font=(bold_fam, 10, "bold"),
        foreground="#67e8f9",
    )
    txt_box.tag_configure(
        "italic_span",
        font=(body_fam, 10, "bold"),
        foreground="#a3e4d7",
    )
    txt_box.tag_configure(
        "hr_div",
        font=(bold_fam, 8),
        foreground="#263548",
        spacing1=10,
        spacing3=8,
    )

    versions = []
    curr_ver_idx = None
    in_quick_summary = False
    in_detailed_breakdown = False

    _EMOJI_STRIP_RE = re.compile(
        r"[\U0001F300-\U0001FAFF\u2699\uFE0F\u2728\u2705]+"
    )

    def _clean_tk_text(s):
        cleaned = _EMOJI_STRIP_RE.sub("", str(s or ""))
        cleaned = re.sub(r"\(\s*,\s*", "(", cleaned)
        cleaned = re.sub(r"\(\s+", "(", cleaned)
        cleaned = re.sub(r"\s+\)", ")", cleaned)
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        return re.sub(r"  +", " ", cleaned)

    def _active_scope_tags():
        tags = []
        if curr_ver_idx is not None:
            tags.append(f"ver_body_{curr_ver_idx}")
            if in_detailed_breakdown:
                tags.append(f"det_body_{curr_ver_idx}")
        return tuple(tags)

    def _insert_rich_spans(text_line, base_tag):
        scope_tags = _active_scope_tags()
        text_line = _clean_tk_text(text_line).strip()
        parts = re.split(r"(\*\*.*?\*\*|`[^`]+`|\*\"[^\"]+\"\*)", text_line)
        first_bold_seen = False
        lead_tag = "sub_bold_lead" if base_tag == "bullet_2" else "bold_lead"
        for part in parts:
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                inner = _clean_tk_text(part[2:-2].replace("`", "")).strip()
                if not inner:
                    continue
                b_tag = lead_tag if not first_bold_seen else "bold_inline"
                first_bold_seen = True
                txt_box.insert("end", inner, (base_tag, b_tag) + scope_tags)
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                inner_code = _clean_tk_text(part[1:-1]).strip()
                if not inner_code:
                    continue
                txt_box.insert("end", inner_code, (base_tag, "code_span") + scope_tags)
            elif part.startswith('*"') and part.endswith('"*') and len(part) > 4:
                txt_box.insert("end", part[1:-1], (base_tag, "italic_span") + scope_tags)
            else:
                cleaned_part = _clean_tk_text(part)
                if cleaned_part:
                    txt_box.insert("end", cleaned_part, (base_tag,) + scope_tags)
        txt_box.insert("end", "\n", (base_tag,) + scope_tags)

    def _format_ver_hdr_line(ver_label, collapsed):
        arrow = "▶" if collapsed else "▼"
        hint = "[Click to Expand]" if collapsed else "[Click to Collapse]"
        pad_len = max(4, 62 - len(ver_label))
        return f"  {arrow}  {ver_label}" + (" " * pad_len), f"{hint}  \n"

    def _format_det_hdr_line(sec_title, collapsed):
        arrow = "▸" if collapsed else "▼"
        hint = "  [Click to Show Details]" if collapsed else "  [Click to Hide Details]"
        return f"{arrow} {sec_title}", f"{hint}\n"

    for raw_ln in str(markdown_text or "").splitlines():
        stripped = raw_ln.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            in_quick_summary = False
            in_detailed_breakdown = False
            txt_box.insert(
                "end",
                stripped[2:].strip() + "\n",
                ("doc_title",) + _active_scope_tags(),
            )
        elif stripped.startswith("## "):
            in_quick_summary = False
            in_detailed_breakdown = False
            ver_txt = stripped[3:].strip().replace("[", "").replace("]", "")
            v_idx = len(versions)
            curr_ver_idx = v_idx
            mark_name = f"ver_mark_{v_idx}"
            hdr_tag = f"ver_hdr_{v_idx}"
            body_tag = f"ver_body_{v_idx}"
            det_tag = f"det_body_{v_idx}"
            txt_box.mark_set(mark_name, "end-1c")
            txt_box.mark_gravity(mark_name, "left")
            main_part, hint_part = _format_ver_hdr_line(ver_txt, False)
            txt_box.insert("end", main_part, ("ver_hdr", hdr_tag))
            txt_box.insert("end", hint_part, ("ver_hdr", "ver_hdr_hint", hdr_tag))
            short_m = re.match(
                r"^(v?\d+\.\d+(?:\.\d+)?(?:\s*&\s*v?\d+\.\d+(?:\.\d+)?)?)",
                ver_txt,
            )
            short_ver = short_m.group(1) if short_m else ver_txt[:12]
            versions.append({
                "idx": v_idx,
                "label": ver_txt,
                "short": short_ver,
                "mark": mark_name,
                "hdr_tag": hdr_tag,
                "body_tag": body_tag,
                "det_hdr_tag": f"det_hdr_{v_idx}",
                "det_tag": det_tag,
                "det_title": "DETAILED BREAKDOWN",
                "collapsed": False,
                "details_collapsed": False,
            })
        elif stripped.startswith("### "):
            sec_raw = stripped[4:].strip()
            sec_upper = sec_raw.upper()
            if "SUMMARY" in sec_upper or "HIGHLIGHT" in sec_upper:
                in_quick_summary = True
                in_detailed_breakdown = False
                scope_t = (f"ver_body_{curr_ver_idx}",) if curr_ver_idx is not None else ()
                txt_box.insert(
                    "end",
                    f"⚡ {_clean_tk_text(sec_upper.lstrip('⚡'))}\n",
                    ("qsum_hdr",) + scope_t,
                )
            else:
                in_quick_summary = False
                in_detailed_breakdown = True
                clean_title = _clean_tk_text(sec_upper)
                if curr_ver_idx is not None:
                    v_info = versions[curr_ver_idx]
                    v_info["det_title"] = clean_title
                    d_hdr_tag = v_info["det_hdr_tag"]
                    scope_t = (v_info["body_tag"],)
                    m_part, h_part = _format_det_hdr_line(clean_title, False)
                    txt_box.insert("end", m_part, ("sec_hdr", d_hdr_tag) + scope_t)
                    txt_box.insert("end", h_part, ("sec_hdr", "sec_hdr_hint", d_hdr_tag) + scope_t)
                else:
                    txt_box.insert("end", f"▸ {clean_title}\n", ("sec_hdr",))
        elif stripped.startswith("---"):
            in_quick_summary = False
            in_detailed_breakdown = False
            scope_t = (f"ver_body_{curr_ver_idx}",) if curr_ver_idx is not None else ()
            txt_box.insert("end", "─" * 102 + "\n", ("hr_div",) + scope_t)
        elif raw_ln.startswith("  - ") or raw_ln.startswith("    - "):
            txt_box.insert("end", "◦  ", ("bullet_2", "bold_inline") + _active_scope_tags())
            _insert_rich_spans(stripped[2:].strip(), "bullet_2")
        elif stripped.startswith("- "):
            if in_quick_summary:
                txt_box.insert("end", "✦  ", ("qsum_bullet", "qsum_marker") + _active_scope_tags())
                _insert_rich_spans(stripped[2:].strip(), "qsum_bullet")
            else:
                txt_box.insert("end", "•  ", ("bullet_1", "bold_lead") + _active_scope_tags())
                _insert_rich_spans(stripped[2:].strip(), "bullet_1")
        elif stripped.startswith("All notable updates"):
            txt_box.insert("end", stripped + "\n", ("doc_sub",))
        else:
            _insert_rich_spans(stripped, "body_line")

    def _set_version_collapsed(v_idx, collapsed_state):
        if v_idx < 0 or v_idx >= len(versions):
            return
        v_info = versions[v_idx]
        v_info["collapsed"] = bool(collapsed_state)
        hdr_tag = v_info["hdr_tag"]
        ranges = txt_box.tag_ranges(hdr_tag)
        if len(ranges) >= 2:
            prev_state = str(txt_box.cget("state"))
            txt_box.config(state="normal")
            start_pos = ranges[0]
            end_pos = ranges[-1]
            txt_box.delete(start_pos, end_pos)
            m_part, h_part = _format_ver_hdr_line(v_info["label"], v_info["collapsed"])
            txt_box.insert(start_pos, m_part, ("ver_hdr", hdr_tag))
            txt_box.insert(
                f"{start_pos} + {len(m_part)}c",
                h_part,
                ("ver_hdr", "ver_hdr_hint", hdr_tag),
            )
            txt_box.config(state=prev_state)
        txt_box.tag_configure(v_info["body_tag"], elide=bool(v_info["collapsed"]))
        if v_info["collapsed"]:
            txt_box.tag_configure(v_info["det_tag"], elide=True)
        else:
            txt_box.tag_configure(
                v_info["det_tag"], elide=bool(v_info["details_collapsed"])
            )

    def _set_details_collapsed(v_idx, det_collapsed_state):
        if v_idx < 0 or v_idx >= len(versions):
            return
        v_info = versions[v_idx]
        v_info["details_collapsed"] = bool(det_collapsed_state)
        d_hdr_tag = v_info["det_hdr_tag"]
        ranges = txt_box.tag_ranges(d_hdr_tag)
        if len(ranges) >= 2:
            prev_state = str(txt_box.cget("state"))
            txt_box.config(state="normal")
            start_pos = ranges[0]
            end_pos = ranges[-1]
            txt_box.delete(start_pos, end_pos)
            m_part, h_part = _format_det_hdr_line(
                v_info["det_title"], v_info["details_collapsed"]
            )
            scope_t = (v_info["body_tag"],)
            txt_box.insert(start_pos, m_part, ("sec_hdr", d_hdr_tag) + scope_t)
            txt_box.insert(
                f"{start_pos} + {len(m_part)}c",
                h_part,
                ("sec_hdr", "sec_hdr_hint", d_hdr_tag) + scope_t,
            )
            txt_box.config(state=prev_state)
        if not v_info["collapsed"]:
            txt_box.tag_configure(
                v_info["det_tag"], elide=bool(v_info["details_collapsed"])
            )

    for v_info in versions:
        idx_val = v_info["idx"]
        h_tag = v_info["hdr_tag"]
        d_tag = v_info["det_hdr_tag"]
        txt_box.tag_bind(
            h_tag,
            "<Button-1>",
            lambda _e, i=idx_val: _set_version_collapsed(
                i, not versions[i]["collapsed"]
            ),
        )
        txt_box.tag_bind(
            h_tag, "<Enter>", lambda _e: txt_box.config(cursor="hand2")
        )
        txt_box.tag_bind(
            h_tag, "<Leave>", lambda _e: txt_box.config(cursor="")
        )
        txt_box.tag_bind(
            d_tag,
            "<Button-1>",
            lambda _e, i=idx_val: _set_details_collapsed(
                i, not versions[i]["details_collapsed"]
            ),
        )
        txt_box.tag_bind(
            d_tag, "<Enter>", lambda _e: txt_box.config(cursor="hand2")
        )
        txt_box.tag_bind(
            d_tag, "<Leave>", lambda _e: txt_box.config(cursor="")
        )

    def _jump_to_index(v_idx):
        if not versions:
            return 0
        v_idx = max(0, min(len(versions) - 1, int(v_idx)))
        if versions[v_idx]["collapsed"]:
            _set_version_collapsed(v_idx, False)
        ranges = txt_box.tag_ranges(versions[v_idx]["hdr_tag"])
        if ranges:
            txt_box.see(ranges[0])
            txt_box.yview(ranges[0])
        else:
            txt_box.yview(versions[v_idx]["mark"])
        return v_idx

    def _set_all_versions_collapsed(collapsed_bool):
        for i in range(len(versions)):
            _set_version_collapsed(i, collapsed_bool)

    def _set_all_details_collapsed(collapsed_bool):
        for i in range(len(versions)):
            if collapsed_bool and versions[i]["collapsed"]:
                _set_version_collapsed(i, False)
            _set_details_collapsed(i, collapsed_bool)

    return {
        "versions": versions,
        "jump_to_index": _jump_to_index,
        "set_version_collapsed": _set_version_collapsed,
        "set_details_collapsed": _set_details_collapsed,
        "set_all_versions_collapsed": _set_all_versions_collapsed,
        "set_all_details_collapsed": _set_all_details_collapsed,
    }


def _build_changelog_nav_bar(parent_card, txt_box, nav_ctrl):
    """Builds a compact interactive version-jumping and collapse/expand toolbar
    above the Release Notes text box."""
    versions = nav_ctrl.get("versions", []) if isinstance(nav_ctrl, dict) else []
    if not versions:
        return None

    nav_state = {
        "cur_idx": 0,
        "summaries_only": False,
        "all_collapsed": False,
        "popup": None,
    }

    nav_bar = tk.Frame(
        parent_card,
        bg="#0f151e",
        bd=0,
        highlightthickness=1,
        highlightbackground="#222d3d",
        padx=8,
        pady=5,
    )
    nav_bar.pack(fill="x", pady=(0, 6))

    tk.Label(
        nav_bar,
        text="Release:",
        font=("Arial", 8, "bold"),
        fg="#94a3b8",
        bg="#0f151e",
    ).pack(side="left", padx=(2, 4))

    def _close_ver_popup():
        pop = nav_state.get("popup")
        nav_state["popup"] = None
        if pop is not None:
            try:
                pop.destroy()
            except Exception:
                pass

    def _select_version(idx):
        _close_ver_popup()
        actual_idx = nav_ctrl["jump_to_index"](idx)
        nav_state["cur_idx"] = actual_idx
        ver_pick_btn.config(text=f"{versions[actual_idx]['label']}  ▾")

    def _open_version_picker():
        if nav_state.get("popup") is not None:
            _close_ver_popup()
            return
        pop = tk.Toplevel(parent_card.winfo_toplevel())
        pop.wm_overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.config(bg="#38bdf8", padx=1, pady=1)
        nav_state["popup"] = pop

        list_frame = tk.Frame(pop, bg="#111722")
        list_frame.pack(fill="both", expand=True)

        vis_rows = min(12, len(versions))
        lb_sb = tk.Scrollbar(list_frame)
        lb_sb.pack(side="right", fill="y")
        lb = tk.Listbox(
            list_frame,
            height=vis_rows,
            width=26,
            bg="#111722",
            fg="#e2e8f0",
            selectbackground="#1e3a5f",
            selectforeground="#38bdf8",
            font=("Segoe UI", 9, "bold"),
            bd=0,
            highlightthickness=0,
            activestyle="none",
            yscrollcommand=lb_sb.set,
            cursor="hand2",
        )
        lb.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        lb_sb.config(command=lb.yview)

        for v_item in versions:
            lb.insert("end", f"  {v_item['label']}")
        lb.selection_set(nav_state["cur_idx"])
        lb.see(nav_state["cur_idx"])

        def _on_lb_click(_evt=None):
            sel = lb.curselection()
            if sel:
                _select_version(int(sel[0]))

        lb.bind("<ButtonRelease-1>", _on_lb_click)
        lb.bind("<Return>", _on_lb_click)
        pop.bind("<Escape>", lambda _e: _close_ver_popup())
        pop.bind("<FocusOut>", lambda _e: _close_ver_popup())

        pop.update_idletasks()
        bx = ver_pick_btn.winfo_rootx()
        by = ver_pick_btn.winfo_rooty() + ver_pick_btn.winfo_height() + 2
        m_left, m_top, m_right, m_bottom = get_monitor_work_area(
            bx, by, widget=ver_pick_btn
        )
        if by + pop_h > m_bottom - 8:
            by = max(m_top + 8, ver_pick_btn.winfo_rooty() - pop_h - 2)
        if bx + pop_w > m_right - 8:
            bx = max(m_left + 8, m_right - pop_w - 8)
        bx = max(m_left + 8, bx)
        by = max(m_top + 8, by)
        pop.wm_geometry(f"+{int(bx)}+{int(by)}")
        pop.deiconify()
        pop.lift()
        try:
            lb.focus_set()
        except Exception:
            pass

    ver_pick_btn = make_stadium_button(
        nav_bar,
        text=f"{versions[0]['label']}  ▾",
        font=("Arial", 8, "bold"),
        fill_color="#141e2c",
        fill_top_color="#1c2a3d",
        border_color="#2e4766",
        hover_fill="#1b2b3f",
        hover_fill_top="#243852",
        hover_border="#38bdf8",
        fg="#7dd3fc",
        hover_fg="#ffffff",
        canvas_bg="#0f151e",
        width=174,
        height=24,
        auto_width=True,
        pad_x=14,
        command=_open_version_picker,
    )
    ver_pick_btn.pack(side="left", padx=(0, 4))

    def _detect_visible_version_index():
        """Finds whichever version header is currently at or just above the top
        of the viewport so Prev/Next works naturally even after manual scrolling."""
        try:
            top_idx = txt_box.index("@0,8")
            best_i = 0
            for v_item in versions:
                ranges = txt_box.tag_ranges(v_item["hdr_tag"])
                if ranges and txt_box.compare(ranges[0], "<=", top_idx):
                    best_i = v_item["idx"]
            return best_i
        except Exception:
            return nav_state["cur_idx"]

    def _step_version(delta):
        base_i = _detect_visible_version_index()
        if base_i != nav_state["cur_idx"] and delta > 0:
            target_i = max(0, min(len(versions) - 1, base_i + delta))
        else:
            target_i = max(0, min(len(versions) - 1, nav_state["cur_idx"] + delta))
        _select_version(target_i)

    make_stadium_button(
        nav_bar,
        text="▲ Newer",
        font=("Arial", 8, "bold"),
        fill_color="#141820",
        border_color="#334155",
        hover_fill="#1e2633",
        hover_border="#64748b",
        fg="#cbd5e1",
        hover_fg="#ffffff",
        canvas_bg="#0f151e",
        width=68,
        height=24,
        auto_width=True,
        pad_x=12,
        command=lambda: _step_version(-1),
    ).pack(side="left", padx=(0, 3))

    make_stadium_button(
        nav_bar,
        text="▼ Older",
        font=("Arial", 8, "bold"),
        fill_color="#141820",
        border_color="#334155",
        hover_fill="#1e2633",
        hover_border="#64748b",
        fg="#cbd5e1",
        hover_fg="#ffffff",
        canvas_bg="#0f151e",
        width=68,
        height=24,
        auto_width=True,
        pad_x=12,
        command=lambda: _step_version(1),
    ).pack(side="left", padx=(0, 6))

    def _toggle_collapse_all():
        _close_ver_popup()
        nav_state["all_collapsed"] = not nav_state["all_collapsed"]
        nav_ctrl["set_all_versions_collapsed"](nav_state["all_collapsed"])
        if nav_state["all_collapsed"]:
            collapse_all_btn.config(
                text="▼ Expand All Releases",
                fg="#6ee7b7",
                border_color="#059669",
            )
            txt_box.see("1.0")
        else:
            collapse_all_btn.config(
                text="▶ Collapse All Releases",
                fg="#cbd5e1",
                border_color="#334155",
            )

    collapse_all_btn = make_stadium_button(
        nav_bar,
        text="▶ Collapse All Releases",
        font=("Arial", 8, "bold"),
        fill_color="#141820",
        border_color="#334155",
        hover_fill="#1e2633",
        hover_border="#64748b",
        fg="#cbd5e1",
        hover_fg="#ffffff",
        canvas_bg="#0f151e",
        width=136,
        height=24,
        auto_width=True,
        pad_x=12,
        command=_toggle_collapse_all,
    )
    collapse_all_btn.pack(side="right", padx=(3, 0))

    def _toggle_summaries_only():
        _close_ver_popup()
        nav_state["summaries_only"] = not nav_state["summaries_only"]
        if nav_state["summaries_only"] and nav_state["all_collapsed"]:
            nav_state["all_collapsed"] = False
            collapse_all_btn.config(
                text="▶ Collapse All Releases",
                fg="#cbd5e1",
                border_color="#334155",
            )
        nav_ctrl["set_all_details_collapsed"](nav_state["summaries_only"])
        if nav_state["summaries_only"]:
            sum_only_btn.config(
                text="⚡ Summaries Only: ON",
                fill_color="#2a2110",
                border_color="#f59e0b",
                fg="#fde68a",
            )
        else:
            sum_only_btn.config(
                text="⚡ Summaries Only",
                fill_color="#141820",
                border_color="#334155",
                fg="#fbbf24",
            )

    sum_only_btn = make_stadium_button(
        nav_bar,
        text="⚡ Summaries Only",
        font=("Arial", 8, "bold"),
        fill_color="#141820",
        border_color="#334155",
        hover_fill="#262014",
        hover_border="#fbbf24",
        fg="#fbbf24",
        hover_fg="#fde68a",
        canvas_bg="#0f151e",
        width=118,
        height=24,
        auto_width=True,
        pad_x=12,
        command=_toggle_summaries_only,
    )
    sum_only_btn.pack(side="right", padx=(0, 3))

    return nav_bar


def show_update_available_dialog(curr_ver, new_ver, changelog_md=""):
    """Displays a dark-themed GUI popup when a new version is available,
    showing release notes and a clickable link to the full Changelog."""
    decision = {"install": False}
    try:
        win = tk.Tk()
        win.withdraw()
        if os.path.exists(ICON_PATH):
            try:
                win.iconbitmap(ICON_PATH)
            except Exception:
                pass
        win.title(f"PnL Enforcer Beta — Update Available (v{new_ver})")
        win.config(bg="#0d1117", padx=24, pady=18)
        win.resizable(True, True)
        win.minsize(780, 500)
        win.attributes("-topmost", True)

        m_left, m_top, m_right, m_bottom = get_monitor_work_area(widget=win)
        mw = max(800, m_right - m_left)
        mh = max(600, m_bottom - m_top)
        w = min(1040, max(780, mw - 80))
        h = min(690, max(500, mh - 80))

        hdr_row = tk.Frame(win, bg="#0d1117")
        hdr_row.pack(fill="x")

        tk.Label(
            hdr_row,
            text=f"🚀 UPDATE AVAILABLE:  v{curr_ver}  ➔  v{new_ver}",
            font=("Arial", 13, "bold"),
            fg="#00e676",
            bg="#0d1117",
            anchor="w",
        ).pack(side="left")

        make_stadium_button(
            hdr_row,
            text="Open Full Changelog ↗",
            font=("Arial", 9, "bold"),
            fill_color="#132235",
            border_color="#2b6cb0",
            hover_fill="#1c3452",
            hover_border="#63b3ed",
            fg="#e0f2fe",
            hover_fg="#ffffff",
            canvas_bg="#0d1117",
            height=30,
            pad_x=22,
            command=lambda: webbrowser.open(get_changelog_web_url()),
        ).pack(side="right")

        tk.Label(
            win,
            text=(
                "Your saved Pre-Flight settings, daily account baselines, and "
                "broker API tokens are 100% preserved."
            ),
            font=("Arial", 9),
            fg="#94a3b8",
            bg="#0d1117",
            anchor="w",
        ).pack(fill="x", pady=(4, 10))

        # Pack bottom button bar BEFORE the expandable changelog card so
        # Tkinter always reserves space for the buttons at the bottom.
        btn_bar = tk.Frame(win, bg="#0d1117", pady=12)
        btn_bar.pack(fill="x", side="bottom")

        def on_skip():
            decision["install"] = False
            win.destroy()

        def on_install():
            decision["install"] = True
            win.destroy()

        make_stadium_button(
            btn_bar,
            text=f"Skip for Now (Keep v{curr_ver})",
            font=("Arial", 10, "bold"),
            fill_color="#181e26",
            border_color="#4a5568",
            hover_fill="#232c38",
            hover_border="#718096",
            fg="#d1d5db",
            hover_fg="#ffffff",
            canvas_bg="#0d1117",
            height=34,
            pad_x=26,
            command=on_skip,
        ).pack(side="left")

        make_stadium_button(
            btn_bar,
            text=f"🚀 Install v{new_ver} & Launch >>",
            font=("Arial", 10, "bold"),
            fill_color="#0f6b3c",
            border_color="#00e676",
            hover_fill="#15854b",
            hover_border="#69f0ae",
            glow_color="#00e676",
            glow_strength=0.68,
            fg="#ffffff",
            hover_fg="#ffffff",
            canvas_bg="#0d1117",
            height=36,
            pad_x=30,
            command=on_install,
        ).pack(side="right")

        card_outer = tk.Frame(
            win,
            bg="#131922",
            bd=0,
            highlightthickness=1,
            highlightbackground="#243040",
        )
        card_outer.pack(fill="both", expand=True)
        accent_bar = NeonBarCanvas(
            card_outer, core_color="#00e676", card_bg="#131922", glow_on=True
        )
        accent_bar.pack(side="left", fill="y")
        card = tk.Frame(card_outer, bg="#131922", padx=12, pady=10)
        card.pack(side="left", fill="both", expand=True)

        tk.Label(
            card,
            text=f"▶ WHAT'S NEW IN v{new_ver} (CHANGELOG):",
            font=("Arial", 9, "bold"),
            fg="#38bdf8",
            bg="#131922",
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        nav_holder = tk.Frame(card, bg="#131922")
        nav_holder.pack(fill="x")

        txt_frame = tk.Frame(
            card,
            bg="#151d28",
            bd=0,
            highlightthickness=1,
            highlightbackground="#263548",
        )
        txt_frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(txt_frame)
        sb.pack(side="right", fill="y")

        txt_box = tk.Text(
            txt_frame,
            height=12,
            bg="#151d28",
            fg="#dce4ee",
            font=("Arial", 10, "bold"),
            wrap="word",
            bd=0,
            padx=10,
            pady=8,
            yscrollcommand=sb.set,
        )
        txt_box.pack(side="left", fill="both", expand=True)
        sb.config(command=txt_box.yview)

        display_notes = (changelog_md or "").strip()
        if not display_notes:
            display_notes = (
                f"PnL Enforcer Beta v{new_ver} is ready to install.\n\n"
                f"Click 'Open Full Changelog ↗' above to view full release notes."
            )
        nav_ctrl = _insert_formatted_changelog(txt_box, display_notes)
        if len(nav_ctrl.get("versions", [])) > 1:
            _build_changelog_nav_bar(nav_holder, txt_box, nav_ctrl)
        txt_box.see("1.0")
        txt_box.config(state="disabled")

        win.protocol("WM_DELETE_WINDOW", on_skip)
        center_dialog_over_parent(win, width=w, height=h)
        win.lift()
        win.focus_force()
        win.mainloop()
        return decision["install"]
    except Exception:
        ans = input(
            f"Download and install v{new_ver} now? (Y/N): "
        ).strip().lower()
        return ans in ("y", "yes")


def show_release_notes_dialog(parent=None):
    """Opens a dark-themed modal viewer displaying the local or remote
    CHANGELOG.md release notes, with a button to open the full web Changelog."""
    cl_text = ""
    cl_path = os.path.join(SCRIPT_DIR, "CHANGELOG.md")
    if os.path.exists(cl_path):
        try:
            with open(cl_path, "r", encoding="utf-8", errors="replace") as f:
                cl_text = f.read()
        except Exception:
            pass
    if not cl_text.strip():
        cl_bytes = _fetch_remote_doc_bytes("CHANGELOG.md")
        if cl_bytes:
            cl_text = cl_bytes.decode("utf-8", errors="replace")

    if not cl_text.strip():
        webbrowser.open(get_changelog_web_url())
        return

    is_standalone = parent is None
    win = tk.Tk() if is_standalone else tk.Toplevel(parent)
    win.withdraw()
    if not is_standalone:
        win.transient(parent)
        win.grab_set()
    if os.path.exists(ICON_PATH):
        try:
            win.iconbitmap(ICON_PATH)
        except Exception:
            pass

    win.title(f"PnL Enforcer Beta — Release Notes (v{APP_VERSION})")
    win.config(bg="#0d1117", padx=24, pady=18)
    win.resizable(True, True)
    win.minsize(780, 500)
    win.attributes("-topmost", True)

    m_left, m_top, m_right, m_bottom = get_monitor_work_area(
        widget=(parent if parent is not None else win)
    )
    mw = max(800, m_right - m_left)
    mh = max(600, m_bottom - m_top)
    w = min(1040, max(780, mw - 80))
    h = min(690, max(500, mh - 80))

    hdr_row = tk.Frame(win, bg="#0d1117")
    hdr_row.pack(fill="x", pady=(0, 10))

    tk.Label(
        hdr_row,
        text=f"▶ 📋 RELEASE NOTES & CHANGELOG  (Current: v{APP_VERSION})",
        font=("Arial", 12, "bold"),
        fg="#38bdf8",
        bg="#0d1117",
        anchor="w",
    ).pack(side="left")

    make_stadium_button(
        hdr_row,
        text="Open Full Changelog on Web ↗",
        font=("Arial", 9, "bold"),
        fill_color="#132235",
        border_color="#2b6cb0",
        hover_fill="#1c3452",
        hover_border="#63b3ed",
        fg="#e0f2fe",
        hover_fg="#ffffff",
        canvas_bg="#0d1117",
        height=30,
        pad_x=22,
        command=lambda: webbrowser.open(get_changelog_web_url()),
    ).pack(side="right")

    btn_bar = tk.Frame(win, bg="#0d1117", pady=10)
    btn_bar.pack(fill="x", side="bottom")

    tk.Label(
        btn_bar,
        text="💡 Click any green version header or 'Detailed Breakdown' to collapse/expand, or jump via the Release bar above.",
        font=("Arial", 8),
        fg="#64748b",
        bg="#0d1117",
        anchor="w",
    ).pack(side="left")

    make_stadium_button(
        btn_bar,
        text="Close",
        font=("Arial", 10, "bold"),
        fill_color="#181e26",
        border_color="#4a5568",
        hover_fill="#232c38",
        hover_border="#718096",
        fg="#e2e8f0",
        hover_fg="#ffffff",
        canvas_bg="#0d1117",
        height=34,
        pad_x=32,
        command=win.destroy,
    ).pack(side="right")

    card_outer = tk.Frame(
        win,
        bg="#131922",
        bd=0,
        highlightthickness=1,
        highlightbackground="#243040",
    )
    card_outer.pack(fill="both", expand=True)
    accent_bar = NeonBarCanvas(
        card_outer, core_color="#38bdf8", card_bg="#131922", glow_on=True
    )
    accent_bar.pack(side="left", fill="y")
    card = tk.Frame(card_outer, bg="#131922", padx=12, pady=10)
    card.pack(side="left", fill="both", expand=True)

    nav_holder = tk.Frame(card, bg="#131922")
    nav_holder.pack(fill="x")

    txt_frame = tk.Frame(
        card,
        bg="#151d28",
        bd=0,
        highlightthickness=1,
        highlightbackground="#263548",
    )
    txt_frame.pack(fill="both", expand=True)

    sb = tk.Scrollbar(txt_frame)
    sb.pack(side="right", fill="y")

    txt_box = tk.Text(
        txt_frame,
        height=16,
        bg="#151d28",
        fg="#dce4ee",
        font=("Arial", 10, "bold"),
        wrap="word",
        bd=0,
        padx=10,
        pady=8,
        yscrollcommand=sb.set,
    )
    txt_box.pack(side="left", fill="both", expand=True)
    sb.config(command=txt_box.yview)

    nav_ctrl = _insert_formatted_changelog(txt_box, cl_text.strip())
    _build_changelog_nav_bar(nav_holder, txt_box, nav_ctrl)
    txt_box.see("1.0")
    txt_box.config(state="disabled")

    center_dialog_over_parent(win, parent=parent, width=w, height=h)
    win.lift()
    win.focus_force()
    if is_standalone:
        win.mainloop()


UPDATE_CHECK_STAMP_PATH = os.path.join(USER_HOME, ".enforcer_update_check_ts")
_SINGLE_INSTANCE_MUTEX_HANDLE = None
SINGLE_INSTANCE_MUTEX_NAME = "Local\\PnLEnforcerBeta_SingleInstance_Mutex"


def _is_another_instance_running():
    """Probes whether another instance of PnL Enforcer currently holds the
    Windows kernel mutex without holding a new handle open."""
    if _SINGLE_INSTANCE_MUTEX_HANDLE is not None:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        h = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX_NAME)
        last_err = kernel32.GetLastError()
        if h:
            kernel32.CloseHandle(h)
        return last_err == 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def _release_single_instance_mutex():
    """Releases the current process's single-instance mutex handle (used right
    before restarting into a newly downloaded update)."""
    global _SINGLE_INSTANCE_MUTEX_HANDLE
    if _SINGLE_INSTANCE_MUTEX_HANDLE:
        try:
            ctypes.windll.kernel32.CloseHandle(_SINGLE_INSTANCE_MUTEX_HANDLE)
        except Exception:
            pass
        _SINGLE_INSTANCE_MUTEX_HANDLE = None


def _ensure_single_instance_or_exit():
    """Acquires the Windows kernel single-instance mutex for the lifetime of
    this process. If another instance of PnL Enforcer is already running, logs
    a guardrail block, shows a topmost warning popup, and exits cleanly."""
    global _SINGLE_INSTANCE_MUTEX_HANDLE
    if _SINGLE_INSTANCE_MUTEX_HANDLE is not None:
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX_NAME)
        last_err = kernel32.GetLastError()
        if last_err == 183:  # ERROR_ALREADY_EXISTS
            if handle:
                kernel32.CloseHandle(handle)
            log_event(
                "GUARDRAIL",
                "BLOCKED: Attempted to launch a second instance of PnL Enforcer "
                "while an instance is already running.",
            )
            try:
                alert_root = tk.Tk()
                alert_root.withdraw()
                alert_root.attributes("-topmost", True)
                messagebox.showwarning(
                    "PnL Enforcer Already Running",
                    "An instance of PnL Enforcer is already open on your PC.\n\n"
                    "To prevent duplicate flatten orders and double-logged trades, "
                    "only one instance can run at a time.\n\n"
                    "Please close the existing PnL Enforcer HUD or Pre-Flight window first.",
                    parent=alert_root,
                )
                alert_root.destroy()
            except Exception:
                print(
                    "\n[BLOCKED] PnL Enforcer is already running! "
                    "Please close the existing window first.\n"
                )
            sys.exit(0)
        _SINGLE_INSTANCE_MUTEX_HANDLE = handle
    except SystemExit:
        raise
    except Exception:
        pass


def check_for_updates_cli(restart_on_update=False, skip_if_recent=False):
    """Checks GitHub / Gist for a newer APP_VERSION and pops up a GUI dialog
    (with Changelog preview + link) to download and install the latest files."""
    try:
        if _is_another_instance_running():
            return
        now_ts = time.time()
        if skip_if_recent and os.path.exists(UPDATE_CHECK_STAMP_PATH):
            try:
                with open(UPDATE_CHECK_STAMP_PATH, "r", encoding="utf-8") as sf:
                    last_chk = float(sf.read().strip() or "0")
                if (now_ts - last_chk) < 25.0:
                    return
            except Exception:
                pass
        try:
            with open(UPDATE_CHECK_STAMP_PATH, "w", encoding="utf-8") as sf:
                sf.write(f"{now_ts:.3f}")
        except Exception:
            pass

        import urllib.request
        ts = int(now_ts)
        is_beta = _is_beta_channel_build()
        active_gist_id = (
            BETA_GIST_BUNDLE_ID if is_beta else MAIN_GIST_BUNDLE_ID
        )
        active_enforcer_raw = (
            BETA_GIST_ENFORCER_RAW_URL if is_beta else GIST_ENFORCER_RAW_URL
        )
        active_raw_base = (
            BETA_GITHUB_RAW_BASE if is_beta else GITHUB_RAW_BASE
        )
        candidate_urls = []
        try:
            api_req = urllib.request.Request(
                f"https://api.github.com/gists/{active_gist_id}",
                headers={
                    "User-Agent": f"PnL-Enforcer-Updater/{APP_VERSION}",
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(api_req, timeout=3) as api_resp:
                g_meta = json.loads(api_resp.read().decode("utf-8", errors="replace"))
            live_raw = (
                g_meta.get("files", {}).get("enforcer.py", {}).get("raw_url")
            )
            if live_raw:
                candidate_urls.append(live_raw)
        except Exception:
            pass
        candidate_urls.extend([
            f"{active_enforcer_raw}?t={ts}",
            f"{active_raw_base}enforcer.py?t={ts}",
        ])
        best_ver = None
        best_bytes = None
        best_txt = None

        for url in candidate_urls:
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": f"PnL-Enforcer-Updater/{APP_VERSION}",
                        "Cache-Control": "no-cache",
                    },
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    rem_bytes = resp.read()
                rem_txt = rem_bytes.decode("utf-8", errors="replace")
                if "def data_loop" not in rem_txt:
                    continue
                m_rem = re.search(
                    r'(?m)^APP_VERSION\s*=\s*["\']([^"\']+)["\']', rem_txt
                )
                v_cand = m_rem.group(1).strip() if m_rem else "0.9.4"
                if (
                    best_ver is None
                    or _parse_version_tuple(v_cand) > _parse_version_tuple(best_ver)
                ):
                    best_ver = v_cand
                    best_bytes = rem_bytes
                    best_txt = rem_txt
            except Exception:
                continue

        if not os.path.exists(ICON_PATH):
            ico_bytes = _fetch_remote_doc_bytes("enforcer.ico", ts=ts)
            if ico_bytes:
                try:
                    with open(ICON_PATH, "wb") as icf:
                        icf.write(ico_bytes)
                except Exception:
                    pass

        if best_ver is None:
            print(f"Version check: v{APP_VERSION} (Offline / skipped)")
            return

        if _parse_version_tuple(best_ver) <= _parse_version_tuple(APP_VERSION):
            print(f"Version check: v{APP_VERSION} (Up to date)")
            return

        print(f"New update available: v{APP_VERSION} -> v{best_ver}")
        cl_bytes = _fetch_remote_doc_bytes("CHANGELOG.md", ts=ts)
        cl_text = (
            cl_bytes.decode("utf-8", errors="replace") if cl_bytes else ""
        )

        if show_update_available_dialog(APP_VERSION, best_ver, cl_text):
            script_dir = SCRIPT_DIR
            target_py = os.path.join(script_dir, "enforcer.py")
            tmp_py = target_py + ".tmp"
            with open(tmp_py, "wb") as f:
                f.write(best_bytes)
            os.replace(tmp_py, target_py)

            if cl_bytes:
                try:
                    with open(os.path.join(script_dir, "CHANGELOG.md"), "wb") as cf:
                        cf.write(cl_bytes)
                except Exception:
                    pass

            for doc_name in (
                "Launch_Enforcer.bat",
                "README.md",
                "LICENSE.txt",
                "enforcer.ico",
            ):
                doc_bytes = _fetch_remote_doc_bytes(doc_name, ts=ts)
                if doc_bytes:
                    try:
                        with open(os.path.join(script_dir, doc_name), "wb") as df:
                            df.write(doc_bytes)
                    except Exception:
                        pass
            print(f"[SUCCESS] Updated to PnL Enforcer v{best_ver}.\n")
            if restart_on_update:
                _release_single_instance_mutex()
                sys.exit(subprocess.call([sys.executable, target_py]))
        else:
            print(f"[SKIPPED] Continuing with local v{APP_VERSION}...\n")
    except Exception:
        print(f"Version check: v{APP_VERSION} (Offline / skipped)")


if __name__ == "__main__":
    if "--preview-update-dialog" in sys.argv:
        cl_local = ""
        cl_path = os.path.join(SCRIPT_DIR, "CHANGELOG.md")
        if os.path.exists(cl_path):
            with open(cl_path, "r", encoding="utf-8", errors="replace") as f:
                cl_local = f.read()
        show_update_available_dialog("0.9.10", APP_VERSION, cl_local)
        sys.exit(0)
    if "--check-update" in sys.argv:
        check_for_updates_cli(restart_on_update=False, skip_if_recent=False)
        sys.exit(0)
    _ensure_single_instance_or_exit()
    check_for_updates_cli(restart_on_update=True, skip_if_recent=True)
    init_daily_log()
    print("\n=========================================")
    print(f"  INITIALIZING PnL ENFORCER BETA v{APP_VERSION}  ")
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
            log_event(
                "SESSION",
                f"Launching {len(get_active_hud_columns(config))}-Column HUD."
            )
            start_gui()
        else:
            log_event("SESSION", "Pre-Flight closed without launching. Exiting.")
            sys.exit(0)
    except Exception as e:
        log_event("ERROR", f"Startup failed: {e}")