import json
from collections import Counter
from pathlib import Path

d = json.loads(Path(r"c:\Users\root\d\tools\_match_raw.json").read_text(encoding="utf-8"))
pairs = d["pairs_raw"]
lines = []
for p in pairs:
    cn = int(p["clean"].split("_")[1])
    sn = int(p["stamped"].split("_")[1])
    sec = int(p["second"].split("_")[1]) if p["second"] else None
    weak = p["orb"] < 0.15 or p["score"] < 0
    lines.append(
        f"C{cn:02d}->S{sn:02d} score={p['score']:.1f} orb={p['orb']:.3f} "
        f"ph={p['ph']} ah={p['ah']} hist={p['hist']:.2f} 2nd=S{sec} {'WEAK' if weak else 'ok'}"
    )
Path(r"c:\Users\root\d\tools\_match_summary.txt").write_text("\n".join(lines), encoding="utf-8")
c = Counter(p["stamped"] for p in pairs)
reuse = [f"{v}x {k}" for k, v in c.most_common() if v > 1]
unused = [n for n in d["stamp_names"] if n not in c]
Path(r"c:\Users\root\d\tools\_match_reuse.txt").write_text(
    "REUSE:\n" + "\n".join(reuse) + "\n\nUNUSED:\n" + "\n".join(unused) + f"\n\nweak={sum(1 for p in pairs if p['orb']<0.15 or p['score']<0)}",
    encoding="utf-8",
)
print("wrote summary")
