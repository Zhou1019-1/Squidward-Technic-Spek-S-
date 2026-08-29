import os
from PIL import Image

src = r"E:\homemade-SPEK\icon\HMSicon.png"
dst = r"E:\homemade-SPEK\icon\HMSicon.ico"
img = Image.open(src)
img.save(dst, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
with open(r"E:\homemade-SPEK\tests\ico_log.txt", "w") as f:
    f.write(f"ok {img.size} -> {dst} {os.path.getsize(dst)} bytes")
