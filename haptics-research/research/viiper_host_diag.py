# -*- coding: utf-8 -*-
"""阶段2c：输出回调诊断——HID 能力、WriteFile 结果、回调触发。"""
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

k5 = FlydigiVibration()
k5.open()

hits = []


@OUTCB
def on_output(handle, rs, rl, r, g, b, pl):
    hits.append((rs, rl))
    print(f"  ◄◄ 回调触发: 小={rs} 大={rl} LED=({r},{g},{b}) 灯={pl}", flush=True)


cfg = USBServerConfig(b"0.0.0.0:3241", 30000, 5000, 1)
server = ctypes.c_size_t(0)
bus = ctypes.c_uint32(0)
dev = ctypes.c_size_t(0)
dll.NewUSBServer(ctypes.byref(cfg), ctypes.byref(server), ctypes.cast(None, LOGCB))
dll.CreateUSBBus(server, ctypes.byref(bus))
dll.CreateDualSenseDevice(server, ctypes.byref(dev), bus, True, 0, 0, None)
dll.SetDualSenseOutputCallback(dev, on_output)
print("✓ 宿主就绪", flush=True)

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

hiddll = ctypes.WinDLL("hid")
kernel32 = ctypes.WinDLL("kernel32")
h = kernel32.CreateFileA(ds_path if isinstance(ds_path, bytes) else ds_path.encode(), 0xC0000000, 3, None, 3, 0, None)
if h in (-1, 0xFFFFFFFFFFFFFFFF):
    print("✗ 打开虚拟 DS 失败", flush=True)
    sys.exit(1)

pd = ctypes.c_void_p()
hiddll.HidD_GetPreparsedData(h, ctypes.byref(pd))
caps = (ctypes.c_ushort * 32)()
hiddll.HidP_GetCaps(pd, caps)
print(f"虚拟 DS HID 能力: Input={caps[2]} Output={caps[3]} Feature={caps[4]}", flush=True)
hiddll.HidD_FreePreparsedData(pd)

written = ctypes.c_uint32(0)


def write31(big, small, label):
    rep = bytearray(caps[3])
    rep[0] = 0x31
    rep[1] = 0x01
    rep[2] = small
    rep[3] = big
    ok = kernel32.WriteFile(h, bytes(rep), len(rep), ctypes.byref(written), None)
    print(f"  {label}: WriteFile ok={bool(ok)} written={written.value} err={ctypes.GetLastError()}", flush=True)
    return ok


print("\n发送序列（每种 0.8 秒连发 + 间隔）...", flush=True)
for big, small, label in ((0, 255, "小马达255"), (255, 0, "大马达255"), (255, 255, "双满")):
    t0 = time.perf_counter()
    n = 0
    while time.perf_counter() - t0 < 0.8:
        write31(big, small, label if n == 0 else "")
        n += 1
        time.sleep(0.01)
    time.sleep(1.0)
    print(f"    回调计数: {len(hits)}", flush=True)

kernel32.CloseHandle(h)
k5.close()
print(f"DONE 总回调: {len(hits)}", flush=True)
