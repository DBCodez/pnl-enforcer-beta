"""
PnL Enforcer (Closed Beta) — Dual-Broker Edition (Charles Schwab & Webull)
MIT License & Trading Risk Disclaimer — Provided "AS IS" without warranty of any kind.
Not financial advice; no guarantee of loss prevention; not affiliated with Schwab or Webull.
See LICENSE.txt for full terms, limitation of liability, and indemnification.
"""

APP_VERSION = "0.9.29"

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
        win.update_idletasks()
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
        for k in (
            "selectcolor",
            "disabledforeground",
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
            width=124,
            height=26,
            bg=card_bg,
            bd=0,
            highlightthickness=0
        )
        self._card_bg = card_bg
        self._active = True
        self._bg_photo = None
        self.bind("<Configure>", self._redraw)

    def set_active(self, is_active):
        self._active = bool(is_active)
        self._redraw()

    def _redraw(self, event=None):
        self.delete("all")
        w = max(124, self.winfo_width())
        h = max(26, self.winfo_height())
        if self._active:
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

    def add_command(self, label="", command=None, **_ignored):
        self._items.append({"type": "command", "label": str(label), "command": command})

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
                row = tk.Label(
                    inner,
                    text=lbl_txt,
                    font=self._font,
                    bg=self._bg,
                    fg=self._fg,
                    anchor="w",
                    padx=10,
                    pady=5,
                    cursor="hand2",
                )
                row.pack(fill="x")
                row.bind(
                    "<Enter>",
                    lambda _e, r=row: r.config(bg=self._active_bg, fg=self._active_fg),
                )
                row.bind(
                    "<Leave>",
                    lambda _e, r=row: r.config(bg=self._bg, fg=self._fg),
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
            tw.wm_geometry(f"{req_w}x{req_h}+{pos_x}+{pos_y}")
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

logging.basicConfig(level=logging.INFO)
logging.getLogger("webull").setLevel(logging.CRITICAL)
logging.getLogger("webull.core").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ==========================================
# 2. DEFAULT CONFIGURATION
# ==========================================
WAIVER_VERSION = "2026.10.29"
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
has_reset_at_open = False
has_reset_at_close = False
is_locked_down = False
force_reanchor = False
current_is_flat = True
first_poll_of_launch = True

alarm_active = False
cooldown_active = False
cooldown_end_time = 0.0
cooldown_label = "COOL-DOWN LOCK"
cooldown_30s_announced = False
cooldown_announced_mins = set()
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
            r"((?:Start|LastFlat|TotalAccountValue|NetLiq|Cash|MarketVal)=)\$[0-9,]+(?:\.[0-9]{2})?",
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


def init_daily_log():
    today_str = get_today_str()
    header_line = (
        f"=== ENFORCER SESSION LOG | v{APP_VERSION} | DATE: {today_str} ===\n"
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
                f"Initialized fresh daily log file (v{APP_VERSION})."
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
                f"--- APPLICATION LAUNCHED / RESUMED (v{APP_VERSION}) ---"
            )
    except Exception as e:
        print(f"Could not initialize log file: {e}")


def log_event(category, message):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    clean_msg = _scrub_log_line(message)
    line = f"[{ts}] [{category:<10}] {clean_msg}"
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
    if cat_name == "AuthlibDeprecationWarning" or "httpx2" in msg_clean:
        return
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


_install_global_error_hooks()


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
        f"Broker={broker} | Cols={len(get_active_hud_columns(cfg))} | "
        f"Poll={cfg.get('poll_interval')}s | "
        f"AlarmsOnly={'ON' if cfg.get('alarms_only_mode') else 'OFF'} | "
        f"OpenStop={'ON' if cfg.get('enable_open_flatten') else 'OFF'}"
        f"(-${cfg.get('open_max_loss', 0):,.0f}, CoolDown={cd_str}) | "
        f"DayFlat={'ON' if cfg.get('enable_auto_flatten') else 'OFF'} | "
        f"OptFlat={'ON(BETA)' if is_options_flatten_armed(cfg) else 'OFF'} | "
        f"KillTOS={'ON' if cfg.get('enable_kill_tos') else 'OFF'} | "
        f"KillWB={'ON' if cfg.get('enable_kill_webull') else 'OFF'} | "
        f"LockOS={dl_str} | "
        f"Voice={'ON' if cfg.get('enable_voice_cues', True) else 'OFF'} | "
        f"UpChime={'ON' if cfg.get('enable_upside_chime', True) else 'OFF'} | "
        f"EH_Max=-${cfg.get('pm_max_loss', 0):,.0f} | "
        f"T1_Max=-${cfg.get('t1_max_loss', 0):,.0f}"
    )


def restore_account_session(broker_name, account_id, log_restore=False):
    """Restores today's saved baseline for a specific broker + account_id.
    Returns True if a valid baseline for today was found, False otherwise."""
    global start_equity, max_equity, daily_max_equity
    global last_flat_equity, has_reset_at_open, has_reset_at_close
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
            has_reset_at_close = bool(
                s_data.get("has_reset_at_close", False)
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
        has_reset_at_close = bool(config.get("saved_has_reset_at_close", False))
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
    has_reset_at_close = False
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
        "has_reset_at_close": has_reset_at_close,
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
    parent = getattr(tk, "_default_root", None)
    is_standalone = parent is None

    dlg = tk.Tk() if is_standalone else tk.Toplevel(parent)
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
        self._last_open_eq = {}
        self._last_open_opt = {}
        self._rate_limit_until = 0.0
        self._last_429_log_ts = 0.0
        self.last_error = ""

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
            for order in orders_resp.json():
                status = order.get("status")
                if status in active_statuses:
                    order_id = order.get("orderId")
                    masked_oid = _mask_last4(order_id)
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
            if cancelled_any:
                time.sleep(0.2)
            else:
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
                        if a_type == "EQUITY":
                            open_eq.append((inst["symbol"], qty))
                        elif a_type == "OPTION":
                            open_opt.append((inst["symbol"], qty))
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
            return list(cached[1])
        return None

    def get_open_option_positions(self):
        """Returns ONLY Option positions (symbol, qty) sorted with short legs
        (qty < 0) first for BETA Options Auto-Flatten, or None on API error."""
        cached = self._last_open_opt.get(self.account_id)
        if cached and (time.time() - cached[0]) < 0.45:
            return list(cached[1])
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
                        if a_type == "EQUITY":
                            open_eq.append((inst["symbol"], qty))
                        elif a_type == "OPTION":
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
            return list(cached[1])
        return None

    def submit_option_liquidation_batch(self, open_opt_positions):
        """Submits single-leg RTH Market orders to close open option positions
        (BUY_TO_CLOSE on short legs first, then SELL_TO_CLOSE on long legs)."""
        if not open_opt_positions:
            return
        if not is_market_hours():
            log_event(
                "GUARDRAIL",
                f"Cannot submit Schwab option market flatten outside RTH "
                f"(9:30 AM – 4:00 PM ET): {open_opt_positions}"
            )
            return
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
            except Exception as e:
                log_event(
                    "ERROR",
                    f"Schwab option place_order exception ({symbol}): {e}"
                )

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
                balances = data.get("currentBalances", {})
                raw_eq = float(balances.get("liquidationValue", 0))

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
                self._last_open_eq[self.account_id] = (
                    now_snap_t, open_eq_cache
                )
                self._last_open_opt[self.account_id] = (
                    now_snap_t, open_opt_cache
                )

                if not open_assets:
                    flat_res = (raw_eq, True, 0.0, {}, False)
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
                        "qty": int(net_q),
                        "avg": round(avg_price, 4),
                        "last": round(lp, 4),
                        "open_pnl": round(pos_open_pnl, 2),
                        "confirmed_open_pnl": round(conf_open_pnl, 2),
                        "asset_type": a_type
                    }

                open_res = (
                    adj_eq,
                    False,
                    round(total_open_pnl, 2),
                    pos_details,
                    has_options
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
        self._last_open_eq = {}
        self._last_open_opt = {}
        self._rate_limit_until = 0.0
        self._last_429_log_ts = 0.0
        self.last_error = ""

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
                        masked_cid = _mask_last4(cid)
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
                if cancelled_any:
                    time.sleep(0.2)
                else:
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
        if cached and (time.time() - cached[0]) < 2.15 and cached[1]:
            return list(cached[1])
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
                        if meta["qty"] != 0:
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
                        if sym:
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
            return list(cached[1])
        return None

    def get_open_option_positions(self):
        """Returns (display_sym, qty, meta) for OPTIONS ONLY sorted with short
        legs (qty < 0) first, or None on API error."""
        cached = self._last_open_opt.get(self.account_id)
        if cached and (time.time() - cached[0]) < 2.15:
            return list(cached[1])
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
                        if meta["qty"] != 0:
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
                        if sym:
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
            return list(cached[1])
        return None

    def submit_option_liquidation_batch(self, open_opt_positions):
        """Submits single-leg RTH Market option orders on Webull
        (BUY_TO_CLOSE on short legs first, then SELL_TO_CLOSE on long legs)."""
        if not open_opt_positions:
            return
        if not is_market_hours():
            log_event(
                "GUARDRAIL",
                f"Cannot submit Webull option market flatten outside RTH "
                f"(9:30 AM – 4:00 PM ET): {[x[0] for x in open_opt_positions]}"
            )
            return

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
            except Exception as e:
                log_event(
                    "ERROR",
                    f"Webull option place_order exception ({display_sym}): {e}"
                )

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

            probe_qty_map = {}
            for p_item in pos_list:
                q_val = int(float(p_item.get("quantity") or p_item.get("position") or 0))
                if q_val != 0:
                    s_val = (
                        p_item.get("symbol")
                        or p_item.get("ticker", {}).get("symbol")
                        or "UNKNOWN"
                    )
                    probe_qty_map[s_val] = q_val

            prev_q_map = self._prev_pos_qty_map.get(self.account_id)
            if prev_q_map is not None and probe_qty_map != prev_q_map:
                # Share quantity just changed (entry, scale-out, or exit).
                # Wait briefly before fetching balance so Webull's cash_balance
                # settles into sync with the updated position quantities without
                # firing a duplicate /positions/list call in the same cycle.
                time.sleep(0.25)

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

            raw_eq, cash_bal = self._extract_webull_equity_and_cash(b_data)
            if self.account_id not in self._logged_accounts:
                self._logged_accounts.add(self.account_id)
                log_event(
                    "SESSION",
                    f"Webull Balance Parsed -> TotalAccountValue=${raw_eq:,.2f} "
                    f"(Cash=${cash_bal if cash_bal is not None else 0.0:,.2f})"
                )

            total_open_pnl = 0.0
            total_pos_mkt_val = 0.0
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
                total_pos_mkt_val += pos_mkt_val

                total_open_pnl += pos_open_pnl
                tag = f"{sym} (OPT)" if is_opt else sym
                pos_details[tag] = {
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
            self._last_open_eq[self.account_id] = (now_snap_t, open_eq_cache)
            self._last_open_opt[self.account_id] = (now_snap_t, open_opt_cache)
            is_flat = (len(pos_details) == 0)
            self._prev_pos_qty_map[self.account_id] = {
                s_k.replace(" (OPT)", ""): d_v["qty"]
                for s_k, d_v in pos_details.items()
            }

            if cash_bal is not None and cash_bal > 0:
                adj_eq = round(cash_bal + total_pos_mkt_val, 2)
            else:
                adj_eq = round(raw_eq, 2)

            self.last_error = ""
            res_tuple = (
                adj_eq,
                is_flat,
                round(total_open_pnl, 2),
                pos_details,
                has_options
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
    w.title(f"PnL Enforcer Beta — Legal Disclaimer & Assumption of Risk (v{WAIVER_VERSION})")
    w.config(bg="#0d1117", padx=28, pady=22)
    w.resizable(False, False)
    w.attributes("-topmost", True)

    tk.Label(
        w,
        text=f"⚠️ EXPERIMENTAL BETA SOFTWARE — ASSUMPTION OF RISK (v{WAIVER_VERSION})",
        font=("Arial", 12, "bold"),
        fg="#f5b041",
        bg="#0d1117",
        anchor="w"
    ).pack(fill="x", pady=(0, 12))

    msg_outer = tk.Frame(
        w, bg="#131922", bd=0, highlightthickness=1, highlightbackground="#243040"
    )
    msg_outer.pack(fill="x", pady=(0, 14))
    NeonBarCanvas(
        msg_outer, core_color="#fbbf24", card_bg="#131922", glow_on=True
    ).pack(side="left", fill="y")
    msg_box = tk.Label(
        msg_outer,
        text=waiver_text,
        font=("Arial", 9),
        fg="#dce4ee",
        bg="#131922",
        justify="left",
        anchor="w",
        padx=16,
        pady=14,
    )
    msg_box.pack(side="left", fill="both", expand=True)

    var_agree = tk.BooleanVar(value=False)
    make_glass_checkbutton(
        w,
        text=(
            "I have read this disclaimer and LICENSE.txt, understand that losses cannot be guaranteed, "
            "and assume 100% sole responsibility for my account."
        ),
        variable=var_agree,
        font=("Arial", 9, "bold"),
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
        font=("Arial", 12, "bold"),
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
    msg_outer.pack(fill="x", pady=(0, 14))
    NeonBarCanvas(
        msg_outer, core_color="#f43f5e", card_bg="#131922", glow_on=True
    ).pack(side="left", fill="y")
    msg_box = tk.Label(
        msg_outer,
        text=OPTIONS_WAIVER_TEXT,
        font=("Arial", 9),
        fg="#dce4ee",
        bg="#131922",
        justify="left",
        anchor="w",
        padx=16,
        pady=14,
    )
    msg_box.pack(side="left", fill="both", expand=True)

    var_opt_agree = tk.BooleanVar(value=False)
    make_glass_checkbutton(
        dlg,
        text=(
            "I understand that Options Auto-Flatten is an experimental BETA feature, that Market orders on "
            "option spreads can suffer severe slippage, and I assume 100% sole responsibility for all fills."
        ),
        variable=var_opt_agree,
        font=("Arial", 9, "bold"),
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


def get_full_idle_button_text():
    b_name = config.get("active_broker", "SCHWAB")
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
    if config.get("alarms_only_mode", False):
        return f"{b_name} : ALARMS ONLY MODE (SIREN ONLY)"
    opt_armed = is_options_flatten_armed(config)
    pills = [b_name]
    if config.get("enable_open_flatten", False):
        oml = config.get("open_max_loss", 500.0)
        if config.get("enable_open_cooldown", False):
            cd_m = config.get("open_cooldown_mins", 1.0)
            pills.append(f"OPEN (-${oml:,.0f}/{cd_m:g}m)")
        else:
            pills.append(f"OPEN (-${oml:,.0f})")
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
            f"LOCK ({dl_m:g}m)" if dl_m > 0 else "LOCK (1x)"
        )
    if daily_parts:
        pills.append(" + ".join(daily_parts))

    if len(pills) == 1:
        return f"{b_name} : ALARM ONLY (OBSERVATION)"
    return "ARMED: " + " + ".join(pills)


def get_idle_button_text():
    n_cols = len(get_active_hud_columns(config))
    full_txt = get_full_idle_button_text()
    if n_cols <= 3:
        if "ALARM" in full_txt and not full_txt.startswith("ARMED:"):
            return "● ALARMS ONLY"
        return "● ARMED"
    if n_cols == 4:
        return get_medium_idle_button_text()
    return full_txt


def format_alarm_button_text(reason):
    if is_compact_hud():
        return "MUTE ALARM"
    return f"ACKNOWLEDGE ALARM ({reason})"


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
    global alarm_active, last_alarm_reason
    alarm_active = False
    last_alarm_reason = ""
    hide_fn = getattr(ui_button, "_hide_tooltip_fn", None)
    if callable(hide_fn):
        hide_fn()
    log_event("ALARM", "User acknowledged and muted siren.")
    if not cooldown_active:
        ui_button.config(
            text=get_idle_button_text(),
            bg="#222629",
            fg="#f5b041",
            disabledforeground="#f5b041",
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


def speak_async(text, force=False, voice_override=None):
    """Speaks text asynchronously using Windows OneCore / SAPI speech synthesis
    (supports Zira, Mark, and David voices)."""
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
        ps_cmd = (
            "try { "
            "$sp = New-Object -ComObject SAPI.SpVoice; "
            "$cat = New-Object -ComObject SAPI.SpObjectTokenCategory; "
            "$cat.SetId('HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech_OneCore\\Voices', $false); "
            f"foreach ($t in $cat.EnumerateTokens()) {{ if ($t.GetDescription() -match '{safe_voice}') {{ $sp.Voice = $t; break }} }}; "
            "$sp.Rate = 1; "
            f"[void]$sp.Speak('{safe_text}') "
            "} catch { "
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"try {{ $s.SelectVoice('Microsoft {safe_voice} Desktop') }} catch {{}}; "
            f"$s.Speak('{safe_text}') "
            "}"
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


def _format_lock_voice_msg(duration_mins, label_prefix, upgraded=False):
    mins_val = float(duration_mins)
    dur_words = "1 minute" if mins_val == 1.0 else f"{mins_val:g} minutes"
    is_daily = "DAILY" in str(label_prefix).upper()
    if upgraded:
        reason_words = "Upgraded to daily floor breach" if is_daily else "Lockout extended"
    else:
        reason_words = "Daily floor breached" if is_daily else "Open P and L stop triggered"
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
        speak_async("Warning, straggler shares detected, flattening now.")
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
            speak_async(_format_lock_voice_msg(duration_mins, label_prefix, upgraded=True))
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
        speak_async(_format_lock_voice_msg(duration_mins, cooldown_label, upgraded=False))
        watchdog_launched = False
        while cooldown_active and time.time() < cooldown_end_time:
            alarm_active = False
            rem = int(round(cooldown_end_time - time.time()))
            if rem > 35:
                m_mark = (rem + 4) // 60
                if (
                    m_mark >= 1
                    and m_mark not in cooldown_announced_mins
                    and (m_mark * 60) - 5 <= rem <= (m_mark * 60)
                ):
                    cooldown_announced_mins.add(m_mark)
                    m_word = "minute" if m_mark == 1 else "minutes"
                    speak_async(f"{m_mark} {m_word} remaining until unlock.")
            if not cooldown_30s_announced and 0 < rem <= 30:
                cooldown_30s_announced = True
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
            ctypes.windll.user32.LockWorkStation()
            if not watchdog_launched:
                watchdog_launched = True
                _run_post_lock_watchdog(adapter, ui_button, cooldown_label)
            time.sleep(1.5)

        if not cooldown_active:
            log_event(
                "COOLDOWN",
                f"{cooldown_label} aborted early by post-lock watchdog."
            )
            return

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
        play_unlock_chimes()

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

        if should_exec:
            log_event(
                "FLATTEN",
                "Starting emergency flatten sequence (Equities + Options BETA)..."
                if include_options
                else "Starting emergency equity flatten sequence..."
            )
            adapter.cancel_all_working_orders()

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
                log_event("FLATTEN", f"Equity positions to liquidate: {open_pos}")
                adapter.submit_liquidation_batch(open_pos)
            if include_options and open_opt:
                log_event(
                    "FLATTEN",
                    f"Option positions to liquidate (BETA): {_fmt_opt_summary(open_opt)}"
                )
                adapter.submit_option_liquidation_batch(open_opt)
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
                    adapter.cancel_all_working_orders()
                    if rem_confirm:
                        adapter.submit_liquidation_batch(rem_confirm)
                    if include_options and opt_confirm:
                        adapter.submit_option_liquidation_batch(opt_confirm)
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
                    "Positions still open after 4s — canceling & sweeping..."
                    if include_options
                    else "Equities still open after 4s — canceling & sweeping..."
                )
                adapter.cancel_all_working_orders()
                rem_pos = adapter.get_open_equity_positions()
                rem_opt = (
                    adapter.get_open_option_positions()
                    if include_options and hasattr(adapter, "get_open_option_positions")
                    else []
                )
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
                            f"SUCCESS: Double-confirmed 0 positions after cancel "
                            f"({time.time() - start_wait:.1f}s)."
                            if include_options
                            else f"SUCCESS: Double-confirmed 0 equity shares after cancel "
                            f"({time.time() - start_wait:.1f}s)."
                        )
                        return True
                    rem_pos = rem_confirm
                    rem_opt = opt_confirm
                if rem_pos:
                    adapter.submit_liquidation_batch(rem_pos)
                if include_options and rem_opt:
                    adapter.submit_option_liquidation_batch(rem_opt)

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


def trigger_open_pnl_flatten(
    adapter, reason, ui_button, has_options=False, context_str=""
):
    global alarm_active
    cd_on = config.get("enable_open_cooldown", False)
    opt_armed = is_options_flatten_armed(config)

    if has_options and not opt_armed:
        opt_reason = f"{reason} — MANUAL OPTIONS EXIT REQUIRED!"
        trigger_alarm(opt_reason, ui_button, context_str)
        log_event(
            "GUARDRAIL",
            f"Open PnL Stop breached with OPTIONS open ({context_str}). "
            f"Options Auto-Flatten (BETA) is OFF; flattening any equities and "
            f"waiting for manual options exit."
        )
        flatten_equities(adapter, force_flatten=True, include_options=False)
        return

    if has_options and opt_armed and not is_market_hours():
        opt_reason = f"{reason} — OPTIONS MARKET CLOSED (EXIT MANUALLY!)"
        trigger_alarm(opt_reason, ui_button, context_str)
        log_event(
            "GUARDRAIL",
            f"Open PnL Stop breached with OPTIONS open outside RTH ({context_str}). "
            f"Options cannot be market-flattened outside 9:30–16:00 ET; "
            f"flattening any equities and sounding siren."
        )
        flatten_equities(adapter, force_flatten=True, include_options=False)
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
            "Open PnL flatten timed out — Cool-Down Lock ABORTED! "
            "Check platform manually!"
        )
        fail_reason = (
            f"{reason} — CHECK OPTIONS MANUALLY!"
            if has_options
            else reason
        )
        trigger_alarm(fail_reason, ui_button, context_str)


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
        trigger_alarm(
            f"{reason} (CLOSE OPTIONS MANUALLY!)", ui_button, context_str
        )
        log_event(
            "CRITICAL",
            "OPTIONS ARE STILL OPEN! Holding off on App Kill / OS Lock "
            "until options are manually flattened!"
        )
        return

    if not all_flat:
        log_event(
            "CRITICAL",
            "OS ACTIONS ABORTED: Positions (Equities/Options) still open! Manual action needed!"
            if has_options
            else "OS ACTIONS ABORTED: Equity shares still open! Manual action needed!"
        )
        trigger_alarm(
            f"{reason} (POSITIONS STILL OPEN!)" if has_options else reason,
            ui_button,
            context_str
        )
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
    global has_reset_at_open, has_reset_at_close, is_locked_down, force_reanchor
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
                                    bg="#222629",
                                    fg="#f5b041",
                                    disabledforeground="#f5b041",
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
                    has_reset_at_open = is_rth() or is_after_hours()
                    has_reset_at_close = is_after_hours()
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
                if is_rth() and not has_reset_at_open:
                    has_reset_at_open = True
                    first_poll_of_launch = True
                    if reset_925:
                        old_hwm = max_equity - start_equity
                        max_equity = max(start_equity, last_flat_equity)
                        new_hwm = max_equity - start_equity
                        is_locked_down = False
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
                    if reset_925:
                        old_hwm = max_equity - start_equity
                        max_equity = max(start_equity, last_flat_equity)
                        new_hwm = max_equity - start_equity
                        is_locked_down = False
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
                        floor_breach_cand and conf_eq <= active_floor_now
                    )
                    book_confirms_open = (
                        open_breach_cand and conf_open_pnl <= -open_max
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
                        (book_confirms_floor or book_confirms_open)
                        and not qty_just_changed
                        and not has_options
                    ):
                        log_event(
                            "GUARDRAIL",
                            f"Breach confirmed immediately by NBBO book & "
                            f"account snapshot (0s delay | {spike_ctx})."
                        )
                    else:
                        time.sleep(0.35 if qty_just_changed else 0.2)
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
                                    f"(Spike: {spike_ctx} -> Re-verified 0.2s later: "
                                    f"{v_ctx}). No flatten triggered."
                                )
                            else:
                                log_event(
                                    "GUARDRAIL",
                                    f"Breach confirmed after 0.2s anti-wick check "
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
                # at the 9:30 AM / 4:00 PM transitions, or right after saving Settings
                if first_poll_of_launch or last_rth_mode != rth_now:
                    if last_rth_mode is not None and last_rth_mode != rth_now:
                        first_poll_of_launch = True
                    last_rth_mode = rth_now
                    current_upside_tier = compute_upside_tier(
                        rth_now, max_realized_profit, config
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
                        floor_equity = start_equity + t3_max
                        r_t3 = "Hit $0 (Tier 3)"
                        if t3_max < 0:
                            check_alarm_rearm(r_t3, current_eq, start_equity)
                        if not is_locked_down and current_eq <= floor_equity:
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
                        elif t3_max < 0 and current_eq <= start_equity:
                            trigger_alarm(r_t3, mute_btn, ctx)

                    elif t2_on and max_realized_profit >= t2_trig:
                        floor_equity = start_equity + t2_max
                        r_t2 = "Hit $0 (Tier 2)"
                        if t2_max < 0:
                            check_alarm_rearm(r_t2, current_eq, start_equity)
                        if not is_locked_down and current_eq <= floor_equity:
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
                        elif t2_max < 0 and current_eq <= start_equity:
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
                leash_pct = max(
                    0.0, min(1.0, distance_to_terminate / full_leash)
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
                    lambda d=col_data, f=is_flat, lp=leash_pct: update_gui(
                        ui_labels, d, f, settings_btn, close_btn, leash_pct=lp
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
    pf_timer_state = {"rulebook_after_id": None, "closing": False}

    if parent is None:
        pf = tk.Tk()
    else:
        settings_win_open = True
        pf = tk.Toplevel(parent)
        pf.grab_set()

    pf.title(f"PnL Enforcer Beta v{APP_VERSION} — Pre-Flight & Risk Rulebook")
    pf.config(bg="#0d1117", padx=24, pady=16)
    pf.resizable(False, False)
    pf.attributes("-topmost", True)

    def _cancel_pf_timers():
        pf_timer_state["closing"] = True
        aid = pf_timer_state.get("rulebook_after_id")
        if aid is not None:
            pf_timer_state["rulebook_after_id"] = None
            try:
                pf.after_cancel(aid)
            except Exception:
                pass

    def on_close():
        global settings_win_open, first_poll_of_launch
        _cancel_pf_timers()
        first_poll_of_launch = True
        settings_win_open = False
        pf.destroy()

    pf.protocol("WM_DELETE_WINDOW", on_close)

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
                tw = tk.Toplevel(pf)
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
                pf_right = pf.winfo_rootx() + max(pf.winfo_width(), 900)
                pf_bottom = pf.winfo_rooty() + max(pf.winfo_height(), 600)
                x = widget.winfo_rootx() + 16
                y = widget.winfo_rooty() + widget.winfo_height() + 6
                if x + tip_w > pf_right + 20:
                    x = max(pf.winfo_rootx() + 8, pf_right - tip_w - 8)
                if y + tip_h > pf_bottom + 40:
                    y = widget.winfo_rooty() - tip_h - 6
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
    var_reanchor = tk.BooleanVar(value=False)
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
        "pm_warn_1", "pm_warn_2", "pm_max_loss",
        "pm_lock_trigger", "pm_trail_cushion",
        "t1_warn_1", "t1_warn_2", "t1_max_loss",
        "t2_trigger", "t2_max_loss",
        "t3_trigger", "t3_max_loss",
        "t4_trigger", "t4_trail"
    ]
    loss_display_keys = {
        "open_max_loss",
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
            "remaining Schwab 7-day token lifetime, and today's completed Win/Loss trade count."
        )
        for seg_txt, seg_col in spans:
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
            )
            lbl.pack(side="left")
            attach_tooltip(lbl, base_tip)

    def refresh_baseline_preview():
        """Updates the Active Baseline multi-color telemetry strip in Card 3 to
        match the currently selected Broker + Account."""
        global start_equity, force_reanchor
        if base_sub_lbl is None:
            return
        if active_adapter is None or not active_adapter.account_id:
            _render_baseline_telemetry_spans(
                [
                    (
                        "No broker connected — click API Keys or select broker above.",
                        "#f5b041",
                    )
                ]
            )
            return

        b_name = active_adapter.name
        acct_id = active_adapter.account_id
        had_saved = restore_account_session(b_name, acct_id, log_restore=False)

        if had_saved and start_equity is not None and start_equity > 0:
            force_reanchor = False
            eq_str = f"${start_equity:,.2f} (Preserved)"
        else:
            eq, _, _, _, _ = active_adapter.fetch_account_data()
            if eq is not None and eq > 0:
                start_equity = eq
                force_reanchor = True
                eq_str = f"${start_equity:,.2f} (Live equity)"
            else:
                eq_str = "Will anchor on first API poll"

        spans = [
            (f"Active Baseline ({b_name}): ", "#94a3b8"),
            (eq_str, "#7dd3fc"),
        ]
        if b_name == "SCHWAB":
            rem_h = get_schwab_token_remaining_hours()
            if rem_h is not None and rem_h > 0:
                rem_d = rem_h / 24.0
                tok_col = "#fbbf24" if rem_d < 1.5 else "#4ade80"
                spans.append(("  |  ", "#475569"))
                spans.append((f"Token: {rem_d:.1f}d left", tok_col))

        tot_t = int(win_trades) + int(loss_trades)
        w_pct = (win_trades / tot_t * 100.0) if tot_t > 0 else 0.0
        l_pct = (loss_trades / tot_t * 100.0) if tot_t > 0 else 0.0
        spans.append(("  |  ", "#475569"))
        spans.append((f"W: {win_trades} ({w_pct:.1f}%)", "#58d68d"))
        spans.append(("  |  ", "#475569"))
        spans.append((f"L: {loss_trades} ({l_pct:.1f}%)", "#e07a7a"))
        _render_baseline_telemetry_spans(spans)

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
    for b_opt in ("SCHWAB", "WEBULL"):
        broker_dropdown.add_command(
            label=b_opt, command=lambda b=b_opt: var_broker.set(b)
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
        "Click BROKER (left) to switch between Charles Schwab / Thinkorswim and Webull.\n"
        "Click ACCOUNT (right) to choose which sub-account to monitor.\n"
        "Each broker and account tracks its own separate daily baseline and session history."
    )

    def _sync_broker_acct_pills(*_):
        _capsule_state["connected"] = bool(
            active_adapter and active_adapter.accounts
        )
        _redraw_broker_acct_capsule()

    var_account_label.trace_add("write", _sync_broker_acct_pills)

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
        global active_adapter
        chosen = var_broker.get()
        _sync_broker_acct_pills()
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
                    _sync_broker_acct_pills()

    def edit_api_keys():
        global active_adapter
        chosen = var_broker.get()
        new_ad = connect_broker_adapter(chosen, parent=pf, force_wizard=True)
        if new_ad is not None:
            active_adapter = new_ad
            config["active_broker"] = chosen
            populate_account_dropdown()
            refresh_baseline_preview()

    btn_api_keys = make_stadium_button(
        top_bar,
        text="🔑 API Keys",
        font=("Arial", 9, "bold"),
        fill_color="#141820",
        fill_top_color="#1c212b",
        border_color="#2e3746",
        hover_fill="#181e28",
        hover_fill_top="#232a36",
        hover_border="#475569",
        fg="#e2e8f0",
        canvas_bg="#11161f",
        width=98,
        height=32,
        pad_x=22,
        command=edit_api_keys,
    )
    btn_api_keys.pack(side="left", padx=(0, 5))
    attach_tooltip(
        btn_api_keys,
        "Open the API Credential Setup Wizard to enter or update your App Key & Secret,\n"
        "or to re-authenticate your 7-day Schwab security token."
    )

    def open_hud_columns_dialog():
        dlg = tk.Toplevel(pf)
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

    logs_dropdown = DarkDropdownMenu(
        pf,
        tearoff=0,
        font=("Arial", 9, "bold"),
        bg="#141820",
        fg="#e2e8f0",
        activebackground="#1e293b",
        activeforeground="#ffffff"
    )
    logs_dropdown.add_command(
        label="📄 View Today's Log",
        command=open_log_file
    )
    logs_dropdown.add_command(
        label="🔒 Export Today's Safe Log (Balances Redacted)",
        command=export_sanitized_log_action
    )
    logs_dropdown.add_separator()
    logs_dropdown.add_command(
        label=f"🔒 Open Safe Archived Logs ({LOG_RETENTION_DAYS}-Day Redacted)",
        command=open_sanitized_archive_folder
    )
    logs_dropdown.add_command(
        label=f"📁 Open Raw Archived Logs ({LOG_RETENTION_DAYS}-Day Full)",
        command=open_log_archive_folder
    )
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
            is_full = all(abs(curr_d[k] - full_d[k]) < 0.5 for k in dollar_keys)
            is_half = (
                not is_full
                and all(abs(curr_d[k] - half_d[k]) < 0.5 for k in dollar_keys)
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
        for k, val in preset_dict.items():
            if k in dollar_vars:
                dollar_vars[k].set(_fmt_ui_dollar(k, val))
        refresh_preset_buttons_highlight()

    def apply_half_risk_preset():
        _, half_dict = _get_preset_target_dicts()
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
            msg = (
                "↺ Restored your saved defaults."
                if config.get("user_defaults")
                else "↺ Restored factory defaults."
            )
            default_status_lbl.config(text=msg, fg="#5dade2")

    def save_as_user_defaults():
        try:
            custom_def = {
                "alarms_only_mode": bool(var_alarms_only.get()),
                "enable_open_flatten": bool(var_open_flat.get()),
                "enable_open_cooldown": bool(var_open_cd.get()),
                "open_cooldown_mins": max(0.1, abs(float(var_cd_mins.get()))),
                "enable_auto_flatten": bool(var_flatten.get()),
                "enable_flatten_options": bool(var_flatten_options.get()),
                "enable_kill_tos": bool(var_kill_tos.get()),
                "enable_kill_webull": bool(var_kill_wb.get()),
                "enable_lock_os": bool(var_lock_os.get()),
                "daily_lock_mins": max(0.0, abs(float(var_daily_lock_mins.get()))),
                "reset_at_925": bool(var_reset925.get()),
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

            new_cfg["alarms_only_mode"] = bool(var_alarms_only.get())
            new_cfg["enable_open_flatten"] = bool(var_open_flat.get())
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
            new_cfg["signed_tier_stops"] = True

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
        for k in ("pm_lock_trigger", "pm_trail_cushion", "t4_trigger", "t4_trail")
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
    # LEFT COLUMN: 1. SINGLE-TRADE STOP, 2. DAILY ACTIONS, 3. SYSTEM
    # ==========================================================
    c1 = make_card(
        left_col,
        "▶  1. SINGLE-TRADE STOP (Open PnL)",
        "Flattens open positions on a single trade without ending your day "
        "(Options = Siren Only unless BETA toggle enabled in Card 2).",
        accent="#5dade2",
        bar_color="#38bdf8"
    )

    r_open1 = tk.Frame(c1, bg="#131922")
    r_open1.pack(fill="x", pady=4)
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

    r_open2 = tk.Frame(c1, bg="#131922")
    r_open2.pack(fill="x", pady=4)
    cb_open_cd = make_glass_checkbutton(
        r_open2,
        text="└─ Penalty Box OS Lock After Open Stop",
        variable=var_open_cd,
        font=("Arial", 10, "bold"),
        fg="#c8d4e0",
        bg="#131922",
        anchor="w"
    )
    cb_open_cd.pack(side="left", padx=(18, 0))
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

    # --- CARD 2: DAILY STOP ACTIONS (MAX LOSS & PROFIT LOCK) ---
    c2 = make_card(
        left_col,
        "▶  2. DAILY STOP ACTIONS (Max Loss & Profit Lock)",
        "Fires when Net PnL hits your active Max Loss or Profit Lock in Rulebook 4 or 5.",
        accent="#f5b041",
        bar_color="#fbbf24"
    )

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

    cb_alarms_only = make_glass_checkbutton(
        r_day_top,
        text="Alarms Only Mode",
        variable=var_alarms_only,
        font=("Arial", 10, "bold"),
        fg="#f5b041",
        bg="#131922",
        accent_hex="#d97706",
        check_hex="#fbbf24",
        anchor="e"
    )
    cb_alarms_only.pack(side="right")
    attach_tooltip(
        cb_alarms_only,
        "Alarms Only Mode (Passive Observation / Siren Mode):\n"
        "When checked, all automated broker order execution, platform kill-switches, and Windows OS\n"
        "lockouts across Cards 1 & 2 are completely disabled and greyed out.\n"
        "• Tracks your live Realized, Open, and Net PnL, Session High, and Profit Ratchet Tiers normally.\n"
        "• Sounds audible warning sirens and breach alarms at every configured threshold.\n"
        "• NEVER submits flatten orders, closes trading apps, or locks your Windows screen.\n"
        "• Unchecking this box immediately restores your saved Auto-Flatten and OS Lock checkmarks."
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

    # --- CARD 3: SESSION & SYSTEM SETTINGS (WITH MULTI-COLOR TELEMETRY STRIP) ---
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
    tk.Label(
        c3,
        text="▶  3. SESSION & SYSTEM SETTINGS",
        font=("Arial", 11, "bold"),
        fg="#4ec994",
        bg="#131922",
        anchor="w"
    ).pack(fill="x")

    base_sub_lbl = tk.Frame(c3, bg="#131922")
    base_sub_lbl.pack(fill="x", pady=(2, 6))
    tk.Frame(c3, bg="#222d3d", height=1).pack(fill="x", pady=(0, 6))
    refresh_baseline_preview()
    attach_tooltip(
        base_sub_lbl,
        "Shows today's anchored starting account equity ($0.00 PnL reference point),\n"
        "remaining Schwab 7-day token lifetime, and today's completed Win/Loss trade count."
    )

    cb_reset925 = make_glass_checkbutton(
        c3,
        text="Start Fresh on Rulebook Switch (9:30 AM & 4:00 PM)",
        variable=var_reset925,
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#131922",
        anchor="w"
    )
    cb_reset925.pack(fill="x", pady=2)
    attach_tooltip(
        cb_reset925,
        "If checked, at 9:30 AM ET (RTH Open) and 4:00 PM ET (After-Hours Open) your active Rulebook\n"
        "starts fresh from current flat equity so an earlier session's profit peak won't immediately\n"
        "trigger a tier ratchet or trailing stop. (Your SESSION HIGH column still preserves your full-day peak.)"
    )

    cb_reanchor = make_glass_checkbutton(
        c3,
        text="Re-Zero Today's Starting Baseline to Current Equity",
        variable=var_reanchor,
        font=("Arial", 10, "bold"),
        fg="#f5b041",
        bg="#131922",
        accent_hex="#d97706",
        check_hex="#fbbf24",
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

    r_audio = tk.Frame(c3, bg="#131922")
    r_audio.pack(fill="x", pady=2)
    cb_voice = make_glass_checkbutton(
        r_audio,
        text="Verbal Lockout Voice Cues",
        variable=var_voice_cues,
        font=("Arial", 10, "bold"),
        fg="#dce4ee",
        bg="#131922",
        anchor="w"
    )
    cb_voice.pack(side="left", padx=(0, 14))
    attach_tooltip(
        cb_voice,
        "Uses Windows Speech Synthesis to speak the lockout reason, duration, and 2s/15s\n"
        "post-lock flat check confirmations out loud when a Penalty Box or Daily Lockout triggers,\n"
        "plus an announcement every whole minute remaining and at 30 seconds remaining."
    )

    cb_chime = make_glass_checkbutton(
        r_audio,
        text="Upside Tier Chime & Glow",
        variable=var_upside_chime,
        font=("Arial", 10, "bold"),
        fg="#4ec994",
        bg="#131922",
        anchor="w"
    )
    cb_chime.pack(side="left")
    attach_tooltip(
        cb_chime,
        "When you close a winning trade (100% flat) that unlocks a higher profit ratchet tier\n"
        "(Extended-Hours Profit Lock or RTH Tier 2 / 3 / 4), plays a pleasant 4-note ascending chime\n"
        "and glows the HUD status bar emerald green for 3 seconds."
    )

    r_test_audio = tk.Frame(c3, bg="#131922")
    r_test_audio.pack(fill="x", pady=(4, 2))
    lbl_preview_audio = tk.Label(
        r_test_audio,
        text="Voice / Cue:",
        font=("Arial", 9, "bold"),
        fg="#97a7b9",
        bg="#131922",
        anchor="w"
    )
    lbl_preview_audio.pack(side="left", padx=(0, 5))

    voice_choices = [lbl for lbl, _ in TTS_VOICE_CATALOG]
    voice_dropdown = DarkDropdownMenu(
        pf,
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
        width=118,
        height=26,
        pad_x=20,
        menu=voice_dropdown,
    )
    voice_menu.pack(side="left", padx=(0, 5))
    var_tts_voice.trace_add(
        "write", lambda *_: voice_menu.config(text=var_tts_voice.get())
    )
    attach_tooltip(
        voice_menu,
        "Choose the Windows Speech voice used for Verbal Lockout Voice Cues:\n"
        "• Zira (Female) — Clear female voice (Default)\n"
        "• Mark (Male) — Natural Windows OneCore male voice\n"
        "• David (Male) — Deep classic male voice"
    )

    audio_choices = [
        "Warning Siren (Short Preview)",
        "Upside Tier Chime",
        "Voice: Lockout Alert",
        "Voice: 15s Sweep Clear",
        "Voice: 1m Warning",
        "Voice: 30s Warning",
        "Unlock Chime (3-Tone)",
    ]
    audio_dropdown = DarkDropdownMenu(
        pf,
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
        width=216,
        height=26,
        pad_x=22,
        menu=audio_dropdown,
    )
    audio_menu.pack(side="left", padx=(0, 6))
    var_audio_test.trace_add(
        "write", lambda *_: audio_menu.config(text=var_audio_test.get())
    )

    def play_selected_test_audio():
        choice = var_audio_test.get()
        sel_voice_id = TTS_LABEL_TO_ID.get(var_tts_voice.get(), "Zira")
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
                "Open P and L stop triggered. Locked out for 2 minutes. Initial flat check passed.",
                force=True,
                voice_override=sel_voice_id
            )
        elif choice == "Voice: 15s Sweep Clear":
            speak_async(
                "15 second sweep clear, account confirmed flat.",
                force=True,
                voice_override=sel_voice_id
            )
        elif choice == "Voice: 1m Warning":
            speak_async(
                "1 minute remaining until unlock.",
                force=True,
                voice_override=sel_voice_id
            )
        elif choice == "Voice: 30s Warning":
            speak_async(
                "30 seconds remaining until unlock.",
                force=True,
                voice_override=sel_voice_id
            )
        elif choice == "Unlock Chime (3-Tone)":
            threading.Thread(target=play_unlock_chimes, daemon=True).start()

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
        width=74,
        height=26,
        pad_x=16,
        command=play_selected_test_audio,
    )
    btn_test_audio.pack(side="left")
    audio_test_tip = (
        "Select a voice and any sound or voice announcement from the dropdown, then click '🔊 Test'\n"
        "to preview how it sounds at your current speaker/headset volume."
    )
    attach_tooltip(lbl_preview_audio, audio_test_tip)
    attach_tooltip(audio_menu, audio_test_tip)
    attach_tooltip(btn_test_audio, audio_test_tip)

    r_poll = tk.Frame(c3, bg="#131922")
    r_poll.pack(fill="x", pady=(4, 2))
    lbl_poll = tk.Label(
        r_poll,
        text="Broker API Poll Interval (Seconds):",
        font=("Arial", 10, "bold"),
        fg="#97a7b9",
        bg="#131922",
        anchor="w"
    )
    lbl_poll.pack(side="left", padx=(0, 10))
    ent_poll = make_entry(r_poll, var_poll, width=8)
    ent_poll.pack(side="left")
    poll_tip = (
        "How often (in seconds) Enforcer polls your broker API for live equity and positions.\n"
        "Recommended: 2 seconds (30 requests/min — well within Schwab & Webull rate limits)."
    )
    attach_tooltip(lbl_poll, poll_tip)
    attach_tooltip(ent_poll, poll_tip)

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
    make_dual_field_row(
        c4,
        "Starting Max Loss ($):",
        dollar_vars["pm_max_loss"],
        None,
        None,
        fg1="#dc6d72",
        tip1=(
            "Extended-Hours Starting Max Loss:\n"
            "Your initial worst-case Extended-Hours loss limit before Profit Lock is triggered.\n"
            "If Extended-Hours Net PnL reaches this loss, it immediately triggers your Card 2\n"
            "Daily Stop Actions (Auto-Flatten Equities via Extended-Hours limit order,\n"
            "Kill Apps, and Windows OS Lock for the duration set in Card 2)."
        )
    )
    tk.Frame(c4, bg="#222d3d", height=1).pack(fill="x", pady=7)
    cb_pm_lock, ent_pm_trig, lbl_pm_trail, ent_pm_trail = make_dual_field_row(
        c4,
        "Profit Lock Trigger ($):",
        dollar_vars["pm_lock_trigger"],
        "Trail Peak By ($):",
        dollar_vars["pm_trail_cushion"],
        cb_var1=var_pm_lock_on,
        fg1="#4ec994",
        fg2="#97a7b9",
        tip1=(
            "Extended-Hours Trailing Profit Lock:\n"
            "Once your closed Extended-Hours Realized PnL reaches +Profit Lock Trigger ($),\n"
            "this trailing stop replaces your Starting Max Loss as your active Daily Stop.\n"
            "• IMPORTANT: If Net PnL pulls back and touches this trailed stop, it triggers the\n"
            "  exact same Card 2 Daily Stop Actions (Auto-Flatten, Kill Apps, and OS Lock\n"
            "  for your Card 2 lock duration).\n"
            "Uncheck to disable Extended-Hours profit trailing."
        ),
        tip2=(
            "Extended-Hours Trailing Cushion ($):\n"
            "Once Profit Lock Trigger ($) is reached, your active Daily Stop trails behind\n"
            "your highest closed Realized PnL by this dollar amount.\n"
            "(Example: Trigger +$500 with $500 Trail locks your stop at $0.00 breakeven\n"
            "at +$500, and raises it to +$200 if you reach +$700.)\n"
            "• Hitting this trailed stop triggers your Card 2 Daily Stop Actions & OS Lock timer."
        )
    )

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
        if is_active:
            h0.config(bg="#132e24", padx=1, pady=1)
            outer_w.config(highlightbackground="#1f5c43", highlightthickness=1)
            bar_cv.set_neon("#00e676", glow_on=True)
            title_w.config(fg="#4ade80")
            if badge_w is not None:
                badge_w.set_active(True)
        else:
            h0.config(bg="#151d28", padx=1, pady=1)
            outer_w.config(highlightbackground="#243040", highlightthickness=1)
            bar_cv.set_neon("#334459", glow_on=False)
            title_w.config(fg="#7f8fa3")
            if badge_w is not None:
                badge_w.set_active(False)

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
    make_dual_field_row(
        c5,
        "Starting Max Loss ($):",
        dollar_vars["t1_max_loss"],
        None,
        None,
        fg1="#dc6d72",
        tip1=(
            "RTH Base Tier 1 — Starting Max Loss:\n"
            "Your initial worst-case RTH loss limit before any profit ratchet tiers are unlocked.\n"
            "If Net PnL reaches this loss, it triggers your Card 2 Daily Stop Actions\n"
            "(Auto-Flatten Equities, Kill Apps, and Windows OS Lock for the duration set in Card 2)."
        )
    )

    tk.Frame(c5, bg="#222d3d", height=1).pack(fill="x", pady=8)

    tbl = tk.Frame(c5, bg="#131922")
    tbl.pack(fill="x")
    tbl.columnconfigure(0, weight=2)
    tbl.columnconfigure(1, weight=1)
    tbl.columnconfigure(2, weight=1)

    tk.Label(
        tbl,
        text="PROFIT RATCHET TIERS (Raises Daily Stop)",
        font=("Arial", 10, "bold"),
        fg="#8ec5fc",
        bg="#131922",
        anchor="w"
    ).grid(row=0, column=0, sticky="w", pady=(0, 6))
    tk.Label(
        tbl,
        text="TRIGGER ($)",
        font=("Arial", 8, "bold"),
        fg="#8b9bb0",
        bg="#131922"
    ).grid(row=0, column=1, pady=(0, 6))
    tk.Label(
        tbl,
        text="NEW DAILY STOP",
        font=("Arial", 8, "bold"),
        fg="#8b9bb0",
        bg="#131922"
    ).grid(row=0, column=2, sticky="e", pady=(0, 6))

    tier_rows = [
        (
            "Tier 2 — Fixed Stop Ratchet ($0 Siren)",
            var_t2_on,
            dollar_vars["t2_trigger"],
            "Stop Level ($):",
            dollar_vars["t2_max_loss"],
            "#dce4ee",
            (
                "RTH Tier 2 — Fixed Daily Stop Ratchet:\n"
                "Once your closed Realized PnL reaches 'Trigger ($)', your active Daily Stop\n"
                "moves to 'Stop Level ($)' — supports negative, zero, or positive PnL levels!\n"
                "• Examples: Enter -1000 for a -$1,000 tightened stop, 0 for breakeven, or 250 for a +$250 profit lock.\n"
                "• If 'Stop Level ($)' is below $0, a warning siren sounds if PnL pulls back to $0.00.\n"
                "• Hitting 'Stop Level ($)' triggers your Card 2 Daily Stop Actions.\n"
                "Uncheck to skip Tier 2."
            )
        ),
        (
            "Tier 3 — Fixed Stop Ratchet ($0 Siren)",
            var_t3_on,
            dollar_vars["t3_trigger"],
            "Stop Level ($):",
            dollar_vars["t3_max_loss"],
            "#dce4ee",
            (
                "RTH Tier 3 — Fixed Daily Stop Ratchet:\n"
                "Once your closed Realized PnL reaches 'Trigger ($)', your active Daily Stop\n"
                "moves to 'Stop Level ($)' — supports negative, zero, or positive PnL levels!\n"
                "• Examples: Enter -500 for a -$500 tightened stop, 0 for $0.00 breakeven, or 250 for a +$250 locked profit stop.\n"
                "• If 'Stop Level ($)' is below $0, a warning siren sounds if PnL pulls back to $0.00.\n"
                "• Hitting 'Stop Level ($)' triggers your Card 2 Daily Stop Actions.\n"
                "Uncheck to skip Tier 3."
            )
        ),
        (
            "Tier 4 — Trailing Profit Lock",
            var_t4_on,
            dollar_vars["t4_trigger"],
            "Trail Peak By ($):",
            dollar_vars["t4_trail"],
            "#4ec994",
            (
                "RTH Tier 4 — Dynamic Trailing Profit Stop:\n"
                "Once your closed Realized PnL reaches 'Trigger ($)', your active Daily Stop\n"
                "locks in green and trails behind your highest realized PnL peak by 'Trail Peak By ($)'.\n"
                "(Example: Trigger at +$1,000 with $500 Trail locks in +$500 minimum, and ratchets\n"
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
    ) in enumerate(tier_rows, start=1):
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

        ent_trig = make_entry(tbl, trig_var, width=8)
        ent_trig.grid(row=idx, column=1, padx=8, pady=4)

        fl_cell = tk.Frame(tbl, bg="#131922")
        fl_cell.grid(row=idx, column=2, pady=4, sticky="e")
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
        attach_tooltip(ent_trig, t_tip)
        attach_tooltip(lbl_fl, t_tip)
        attach_tooltip(ent_fl, t_tip)
        tier_widget_refs.append(
            (t_cb_var, cb_t, ent_trig, lbl_fl, ent_fl, cb_fg_col)
        )

    # --- INTERACTIVE SMART DIMMING LOGIC ---
    def refresh_smart_dimming(*_):
        if var_alarms_only.get():
            cb_open_flat.config(state="disabled")
            ent_open_loss.config(state="disabled")
            lbl_open_loss.config(fg="#526070")
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
                cb_open_cd.config(state="normal")
                if var_open_cd.get():
                    ent_cd_mins.config(state="normal")
                    lbl_cd_mins.config(fg="#97a7b9")
                else:
                    ent_cd_mins.config(state="disabled")
                    lbl_cd_mins.config(fg="#526070")
            else:
                ent_open_loss.config(state="disabled")
                lbl_open_loss.config(fg="#526070")
                cb_open_cd.config(state="disabled")
                ent_cd_mins.config(state="disabled")
                lbl_cd_mins.config(fg="#526070")

            cb_day_flat.config(state="normal")
            if var_open_flat.get() or var_flatten.get():
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
        ent_pm_w1.config(state="normal" if var_pm_w1_on.get() else "disabled")
        cb_pm_w1.config(fg="#dce4ee" if var_pm_w1_on.get() else "#526070")
        ent_pm_w2.config(state="normal" if var_pm_w2_on.get() else "disabled")
        cb_pm_w2.config(fg="#dce4ee" if var_pm_w2_on.get() else "#526070")
        if var_pm_lock_on.get():
            cb_pm_lock.config(fg="#4ec994")
            ent_pm_trig.config(state="normal")
            lbl_pm_trail.config(fg="#97a7b9")
            ent_pm_trail.config(state="normal")
        else:
            cb_pm_lock.config(fg="#526070")
            ent_pm_trig.config(state="disabled")
            lbl_pm_trail.config(fg="#526070")
            ent_pm_trail.config(state="disabled")

        # Card 5: RTH Tier 1 Warning Alarms & Profit Ratchet Tiers 2-4
        ent_t1_w1.config(state="normal" if var_t1_w1_on.get() else "disabled")
        cb_t1_w1.config(fg="#dce4ee" if var_t1_w1_on.get() else "#526070")
        ent_t1_w2.config(state="normal" if var_t1_w2_on.get() else "disabled")
        cb_t1_w2.config(fg="#dce4ee" if var_t1_w2_on.get() else "#526070")
        for (
            t_cb_var, cb_t, ent_trig, lbl_fl, ent_fl, cb_fg_col
        ) in tier_widget_refs:
            if t_cb_var.get():
                cb_t.config(fg=cb_fg_col)
                ent_trig.config(state="normal")
                lbl_fl.config(fg="#97a7b9")
                ent_fl.config(state="normal")
            else:
                cb_t.config(fg="#526070")
                ent_trig.config(state="disabled")
                lbl_fl.config(fg="#526070")
                ent_fl.config(state="disabled")

    for trace_var in (
        var_alarms_only,
        var_open_flat, var_open_cd, var_flatten, var_lock_os,
        var_pm_w1_on, var_pm_w2_on, var_pm_lock_on,
        var_t1_w1_on, var_t1_w2_on, var_t2_on, var_t3_on, var_t4_on
    ):
        trace_var.trace_add("write", refresh_smart_dimming)
    refresh_smart_dimming()

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
        fg="#8b9bb0",
        bg="#0d1117",
        anchor="w"
    )
    default_status_lbl.pack(side="left")

    launch_txt = (
        "🚀 SAVE & LAUNCH ENFORCER >>"
        if parent is None else "🚀 SAVE & APPLY CHANGES >>"
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
        width=268,
        height=38,
        pad_x=36,
        command=save_and_launch,
    )
    btn_launch.pack(side="right")

    ver_outer = tk.Frame(pf, bg="#0d1117")
    ver_outer.pack(fill="x", pady=(4, 0))
    ver_frame = tk.Frame(ver_outer, bg="#0d1117")
    ver_frame.pack(anchor="center")

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

    if parent is None:
        pf.mainloop()
        return launched["status"]
    return True


# ==========================================
# 9. DYNAMIC MULTI-COLUMN HUD SETUP
# ==========================================
acct_badge_mode = 0  # 0 = W/L, 1 = FLAT, 2 = BASE
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
    """Updates the clickable left account badge (W/L -> FLAT -> BASE)."""
    if acct_badge_lbl is None:
        return

    if acct_badge_mode == 1:
        val = last_flat_equity if last_flat_equity is not None else start_equity
        txt = f"FLAT: ${val:,.2f}" if (val is not None and val > 0) else "FLAT: ---"
        fg_col = "#ffffff"
    elif acct_badge_mode == 2:
        val = start_equity
        txt = f"BASE: ${val:,.2f}" if (val is not None and val > 0) else "BASE: ---"
        fg_col = "#aed6f1"
    else:
        txt = format_trades_wl_inline(win_trades, loss_trades)
        fg_col = "#e5e8e8"

    acct_badge_lbl.config(text=txt, fg=fg_col)


def toggle_acct_badge(event=None):
    global acct_badge_mode
    acct_badge_mode = (acct_badge_mode + 1) % 3
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

        hdr_lbl = tk.Label(
            col_frame,
            text=title,
            font=("Arial", 8, "bold"),
            fg="#cccccc",
            bg="#1b1e22",
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
            bg="#262a2e",
            justify="center"
        )
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
    for i, (text_val, bg_col) in enumerate(col_data):
        disp_bg = "#262a2e" if bg_col in ("#2c3e50", "#1f538d") else bg_col
        if i < len(ui_labels):
            ui_labels[i].config(text=text_val, bg=disp_bg)
        if i == hud_leash_idx:
            hud_last_leash_bg = disp_bg

    if hud_leash_bar is not None and leash_pct is not None:
        hud_last_leash_pct = max(0.0, min(1.0, float(leash_pct)))
        _redraw_hud_leash_canvas()

    refresh_acct_badge()

    if is_flat:
        settings_btn.config(
            text="⚙ SETTINGS",
            fill_color="#141922",
            fill_top_color="#1c2430",
            border_color="#2e3d4f",
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
            text="🔒 IN TRADE",
            fill_color="#1e2228",
            fill_top_color="#262a30",
            border_color="#6b5b3e",
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
            or len(get_active_hud_columns(config)) >= 5
        ):
            return
        try:
            tw = tk.Toplevel(hud_win)
            tw.wm_overrideredirect(True)
            tw.attributes("-topmost", True)
            tw.config(bg="#334155", padx=1, pady=1)
            inner = tk.Frame(tw, bg="#141820", padx=12, pady=8)
            inner.pack(fill="both", expand=True)

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

            tk.Label(
                inner,
                text=get_full_idle_button_text(),
                font=("Arial", 9, "bold"),
                fg="#ffca58",
                bg="#141820",
                justify="left",
                anchor="w",
            ).pack(fill="x")

            r_mode = (
                "Regular Hours (9:30 AM – 4:00 PM ET)"
                if is_rth()
                else "Extended Hours (Pre-Market & After-Hours)"
            )
            sub_txt = (
                f"Active Rulebook: {r_mode}   ·   "
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
            wx = widget.winfo_rootx()
            wy = widget.winfo_rooty()
            ww = widget.winfo_width()
            wh = widget.winfo_height()
            x = wx + max(0, (ww - tip_w) // 2)
            x = max(8, x)
            y = wy + wh + 5
            try:
                v_top = hud_win.winfo_vrooty()
                v_h = hud_win.winfo_vrootheight()
                if v_h > 200 and (y + tip_h) > (v_top + v_h - 40):
                    y = hud_win.winfo_rooty() - tip_h - 5
            except Exception:
                pass
            tw.wm_geometry(f"+{int(x)}+{int(y)}")
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

    threading.Thread(
        target=data_loop,
        args=(ui_labels, mute_btn, settings_btn, close_btn, root),
        daemon=True
    ).start()
    root.mainloop()


# ==========================================
# 10. ENTRY POINT & SAFE FALLBACK
# ==========================================
GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/DBCodez/pnl-enforcer-beta/main/"
)
GIST_ENFORCER_RAW_URL = (
    "https://gist.githubusercontent.com/DBCodez/"
    "6442a3ab2767aeb5ba0b13940d012634/raw/enforcer.py"
)
CHANGELOG_WEB_URL = (
    "https://gist.github.com/DBCodez/c91f71c6114caf3f2dee17cc8b60a757"
)
GIST_DOC_RAW_URLS = {
    "CHANGELOG.md": (
        "https://gist.githubusercontent.com/DBCodez/"
        "c91f71c6114caf3f2dee17cc8b60a757/raw/CHANGELOG.md"
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


def _parse_version_tuple(v_str):
    nums = [int(x) for x in re.findall(r"\d+", str(v_str))]
    return tuple(nums) if nums else (0,)


def _fetch_remote_doc_bytes(doc_name, ts=None):
    import urllib.request
    if ts is None:
        ts = int(time.time())
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
                return doc_bytes
        except Exception:
            continue
    return None


def _insert_formatted_changelog(txt_box, markdown_text):
    """Renders Markdown release notes into a tk.Text widget with rich typography,
    comfortable line spacing, hanging bullet indents, and color-coded highlights."""
    txt_box.config(
        font=("Arial", 10),
        fg="#e5e8e8",
        bg="#0e131a",
        padx=16,
        pady=12,
    )
    txt_box.tag_configure(
        "doc_title",
        font=("Arial", 13, "bold"),
        foreground="#ffffff",
        spacing1=2,
        spacing3=4,
    )
    txt_box.tag_configure(
        "doc_sub",
        font=("Arial", 10),
        foreground="#94a3b8",
        spacing1=0,
        spacing3=8,
    )
    txt_box.tag_configure(
        "ver_hdr",
        font=("Arial", 11, "bold"),
        foreground="#00e676",
        background="#142b23",
        spacing1=10,
        spacing3=6,
    )
    txt_box.tag_configure(
        "sec_hdr",
        font=("Arial", 10, "bold"),
        foreground="#38bdf8",
        spacing1=6,
        spacing3=3,
    )
    txt_box.tag_configure(
        "bullet_1",
        font=("Arial", 10),
        foreground="#e5e8e8",
        lmargin1=8,
        lmargin2=24,
        spacing1=5,
        spacing2=3,
        spacing3=3,
    )
    txt_box.tag_configure(
        "bullet_2",
        font=("Arial", 10),
        foreground="#d0d7de",
        lmargin1=28,
        lmargin2=44,
        spacing1=3,
        spacing2=2,
        spacing3=3,
    )
    txt_box.tag_configure(
        "body_line",
        font=("Arial", 10),
        foreground="#e5e8e8",
        spacing1=3,
        spacing2=2,
        spacing3=3,
    )
    txt_box.tag_configure(
        "bold_lead",
        font=("Arial", 10, "bold"),
        foreground="#ffd166",
    )
    txt_box.tag_configure(
        "bold_inline",
        font=("Arial", 10, "bold"),
        foreground="#ffffff",
    )
    txt_box.tag_configure(
        "code_span",
        font=("Consolas", 10, "bold"),
        foreground="#7dd3fc",
    )
    txt_box.tag_configure(
        "italic_span",
        font=("Arial", 10, "italic"),
        foreground="#a3e4d7",
    )
    txt_box.tag_configure(
        "hr_div",
        font=("Arial", 7),
        foreground="#243040",
        spacing1=6,
        spacing3=4,
    )

    def _insert_rich_spans(text_line, base_tag):
        parts = re.split(r"(\*\*.*?\*\*|`[^`]+`|\*\"[^\"]+\"\*)", text_line)
        first_bold_seen = False
        for part in parts:
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                inner = part[2:-2].replace("`", "")
                b_tag = "bold_lead" if not first_bold_seen else "bold_inline"
                first_bold_seen = True
                txt_box.insert("end", inner, (base_tag, b_tag))
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                txt_box.insert("end", part[1:-1], (base_tag, "code_span"))
            elif part.startswith('*"') and part.endswith('"*') and len(part) > 4:
                txt_box.insert("end", part[1:-1], (base_tag, "italic_span"))
            else:
                txt_box.insert("end", part, (base_tag,))
        txt_box.insert("end", "\n", (base_tag,))

    for raw_ln in str(markdown_text or "").splitlines():
        stripped = raw_ln.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            txt_box.insert("end", stripped[2:].strip() + "\n", ("doc_title",))
        elif stripped.startswith("## "):
            ver_txt = stripped[3:].strip().replace("[", "").replace("]", "")
            txt_box.insert("end", f"  {ver_txt}  \n", ("ver_hdr",))
        elif stripped.startswith("### "):
            sec_txt = stripped[4:].strip().upper()
            txt_box.insert("end", f"▸ {sec_txt}\n", ("sec_hdr",))
        elif stripped.startswith("---"):
            txt_box.insert("end", "─" * 78 + "\n", ("hr_div",))
        elif raw_ln.startswith("  - ") or raw_ln.startswith("    - "):
            txt_box.insert("end", "◦  ", ("bullet_2", "bold_inline"))
            _insert_rich_spans(stripped[2:].strip(), "bullet_2")
        elif stripped.startswith("- "):
            txt_box.insert("end", "•  ", ("bullet_1", "bold_lead"))
            _insert_rich_spans(stripped[2:].strip(), "bullet_1")
        elif stripped.startswith("All notable updates"):
            txt_box.insert("end", stripped + "\n", ("doc_sub",))
        else:
            _insert_rich_spans(stripped, "body_line")


def show_update_available_dialog(curr_ver, new_ver, changelog_md=""):
    """Displays a dark-themed GUI popup when a new version is available,
    showing release notes and a clickable link to the full Changelog."""
    decision = {"install": False}
    try:
        win = tk.Tk()
        if os.path.exists(ICON_PATH):
            try:
                win.iconbitmap(ICON_PATH)
            except Exception:
                pass
        win.title(f"PnL Enforcer Beta — Update Available (v{new_ver})")
        win.config(bg="#0d1117", padx=24, pady=18)
        win.resizable(False, False)
        win.attributes("-topmost", True)

        w, h = 720, 480
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(20, (sw - w) // 2)
        y = max(20, (sh - h) // 2)
        win.geometry(f"{w}x{h}+{x}+{y}")

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
            command=lambda: webbrowser.open(CHANGELOG_WEB_URL),
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

        txt_frame = tk.Frame(
            card,
            bg="#0e131a",
            bd=0,
            highlightthickness=1,
            highlightbackground="#1e293b",
        )
        txt_frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(txt_frame)
        sb.pack(side="right", fill="y")

        txt_box = tk.Text(
            txt_frame,
            height=12,
            bg="#0e131a",
            fg="#e5e8e8",
            font=("Consolas", 9),
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
        _insert_formatted_changelog(txt_box, display_notes)
        txt_box.see("1.0")
        txt_box.config(state="disabled")

        win.protocol("WM_DELETE_WINDOW", on_skip)
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
        webbrowser.open(CHANGELOG_WEB_URL)
        return

    is_standalone = parent is None
    win = tk.Tk() if is_standalone else tk.Toplevel(parent)
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
    win.attributes("-topmost", True)

    w, h = 790, 570
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(20, (sw - w) // 2)
    y = max(20, (sh - h) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")

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
        command=lambda: webbrowser.open(CHANGELOG_WEB_URL),
    ).pack(side="right")

    btn_bar = tk.Frame(win, bg="#0d1117", pady=10)
    btn_bar.pack(fill="x", side="bottom")

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

    txt_frame = tk.Frame(
        card,
        bg="#0e131a",
        bd=0,
        highlightthickness=1,
        highlightbackground="#1e293b",
    )
    txt_frame.pack(fill="both", expand=True)

    sb = tk.Scrollbar(txt_frame)
    sb.pack(side="right", fill="y")

    txt_box = tk.Text(
        txt_frame,
        height=16,
        bg="#0e131a",
        fg="#e5e8e8",
        font=("Consolas", 9),
        wrap="word",
        bd=0,
        padx=10,
        pady=8,
        yscrollcommand=sb.set,
    )
    txt_box.pack(side="left", fill="both", expand=True)
    sb.config(command=txt_box.yview)

    _insert_formatted_changelog(txt_box, cl_text.strip())
    txt_box.see("1.0")
    txt_box.config(state="disabled")

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
        candidate_urls = []
        try:
            api_req = urllib.request.Request(
                "https://api.github.com/gists/6442a3ab2767aeb5ba0b13940d012634",
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
            f"{GIST_ENFORCER_RAW_URL}?t={ts}",
            f"{GITHUB_RAW_BASE}enforcer.py?t={ts}",
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