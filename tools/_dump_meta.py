import json
from pathlib import Path

m = json.loads(Path(r"c:\Users\root\d\tools\_stamp_meta.json").read_text(encoding="utf-8"))
lines = []
for k, v in sorted(m.items(), key=lambda x: int(x[0].split("_")[1])):
    n = int(k.split("_")[1])
    addr = (v["addr"] or "")[:80]
    lines.append(f"S{n:02d} lat={v['lat']} lon={v['lon']} acc={v['acc']} addr={addr}")
Path(r"c:\Users\root\d\tools\_meta_summary.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
