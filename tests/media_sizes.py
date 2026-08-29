import os

with open(r"E:\homemade-SPEK\tests\media_sizes.txt", "w") as f:
    for name in sorted(os.listdir(r"E:\homemade-SPEK\test_media")):
        size = os.path.getsize(os.path.join(r"E:\homemade-SPEK\test_media", name))
        f.write(f"{name} {size // 1024}KB\n")
