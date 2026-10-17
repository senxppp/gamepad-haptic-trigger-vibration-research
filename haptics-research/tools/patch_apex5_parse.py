# -*- coding: utf-8 -*-
# patch_apex5_parse.py —— ApexSenseBridge v1.0.1 APEX5 dongle 模式修复（二字节补丁）
#
# 根因（2026-10-11 实锤，证据 probe_transport.py 抓帧）：
#   ApexSenseBridge 的 parseInputTransportStatus 按 APEX6 固件建模，要求
#   0x10 (read input transport) 应答 [6..10] 五个字节全部 <=1（五个开关位）。
#   八爪鱼5（k5, REV_0800, dongle 连接）的应答布局不同：
#     04 5A A5 10 01 00 | 01 00 00 00 16 ...
#     [6]=c=1 [7]=r=0 [8]=0 [9]=0 [10]=0x16（校验和，不是开关！）
#   → [10]=0x16 > 1 → "malformed input-transport status"
#   → 桥接的恢复逻辑"不知道原始状态，拒绝恢复以保护手柄设置" → 激活被拒。
#   与状态无关：无论怎么设 0x11，应答 [10] 永远是校验和。
#
# 补丁：0x14005A6D7 的 `ja fail`（77 40）→ `nop nop`（90 90）。
#   校验循环 (cmp [rax+rcx],1 / ja) 失去拒绝能力，5 次迭代照常走完，
#   后续 setne 布尔解析不变（非零即真：t=[10]=0x16→true，无害——
#   setInputTransport 的验证只比对 c=[6] 和 r=[7]）。
#
# 实测（2026-10-11）：
#   identify 正常（无自校验拦截）；bridge-triggers --rumble 15 秒完整运行，
#   apex_original_restored=yes，LT/RT 正常复位——激活成功。
#
# 还原：copy ApexSenseBridge.exe.orig ApexSenseBridge.exe
import struct, sys, shutil

PATH = r'C:\Users\xpppj\Downloads\ApexSenseBridge-Portable\ApexSenseBridge.exe'
BAK  = PATH + '.orig'
OFF  = 0x400 + (0x5A6D7 - 0x1000)          # VA 0x14005A6D7 (.text raw 0x400)

d = bytearray(open(PATH, 'rb').read())
cur = bytes(d[OFF:OFF + 2])
if cur == b'\x90\x90':
    print('已打过补丁，无需重复'); sys.exit(0)
assert cur == b'\x77\x40', '字节不符(版本变了?): %s' % cur.hex()
shutil.copy(PATH, BAK)
d[OFF:OFF + 2] = b'\x90\x90'
open(PATH, 'wb').write(d)
print('OK: 0x14005A6D7  77 40 (ja fail) -> 90 90 (nop nop)，备份 .orig')
