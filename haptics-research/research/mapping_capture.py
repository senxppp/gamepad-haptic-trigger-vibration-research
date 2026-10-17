# -*- coding: utf-8 -*-
"""映射校验捕获：k5 XInput 源 vs 虚拟 DS HID 报文，逐项对照输出。"""
import ctypes
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---- 虚拟 DS HID ----
import hid as hidapi
ds_path = None
for d in hidapi.enumerate():
    if d["vendor_id"] == 0x054c and d["usage_page"] == 1 and d["usage"] == 5:
        p = d["path"]
        ds_path = p if isinstance(p, bytes) else p.encode()
        break
assert ds_path, "虚拟 DS 未枚举（守护进程在跑吗？）"
ds = hidapi.device()
ds.open_path(ds_path)
ds.set_nonblocking(True)

# ---- k5 XInput ----
xinput = ctypes.WinDLL("xinput1_4")


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("wButtons", ctypes.c_uint16),
                ("sThumbLX", ctypes.c_int16), ("sThumbLY", ctypes.c_int16),
                ("sThumbRX", ctypes.c_int16), ("sThumbRY", ctypes.c_int16),
                ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte)]


xinput.XInputGetState.argtypes = [ctypes.c_uint32, ctypes.POINTER(XINPUT_STATE)]

K5_BTN = {0x1000: "A", 0x2000: "B", 0x4000: "X", 0x8000: "Y",
          0x0100: "LB", 0x0200: "RB", 0x0080: "LS", 0x0040: "RS",
          0x0010: "BACK", 0x0020: "START",
          0x0001: "十字上", 0x0002: "十字下", 0x0004: "十字左", 0x0008: "十字右"}
BTN_NAME = {0x0010: "方块", 0x0020: "叉", 0x0040: "圆", 0x0080: "三角",
            0x0100: "L1", 0x0200: "R1", 0x0400: "L2键", 0x0800: "R2键",
            0x1000: "CREATE", 0x2000: "OPTIONS", 0x4000: "L3", 0x8000: "R3"}
DP_NAME = {1: "上", 2: "下", 4: "左", 8: "右", 3: "右上", 6: "右下", 9: "左上", 12: "左下"}


def stick_name(lx, ly):
    if abs(lx) < 40 and abs(ly) < 40:
        return ""
    d = []
    if ly > 40: d.append("上")
    if ly < -40: d.append("下")
    if lx > 40: d.append("右")
    if lx < -40: d.append("左")
    return "".join(d)


def describe_k5(st):
    parts = [n for m, n in K5_BTN.items() if st.wButtons & m]
    ls = stick_name(st.sThumbLX, st.sThumbLY)
    rs = stick_name(st.sThumbRX, st.sThumbRY)
    if ls: parts.append(f"左摇杆{ls}")
    if rs: parts.append(f"右摇杆{rs}")
    if st.bLeftTrigger: parts.append(f"LT={st.bLeftTrigger}")
    if st.bRightTrigger: parts.append(f"RT={st.bRightTrigger}")
    return " ".join(parts) if parts else "（无输入）"


def describe_ds(b):
    lx, ly, rx, ry = b[1], b[2], b[3], b[4]
    btns = (b[8] & 0xF0) | (b[9] << 8) | (b[10] << 16)
    dp = b[8] & 0x0F
    parts = [n for bit, n in BTN_NAME.items() if btns & bit]
    dp_names = {0: "上", 1: "右上", 2: "右", 3: "右下", 4: "下", 5: "左下", 6: "左", 7: "左上", 8: ""}
    if dp in dp_names and dp != 8:
        parts.append(f"十字{dp_names[dp]}")
    lsn = "上" if ly < 118 else ("下" if ly > 138 else "")
    lsn += "" if not lsn else ""
    lx_d = "右" if lx > 138 else ("左" if lx < 118 else "")
    rs_ = "上" if ry < 118 else ("下" if ry > 138 else "")
    rsd = "右" if rx > 138 else ("左" if rx < 118 else "")
    if lsn or lx_d: parts.append(f"左摇杆{lsn}{lx_d}")
    if rs_ or rsd: parts.append(f"右摇杆{rs_}{rsd}")
    if b[5]: parts.append(f"L2={b[5]}")
    if b[6]: parts.append(f"R2={b[6]}")
    return " ".join(parts) if parts else "（全零）"


print("开始捕获 75 秒——请逐个操作：按键→摇杆→十字键→扳机", flush=True)
last_sig = None
t0 = time.perf_counter()
n = 0
while time.perf_counter() - t0 < 75:
    st = XINPUT_STATE()
    k5s = ""
    for idx in range(4):
        if xinput.XInputGetState(idx, ctypes.byref(st)) == 0:
            k5s = describe_k5(st)
            break
    rep = ds.read(64)
    dss = ""
    if rep and len(rep) >= 11 and rep[0] == 1:
        dss = describe_ds(rep)
    sig = (k5s, dss)
    if sig != last_sig and (k5s != "（无输入）" or dss != "（全零）"):
        print(f"[{time.strftime('%H:%M:%S')}] k5: {k5s}  ⇄  DS: {dss}", flush=True)
        last_sig = sig
        n += 1
    time.sleep(0.01)
print(f"捕获结束，共 {n} 条变化记录。", flush=True)
