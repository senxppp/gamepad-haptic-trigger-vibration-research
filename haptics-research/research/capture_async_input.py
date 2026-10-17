# -*- coding: utf-8 -*-
"""异步 ReadFile 捕获 k5 Col01 原始输入流（APEXtoDS 同款读法）。"""
import ctypes
import sys
import time
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import hid as hidapi

kernel32 = ctypes.WinDLL("kernel32")

path = None
for d in hidapi.enumerate():
    if d["vendor_id"] == 0x37d7 and d["usage_page"] == 0xFFA0:
        p = d["path"]
        path = p if isinstance(p, bytes) else p.encode()
assert path, "0xFFA0 未找到"

GENERIC_READ = 0x80000000
FILE_FLAG_OVERLAPPED = 0x40000000
h = kernel32.CreateFileA(path, GENERIC_READ, 3, None, 3,
                         FILE_FLAG_OVERLAPPED, None)
assert h not in (-1, 0xFFFFFFFFFFFFFFFF), "异步打开失败"


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", ctypes.c_uint32), ("OffsetHigh", ctypes.c_uint32),
                ("hEvent", ctypes.c_void_p)]


buf = (ctypes.c_ubyte * 64)()
ov = OVERLAPPED()
ev = kernel32.CreateEventA(None, True, False, None)
ov.hEvent = ev

frames = Counter()
t0 = time.time()
n = 0
print("异步捕获 15 秒...", flush=True)
while time.time() - t0 < 15:
    ok = kernel32.ReadFile(h, buf, 64, None, ctypes.byref(ov))
    err = kernel32.GetLastError()
    if ok == 0 and err == 997:   # ERROR_IO_PENDING
        kernel32.WaitForSingleObject(ev, 100)
        got = ctypes.c_uint32(0)
        kernel32.GetOverlappedResult(h, ctypes.byref(ov), ctypes.byref(got), False)
        n_got = got.value
    elif ok:
        n_got = 64
    else:
        time.sleep(0.01)
        continue
    if n_got:
        frame = bytes(buf[:n_got])
        frames[frame] += 1
        n += 1
    else:
        kernel32.CancelIo(h)
        time.sleep(0.005)

kernel32.CloseHandle(h)
print(f"\n捕获 {n} 帧，{len(frames)} 种。Top 10：", flush=True)
for frame, cnt in frames.most_common(10):
    print(f"  ×{cnt:5d}  [{len(frame)}B] {frame.hex()}", flush=True)
print("CAPTURE_DONE", flush=True)
