"""窗口隐藏到托盘后把工作集归还系统（后台常驻时降低物理内存占用；显示后按需换回）。

只影响「工作集」统计（页面转入待机/压缩内存），不改数据、不改功能行为；
延迟期间窗口重新显示会取消未执行的归还。目标 = 本进程 + WebView2 子进程树
（用户机器 16G 内存偏紧，后台常驻的 Chromium 子树是最大可回收项）。

用法（desktop.py 注入）：
    mem_trim.schedule_trim()   窗口隐藏到托盘时调用（延迟 TRIM_DELAY 秒执行）
    mem_trim.cancel_trim()     窗口重新显示时调用
"""
import ctypes
import logging
import os
import threading
from ctypes import wintypes

log = logging.getLogger("workbench")

TRIM_DELAY = 60.0

_lock = threading.Lock()
_timer = None

_psapi = ctypes.WinDLL("psapi")
_psapi.EmptyWorkingSet.argtypes = [ctypes.c_void_p]
_psapi.EmptyWorkingSet.restype = ctypes.c_int
_kernel32 = ctypes.WinDLL("kernel32")
_kernel32.GetCurrentProcess.restype = ctypes.c_void_p
_kernel32.OpenProcess.restype = ctypes.c_void_p
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
_kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

_INVALID_HANDLE = ctypes.c_void_p(-1).value
_TH32CS_SNAPPROCESS = 0x00000002
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_QUERY_INFORMATION = 0x0400


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def _processes():
    """系统进程快照 [(pid, ppid, exe)]；失败返回 []。"""
    snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snap or snap in (_INVALID_HANDLE, -1):
        return []
    out = []
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = _kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((int(e.th32ProcessID), int(e.th32ParentProcessID), e.szExeFile))
            ok = _kernel32.Process32NextW(snap, ctypes.byref(e))
    except Exception:
        pass
    finally:
        _kernel32.CloseHandle(snap)
    return out


def _browser_descendants():
    """本进程的 WebView2 子进程 PID 列表（沿父子树查找，含孙代）。"""
    procs = _processes()
    children = {}
    for pid, ppid, name in procs:
        children.setdefault(ppid, []).append((pid, name))
    me = os.getpid()
    seen = set()
    stack = [me]
    found = []
    while stack:
        cur = stack.pop()
        for pid, name in children.get(cur, []):
            if pid in seen:
                continue
            seen.add(pid)
            stack.append(pid)
            if "msedgewebview2" in (name or "").lower():
                found.append(pid)
    return found


def trim_now(include_self: bool = True) -> dict:
    """把自身 + WebView2 子进程的工作集归还系统。返回 {self, children} 统计。"""
    out = {"self": False, "children": 0}
    if include_self:
        try:
            out["self"] = bool(_psapi.EmptyWorkingSet(_kernel32.GetCurrentProcess()))
        except Exception:
            pass
    for pid in _browser_descendants():
        h = _kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_QUERY_INFORMATION, False, pid)
        if not h:
            continue
        try:
            if _psapi.EmptyWorkingSet(h):
                out["children"] += 1
        except Exception:
            pass
        finally:
            _kernel32.CloseHandle(h)
    return out


def _fire():
    global _timer
    with _lock:
        _timer = None
    try:
        res = trim_now()
        log.info("mem-trim: %s", res)
    except Exception as e:
        log.warning("mem-trim failed: %s", e)


def schedule_trim(delay: float = TRIM_DELAY) -> bool:
    """窗口隐藏到托盘后调用：延迟归还内存；重复调用重置计时。"""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(delay, _fire)
        _timer.daemon = True
        t = _timer
    t.start()
    return True


def cancel_trim() -> bool:
    """窗口重新显示时调用：取消未执行的归还。"""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
    return True
