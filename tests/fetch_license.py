import subprocess, os

r = subprocess.run(
    ["gh", "api", "licenses/gpl-3.0", "--jq", ".body"],
    capture_output=True, text=True, encoding="utf-8",
)
base = r"E:\homemade-SPEK"
with open(os.path.join(base, "tests", "lic_diag.txt"), "w") as f:
    f.write(f"rc={r.returncode} stdout_len={len(r.stdout)} stderr={r.stderr[:200]}")
if r.returncode == 0 and len(r.stdout) > 1000:
    with open(os.path.join(base, "LICENSE"), "w", encoding="utf-8", newline="\n") as f:
        f.write(r.stdout)
