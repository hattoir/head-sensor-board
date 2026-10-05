#!/usr/bin/env python
"""基板の実測値を、発注先の公開仕様（tools/fab_rules.json）と突き合わせる。KiCad 同梱の Python で実行する:

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/check_fab_rules.py [--fab jlcpcb,pcbway] [--pcb ...]

測る値（基板から直接）: 配線の最小幅、間隔（プロジェクトの規則 = DRC が守る値）、ビア・スルーホールの穴径・外径・アニュラリング、
シルクの線の最小の太さ・文字の最小の高さ・ランドとのすきま、ランドどうしの最小のすきま（マスクのブリッジの目安）、銅と縁の距離（規則）、
外形の大きさ、板厚。結果は PASS / FAIL / WARN（推奨値に届かない）/ -（仕様に記載なし）。
**これは公開仕様との机上の照合であって、注文して確かめたものではない。** 終了コード: 指定した発注先のどれかに FAIL があれば 1。
"""
import argparse
import json
import pathlib
import sys

import pcbnew
from pcbnew import ToMM

ROOT = pathlib.Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--pcb", default=str(ROOT / "head-sensor-board.kicad_pcb"))
ap.add_argument("--fab", default="all", help="カンマ区切り（jlcpcb,pcbway,seeed_fusion,elecrow）。all = 全部")
ap.add_argument("--json", default=None, help="結果を JSON で書き出すパス")
ap.add_argument("--md", default=None, help="結果を Markdown の表で書き出すパス（docs/fab_check.md）")
args = ap.parse_args()

rules = json.loads((ROOT / "tools" / "fab_rules.json").read_text(encoding="utf-8"))
fabs = rules["fabs"] if args.fab == "all" else {k: rules["fabs"][k] for k in args.fab.split(",")}
pro = json.loads((ROOT / "head-sensor-board.kicad_pro").read_text(encoding="utf-8"))["board"]["design_settings"]
board = pcbnew.LoadBoard(args.pcb)


def mm(v):
    return ToMM(v)


# ---------------------------------------------------------------- 実測
tracks, vias = [], []
for t in board.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        try:
            dia = mm(t.GetWidth(pcbnew.F_Cu))
        except TypeError:
            dia = mm(t.GetWidth())
        vias.append((dia, mm(t.GetDrillValue())))
    else:
        tracks.append(mm(t.GetWidth()))
tht = []                                           # (最小の寸法, 穴径)
pads = []                                          # (side set, bbox, 名前)
for fp in board.GetFootprints():
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        box = (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
        sides = {"F"} if not p.HasHole() else {"F", "B"}
        if p.HasHole() and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
            tht.append((min(mm(p.GetSizeX()), mm(p.GetSizeY())), mm(p.GetDrillSizeX())))
        if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
            pads.append((sides, box, f"{fp.GetReference()}.{p.GetNumber()}"))
all_holes = [d for _, d in vias] + [d for _, d in tht] + [mm(p.GetDrillSizeX()) for fp in board.GetFootprints() for p in fp.Pads()
                                                          if p.HasHole() and p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]

strokes, heights, silk_prims = [], [], []          # silk_prims: (名前, 点列 or 枠, 半幅, 部品か)
S = lambda v: (mm(v.x), mm(v.y))                   # noqa: E731


def sample(a, b, step=0.05):
    n = max(1, int(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 / step))
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


def shape_pts(d):
    k = d.GetShape()
    if k == pcbnew.SHAPE_T_SEGMENT:
        return sample(S(d.GetStart()), S(d.GetEnd()))
    b = d.GetBoundingBox()
    x0, y0, x1, y1 = mm(b.GetLeft()), mm(b.GetTop()), mm(b.GetRight()), mm(b.GetBottom())
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [p for i in range(4) for p in sample(c[i], c[(i + 1) % 4])]


for d in board.GetDrawings():
    if d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
        if isinstance(d, pcbnew.PCB_TEXT):
            strokes.append(mm(d.GetTextThickness()))
            heights.append(mm(d.GetTextHeight()))
            b = d.GetEffectiveTextShape().BBox()
            silk_prims.append((f"文字 {d.GetText()}", "box", (mm(b.GetLeft()), mm(b.GetTop()), mm(b.GetRight()), mm(b.GetBottom())), 0.0, False, d.GetLayer()))
        elif isinstance(d, pcbnew.PCB_SHAPE):
            strokes.append(mm(d.GetWidth()))
            silk_prims.append(("線", "pts", shape_pts(d), mm(d.GetWidth()) / 2, False, d.GetLayer()))
for fp in board.GetFootprints():
    for g in fp.GraphicalItems():
        if g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) and isinstance(g, pcbnew.PCB_SHAPE):
            strokes.append(mm(g.GetWidth()))
            silk_prims.append((f"{fp.GetReference()} の枠", "pts", shape_pts(g), mm(g.GetWidth()) / 2, True, g.GetLayer()))
    for f in fp.GetFields():
        if f.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) and f.IsVisible():
            strokes.append(mm(f.GetTextThickness()))
            heights.append(mm(f.GetTextHeight()))


def pt_box_gap(pt, box):
    dx = max(box[0] - pt[0], 0, pt[0] - box[2])
    dy = max(box[1] - pt[1], 0, pt[1] - box[3])
    return (dx * dx + dy * dy) ** 0.5


def box_box_gap(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    return (dx * dx + dy * dy) ** 0.5


def silk_pad_gap(own_part):
    best = 9e9
    for name, kind, geom, hw, is_part, layer in silk_prims:
        if is_part != own_part:
            continue
        side = "F" if layer == pcbnew.F_SilkS else "B"
        for sides, pbox, pname in pads:
            if side not in sides:
                continue
            if own_part and name.split(" ")[0] == pname.split(".")[0]:
                pass                                                   # 自分の部品のランドも含める（ライブラリの標準の枠）
            g = box_box_gap(geom, pbox) if kind == "box" else min(pt_box_gap(p, pbox) for p in geom) - hw
            best = min(best, g)
    return best


web = 9e9
for i in range(len(pads)):
    for j in range(i + 1, len(pads)):
        if pads[i][0] & pads[j][0]:
            web = min(web, box_box_gap(pads[i][1], pads[j][1])) if pads[i][2].split(".")[0] != pads[j][2].split(".")[0] or True else web

eb = board.GetBoardEdgesBoundingBox()
size = (mm(eb.GetWidth()) - 0.05, mm(eb.GetHeight()) - 0.05)        # 外形線の太さ 0.05 mm を除く
thickness = mm(board.GetDesignSettings().GetBoardThickness())

M = {
    "track_min": min(tracks) if tracks else None,
    "space_min": pro["rules"].get("min_clearance") or 0.2,          # プロジェクトの既定のクリアランス（net class）
    "via_hole_min": min(d for _, d in vias),
    "via_dia_min": min(v for v, _ in vias),
    "pth_hole_min": min(all_holes),
    "pth_annular_min": min((s - d) / 2 for s, d in tht),
    "via_annular": min((v - d) / 2 for v, d in vias),
    "silk_stroke_min": min(strokes),
    "silk_height_min": min(heights),
    "silk_pad_clear_own": silk_pad_gap(False),
    "silk_pad_clear_part": silk_pad_gap(True),
    "mask_web_min": web,
    "copper_edge_min": pro["rules"]["min_copper_edge_clearance"],
    "pad_space_min": web,
}
# 既定のクリアランスは net class（.kicad_pro）から
try:
    nc = json.loads((ROOT / "head-sensor-board.kicad_pro").read_text(encoding="utf-8"))["net_settings"]["classes"][0]
    M["space_min"] = nc["clearance"]
except Exception:
    pass
print("== 基板の実測値 ==")
print(f"  配線の最小幅 {M['track_min']:.3f} / 間隔（規則）{M['space_min']:.3f} / ビア 穴 {M['via_hole_min']:.3f}・外径 {M['via_dia_min']:.3f}・アニュラリング {M['via_annular']:.3f}")
print(f"  部品のスルーホールのアニュラリング 最小 {M['pth_annular_min']:.3f} / 穴の最小 {M['pth_hole_min']:.3f}")
print(f"  シルク: 線の太さ 最小 {M['silk_stroke_min']:.3f} / 文字の高さ 最小 {M['silk_height_min']:.3f} / ランドとのすきま 最小 {M['silk_pad_clear_own']:.3f}（基板上の刻印）、{M['silk_pad_clear_part']:.3f}（部品の標準の枠。ライブラリのまま）")
print(f"  ランドどうしの最小のすきま {M['mask_web_min']:.3f}（半田ジャンパーの 3 パッドの間。わざとはんだでつなぐ）/ 銅と縁（規則）{M['copper_edge_min']:.3f} / 外形 {size[0]:.2f} × {size[1]:.2f} / 板厚 {thickness:.2f}")

# ---------------------------------------------------------------- 照合
ROWS = [
    ("配線の最小幅", "track_min", "track_min", ">="),
    ("配線の間隔", "space_min", "space_min", ">="),
    ("ビアの穴径", "via_hole_min", "via_hole_min", ">="),
    ("ビアの外径", "via_dia_min", "via_dia_min", ">="),
    ("最小の穴径（ビア・スルーホール）", "pth_hole_min", "pth_hole_min", ">="),
    ("部品のスルーホールのアニュラリング", "pth_annular_min", "pth_annular_min", ">="),
    ("シルクの線の太さ", "silk_stroke_min", "silk_stroke_min", ">="),
    ("シルクの文字の高さ", "silk_height_min", "silk_height_min", ">="),
    ("基板上の刻印とランドのすきま", "silk_pad_clear_own", "silk_pad_clear_min", ">="),
    ("ランドどうしのすきま（マスクのブリッジ）", "mask_web_min", "mask_web_min", ">="),
    ("銅と縁の距離", "copper_edge_min", "copper_edge_min", ">="),
]
result = {}
fail_any = False
md_rows = []
print("\n== 発注先の公開仕様との照合 ==")
hdr = f"{'項目':34s} {'基板':>7s} " + " ".join(f"{f['name']:>13s}" for f in fabs.values())
print(hdr)
for label, mkey, rkey, _ in ROWS:
    v = M[mkey]
    cells = []
    for k, f in fabs.items():
        need = f.get(rkey)
        if need is None:
            cells.append("-")
            continue
        eps = 1e-9
        if v + eps >= need:
            st = "PASS"
            rec = f.get(rkey.replace("_min", "_recommended"))
            if rec is not None and v + eps < rec:
                st = "WARN"
        else:
            st = "FAIL"
            hp = f.get(rkey.replace("silk_stroke_min", "silk_hp_stroke_min").replace("silk_height_min", "silk_hp_height_min"))
            if rkey in ("silk_stroke_min", "silk_height_min") and hp is not None and v + eps >= hp:
                st = "FAIL*"                                                       # 高精度の文字なら通る
        cells.append(f"{st} ({need:g})")
        result.setdefault(k, {})[label] = st
        fail_any = fail_any or (st.startswith("FAIL") and True)
    print(f"{label:34s} {v:7.3f} " + " ".join(f"{c:>13s}" for c in cells))
    md_rows.append((label, v, cells))
# 外形・板厚
for k, f in fabs.items():
    ok_t = f["thickness"] is None or any(abs(thickness - t) < 1e-6 for t in f["thickness"])
    ok_s = f["size_min"] is None or (size[0] >= f["size_min"][0] and size[1] >= f["size_min"][1])
    result.setdefault(k, {})["板厚 1.6 mm"] = "PASS" if ok_t else "FAIL"
    result[k]["外形の大きさ"] = "PASS" if ok_s else "FAIL"
print("\n  FAIL* = 発注先の「高精度の文字」などの上位オプションなら通る（JLCPCB）。WARN = 最小は満たすが推奨値に届かない。- = 仕様に記載なし")
print("\n== 発注先ごとの結果 ==")
for k, f in fabs.items():
    r = result.get(k, {})
    nf = [a for a, s in r.items() if s.startswith("FAIL")]
    nw = [a for a, s in r.items() if s == "WARN"]
    print(f"  {f['name']:14s} FAIL {len(nf)} {nf}  WARN {len(nw)} {nw}")
if args.md:
    md = ["# 発注先の公開仕様との照合（`tools/check_fab_rules.py` が作る。手で直さない）", "",
          f"公開仕様の取得日 {rules['fetched']}。**公開ページの値との机上の照合であって、注文して確かめたものではない。** 発注の前に、発注ページの最新の値と照合すること。値は mm。括弧 = 発注先の最小（推奨）。",
          "", "| 項目 | 基板 | " + " | ".join(f["name"] for f in fabs.values()) + " |", "|---|---|" + "---|" * len(fabs)]
    for label, v, cells in md_rows:
        md.append(f"| {label} | {v:.3f} | " + " | ".join(cells) + " |")
    md += ["", "- `FAIL*` = 上位オプション（JLCPCB の「高精度の文字」: 線幅 0.10 以上・高さ 0.8 以上）なら通る。`WARN` = 最小は満たすが推奨値に届かない。`-` = 仕様に記載なし。",
           "- 基板の値の出し方: 配線・ビア・穴・シルクの太さと文字の高さは基板から直接。間隔と銅と縁はプロジェクトの規則（DRC が守る値）。ランドとのすきまは基板上の刻印について。ランドどうしのすきま 0.25 mm は半田ジャンパーの 3 パッドの間（わざとはんだでつなぐ）。",
           "- 部品の標準の枠（ライブラリのシルク）には、ランドに触れるものがある（最小 −0.075 mm）。ガーバーは `--subtract-soldermask` で、ランドの上のシルクを除いてある。JLCPCB は 0.15 mm 以内の文字を消すので、その部分の枠は欠ける（機能には影響しない）。",
           "", "## 板厚・外形", ""]
    for k, f in fabs.items():
        r = result.get(k, {})
        md.append(f"- {f['name']}: 板厚 1.6 mm {r.get('板厚 1.6 mm')}、外形の大きさ {r.get('外形の大きさ')}")
    md += ["", "## 出典（2026-10-05 取得）", ""]
    for k, f in fabs.items():
        md.append(f"- {f['name']}: " + "、".join(f["sources"]))
        if f.get("notes"):
            md.append(f"  - 注: {f['notes']}")
    pathlib.Path(args.md).write_text(chr(10).join(md) + chr(10), encoding="utf-8", newline=chr(10))
if args.json:
    pathlib.Path(args.json).write_text(json.dumps(dict(measured=M, result=result, fetched=rules["fetched"]), ensure_ascii=False, indent=1), encoding="utf-8")
sys.exit(1 if any(s.startswith("FAIL") and s == "FAIL" for r in result.values() for s in r.values()) else 0)
