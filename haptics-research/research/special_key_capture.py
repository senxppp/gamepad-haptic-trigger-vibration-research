# -*- coding: utf-8 -*-
"""特殊按键捕获：监听 k5 全部 HID 接口的输入报文，找出特殊键的字节特征。"""
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import hid as hidapi

DUR = 30
DURATION_NOTICE = 3

# 收集 k5 的所有 HID 接口（排除虚拟 DS）
targets = []
for d in hidapi.enumerate():
    if d["vendor_id"] == 0x37d7:
        p = d["path"]
        targets.append((d, p if isinstance(p, bytes) else p.encode()))
print(f"k5 HID 接口共 {len(targets)} 个：", flush=True)
for d, _ in targets:
    print(f"  MI? usage_page={d['usage_page']:#06x} usage={d['usage']:#04x} col={d['path'][-40:-30]}", flush=True)

states = {}       # path -> last report bytes
hits = []         # (time, path, hex)
lock = threading.Lock()
stop = threading.Event()


def reader(path, tag):
    try:
        dev = hidapi.device()
        dev.open_path(path)
        dev.set_nonblocking(True)
    except Exception as e:
        print(f"  [{tag}] 打开失败: {e}", flush=True)
        return
    while not stop.is_set():
        data = dev.read(64)
        if data:
            b = bytes(data)
            with lock:
                prev = states.get(tag)
                if prev != b:
                    states[tag] = b
                    hits.append((time.time(), tag, b))
        time.sleep(0.002)


threads = []
for i, (d, p) in enumerate(targets):
    t = threading.Thread(target=reader, args=(p, f"接口{i}(up={d['usage_page']:#x},u={d['usage']:#04x})"),
                         daemon=True)
    t.start()
    threads.append(t)
    time.sleep(0.05)

print(f"\n{DURATION_NOTICE} 秒后开始捕获 {DUR} 秒——请现在连续按那个特殊键（别的什么都别按）！", flush=True)
time.sleep(DURATION_NOTICE)
t_cap = time.time()
while time.time() - t_cap < DUR:
    time.sleep(0.2)
    with lock:
        recent = [h for h in hits if h[0] > t_cap]
    if recent:
        pass  # 安静收集
stop.set()
time.sleep(0.3)

with lock:
    recent = [h for h in hits if h[0] > t_cap]
print(f"\n=== 捕获到 {len(recent)} 条变化 ===", flush=True)
from collections import defaultdict
by_iface = defaultdict(list)
for t, tag, b in recent:
    by_iface[tag].append(b)
for tag, reports in by_iface.items():
    uniq = []
    seen = set()
    for b in reports:
        h = b.hex()
        if h not in seen:
            seen.add(h)
            uniq.append(h)
    print(f"\n[{tag}] {len(reports)} 次变化，{len(uniq)} 种报文：", flush=True)
    for h in uniq[:12]:
        print("   ", h, flush=True)
print("\nCAPTURE_DONE", flush=True)
