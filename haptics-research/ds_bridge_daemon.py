# -*- coding: utf-8 -*-
"""85-to-DS 全功能桥接守护进程
================================

一键全开：虚拟 DualSense + 输入喂入 + 震动翻译 + 音频触觉拦截 + 扳机感觉合成。

  游戏 ──(以为是真DS5)──► 虚拟 DS (VIIPER + usbip-win2)
    ├ 输出报文(震动)  ──► k5 握把
    └ 音频触觉流      ──► 回环拦截 → 分析 ──► k5 握把 + 扳机感觉调色板
  k5 物理输入(XInput) ──► 虚拟 DS ──► 游戏

用法: python ds_bridge_daemon.py [运行秒数，默认1800]
停止: Ctrl+C
"""
import ctypes
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = r"C:\Users\xpppj\.zcode\workspace\default"
sys.path.insert(0, HERE + r"\flydigi-haptic-middleware\vib_out")
sys.path.insert(0, HERE + r"\flydigi-music-haptic")

import numpy as np  # noqa: E402
import hid  # noqa: E402
import pyaudiowpatch as pa  # noqa: E402
from flydigi_vib import FlydigiVibration  # noqa: E402
from flydigi_trigger import FlydigiTrigger  # noqa: E402

DLL_PATH = HERE + r"\research\apextods\APEXtoDS\libVIIPER.dll"
RATE, CH, FRAME = 48000, 4, 480
RUN_SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 1800


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

# ---------- k5 输出通道 ----------
k5 = FlydigiVibration()
k5.open()
trg = FlydigiTrigger()
trg.open()
print("✓ k5 握把+扳机通道已开", flush=True)

# ---------- 虚拟 DS ----------
cfg = USBServerConfig(b"0.0.0.0:3241", 30000, 5000, 1)
server = ctypes.c_size_t(0)
bus = ctypes.c_uint32(0)
dev = ctypes.c_size_t(0)
assert dll.NewUSBServer(ctypes.byref(cfg), ctypes.byref(server), ctypes.cast(None, LOGCB))
assert dll.CreateUSBBus(server, ctypes.byref(bus))
assert dll.CreateDualSenseDevice(server, ctypes.byref(dev), bus, True, 0, 0, None)
print(f"✓ 虚拟 DualSense 已创建 (server={server.value:#x} bus={bus.value} dev={dev.value:#x})", flush=True)

rumble_hits = [0]


@OUTCB
def on_output(handle, rs, rl, r, g, b, pl):
    if rs or rl:
        rumble_hits[0] += 1
        k5.set(rs, rl)   # 游戏震动 → k5 握把


dll.SetDualSenseOutputCallback(dev, on_output)
print("✓ 输出回调已注册（游戏震动→k5 握把）", flush=True)

# ---------- 输入喂入 ----------
xinput = ctypes.WinDLL("xinput1_4")


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("wButtons", ctypes.c_uint16),
                ("sThumbLX", ctypes.c_int16), ("sThumbLY", ctypes.c_int16),
                ("sThumbRX", ctypes.c_int16), ("sThumbRY", ctypes.c_int16),
                ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte)]


stop = threading.Event()
feed = {"n": 0, "ok": 0}


def feeder():
    st = XINPUT_STATE()
    while not stop.is_set():
        for idx in range(4):
            if xinput.XInputGetState(idx, ctypes.byref(st)) == 0:
                s = DSDeviceState()
                s.LX = int(st.sThumbLX / 257); s.LY = int(st.sThumbLY / 257)
                s.RX = int(st.sThumbRX / 257); s.RY = int(st.sThumbRY / 257)
                s.L2 = st.bLeftTrigger; s.R2 = st.bRightTrigger
                wb = st.wButtons
                btn = 0
                for mask, bit in ((0x1000, 0x20), (0x2000, 0x40), (0x4000, 0x10),
                                  (0x8000, 0x80), (0x0100, 0x100), (0x0200, 0x200),
                                  (0x0080, 0x4000), (0x0040, 0x8000),
                                  (0x0010, 0x10000), (0x0020, 0x20000)):
                    if wb & mask:
                        btn |= bit
                s.Buttons = btn
                feed["n"] += 1
                if dll.SetDualSenseDeviceState(dev, s):
                    feed["ok"] += 1
                break
        time.sleep(0.004)


threading.Thread(target=feeder, daemon=True).start()
print("✓ k5 XInput → 虚拟DS 喂入线程已启动", flush=True)

# ---------- 等虚拟声卡就绪（约 10 秒），然后音频触觉拦截 ----------
time.sleep(12)
p = pa.PyAudio()
ds_lb_idx = None
for devinfo in p.get_loopback_device_info_generator():
    if "DualSense" in devinfo["name"]:
        ds_lb_idx = int(devinfo["index"])
        break
audio_on = ds_lb_idx is not None
print(f"{'✓' if audio_on else '✗'} 虚拟 DS 音频回环端点: {'index ' + str(ds_lb_idx) if audio_on else '未找到（音频触觉拦截停用）'}", flush=True)

# ---------- 音频触觉分析 → 握把 + 扳机 ----------
audio_stats = {"frames": 0, "shots": 0, "peak": 0}
last_trig_t = -1.0
baseline = 0.0005


def audio_loop():
    global baseline, last_trig_t
    lb = p.open(format=pa.paInt16, channels=CH, rate=RATE, input=True,
                input_device_index=ds_lb_idx, frames_per_buffer=FRAME)
    t_now = 0
    while not stop.is_set():
        raw = lb.read(FRAME, exception_on_overflow=False)
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0
        level = min(255, int(rms * 1500))
        audio_stats["frames"] += 1
        audio_stats["peak"] = max(audio_stats["peak"], level)
        wall = time.perf_counter()
        # 瞬态 → 单发后座（右扳机）
        ratio = rms / max(baseline, 1e-5)
        if rms > 0.004 and ratio > 2.2 and wall - last_trig_t > 0.12:
            trg.feel("单发后座", side=2)
            audio_stats["shots"] += 1
            last_trig_t = wall
        # 持续强声 → 握把 + 双扳机持续嗡震（配握把同步）
        if level > 60:
            k5.set(level, level)
            trg.feel("持续嗡震", side=3, viblevel=min(160, level))
        elif level > 8:
            k5.set(level, level)
        else:
            k5.set(0, 0)
        baseline = 0.9 * baseline + 0.1 * rms
    lb.stop_stream(); lb.close()


if audio_on:
    threading.Thread(target=audio_loop, daemon=True).start()
    print("✓ 音频触觉拦截线程已启动（瞬态→单发后座 / 持续→握把+扳机嗡震）", flush=True)

print(f"\n=== 全功能桥接已就绪，运行 {RUN_SECONDS} 秒。去开游戏/软件测试吧 ===", flush=True)
print("  · 需要触觉音频的游戏：把音频输出选到「DualSense Wireless Controller」扬声器", flush=True)
print("  · 手柄输入会同步进虚拟 DS；游戏震动/音频事件实时转 k5", flush=True)
try:
    t_end = time.perf_counter() + RUN_SECONDS
    while time.perf_counter() < t_end:
        time.sleep(10)
        print(f"  [状态] 喂入 {feed['ok']}/{feed['n']} | 震动翻译 {rumble_hits[0]} 次 | "
              f"音频 {audio_stats['frames']} 帧 峰值 {audio_stats['peak']} 后座 {audio_stats['shots']}", flush=True)
finally:
    stop.set()
    k5.stop(); k5.close(); trg.feel("轻油门刹车"); trg.close()
    print("守护进程已退出，手柄已复位。", flush=True)
