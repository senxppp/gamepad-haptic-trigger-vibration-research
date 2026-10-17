# -*- coding: utf-8 -*-
"""按键位标定捕获：使能原始流，监控 EF 帧按键区变化，按顺序按键即可。"""
import ctypes
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import hid as hidapi

kernel32 = ctypes.WinDLL("kernel32")
M32 = 0xFFFFFFFF

path = None
for d in hidapi.enumerate():
    if d["vendor_id"] == 0x37d7 and d["usage_page"] == 0xFFA0:
        p = d["path"]
        path = p if isinstance(p, bytes) else p.encode()
assert path, "0xFFA0 未找到"

h = kernel32.CreateFileA(path, 0xC0000000, 3, None, 3, 0, None)
written = ctypes.c_uint32(0)


def crc(buf, start, end):
    return sum(buf[start:end]) & 0xFF


def send_enable():
    rep = bytearray(32)
    rep[0] = 0x03; rep[1] = 0x5A; rep[2] = 0xA5; rep[3] = 0x11; rep[4] = 0x07
    rep[5] = 1; rep[6] = 1; rep[7] = 1; rep[8] = 1; rep[9] = 255
    rep[10] = crc(rep, 3, 3 + rep[4])
    return kernel32.WriteFile(h, bytes(rep), 32, ctypes.byref(written), None)


FILE_FLAG_OVERLAPPED = 0x40000000
GENERIC_READ = 0x80000000
h2 = kernel32.CreateFileA(path, GENERIC_READ, 3, None, 3, FILE_FLAG_OVERLAPPED, None)


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", ctypes.c_uint32), ("OffsetHigh", ctypes.c_uint32),
                ("hEvent", ctypes.c_void_p)]


buf = (ctypes.c_ubyte * 64)()
ov = OVERLAPPED()
ov.hEvent = kernel32.CreateEventA(None, True, False, None)

print("使能原始流:", send_enable(), flush=True)
time.sleep(0.5)
send_enable()
time.sleep(0.5)
send_enable()

print("""
=== 按键位标定开始（运行 8 分钟）===
请按这个顺序按，每个按 1 秒、间隔 1 秒：
  A → B → X → Y → LB → RB → LS(按左摇杆) → RS(按右摇杆)
  → BACK → START → 十字上 → 十字下 → 十字左 → 十字右 → LT扣满 → RT扣满
""", flush=True)

prev = None
t0 = time.time()
log = []
while time.time() - t0 < 480:
    ok = kernel32.ReadFile(h2, buf, 64, None, ctypes.byref(ov))
    err = kernel32.GetLastError()
    n_got = 0
    if ok == 0 and err == 997:
        kernel32.WaitForSingleObject(ov.hEvent, 100)
        got = ctypes.c_uint32(0)
        kernel32.GetOverlappedResult(h2, ctypes.byref(ov), ctypes.byref(got), False)
        n_got = got.value
    elif ok:
        n_got = 64
    else:
        kernel32.CancelIo(h2)
        time.sleep(0.005)
        continue
    if n_got >= 22:
        frame = bytes(buf[:n_got])
        if frame[1] == 0x5A and frame[2] == 0xA5 and frame[3] == 0xEF:
            state = frame[4:16]   # 按键区 12 字节（排除陀螺仪 [16..21]，否则全是抖动噪声）
            if state != prev:
                ts = time.strftime("%H:%M:%S")
                changed = [(i, hex(b)) for i, b in enumerate(state)
                           if prev is None or b != prev[i]]
                print(f"[{ts}] {'首帧' if prev is None else '变化'} @字节{changed}: {state.hex()}", flush=True)
                log.append((ts, state.hex()))
                prev = state
    else:
        kernel32.CancelIo(h2)
        time.sleep(0.005)

with open(r"C:/Users/xpppj/.zcode/workspace/default/research/bitmap_log.txt", "w", encoding="utf-8") as f:
    for ts, hx in log:
        f.write(f"{ts} {hx}\n")
print(f"标定捕获结束，{len(log)} 条状态记录已存 bitmap_log.txt", flush=True)
kernel32.CloseHandle(h); kernel32.CloseHandle(h2)
