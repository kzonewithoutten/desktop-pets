import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

LVM_GETITEMCOUNT = 0x1004
LVM_GETITEMRECT = 0x100E
LVIR_ICON = 1

user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.VirtualAllocEx.restype = ctypes.c_void_p
kernel32.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
kernel32.VirtualFreeEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
kernel32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                        ctypes.POINTER(ctypes.c_size_t)]
kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                       ctypes.POINTER(ctypes.c_size_t)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _find_listview():
    progman = user32.FindWindowW("Progman", None)
    shell = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
    worker = None
    while not shell:
        worker = user32.FindWindowExW(None, worker, "WorkerW", None)
        if not worker:
            return None
        shell = user32.FindWindowExW(worker, None, "SHELLDLL_DefView", None)
    return user32.FindWindowExW(shell, None, "SysListView32", None)


def _scale():
    try:
        gdi32 = ctypes.windll.gdi32
        hdc = user32.GetDC(None)
        real = gdi32.GetDeviceCaps(hdc, 118)
        user32.ReleaseDC(None, hdc)
        seen = user32.GetSystemMetrics(0)
        return seen / real if real else 1.0
    except Exception:
        return 1.0


def icon_rects(max_icons=300):
    k = _scale()
    rects = _raw_icon_rects(max_icons)
    if abs(k - 1) < 0.01:
        return rects
    return [tuple(round(v * k) for v in r) for r in rects]


def _raw_icon_rects(max_icons):
    lv = _find_listview()
    if not lv or not user32.IsWindowVisible(lv):
        return []
    count = min(user32.SendMessageW(lv, LVM_GETITEMCOUNT, 0, 0), max_icons)
    if count <= 0:
        return []
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(lv, ctypes.byref(pid))
    proc = kernel32.OpenProcess(0x0008 | 0x0010 | 0x0020 | 0x0400, False, pid.value)
    if not proc:
        return []
    out = []
    remote = kernel32.VirtualAllocEx(proc, None, ctypes.sizeof(wintypes.RECT), 0x1000 | 0x2000, 0x04)
    try:
        if not remote:
            return []
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(lv, ctypes.byref(origin))
        for i in range(count):
            rect = wintypes.RECT(LVIR_ICON, 0, 0, 0)
            kernel32.WriteProcessMemory(proc, remote, ctypes.byref(rect), ctypes.sizeof(rect), None)
            if not user32.SendMessageW(lv, LVM_GETITEMRECT, i, remote):
                continue
            kernel32.ReadProcessMemory(proc, remote, ctypes.byref(rect), ctypes.sizeof(rect), None)
            if rect.right > rect.left and rect.bottom > rect.top:
                out.append((rect.left + origin.x, rect.top + origin.y, rect.right + origin.x, rect.bottom + origin.y))
    finally:
        if remote:
            kernel32.VirtualFreeEx(proc, remote, 0, 0x8000)
        kernel32.CloseHandle(proc)
    return out


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    r = icon_rects()
    print(len(r), r[:8])
