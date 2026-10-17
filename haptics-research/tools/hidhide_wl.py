# -*- coding: utf-8 -*-
# hidhide_wl.py —— 读 HidHide 白名单并追加指定进程（覆盖式写回前先完整读取）
# 用法（管理员）：python hidhide_wl.py [追加路径]   不带参数 = 只读
import ctypes, ctypes.wintypes as wt, sys, os

GENERIC_READ = 0x80000000
IOCTL_GET_WL = 0x80016000
IOCTL_SET_WL = 0x80016004

k32 = ctypes.WinDLL('kernel32', use_last_error=True)

h = k32.CreateFileW(r'\\.\HidHide', GENERIC_READ, 0, None, 3, 0, None)
if h == -1 or h == 0xFFFFFFFFFFFFFFFF:
    print('打开 \\\\.\\HidHide 失败 err=%d（需要管理员）' % ctypes.get_last_error())
    sys.exit(1)

def get_list(code):
    need = wt.DWORD(0)
    k32.DeviceIoControl(h, code, None, 0, None, 0, ctypes.byref(need), None)
    if need.value == 0:
        return []
    buf = ctypes.create_unicode_buffer(need.value // 2)
    ret = wt.DWORD(0)
    ok = k32.DeviceIoControl(h, code, None, 0, buf, need.value, ctypes.byref(ret), None)
    if not ok:
        print('read err', ctypes.get_last_error()); sys.exit(1)
    raw = buf.raw[:ret.value].decode('utf-16-le')
    parts = raw.split('\x00')
    return [p for p in parts if p]

def set_list(code, items):
    raw = '\x00'.join(items) + '\x00\x00'
    buf = ctypes.create_unicode_buffer(raw)
    ret = wt.DWORD(0)
    ok = k32.DeviceIoControl(h, code, buf, len(raw) * 2, None, 0, ctypes.byref(ret), None)
    if not ok:
        print('write err', ctypes.get_last_error()); sys.exit(1)

wl = get_list(IOCTL_GET_WL)
print('当前白名单 %d 项:' % len(wl))
for p in wl:
    print('  ', p)

if len(sys.argv) > 1:
    add = os.path.abspath(sys.argv[1])
    if add not in wl:
        wl.append(add)
        set_list(IOCTL_SET_WL, wl)
        print('已追加:', add)
        print('回读验证:', get_list(IOCTL_GET_WL))
    else:
        print('已在白名单中:', add)
