"""Windows: the parts the Linux desktop does through GNOME, done through the Win32 API (ctypes).

The sky goes behind the desktop icons the way live-wallpaper apps do it: Progman is asked to
create the WorkerW window that sits between the wallpaper and the icons, and the sky window becomes
its child. Windows 11 24H2 moved the icons (SHELLDLL_DefView) and the WorkerW inside Progman; there
the sky becomes Progman's child, ordered just below the icons. Behind the icons the sky gets no
clicks, so Settings and Quit live in a tray icon. With click-through off, the sky is a normal
bottom-most window instead, over the icons, and takes every click.

Only imported on Windows.
"""

import ctypes
import os
import sys
import winreg
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32')

_GWL_STYLE, _GWL_EXSTYLE = -16, -20
_WS_CHILD, _WS_POPUP = 0x40000000, 0x80000000
_WS_EX_TOOLWINDOW, _WS_EX_NOACTIVATE, _WS_EX_APPWINDOW = 0x80, 0x08000000, 0x40000
_WS_EX_LAYERED, _LWA_ALPHA = 0x80000, 0x2
_SWP_NOSIZE, _SWP_NOZORDER = 0x1, 0x4
_SWP_NOACTIVATE, _SWP_SHOWWINDOW, _SWP_FRAMECHANGED = 0x10, 0x40, 0x20
_HWND_BOTTOM = 1
_RGN_OR = 2
_GW_HWNDPREV = 3
_SMTO_NORMAL = 0
_SPI_GETDESKWALLPAPER, _SPI_SETDESKWALLPAPER = 0x73, 0x14
_SPIF_UPDATEINIFILE, _SPIF_SENDCHANGE = 0x1, 0x2
_MONITOR_DEFAULTTOPRIMARY = 1
_SM_XVIRTUALSCREEN, _SM_YVIRTUALSCREEN = 76, 77

_LONG_PTR = ctypes.c_ssize_t
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SendMessageTimeoutW.restype = _LONG_PTR
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SetParent.restype = wintypes.HWND
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.GetWindowLongPtrW.restype = _LONG_PTR
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = _LONG_PTR
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, _LONG_PTR]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE,
                                              wintypes.DWORD]
user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
gdi32.CreateRectRgn.restype = wintypes.HRGN
gdi32.CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
user32.GetWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_ENUM_PROC, wintypes.LPARAM]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


# ─── Folders ─────────────────────────────────────────────────────────────────

def config_home():
    """Roaming settings (follow the user between PCs)."""
    return os.environ.get('APPDATA') or os.path.expanduser('~\\AppData\\Roaming')


def data_home():
    """This PC's files: personal landscapes, the wallpaper picture."""
    return os.environ.get('LOCALAPPDATA') or os.path.expanduser('~\\AppData\\Local')


# ─── The sky window ──────────────────────────────────────────────────────────

def hwnd_of(gdk_window):
    """The Win32 handle behind a realized Gdk.Window."""
    get_ptr = ctypes.pythonapi.PyCapsule_GetPointer
    get_ptr.restype, get_ptr.argtypes = ctypes.c_void_p, [ctypes.py_object, ctypes.c_char_p]
    gdk = ctypes.CDLL('libgdk-3-0.dll')
    gdk.gdk_win32_window_get_handle.restype = ctypes.c_void_p
    gdk.gdk_win32_window_get_handle.argtypes = [ctypes.c_void_p]
    return gdk.gdk_win32_window_get_handle(get_ptr(gdk_window.__gpointer__, None))


def _icon_layer():
    """(parent, insert_after) for a window behind the desktop icons, or None if not found."""
    progman = user32.FindWindowW('Progman', None)
    if not progman:
        return None
    # Ask Progman for the WorkerW between the wallpaper and the icons (undocumented, long stable)
    user32.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, _SMTO_NORMAL, 1000, None)
    defview = user32.FindWindowExW(progman, None, 'SHELLDLL_DefView', None)
    if defview:
        # Windows 11 24H2 and later: the icons are Progman's child; go just below them
        return progman, defview
    found = []

    def _probe(hwnd, _lparam):
        if user32.FindWindowExW(hwnd, None, 'SHELLDLL_DefView', None):
            # Earlier Windows: the WorkerW after the icons' top-level window is the one to use
            worker = user32.FindWindowExW(None, hwnd, 'WorkerW', None)
            if worker:
                found.append(worker)
            return False
        return True
    user32.EnumWindows(_ENUM_PROC(_probe), 0)
    return (found[0], None) if found else None


def taskbar_edges():
    """((left, top, right, bottom) of the primary monitor covered by the taskbar, monitor width)."""
    info = _primary_info()
    m, w = info.rcMonitor, info.rcWork
    return (w.left - m.left, w.top - m.top, m.right - w.right, m.bottom - w.bottom), m.right - m.left


def _primary_info():
    info = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
    mon = user32.MonitorFromPoint(wintypes.POINT(0, 0), _MONITOR_DEFAULTTOPRIMARY)
    user32.GetMonitorInfoW(mon, ctypes.byref(info))
    return info


def _primary_rect():
    """Primary monitor (x, y, w, h) in virtual-screen coordinates, as the icon layer's client
    area counts them."""
    r = _primary_info().rcMonitor
    return r.left, r.top, r.right - r.left, r.bottom - r.top


_layered_by_us = set()   # sky windows made layered here, not by GTK


def primary_size():
    """Primary monitor (width, height) in the pixels this process sees."""
    return _primary_rect()[2:]


def place_sky(hwnd, behind_icons):
    """
    Put the sky window behind the desktop icons, or (behind_icons False, or no icon layer found)
    at the bottom of the normal windows. Returns True when it went behind the icons.
    Only the position changes: GTK sizes the window itself, and paints at the size it asked for.
    """
    x, y, _w, _h = _primary_rect()
    flags = _SWP_NOSIZE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW | _SWP_FRAMECHANGED
    ex = user32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
    # GTK paints through a layered window (UpdateLayeredWindow) unless GDK_WIN32_LAYERED=0 (app.py)
    # turned that off; the bit is GTK's then, keep it
    gtk_layered = bool(ex & _WS_EX_LAYERED) and hwnd not in _layered_by_us
    # Never in the taskbar or Alt+Tab, and a click doesn't raise it over the user's windows
    ex = (ex | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE) & ~_WS_EX_APPWINDOW
    if not gtk_layered:
        # Layered and fully opaque: 24H2's Progman is composited and only draws a layered child,
        # and a plain bottom-most window didn't show either (Windows Server 2025 runner)
        ex |= _WS_EX_LAYERED
        _layered_by_us.add(hwnd)
    if 'style' not in os.environ.get('CAELUM_WIN_SKIP', ''):   # TEMPORARY: CI bisection
        user32.SetWindowLongPtrW(hwnd, _GWL_EXSTYLE, ex)
    if hwnd in _layered_by_us:
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, _LWA_ALPHA)
    style = user32.GetWindowLongPtrW(hwnd, _GWL_STYLE)
    layer = _icon_layer() if behind_icons else None
    if layer:
        parent, below = layer
        user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, (style | _WS_CHILD) & ~_WS_POPUP)
        user32.SetParent(hwnd, parent)
        x -= user32.GetSystemMetrics(_SM_XVIRTUALSCREEN)
        y -= user32.GetSystemMetrics(_SM_YVIRTUALSCREEN)
        user32.SetWindowPos(hwnd, below or _HWND_BOTTOM, x, y, 0, 0, flags)
        _log(hwnd, 'behind the icons (24H2 Progman)' if below else 'behind the icons (WorkerW)')
        return True
    user32.SetParent(hwnd, None)
    user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, (style | _WS_POPUP) & ~_WS_CHILD)
    _just_above_icons(hwnd, x, y, flags)
    _log(hwnd, 'bottom-most window' + ('' if not behind_icons else ' (no icon layer found)'))
    return False


def _icons_top():
    """The top-level window that holds the desktop icons: Progman on 24H2+, a WorkerW before."""
    progman = user32.FindWindowW('Progman', None)
    if progman and user32.FindWindowExW(progman, None, 'SHELLDLL_DefView', None):
        return progman
    found = []

    def _probe(hwnd, _lparam):
        if user32.FindWindowExW(hwnd, None, 'SHELLDLL_DefView', None):
            found.append(hwnd)
            return False
        return True
    user32.EnumWindows(_ENUM_PROC(_probe), 0)
    return found[0] if found else progman


def _just_above_icons(hwnd, x, y, flags):
    """Bottom of the normal windows, yet over the desktop and its icons (full-screen windows
    themselves): a plain HWND_BOTTOM window goes under them and is never seen."""
    icons = _icons_top()
    above = user32.GetWindow(icons, _GW_HWNDPREV) if icons else None
    if above == hwnd:
        flags |= _SWP_NOZORDER
    user32.SetWindowPos(hwnd, above or _HWND_BOTTOM, x, y, 0, 0, flags)


# ─── Clicks on the sky's controls while it is behind the icons ──────────────

def place_hit_layer(hwnd):
    """
    An invisible window over the icons that takes the clicks the sky's controls need (gear,
    compass, forecast cards; see set_hit_region): at alpha 1 nothing shows, yet Windows still
    sends it the clicks. Clicks elsewhere go to the icons, as on Linux with the input shape.
    """
    ex = user32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
    ex = (ex | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE | _WS_EX_LAYERED) & ~_WS_EX_APPWINDOW
    user32.SetWindowLongPtrW(hwnd, _GWL_EXSTYLE, ex)
    user32.SetLayeredWindowAttributes(hwnd, 0, 1, _LWA_ALPHA)
    x, y, _w, _h = _primary_rect()
    _just_above_icons(hwnd, x, y, _SWP_NOSIZE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW)


def set_hit_region(hwnd, rects, scale=1.0):
    """The hit layer takes clicks only inside rects ((x, y, w, h), GTK pixels × scale = Windows
    pixels); None: everywhere (exploring the sky)."""
    if rects is None:
        user32.SetWindowRgn(hwnd, None, True)
        return
    rgn = gdi32.CreateRectRgn(0, 0, 0, 0)
    for x, y, w, h in rects:
        part = gdi32.CreateRectRgn(*(int(round(v * scale)) for v in (x, y, x + w, y + h)))
        gdi32.CombineRgn(rgn, rgn, part, _RGN_OR)
        gdi32.DeleteObject(part)
    user32.SetWindowRgn(hwnd, rgn, True)     # Windows owns rgn from here


def _log(hwnd, where):
    """One line in caelum.log: where the sky went, for bug reports from Windows users."""
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    print(f'Caelum: sky placed {where}, {r.right - r.left}x{r.bottom - r.top} at '
          f'({r.left}, {r.top}), visible={bool(user32.IsWindowVisible(hwnd))}',
          file=sys.stderr, flush=True)


def restore_desktop():
    """After the sky leaves the icon layer, redraw the user's own wallpaper there."""
    buf = ctypes.create_unicode_buffer(260)
    if user32.SystemParametersInfoW(_SPI_GETDESKWALLPAPER, len(buf), buf, 0) and buf.value:
        user32.SystemParametersInfoW(_SPI_SETDESKWALLPAPER, 0, buf, 0)


# ─── Wallpaper ───────────────────────────────────────────────────────────────

def set_wallpaper(path):
    """Desktop background; Windows has no lock-screen picture API for desktop apps."""
    if not user32.SystemParametersInfoW(_SPI_SETDESKWALLPAPER, 0, ctypes.c_wchar_p(path),
                                        _SPIF_UPDATEINIFILE | _SPIF_SENDCHANGE):
        raise ctypes.WinError(ctypes.get_last_error())


# ─── Autostart (the per-user Run key) ───────────────────────────────────────

_RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
_RUN_NAME = 'Caelum'


def _command():
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    # From source or pip: pythonw has no console window
    exe = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    return f'"{exe if os.path.exists(exe) else sys.executable}" -m caelum'


def set_autostart(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, _RUN_NAME)
            except FileNotFoundError:
                pass


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_NAME)
        return True
    except OSError:
        return False
