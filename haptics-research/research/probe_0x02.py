# -*- coding: utf-8 -*-
"""0x02 活体探测：宿主虚拟 DS + 输出回调 + 0x02 探针写入。"""
import ctypes
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

events = []


@OUTCB
def on_output(handle, rs, rl, r, g, b, pl):
    events.append(("OUT", rs, rl, r, g, b, pl))
    print(f"  ◄◄ OUT回调: 小={rs} 大={rl} LED=({r},{g},{b}) 灯={pl}", flush=True)


cfg = USBServerConfig(b"0.0.0.0:3241", 30000, 5000, 1)
server = ctypes.c_size_t(0)
bus = ctypes.c_uint32(0)
dev = ctypes.c_size_t(0)
dll.NewUSBServer(ctypes.byref(cfg), ctypes.byref(server), ctypes.cast(None, LOGCB))
dll.CreateUSBBus(server, ctypes.byref(bus))
dll.CreateDualSenseDevice(server, ctypes.byref(dev), bus, True, 0, 0, None)
dll.SetDualSenseOutputCallback(dev, on_output)
print("✓ 宿主就绪，回调已注册", flush=True)

import hid
ds_path = None
for _ in range(15):
    time.sleep(1)
    for d in hid.enumerate():
        if d["vendor_id"] == 0x054c and d["usage_page"] == 1 and d["usage"] == 5:
            p = d["path"]
            ds_path = p if isinstance(p, bytes) else p.encode()
            break
    if ds_path:
        break
assert ds_path, "虚拟 DS 未枚举"

hiddll = ctypes.WinDLL("hid")
kernel32 = ctypes.WinDLL("kernel32")
h = kernel32.CreateFileA(ds_path, 0xC0000000, 3, None, 3, 0, None)
written = ctypes.c_uint32(0)

print("\n探针0：0x02 全 0xFF（47B）", flush=True)
rep = bytearray(48)
rep[0] = 0x02
for i in range(1, 48):
    rep[i] = 0xFF
ok = kernel32.WriteFile(h, bytes(rep), 48, ctypes.byref(written), None)
print(f"  WriteFile ok={bool(ok)} err={ctypes.GetLastError()}", flush=True)
time.sleep(1.0)
print(f"  回调: {events}", flush=True)

print("\n探针1：偏移扫描——每次一个字节=255，其余0，写偏移 1..46", flush=True)
baseline = len(events)
for off in range(1, 48):
    rep = bytearray(48)
    rep[0] = 0x02
    rep[off] = 0xFF
    kernel32.WriteFile(h, bytes(rep), 48, ctypes.byref(written), None)
    time.sleep(0.06)
    if len(events) > baseline:
        print(f"  偏移 {off}: 触发回调 {events[baseline:]}", flush=True)
        baseline = len(events)
print(f"  偏移扫描完成，总回调 {len(events)}", flush=True)

kernel32.CloseHandle(h)
print("PROBE_DONE")
