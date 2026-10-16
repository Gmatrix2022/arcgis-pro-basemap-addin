#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArcGIS Pro 3.7 纯净环境启动与窗口左屏归位工具 (GeoAI Workspace Standard)
核心特性：
1. 从 Windows 注册表重建 System+User 干净环境，剥离 Conda/QGIS/MinGW/WorkBuddy 变量污染，
   解决 UIFrameworkUtil.dll (0x8007007E) 崩溃问题；
2. 强制显式指定 STARTUPINFOW.lpDesktop = "WinSta0\\Default" 并切换线程桌面至 Default，
   穿透智能体沙箱桌面 (exebox-*)，确保窗口真实呈现在用户主桌面左屏；
3. 支持从 Blank.aprx 种子创建工作工程，自动等待工程主窗口就绪并归位至左屏 (0, 96, 1920, 1200)。
"""
import argparse
import ctypes
from ctypes import wintypes
import os
import shutil
import sys
import time
import winreg
from pathlib import Path

AGP_EXE = r"C:\Program Files\ArcGIS\Pro\bin\ArcGISPro.exe"
SEED_APRX = r"C:\Program Files\ArcGIS\Pro\Resources\ArcToolBox\Services\routingservices\data\Blank.aprx"

KEEP = (
    "ALLUSERSPROFILE", "APPDATA", "CommonProgramFiles", "CommonProgramFiles(x86)",
    "CommonProgramW6432", "COMPUTERNAME", "ComSpec", "DriverData", "HOMEDRIVE",
    "HOMEPATH", "LOCALAPPDATA", "LOGONSERVER", "NUMBER_OF_PROCESSORS", "OS",
    "PATHEXT", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
    "PROCESSOR_LEVEL", "PROCESSOR_REVISION", "ProgramData", "ProgramFiles",
    "ProgramFiles(x86)", "ProgramW6432", "PUBLIC", "SESSIONNAME", "SystemDrive",
    "SystemRoot", "TEMP", "TMP", "USERDOMAIN", "USERDOMAIN_ROAMINGPROFILE",
    "USERNAME", "USERPROFILE", "windir",
)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def switch_to_default_desktop():
    hd = user32.OpenDesktopW("Default", 0, True, 0x01FF)
    if hd:
        user32.SetThreadDesktop(hd)
    return hd


def _reg(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except Exception:
        return None


def build_clean_env() -> dict:
    env = {}
    for k in KEEP:
        v = _reg(r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment", k)
        if v is None:
            v = os.environ.get(k)
        if v is not None:
            env[k] = os.path.expandvars(v)

    env.setdefault("SystemRoot", r"C:\Windows")
    env.setdefault("windir", env["SystemRoot"])
    env["PROCESSOR_ARCHITECTURE"] = env.get("PROCESSOR_ARCHITECTURE", "AMD64")

    up = r"C:\Users\keche"
    env["USERPROFILE"] = up
    env["USERNAME"] = "keche"
    env["APPDATA"] = os.path.join(up, "AppData", "Roaming")
    env["LOCALAPPDATA"] = os.path.join(up, "AppData", "Local")
    t = os.path.join(env["LOCALAPPDATA"], "Temp")
    os.makedirs(t, exist_ok=True)
    env["TEMP"] = env["TMP"] = t

    env["PATH"] = ";".join([
        os.path.join(env["SystemRoot"], "system32"),
        env["SystemRoot"],
        os.path.join(env["SystemRoot"], "System32", "Wbem"),
        os.path.join(env["SystemRoot"], "System32", "WindowsPowerShell", "v1.0"),
        os.path.join(env["SystemRoot"], "System32", "OpenSSH"),
        r"C:\Program Files\ArcGIS\Pro\bin",
        r"C:\Program Files\Java\jdk-17\bin",
    ])
    return env


def spawn_on_default_desktop(cmd_list: list[str], env: dict, cwd: str) -> int:
    switch_to_default_desktop()
    cmd_line = " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd_list)
    env_block = "\0".join(f"{k}={v}" for k, v in sorted(env.items())) + "\0\0"
    env_buf = ctypes.create_unicode_buffer(env_block)

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(STARTUPINFOW)
    si.lpDesktop = "WinSta0\\Default"
    pi = PROCESS_INFORMATION()

    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    ok = kernel32.CreateProcessW(
        None,
        ctypes.create_unicode_buffer(cmd_line),
        None,
        None,
        False,
        CREATE_UNICODE_ENVIRONMENT,
        ctypes.byref(env_buf),
        cwd,
        ctypes.byref(si),
        ctypes.byref(pi),
    )
    if not ok:
        raise RuntimeError(f"CreateProcessW failed with error {kernel32.GetLastError()}")
    kernel32.CloseHandle(pi.hThread)
    kernel32.CloseHandle(pi.hProcess)
    return pi.dwProcessId


def find_agp_windows(aprx_stem: str = ""):
    switch_to_default_desktop()
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        low = title.lower()
        if "arcgis pro" in low or (aprx_stem and aprx_stem.lower() in low):
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 300 and h > 200:
                found.append((hwnd, title, (rect.left, rect.top, w, h)))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def move_to_left_screen(hwnd: int, x: int = 0, y: int = 96, w: int = 1920, h: int = 1200):
    switch_to_default_desktop()
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.MoveWindow(hwnd, x, y, w, h, True)
    user32.SetForegroundWindow(hwnd)


def main():
    parser = argparse.ArgumentParser(description="Launch ArcGIS Pro 3.7 on Default desktop in a clean environment")
    parser.add_argument("--aprx", type=str, default="", help="Path to .aprx project file to open")
    parser.add_argument("--create-from-seed", action="store_true", help="Copy Blank.aprx if --aprx does not exist")
    parser.add_argument("--wait-seconds", type=int, default=42, help="Seconds to wait for main project window")
    parser.add_argument("--left-screen", action="store_true", default=True, help="Move main window to left monitor")
    args = parser.parse_args()

    cmd = [AGP_EXE]
    aprx_stem = ""
    if args.aprx:
        aprx_path = Path(args.aprx).resolve()
        aprx_stem = aprx_path.stem
        if not aprx_path.exists():
            if args.create_from_seed:
                aprx_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SEED_APRX, aprx_path)
                print(f"[clean_launch] Created project from Blank.aprx -> {aprx_path}")
            else:
                print(f"[clean_launch] ERROR: {aprx_path} does not exist. Use --create-from-seed.", file=sys.stderr)
                sys.exit(1)
        cmd.append(str(aprx_path))

    env = build_clean_env()
    pid = spawn_on_default_desktop(cmd, env, r"C:\Users\keche")
    print(f"[clean_launch] Spawned ArcGISPro.exe on WinSta0\\Default PID={pid}")

    deadline = time.time() + args.wait_seconds
    main_win = None
    while time.time() < deadline:
        wins = find_agp_windows(aprx_stem)
        for hwnd, title, rect in wins:
            # 忽略启动闪屏（标题恰为 'ArcGIS Pro' 且工程名尚未出现）
            if aprx_stem and aprx_stem.lower() in title.lower():
                main_win = (hwnd, title, rect)
                break
            elif not aprx_stem and rect[2] > 900 and title != "ArcGIS Pro":
                main_win = (hwnd, title, rect)
                break
        if main_win:
            break
        time.sleep(2.0)

    if main_win:
        hwnd, title, rect = main_win
        print(f"[clean_launch] Project window ready: HWND=0x{hwnd:X} Title='{title}' Rect={rect}")
        if args.left_screen:
            time.sleep(3.0)
            move_to_left_screen(hwnd)
            print("[clean_launch] Positioned window on left screen (0, 96, 1920, 1200)")
    else:
        wins = find_agp_windows(aprx_stem)
        print(f"[clean_launch] Current visible ArcGIS Pro windows after {args.wait_seconds}s: {wins}")


if __name__ == "__main__":
    main()
