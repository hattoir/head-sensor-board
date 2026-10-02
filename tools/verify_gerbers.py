#!/usr/bin/env python3
"""出力したガーバー・ドリルを、KiCad とは別のライブラリ（gerbonara）で読み直して確かめる。

    pip install gerbonara     （検査にだけ使う。出力には使わない）
    python tools/verify_gerbers.py [gerbers/head-sensor-board_gerbers.zip]

確かめること（zip の中身だけを見る = 発注先に渡るものそのもの）:
  1. 必要な層がそろっている（表銅・裏銅・表/裏レジスト・表/裏シルク・表ペースト・外形）と、ドリル（PTH / NPTH）
  2. 外形の大きさ = 基板の寸法、原点 = 基板の左下、銅は縁から 0.5 mm 以上内側
  3. ドリルの穴の位置・径が、基板（docs/placement_geometry.json のスルーホールのランド）と docs/routes.json のビアに 1 対 1 で一致する
  4. 表・裏の銅の図形が、全ランド・全トラック・全ビアの位置を覆っている（抜けがない）
"""
import json
import pathlib
import sys
import warnings

warnings.simplefilter("ignore")
from gerbonara import LayerStack                       # noqa: E402
from gerbonara.utils import MM                         # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
zip_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "gerbers" / "head-sensor-board_gerbers.zip"
if not (ROOT / "docs" / "placement_geometry.json").exists():
    sys.exit("docs/placement_geometry.json が無い（git に入れていない作業用ファイル）。先に python tools/make_board.py --reuse-routes")
geo = json.loads((ROOT / "docs" / "placement_geometry.json").read_text(encoding="utf-8"))
routes = json.loads((ROOT / "docs" / "routes.json").read_text(encoding="utf-8"))
W, H = geo["W"], geo["H"]
bad = []

st = LayerStack.open(str(zip_path))
need = [("top", "copper"), ("bottom", "copper"), ("top", "mask"), ("bottom", "mask"), ("top", "silk"), ("bottom", "silk"), ("top", "paste"), ("mechanical", "outline")]
for k in need:
    if k not in st.graphic_layers:
        bad.append(f"層がない: {k}")
print("層:", ", ".join(f"{a}-{b}" for a, b in st.graphic_layers.keys()), "| ドリル: PTH", bool(st.drill_pth), "NPTH", bool(st.drill_npth))

# 2. 外形
(x0, y0), (x1, y1) = st.outline.bounding_box(MM)
lw = 0.05
print(f"外形: x {x0 + lw / 2:.3f}〜{x1 - lw / 2:.3f}, y {y0 + lw / 2:.3f}〜{y1 - lw / 2:.3f} mm（基板 {W} × {H}、原点は左下）")
if abs((x1 - x0 - lw) - W) > 0.01 or abs((y1 - y0 - lw) - H) > 0.01 or abs(x0 + lw / 2) > 0.01 or abs(y0 + lw / 2) > 0.01:
    bad.append("外形の大きさ・原点が基板と合わない")
for key in (("top", "copper"), ("bottom", "copper")):
    (cx0, cy0), (cx1, cy1) = st.graphic_layers[key].bounding_box(MM)
    m = min(cx0, cy0, W - cx1, H - cy1)
    print(f"銅 {key[0]}: 縁からの最小距離 {m:.3f} mm")
    if m < 0.5 - 0.01:
        bad.append(f"{key} の銅が縁から 0.5 mm 未満")

# 3. ドリル
expected = []                                           # (x, y, 径, めっき)
for fp in geo["fps"]:
    for p in fp["pads"]:
        if p["thru"]:
            expected.append((p["c"][0], H - p["c"][1], p["drill"], not p["npth"]))
for v in routes["vias"]:
    expected.append((v["at"][0] / 1e6, H - v["at"][1] / 1e6, v["drill"], True))
got = []
for f, plated in ((st.drill_pth, True), (st.drill_npth, False)):
    for o in f.objects:
        got.append((o.x, o.y, o.aperture.diameter, plated))
print(f"ドリル: 期待 {len(expected)} 個（PTH {sum(1 for e in expected if e[3])}、NPTH {sum(1 for e in expected if not e[3])}）、ファイル {len(got)} 個")
left = list(got)
for e in expected:
    hit = [g for g in left if abs(g[0] - e[0]) < 0.01 and abs(g[1] - e[1]) < 0.01 and abs(g[2] - e[2]) < 0.01 and g[3] == e[3]]
    if not hit:
        bad.append(f"穴が無い: {e}")
    else:
        left.remove(hit[0])
for g in left:
    bad.append(f"余分な穴: {g}")
print("穴の径（mm）:", sorted(set((round(g[2], 3), "PTH" if g[3] else "NPTH") for g in got)))


# 4. 銅が全ランド・全トラック・全ビアを覆うか（図形の外形 = bounding box で点を調べる）
def covered(layer, x, y, r=0.05):
    for o in layer.objects:
        (bx0, by0), (bx1, by1) = o.bounding_box(MM)
        if bx0 - r <= x <= bx1 + r and by0 - r <= y <= by1 + r:
            return True
    return False


cu = {"F.Cu": st.graphic_layers[("top", "copper")], "B.Cu": st.graphic_layers[("bottom", "copper")]}
miss = 0
for fp in geo["fps"]:
    for p in fp["pads"]:
        if p["npth"]:
            continue
        layers = ["F.Cu", "B.Cu"] if p["thru"] else ["F.Cu"]
        for ly in layers:
            if not covered(cu[ly], p["bc"][0], H - p["bc"][1]):
                bad.append(f"{ly} にランドの銅が無い: {fp['ref']}.{p['n']}")
                miss += 1
for t in routes["tracks"]:
    for q in (t["a"], t["b"]):
        if not covered(cu[t["layer"]], q[0] / 1e6, H - q[1] / 1e6):
            bad.append(f"{t['layer']} にトラックの銅が無い: {t['net']}")
            miss += 1
for v in routes["vias"]:
    for ly in ("F.Cu", "B.Cu"):
        if not covered(cu[ly], v["at"][0] / 1e6, H - v["at"][1] / 1e6):
            bad.append(f"{ly} にビアの銅が無い")
            miss += 1
print(f"銅の抜け: {miss} 個（ランド・トラックの端・ビアを調べた）")

print("RESULT:", "OK" if not bad else f"{len(bad)} 件の問題")
for b in bad[:20]:
    print("  NG:", b)
sys.exit(1 if bad else 0)
