"""Windows: the parts the Linux desktop does through GNOME, done through the Win32 API (ctypes).

The sky goes behind the desktop icons the way live-wallpaper apps do it: Progman is asked to
create the WorkerW window that sits between the wallpaper and the icons, and a window showing the
sky becomes its child. Windows 11 24H2 moved the icons (SHELLDLL_DefView) and the WorkerW inside
Progman; there the sky becomes Progman's child, ordered just below the icons. That window is a
plain Win32 one (DesktopCanvas): a reparented GTK window never paints again. An invisible hit
layer over the icons takes the clicks on the sky's controls; the tray icon opens Settings too.
With click-through off, the GTK window itself sits over the icons, under every other window, and
takes every click.

Only imported on Windows.
"""

import ctypes
import os
import queue
import sys
import threading
import winreg
from concurrent.futures import Future
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32')

_GWL_STYLE, _GWL_EXSTYLE = -16, -20
_WS_CHILD, _WS_POPUP, _WS_VISIBLE = 0x40000000, 0x80000000, 0x10000000
_WS_EX_TOOLWINDOW, _WS_EX_NOACTIVATE, _WS_EX_APPWINDOW = 0x80, 0x08000000, 0x40000
_WS_EX_LAYERED, _LWA_ALPHA = 0x80000, 0x2
_SWP_NOSIZE, _SWP_NOMOVE, _SWP_NOZORDER = 0x1, 0x2, 0x4
_SWP_NOACTIVATE, _SWP_SHOWWINDOW, _SWP_FRAMECHANGED = 0x10, 0x40, 0x20
_HWND_TOP, _HWND_BOTTOM = 0, 1
_RGN_OR = 2
_GW_HWNDNEXT, _GW_HWNDPREV = 2, 3
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
        # Windows 11 24H2 and later ("raised desktop"): the icons and the wallpaper's WorkerW are
        # both Progman's children. The sky goes between them, the WorkerW at the bottom
        worker = user32.FindWindowExW(progman, None, 'WorkerW', None)
        if worker:
            user32.SetWindowPos(worker, _HWND_BOTTOM, 0, 0, 0, 0,
                                _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE)
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


def taskbar_edges(hwnd=None):
    """
    ((left, top, right, bottom) covered by the taskbar, width) of the primary monitor, or of the
    window `hwnd` when given: Windows may keep a window short of the screen (1024×749 on a
    1024×768 screen), so the margins are measured from its real edges.
    """
    info = _primary_info()
    m, w = info.rcMonitor, info.rcWork
    if hwnd:
        m = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(m))
    edges = (w.left - m.left, w.top - m.top, m.right - w.right, m.bottom - w.bottom)
    return tuple(max(0, e) for e in edges), m.right - m.left


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


def primary_size():
    """Primary monitor (width, height) in the pixels this process sees."""
    return _primary_rect()[2:]


def place_sky(hwnd):
    """The GTK sky window over the desktop icons, under every other window (click-through off,
    or no icon layer found). Only the position changes: GTK sizes the window and paints at the
    size it asked for. Never SetParent a GTK window: it stops painting for good."""
    x, y, _w, _h = _primary_rect()
    ex = user32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
    # Never in the taskbar or Alt+Tab, and a click doesn't raise it over the user's windows
    ex = (ex | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE) & ~_WS_EX_APPWINDOW
    user32.SetWindowLongPtrW(hwnd, _GWL_EXSTYLE, ex)
    _just_above_icons(hwnd, x, y, _SWP_NOSIZE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW | _SWP_FRAMECHANGED)
    _log(hwnd, 'over the icons')


# ─── The sky behind the icons ────────────────────────────────────────────────

_WM_ERASEBKGND = 0x0014
_SW_HIDE = 0
_WNDPROC = ctypes.WINFUNCTYPE(_LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                              wintypes.LPARAM)
user32.DefWindowProcW.restype = _LONG_PTR
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
class _GUID(ctypes.Structure):
    _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD),
                ('Data4', ctypes.c_ubyte * 8)]


class _DXGI_MODE_DESC(ctypes.Structure):
    _fields_ = [('Width', wintypes.UINT), ('Height', wintypes.UINT),
                ('RefreshNumerator', wintypes.UINT), ('RefreshDenominator', wintypes.UINT),
                ('Format', wintypes.UINT), ('ScanlineOrdering', wintypes.UINT),
                ('Scaling', wintypes.UINT)]


class _DXGI_SWAP_CHAIN_DESC(ctypes.Structure):
    _fields_ = [('BufferDesc', _DXGI_MODE_DESC), ('SampleCount', wintypes.UINT),
                ('SampleQuality', wintypes.UINT), ('BufferUsage', wintypes.UINT),
                ('BufferCount', wintypes.UINT), ('OutputWindow', wintypes.HWND),
                ('Windowed', wintypes.BOOL), ('SwapEffect', wintypes.UINT), ('Flags', wintypes.UINT)]


_IID_TEXTURE2D = _GUID(0x6f15aaf2, 0xd208, 0x4e89,
                       (ctypes.c_ubyte * 8)(0x9a, 0xb4, 0x48, 0x95, 0x35, 0xd3, 0x4f, 0x9c))


def _com(obj, index, *argtypes, restype=ctypes.HRESULT):
    """Method `index` of a COM object's vtable, as a callable taking the remaining arguments."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])
    return lambda *args: fn(obj, *args)


class _D3DPresenter:
    """
    A Direct3D 11 flip-model swap chain on a window: frames (BGRA, premultiplied: Cairo's ARGB32)
    are copied into the back buffer and presented. The raised desktop composites this, where
    pixels drawn with GDI never show. Hardware first, then WARP (software; no GPU needed).
    """
    def __init__(self, hwnd, w, h):
        d3d11 = ctypes.WinDLL('d3d11')
        desc = _DXGI_SWAP_CHAIN_DESC(
            BufferDesc=_DXGI_MODE_DESC(Width=w, Height=h, Format=87),   # B8G8R8A8_UNORM
            SampleCount=1, BufferUsage=0x20, BufferCount=2,            # render target output
            OutputWindow=hwnd, Windowed=True, SwapEffect=4)            # FLIP_DISCARD
        self._swap, self._dev, self._ctx = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        hr = 0
        for driver in (1, 5):   # D3D_DRIVER_TYPE_HARDWARE, _WARP
            hr = d3d11.D3D11CreateDeviceAndSwapChain(
                None, driver, None, 0x20, None, 0, 7, ctypes.byref(desc),   # BGRA support
                ctypes.byref(self._swap), ctypes.byref(self._dev), None, ctypes.byref(self._ctx))
            if hr >= 0:
                print(f"Caelum: Direct3D 11 swap chain ({'hardware' if driver == 1 else 'WARP'})",
                      file=sys.stderr, flush=True)
                break
        else:
            raise OSError(f'D3D11CreateDeviceAndSwapChain failed: {hr & 0xFFFFFFFF:#010x}')

    def present(self, data, stride):
        tex = ctypes.c_void_p()
        _com(self._swap, 9, wintypes.UINT, ctypes.POINTER(_GUID),           # GetBuffer
             ctypes.POINTER(ctypes.c_void_p))(0, ctypes.byref(_IID_TEXTURE2D), ctypes.byref(tex))
        try:
            _com(self._ctx, 48, ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p,  # UpdateSubresource
                 ctypes.c_char_p, wintypes.UINT, wintypes.UINT, restype=None)(
                tex, 0, None, data, stride, 0)
        finally:
            _com(tex, 2, restype=wintypes.ULONG)()                           # Release
        _com(self._swap, 8, wintypes.UINT, wintypes.UINT)(0, 0)              # Present, no wait

    def release(self):
        for obj in (self._ctx, self._swap, self._dev):
            if obj:
                _com(obj, 2, restype=wintypes.ULONG)()


_kernel32 = ctypes.WinDLL('kernel32')
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.UINT), ('style', wintypes.UINT), ('lpfnWndProc', _WNDPROC),
                ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON),
                ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HBRUSH),
                ('lpszMenuName', wintypes.LPCWSTR), ('lpszClassName', wintypes.LPCWSTR),
                ('hIconSm', wintypes.HICON)]


_QS_ALLINPUT, _PM_REMOVE, _INFINITE = 0x04FF, 0x0001, 0xFFFFFFFF
_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.SetEvent.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
user32.MsgWaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
                                             wintypes.BOOL, wintypes.DWORD, wintypes.DWORD]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                                wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]


class DesktopCanvas:
    """
    The sky behind the desktop icons, in plain Win32 windows (GTK can't be reparented). A layered
    host goes into the icon layer, created top-level and then made a child, as live-wallpaper
    apps do on the raised desktop; a child window inside it shows the frames, rendered off screen
    with Cairo, through a Direct3D swap chain (the raised desktop ignores GDI drawing there).

    These windows live on a thread of their own that only pumps their messages and presents the
    latest frame. A window inside Explorer's desktop ties Explorer's input to the thread that owns
    it: owned by the main thread, which renders the sky, it froze the whole desktop.
    """
    _CLASS = 'CaelumDesktopSky'

    def __init__(self):
        _x, _y, w, h = _primary_rect()
        self.size = (w, h)
        self._frame = None                    # latest (pixels, stride) not yet presented
        self._lock = threading.Lock()
        self._calls = queue.Queue()           # (function, Future) to run on the canvas thread
        self._wake = _kernel32.CreateEventW(None, False, False, None)
        self._error = False
        started = Future()
        threading.Thread(target=self._run, args=(started,), name='caelum-desktop',
                         daemon=True).start()
        started.result(timeout=10)            # raises what went wrong on the thread

    # ── Called from the main thread ──

    def place(self):
        """Behind the icons; False when there is no icon layer to go behind."""
        return self._call(self._place)

    def show(self, pixels, w, h, stride):
        """Hand over a frame (Cairo ARGB32 pixels, h rows of `stride` bytes); never waits."""
        if (w, h) != self.size:
            return
        with self._lock:
            self._frame = (bytes(pixels), stride)
        _kernel32.SetEvent(self._wake)

    def destroy(self):
        try:
            self._call(self._destroy, timeout=5)
        except Exception as e:
            print(f'Caelum: desktop canvas: {e}', file=sys.stderr, flush=True)

    def _call(self, fn, timeout=10):
        done = Future()
        self._calls.put((fn, done))
        _kernel32.SetEvent(self._wake)
        return done.result(timeout=timeout)

    # ── On the canvas thread ──

    def _run(self, started):
        try:
            self._create()
        except Exception as e:
            started.set_exception(e)
            return
        started.set_result(None)
        msg = wintypes.MSG()
        handles = (wintypes.HANDLE * 1)(self._wake)
        while True:
            user32.MsgWaitForMultipleObjects(1, handles, False, _INFINITE, _QS_ALLINPUT)
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, _PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            while not self._calls.empty():
                fn, done = self._calls.get_nowait()
                try:
                    done.set_result(fn())
                except Exception as e:
                    done.set_exception(e)
                if fn == self._destroy:
                    return
            with self._lock:
                frame, self._frame = self._frame, None
            if frame:
                self._present(*frame)

    def _create(self):
        self._proc = _WNDPROC(self._wndproc)    # keep a reference: Windows calls it
        hinst = _kernel32.GetModuleHandleW(None)
        wc = _WNDCLASSEXW(cbSize=ctypes.sizeof(_WNDCLASSEXW), lpfnWndProc=self._proc,
                          hInstance=hinst, lpszClassName=self._CLASS)
        user32.RegisterClassExW(ctypes.byref(wc))   # fails harmlessly if already registered
        x, y, w, h = _primary_rect()
        self.hwnd = user32.CreateWindowExW(_WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE | _WS_EX_LAYERED,
                                           self._CLASS, 'Caelum sky', _WS_POPUP,
                                           x, y, w, h, None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        user32.SetLayeredWindowAttributes(self.hwnd, 0, 255, _LWA_ALPHA)
        self._view = user32.CreateWindowExW(0, self._CLASS, 'Caelum sky view',
                                            _WS_CHILD | _WS_VISIBLE, 0, 0, w, h,
                                            self.hwnd, None, hinst, None)
        if not self._view:
            raise ctypes.WinError(ctypes.get_last_error())
        self._d3d = _D3DPresenter(self._view, w, h)

    def _place(self):
        layer = _icon_layer()
        if not layer:
            return False
        parent, below = layer
        x, y, w, h = _primary_rect()
        user32.SetParent(self.hwnd, parent)
        style = user32.GetWindowLongPtrW(self.hwnd, _GWL_STYLE)
        user32.SetWindowLongPtrW(self.hwnd, _GWL_STYLE, (style | _WS_CHILD) & ~_WS_POPUP)
        x -= user32.GetSystemMetrics(_SM_XVIRTUALSCREEN)
        y -= user32.GetSystemMetrics(_SM_YVIRTUALSCREEN)
        # In Progman: just below the icons; in an older Windows' WorkerW: on top of its children
        user32.SetWindowPos(self.hwnd, below or _HWND_TOP, x, y, w, h,
                            _SWP_NOACTIVATE | _SWP_SHOWWINDOW | _SWP_FRAMECHANGED)
        _log(self.hwnd, 'behind the icons (in Progman, below the icons)' if below
             else 'behind the icons (in the WorkerW)')
        self._log_neighbours()
        return True

    def _log_neighbours(self):
        """For bug reports: the canvas's styles and the windows just above and below it."""
        names = []
        for rel in (_GW_HWNDPREV, _GW_HWNDNEXT):
            other = user32.GetWindow(self.hwnd, rel)
            buf = ctypes.create_unicode_buffer(64)
            if other:
                user32.GetClassNameW(other, buf, len(buf))
            names.append(buf.value or 'none')
        ex = user32.GetWindowLongPtrW(self.hwnd, _GWL_EXSTYLE)
        style = user32.GetWindowLongPtrW(self.hwnd, _GWL_STYLE)
        print(f'Caelum: desktop canvas: above it {names[0]}, below it {names[1]}; '
              f'style {style & 0xFFFFFFFF:#010x}, exstyle {ex & 0xFFFFFFFF:#010x}',
              file=sys.stderr, flush=True)

    def _present(self, data, stride):
        try:
            self._d3d.present(data, stride)
        except OSError as e:
            if not self._error:
                self._error = True    # once: the log would fill up 10 times a second
                print(f'Caelum: desktop canvas: {e}', file=sys.stderr, flush=True)

    def _destroy(self):
        user32.ShowWindow(self.hwnd, _SW_HIDE)
        self._d3d.release()
        user32.DestroyWindow(self.hwnd)
        _kernel32.CloseHandle(self._wake)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == _WM_ERASEBKGND:
            return 1      # Direct3D covers everything: no flash of the class brush
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


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
