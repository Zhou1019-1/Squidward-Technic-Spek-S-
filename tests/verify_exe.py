# -*- coding: utf-8 -*-
"""验证打包后的 exe：带测试文件启动，观察进程存活与崩溃。"""
import os
import subprocess
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(BASE, "dist", "章鱼频谱查看器.exe")
WAV = os.path.join(BASE, "test_media", "base.wav")
LOG = os.path.join(BASE, "tests", "verify_exe_log.txt")

out = open(LOG, "w", encoding="utf-8")

proc = subprocess.Popen([EXE, WAV])
out.write(f"pid={proc.pid}\n")
out.flush()

alive_checks = []
for i in range(10):
    time.sleep(1)
    code = proc.poll()
    alive_checks.append(code is None)
    if code is not None:
        out.write(f"进程在第 {i+1} 秒退出，退出码={code}\n")
        break
else:
    out.write("进程存活 10 秒，未崩溃\n")

if proc.poll() is None:
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
    out.write("已正常结束测试进程\n")

out.write("结果: " + ("PASS" if all(alive_checks) and len(alive_checks) == 10 else "FAIL") + "\n")
out.close()
