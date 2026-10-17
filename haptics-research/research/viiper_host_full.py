# -*- coding: utf-8 -*-
"""阶段2：全双工宿主。
- 虚拟 DS 输出回调 → 转发 k5 握把
- k5 XInput 输入 → 喂虚拟 DS
- 5 秒后模拟游戏写一条 0x31 震动报文到虚拟 DS（全链路自测）
"""
import ctypes
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\xpppj\.zcode\workspace\default\flydigi-haptic-middleware\vib_out")
from flydigi_vib import FlydigiVibration  # noqa: E402

DLL_PATH = r"C:\Users\xpppj\.zcode\workspace\default\research\apextods\APEXtoDS\libVIIPER.dll"


class USBServerConfig(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_char_p),
                ("connection_timeout_ms", ctypes.c_uint64),
                ("device_handler_connect_timeout_ms", ctypes.c_uint64),
                ("write_batch_flush_interval_ms", ctypes.c_uint32)]


class DSDeviceState(ctypes.Structure):
    _fields_ = [("LX", ctypes.c_int8), ("LY", ctypes.c_int8),
                ("RX", ctypes.c_int8), ("RY", ctypes.c_int8),
                ("Buttons", ctypes.c_uint32), ("DPad", ctypes.c_uint8),
                ("L2", ctypes.c_uint8), ("R2", ctypes.c_uint8),
                ("Touch1X", ctypes.c_uint16), ("Touch1Y", ctypes.c_uint16),
                ("Touch1Active", ctypes.c_bool),
                ("Touch2X", ctypes.c_uint16), ("Touch2Y", ctypes.c_uint16),
                ("Touch2Active", ctypes.c_bool),
                ("GyroX", ctypes.c_int16), ("GyroY", ctypes.c_int16),
                ("GyroZ", ctypes.c_int16),
                ("AccelX", ctypes.c_int16), ("AccelY", ctypes.c_int16),
                ("AccelZ", ctypes.c_int16)]


LOGCB = ctypes.WINFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)
OUTCB = ctypes.WINFUNCTYPE(None, ctypes.c_size_t,
                           ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ubyte,
                           ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ubyte)

dll = ctypes.CDLL(DLL_PATH)
dll.NewUSBServer.argtypes = [ctypes.POINTER(USBServerConfig), ctypes.POINTER(ctypes.c_size_t), LOGCB]
dll.CreateUSBBus.argtypes = [ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint32)]
dll.CreateDualSenseDevice.argtypes = [ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
                                      ctypes.c_uint32, ctypes.c_bool,
                                      ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
dll.SetDualSenseOutputCallback.argtypes = [ctypes.c_size_t, OUTCB]
dll.SetDualSenseDeviceState.argtypes = [ctypes.c_size_t, DSDeviceState]

k5 = FlydigiVibration()
k5.open()
print("✓ k5 握把直发通道已开", flush=True)

hits = []


@OUTCB
def on_output(handle, rs, rl, r, g, b, pl):
    hits.append((rs, rl))
    print(f"  ◄ 游戏输出: 小马达={rs} 大马达={rl} LED=({r},{g},{b}) 玩家灯={pl}", flush=True)
    if rs or rl:
        k5.set(rs, rl)   # 直通 k5 握把


cfg = USBServerConfig(b"0.0.0.0:3241", 30000, 5000, 1)
server = ctypes.c_size_t(0)
bus = ctypes.c_uint32(0)
dev = ctypes.c_size_t(0)
assert dll.NewUSBServer(ctypes.byref(cfg), ctypes.byref(server), ctypes.cast(None, LOGCB))
assert dll.CreateUSBBus(server, ctypes.byref(bus))
assert dll.CreateDualSenseDevice(server, ctypes.byref(dev), bus, True, 0, 0, None)
print(f"✓ 虚拟 DS 已创建 server={server.value:#x} bus={bus.value} ds={dev.value:#x}", flush=True)

ok_cb = dll.SetDualSenseOutputCallback(dev, on_output)
print(f"✓ 输出回调注册: {ok_cb}", flush=True)

# ---- 找虚拟 DS 的 HID（写测试报文用）----
import hid
ds_path = None
for _ in range(10):
    for d in hid.enumerate():
        if d["vendor_id"] == 0x054c and d["usage_page"] == 1 and d["usage"] == 5:
            ds_path = d["path"]
            break
    if ds_path:
        break
    time.sleep(1)
print(f"✓ 虚拟 DS HID: {'找到' if ds_path else '未找到'}", flush=True)

# ---- k5 XInput 输入喂入线程 ----
xinput = ctypes.WinDLL("xinput1_4")
class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32),
                ("wButtons", ctypes.c_uint16),
                ("sThumbLX", ctypes.c_int16), ("sThumbLY", ctypes.c_int16),
                ("sThumbRX", ctypes.c_int16), ("sThumbRY", ctypes.c_int16),
                ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte)]
xinput.XInputGetState.argtypes = [ctypes.c_uint32, ctypes.POINTER(XINPUT_STATE)]

stop = threading.Event()
feed_stats = {"n": 0, "ok": 0}

def feeder():
    st = XINPUT_STATE()
    while not stop.is_set():
        for idx in range(4):
            if xinput.XInputGetState(idx, ctypes.byref(st)) == 0:
                s = DSDeviceState()
                s.LX = int(st.sThumbLX / 257)
                s.LY = int(st.sThumbLY / 257)
                s.RX = int(st.sThumbRX / 257)
                s.RY = int(st.sThumbRY / 257)
                s.L2 = st.bLeftTrigger
                s.R2 = st.bRightTrigger
                # 按钮：A=X 交叉 B=圆 X=方块 Y=三角，LB=□ RB=○（粗略映射）
                wb = st.wButtons
                btn = 0
                if wb & 0x1000: btn |= 0x20   # A→CROSS
                if wb & 0x2000: btn |= 0x40   # B→CIRCLE
                if wb & 0x4000: btn |= 0x10   # X→SQUARE
                if wb & 0x8000: btn |= 0x80   # Y→TRIANGLE
                if wb & 0x0100: btn |= 0x100  # LB→L1
                if wb & 0x0200: btn |= 0x200  # RB→R1
                if wb & 0x0080: btn |= 0x4000 # LS→L3
                if wb & 0x0040: btn |= 0x8000 # RS→R3
                if wb & 0x0010: btn |= 0x10000# BACK→CREATE
                if wb & 0x0020: btn |= 0x20000# START→OPTIONS
                s.Buttons = btn
                feed_stats["n"] += 1
                if dll.SetDualSenseDeviceState(dev, s):
                    feed_stats["ok"] += 1
                break
        time.sleep(0.004)

threading.Thread(target=feeder, daemon=True).start()
print("✓ k5 XInput → 虚拟DS 喂入线程已启动", flush=True)

# ---- 全链路自测：往虚拟 DS 写 0x31 报文（模拟游戏）----
def game_sim():
    time.sleep(5)
    if not ds_path:
        print("✗ 虚拟 DS HID 未找到，跳过自测", flush=True)
        return
    hiddll = ctypes.WinDLL("hid")
    kernel32 = ctypes.WinDLL("kernel32")
    h = kernel32.CreateFileA(ds_path.encode() if isinstance(ds_path, str) else ds_path,
                             0xC0000000, 3, None, 3, 0, None)
    if h in (-1, 0xFFFFFFFFFFFFFFFF):
        print(f"✗ 打开虚拟 DS HID 失败 err={ctypes.GetLastError()}", flush=True)
        return
    written = ctypes.c_uint32(0)
    print("▶ 模拟游戏：先 30/0，再 0/200，各 1.5 秒", flush=True)
    for big, small, label in ((0, 200, "小马达200"), (200, 0, "大马达200")):
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 1.5:
            rep = bytearray(48)
            rep[0] = 0x31
            rep[1] = 0x01
            rep[2] = small   # 右/小
            rep[3] = big     # 左/大
            kernel32.WriteFile(h, bytes(rep), len(rep), ctypes.byref(written), None)
            time.sleep(0.01)
    kernel32.CloseHandle(h)
    print("▶ 自测报文发送完毕", flush=True)

threading.Thread(target=game_sim, daemon=True).start()

print("\n保持 30 秒（期间观察：游戏模拟震动→k5 握把应同步震动；拖动摇杆喂入）...", flush=True)
try:
    time.sleep(30)
finally:
    stop.set()
    k5.stop()
    k5.close()
    print(f"喂入统计: {feed_stats['ok']}/{feed_stats['n']} 成功；输出回调收到 {len(hits)} 次: {hits[:10]}", flush=True)
    print("STAGE2_DONE")
