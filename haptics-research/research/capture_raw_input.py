# -*- coding: utf-8 -*-
"""捕获八爪鱼5 的原始输入流（Col01 读方向，report 0x04），统计帧结构。"""
import ctypes
import sys
import time
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import hid as hidapi

hiddll = ctypes.WinDLL("hid")
kernel32 = ctypes.WinDLL("kernel32")

path = None
for d in hidapi.enumerate():
    if d["vendor_id"] == 0x37d7 and d["usage_page"] == 0xFFA0:
        p = d["path"]
        path = p if isinstance(p, bytes) else p.encode()
assert path, "0xFFA0 未找到"
h = kernel32.CreateFileA(path, 0xC0000000, 3, None, 3, 0, None)
assert h not in (-1, 0xFFFFFFFFFFFFFFFF), "打开失败"

GENERIC_READ = 0x80000000
h2 = kernel32.CreateFileA(path, GENERIC_READ, 3, None, 3, 0, None)
read_handle = h2 if h2 not in (-1, 0xFFFFFFFFFFFFFFFF) else h

def get_input(rid=0x04, size=32):
    buf = (ctypes.c_ubyte * (size + 1))()
    buf[0] = rid
    ok = hiddll.HidD_GetInputReport(read_handle, ctypes.byref(buf), size + 1)
    return (bytes(buf[1:size + 1]), ok)

print("捕获 20 秒 Col01 输入报文（GetInputReport 0x04 @200Hz）...", flush=True)
seen = Counter()
t0 = time.time()
n = 0
while time.time() - t0 < 20:
    data, ok = get_input()
    if ok:
        n += 1
        seen[data] += 1
    time.sleep(0.005)

print(f"\n读取 {n} 次，{len(seen)} 种不同报文。Top 12：", flush=True)
for frame, cnt in seen.most_common(12):
    print(f"  ×{cnt:4d}  {frame.hex()}", flush=True)

# cmdId 分布（假设帧头 5A A5）
print("\ncmdId 分布（frame[1:3]==5A A5 的帧）：", flush=True)
cc = Counter()
for frame, cnt in seen.items():
    if len(frame) >= 3 and frame[0] == 0x5A and frame[1] == 0xA5:
        cc[frame[2]] += cnt
    else:
        cc["非5AA5帧"] += cnt
for k, v in cc.most_common():
    print(f"  cmdId={k if isinstance(k, str) else hex(k)}: {v}", flush=True)
kernel32.CloseHandle(h); kernel32.CloseHandle(read_handle)
print("CAPTURE_DONE", flush=True)
