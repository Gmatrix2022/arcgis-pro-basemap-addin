#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArcGIS Pro / 桌面 GIS 窗口精准截图工具 (GeoAI Workspace Standard)
自动切换线程桌面至 WinSta0\\Default（穿透 Antigravity exebox-* 沙箱桌面），
支持 PrintWindow(PW_RENDERFULLCONTENT=2) 与左屏置顶 ImageGrab 双模式。
"""
import argparse
import ctypes
from ctypes import wintypes
import sys
import time
from pathlib import Path
from PIL import Image, ImageGrab

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


def switch_to_default_desktop():
    hd = user32.OpenDesktopW("Default", 0, True, 0x01FF)
    if hd:
        user32.SetThreadDesktop(hd)
    return hd


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def find_windows(title_substr: str):
    switch_to_default_desktop()
    result = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if title_substr.lower() in title.lower():
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 300 and h > 200:
                result.append((hwnd, title, (rect.left, rect.top, rect.right, rect.bottom)))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return result


def capture_window(hwnd: int, out_path: str, force_foreground: bool = True) -> bool:
    switch_to_default_desktop()
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.5)

    if force_foreground:
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.6)

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return False

    hwndDC = user32.GetWindowDC(hwnd)
    mfcDC = gdi32.CreateCompatibleDC(hwndDC)
    saveBitMap = gdi32.CreateCompatibleBitmap(hwndDC, w, h)
    gdi32.SelectObject(mfcDC, saveBitMap)
    res = user32.PrintWindow(hwnd, mfcDC, 2)

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mfcDC, saveBitMap, 0, h, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")

    gdi32.DeleteObject(saveBitMap)
    gdi32.DeleteDC(mfcDC)
    user32.ReleaseDC(hwnd, hwndDC)

    extrema = img.getextrema()
    if res == 0 or all(lo == hi == 0 for lo, hi in extrema):
        img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"[winshot] Saved {w}x{h} screenshot -> {out_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Capture ArcGIS Pro or desktop GIS window on Default desktop")
    parser.add_argument("--title", type=str, default="dianchi", help="Substring of window title")
    parser.add_argument("--out", type=str, required=True, help="Output PNG path")
    args = parser.parse_args()

    wins = find_windows(args.title)
    if not wins:
        print(f"[winshot] ERROR: No visible window matching '{args.title}' on Default desktop", file=sys.stderr)
        sys.exit(1)

    hwnd, title, bbox = wins[0]
    print(f"[winshot] Matched HWND=0x{hwnd:X} Title='{title}' BBox={bbox}")
    capture_window(hwnd, args.out)


if __name__ == "__main__":
    main()
