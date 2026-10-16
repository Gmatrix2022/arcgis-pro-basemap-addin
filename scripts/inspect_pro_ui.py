import ctypes
from ctypes import wintypes
import time

user32 = ctypes.windll.user32
h_desk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
if h_desk:
    user32.SetThreadDesktop(h_desk)

# Use UIAutomation via pywinauto or ctypes if available
try:
    import pywinauto
    print("pywinauto available!")
    app = pywinauto.Application(backend="uia").connect(process=111244)
    dlg = app.top_window()
    print("Window title:", dlg.window_text())
    tabs = dlg.descendants(control_type="TabItem")
    print("Found tabs:", len(tabs))
    for t in tabs:
        print(f"  Tab: {t.window_text()} (AutoId: {t.automation_id()})")
except Exception as e:
    print("pywinauto error:", e)
