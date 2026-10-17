# -*- coding: utf-8 -*-
# probe_transport.py —— k5 输入传输状态实验
# 1) 读 0x10 现状（ASB 视角 parse 校验）  2) 发 0x11 预置 c=1 r=1（键盘/鼠标保持 0xFF）
# 3) 复读 0x10 验证
import ctypes, time, sys

K32 = ctypes.WinDLL('kernel32', use_last_error=True)
GENERIC_READWRITE = 0xC0000000
PATH = br"\\?\hid#vid_37d7&pid_2501&mi_02&col01#7&c9f15d8&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"

h = K32.CreateFileA(PATH, GENERIC_READWRITE, 3, None, 3, 0x40000000, None)
if h in (-1, 0xFFFFFFFFFFFFFFFF):
    print('open FAIL err=%d' % ctypes.get_last_error()); sys.exit(1)
print('opened handle', h)

def read_once(ms):
    ov = (ctypes.c_uint64 * 4)(); ov[3] = K32.CreateEventW(None, True, False, None)
    buf = ctypes.create_string_buffer(32); n = ctypes.c_uint32()
    if not K32.ReadFile(h, buf, 32, ctypes.byref(n), ov):
        if ctypes.get_last_error() != 997:
            K32.CloseHandle(ov[3]); return None
        if K32.WaitForSingleObject(ov[3], ms) != 0:
            K32.CancelIoEx(h, ov); K32.CloseHandle(ov[3]); return None
    K32.GetOverlappedResult(h, ov, ctypes.byref(n), False)
    K32.CloseHandle(ov[3])
    return buf.raw[:n.value]

def write_frame(cmd, payload):
    f = bytearray(32)
    f[0:4] = b'\x03\x5a\xa5' + bytes([cmd])
    f[4] = len(payload) + 2
    for i, b in enumerate(payload): f[5 + i] = b
    c = 0
    for i in range(3, 3 + f[4]): c = (c + f[i]) & 0xFF
    f[3 + f[4]] = c
    ov = (ctypes.c_uint64 * 4)(); ov[3] = K32.CreateEventW(None, True, False, None)
    n = ctypes.c_uint32()
    if not K32.WriteFile(h, bytes(f), 32, ctypes.byref(n), ov):
        K32.GetOverlappedResult(h, ov, ctypes.byref(n), True)
    K32.CloseHandle(ov[3])

def asb_verdict(d):
    if len(d) >= 11 and d[1:3] == b'\x5a\xa5':
        v = ' '.join('%02X' % d[i] for i in range(6, 11))
        ok = all(d[i] <= 1 for i in range(6, 11))
        return ' cmd=0x%02X [4]=%d [6..10]=%s ASB=%s' % (d[3], d[4], v, 'OK' if ok else 'MALFORMED')
    return ''

def collect(seconds, label):
    print('--- %s ---' % label)
    t0 = time.time()
    seen = 0
    while time.time() - t0 < seconds:
        d = read_once(300)
        if d is None: continue
        seen += 1
        print('recv:', d.hex(' ') + asb_verdict(d))
        if d[1:3] == b'\x5a\xa5' and d[3] == 0x10:
            return d
    if not seen: print('(3 秒内无任何帧)')
    return None

collect(2.5, '0x10 现状读（先纯听流）')
write_frame(0x10, [])
d = collect(2.5, '0x10 查询后')
print()
print('=== 发 0x11 设置 c=1 r=1 k=FF m=FF t=FF（保持键鼠不变）===')
write_frame(0x11, [1, 1, 0xFF, 0xFF, 0xFF])
collect(2.5, '0x11 后的应答')
print()
write_frame(0x10, [])
d2 = collect(2.5, '0x10 复读')
if d2:
    print()
    print('最终 [6..10] =', ' '.join('%02X' % d2[i] for i in range(6, 11)),
          '→ ASB parse:', 'OK ✓' if all(d2[i] <= 1 for i in range(6, 11)) else '还是 MALFORMED')
