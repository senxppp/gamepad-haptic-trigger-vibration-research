# -*- coding: utf-8 -*-
"""按键位标定分析：bitmap_log.txt → 按键名 ↔ (字节偏移, 位掩码) 对照表。"""
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ORDER = ["A", "B", "X", "Y", "LB", "RB", "L3", "R3",
         "BACK", "START", "十字上", "十字下", "十字左", "十字右", "LT", "RT"]

lines = []
for ln in open(r"C:/Users/xpppj/.zcode/workspace/default/research/bitmap_log.txt",
               encoding="utf-8"):
    parts = ln.split()
    if len(parts) == 2:
        lines.append((parts[0], bytes.fromhex(parts[1])))
print(f"日志 {len(lines)} 条状态记录", flush=True)

if not lines:
    print("空日志"); sys.exit(1)

# 基线 = 最常见状态（空闲）
cnt = Counter(s for _, s in lines)
baseline = cnt.most_common(1)[0][0]
print(f"空闲基线: {baseline.hex()}", flush=True)

# 聚类：从基线离开 → 变化期间 → 回到基线 = 一个按键事件
events = []
cur = None
for ts, s in lines:
    if s == baseline:
        if cur:
            events.append(cur)
            cur = None
    else:
        if cur is None:
            cur = {"states": [], "t0": ts}
        cur["states"].append(s)
        cur["t1"] = ts
if cur:
    events.append(cur)
print(f"识别出 {len(events)} 个按键事件（期望 16）\n", flush=True)

# 每个事件：找与基线不同的字节/位
table = []
for i, ev in enumerate(events[:len(ORDER)]):
    name = ORDER[i] if i < len(ORDER) else f"事件{i+1}"
    bits = {}
    for s in ev["states"]:
        for bi in range(len(baseline)):
            if s[bi] != baseline[bi]:
                d = s[bi] ^ baseline[bi]
                for bit in range(8):
                    if d & (1 << bit):
                        bits[(bi, bit)] = bits.get((bi, bit), 0) + 1
    # 按出现次数排序
    ranked = sorted(bits.items(), key=lambda kv: -kv[1])
    top = [(f"字节[{bi}].bit{bt}", c) for (bi, bt), c in ranked[:3]]
    # 模拟量（某字节=固定值而非位）
    valset = set(s[bi] for s in ev["states"] for bi in range(len(baseline))
                 if s[bi] != baseline[bi])
    table.append((name, top, valset))
    print(f"{name:8} → 位变化: {top}  |  变化字节值域: {sorted(hex(v) for v in valset)}", flush=True)

print("\n=== 对照表 ===", flush=True)
for name, top, vals in table:
    print(f"{name:8} : {top}", flush=True)
