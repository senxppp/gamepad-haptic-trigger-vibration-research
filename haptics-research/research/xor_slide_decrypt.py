# -*- coding: utf-8 -*-
"""滑动解密器：对每个 (seed,len) 循环，全数据段滑动找可读明文位置。"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np

DIS = r"C:/Users/xpppj/.zcode/workspace/default/research/apextods_v0511/dis_full.txt"
ORIG = r"C:/Users/xpppj/.zcode/workspace/default/research/apextods_v0511/APEXtoDS/APEXtoDS.exe"
M32 = 0xFFFFFFFF
raw = open(ORIG, "rb").read()


def keystream(seed, n, variant):
    ks = bytearray()
    for i in range(n):
        x = (seed - i * 0x61C88647) & M32
        h = (x >> 15) ^ x
        y = (h * 0x85EBCA6B) & M32
        mixed = ((y >> 13) ^ y) & M32
        ks.append(mixed & 0xFF)             # lo8(mix)=lo8((y>>13)^y) —— 隔离测试验证
    return bytes(ks)


# 可打印查找表（含 \t \n \r）
TBL = np.zeros(256, dtype=bool)
for c in range(256):
    TBL[c] = (0x20 <= c < 0x7F) or c in (0, 9, 10, 13)   # 0 = 字符串终止符，允许
# 中文区（UTF-8 首字节 0xE0-0xEF、续字节 0x80-0xBF）单独宽松处理：先按“全 ASCII 可打印”找，
# 再把“含高字节的候选”解码验证。

data = np.frombuffer(raw, dtype=np.uint8)
N = len(data)

lines = open(DIS, encoding="utf-8", errors="replace").read().splitlines()
imul_re = re.compile(r"imul\s+\w+,\w+,0x61c88647")
seed_re = re.compile(r"\bmov\s+e\w+,0x([0-9a-f]{6,8})\b")
cnt_re = re.compile(r"\bcmp\s+r\w+,0x([0-9a-f]+)\b")
func_re = re.compile(r"^[0-9a-f]{9,16} <(.+)>:")
func_of = {}
cur = "?"
for i, ln in enumerate(lines):
    fm = func_re.match(ln)
    if fm:
        cur = fm.group(1)
    func_of[i] = cur

loops = [i for i, ln in enumerate(lines) if imul_re.search(ln)]
print(f"共 {len(loops)} 个循环", flush=True)

results = []
for li in loops:
    win = lines[li: li + 50]
    seed = None
    for ln in win[:5]:
        m = seed_re.search(ln)
        if m:
            seed = int(m.group(1), 16)
            break
    ln_len = None
    for ln in win:
        m = cnt_re.search(ln)
        if m:
            v = int(m.group(1), 16)
            if 2 <= v <= 300:
                ln_len = v
                break
    if seed is None or ln_len is None:
        print(f"[{func_of[li]}] @{li}: seed={seed and hex(seed)} len={ln_len} → 缺参数，跳过", flush=True)
        continue
    ks = np.frombuffer(keystream(seed, ln_len, 0), dtype=np.uint8)
    found = []
    for variant in (0, 1):
        if variant == 1 and variant != 0:
            ks = np.frombuffer(keystream(seed, ln_len, 1), dtype=np.uint8)
        mask = np.ones(N - ln_len + 1, dtype=bool)
        for i in range(ln_len):
            mask[: N - ln_len] &= TBL[data[i: i + (N - ln_len)] ^ ks[i]]
            if not mask.any():
                break
        for off in np.nonzero(mask)[0][:8]:
            dec = bytes(int(x) ^ k for x, k in zip(data[off:off + ln_len], ks))
            found.append((variant, int(off), dec))
        if found:
            break   # variant0 有结果就不试 variant1
    tag = f"[{func_of[li]}] seed={seed:#x} len={ln_len}"
    if found:
        for v, off, dec in found[:3]:
            results.append((tag, v, off, dec))
        print(f"  {tag}: {len(found)} 处命中，如 @{found[0][1]:#x} → {found[0][2][:60]!r}", flush=True)
    else:
        print(f"  {tag}: 无命中", flush=True)

print(f"\n=== 总命中 {len(results)} ===", flush=True)
