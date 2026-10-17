# -*- coding: utf-8 -*-
"""阶段1b：保持宿主存活，验证虚拟 DS 的自动附加与枚举。"""
import ctypes
import subprocess
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

dll = ctypes.CDLL(DLL_PATH)
dll.NewUSBServer.argtypes = [ctypes.POINTER(USBServerConfig),
                             ctypes.POINTER(ctypes.c_size_t), LOGCB]
dll.NewUSBServer.restype = ctypes.c_bool
dll.CreateUSBBus.argtypes = [ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint32)]
dll.CreateUSBBus.restype = ctypes.c_bool
dll.CreateDualSenseDevice.argtypes = [ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
                                      ctypes.c_uint32, ctypes.c_bool,
                                      ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
dll.CreateDualSenseDevice.restype = ctypes.c_bool

cfg = USBServerConfig(b"0.0.0.0:3241", 30000, 5000, 1)
server = ctypes.c_size_t(0)
assert dll.NewUSBServer(ctypes.byref(cfg), ctypes.byref(server), ctypes.cast(None, LOGCB))
bus = ctypes.c_uint32(0)
assert dll.CreateUSBBus(server, ctypes.byref(bus))
dev = ctypes.c_size_t(0)
ok = dll.CreateDualSenseDevice(server, ctypes.byref(dev), bus, True, 0, 0, None)
print(f"server={server.value:#x} bus={bus.value} ds={dev.value:#x} created={ok}", flush=True)

import hid
for i in range(8):
    time.sleep(5)
    ds = [d for d in hid.enumerate() if d["vendor_id"] == 0x054c]
    print(f"[{i*5+5}s] VID_054C HID 接口数: {len(ds)}", flush=True)
    for d in ds:
        print(f"    PID={d['product_id']:#06x} up={d['usage_page']:#06x} u={d['usage']:#04x} {d['product_string']!r}", flush=True)
    if i == 2:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                            "Get-PnpDevice -PresentOnly | ? {$_.InstanceId -match 'VID_054C'} | "
                            "% {$_.Class + ' | ' + $_.FriendlyName + ' | ' + $_.Status}"],
                           capture_output=True, encoding="gbk", errors="replace")
        print("PnP:", (r.stdout or "").strip() or "（无）", flush=True)
print("KEEPALIVE_DONE")
