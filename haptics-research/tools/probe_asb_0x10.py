# -*- coding: utf-8 -*-
# probe_asb_0x10.py —— 实测 k5 对 0x10 (read input transport) 的真实应答
# 对比 ApexSenseBridge parseInputTransportStatus 的期待：
#   size>=11, [0]=04 [1]=5A [2]=A5 [3]=0x10, [6..10] 全部 <=1
import ctypes, ctypes.wintypes as wt, sys, time

K32 = ctypes.WinDLL('kernel32', use_last_error=True)
GENERIC_READ  = 0x80000000
GENERIC_WRITE = 0x40000000
SHARE = 3
OPEN_EXISTING = 3
INVALID = wt.HANDLE(-1).value or -1
ctypes.c_uint64.__repr__ = lambda s: hex(s.value)

PATH = br"\\?\hid#vid_37d7&pid_2501&mi_02&col01#7&c9f15d8&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"

class OVERLAPPED(ctypes.Structure):
    _fields_ = [('Internal', ctypes.c_uint64), ('InternalHigh', ctypes.c_uint64),
                ('DUMMY', ctypes.c_uint64 * 2), ('hEvent', wt.HANDLE)]

h = K32.CreateFileA(PATH, GENERIC_READ | GENERIC_WRITE, SHARE, None, OPEN_EXISTING, 0x40000000, None)  # FILE_FLAG_OVERLAPPED
if h == INVALID or h == -1:
    print('open failed', ctypes.get_last_error()); sys.exit(1)
print('opened handle', h)

def write_report(buf):
    ov = OVERLAPPED()
    ov.hEvent = K32.CreateEventW(None, True, False, None)
    n = ctypes.c_uint32()
    buf = bytes(buf) + b'\x00' * (32 - len(buf))
    ok = K32.WriteFile(h, buf, 32, ctypes.byref(n), ctypes.byref(ov))
    if not ok:
        K32.GetOverlappedResult(h, ctypes.byref(ov), ctypes.byref(n), True)
    K32.CloseHandle(ov.hEvent)
    return n.value

def read_report(timeout_ms):
    ov = OVERLAPPED()
    ov.hEvent = K32.CreateEventW(None, True, False, None)
    buf = ctypes.create_string_buffer(32)
    n = ctypes.c_uint32()
    ok = K32.ReadFile(h, buf, 32, ctypes.byref(n), ctypes.byref(ov))
    if not ok:
        err = ctypes.get_last_error()
        if err != 997:  # ERROR_IO_PENDING
            K32.CloseHandle(ov.hEvent)
            return None, err
        r = K32.WaitForSingleObject(ov.hEvent, timeout_ms)
        if r != 0:
            K32.CancelIoEx(h, ctypes.byref(ov))
            K32.CloseHandle(ov.hEvent)
            return None, 'timeout'
    K32.GetOverlappedResult(h, ctypes.byref(ov), ctypes.byref(n), False)
    K32.CloseHandle(ov.hEvent)
    return buf.raw[:n.value], 0

# 常驻一个 pending read（吃掉流上的普通输入帧），再发查询、再收
def query(cmd, payload, tries=6):
    # 挂读
    pend = OVERLAPPED()
    pend.hEvent = K32.CreateEventW(None, True, False, None)
    pbuf = ctypes.create_string_buffer(32)
    pn = ctypes.c_uint32()
    K32.ReadFile(h, pbuf, 32, ctypes.byref(pn), ctypes.byref(pend))

    frame = bytearray(32)
    frame[0], frame[1], frame[2], frame[3] = 0x03, 0x5A, 0xA5, cmd
    frame[4] = len(payload) + 2
    for i, b in enumerate(payload):
        frame[5 + i] = b
    cks = 0
    for i in range(3, 3 + frame[4]):
        cks = (cks + frame[i]) & 0xFF
    frame[3 + frame[4]] = cks
    w = write_report(frame)
    print('wrote:', bytes(frame[:12]).hex(' '), '(n=%d)' % w)

    out = []
    deadline = time.time() + 2.0
    while time.time() < deadline and len(out) < tries:
        buf, n2, err = ctypes.create_string_buffer(32), ctypes.c_uint32(), ctypes.c_uint32()
        ov2 = OVERLAPPED()
        ov2.hEvent = K32.CreateEventW(None, True, False, None)
        ok = K32.ReadFile(h, buf, 32, ctypes.byref(n2), ctypes.byref(ov2))
        if not ok:
            e = ctypes.get_last_error()
            if e != 997:
                break
            r = K32.WaitForSingleObject(ov2.hEvent, int(max(0, (deadline - time.time()) * 1000)))
            if r != 0:
                K32.CancelIoEx(h, ctypes.byref(ov2))
                K32.CloseHandle(ov2.hEvent)
                break
        K32.GetOverlappedResult(h, ctypes.byref(ov2), ctypes.byref(n2), False)
        K32.CloseHandle(ov2.hEvent)
        data = buf.raw[:n2.value]
        out.append(data)
        tag = ''
        if len(data) >= 11 and data[1:3] == b'\x5a\xa5':
            tag = ' cmd=0x%02X [4]=%d [6..10]=%s' % (data[3], data[4], ' '.join('%02X' % data[i] for i in range(6, 11)))
            if data[3] == 0x10:
                ok_parse = (len(data) >= 11 and all(data[i] <= 1 for i in range(6, 11)))
                tag += '  ASB解析=%s' % ('OK' if ok_parse else 'MALFORMED ← 就是它')
        print('recv :', data.hex(' ') + tag)
    # 清 pending
    K32.CancelIoEx(h, ctypes.byref(pend))
    K32.CloseHandle(pend.hEvent)

print('--- 0x10 读输入传输状态 ---')
query(0x10, [])
K32.CloseHandle(h)
