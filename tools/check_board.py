#!/usr/bin/env python
"""基板の追加検査（DRC では見ないもの）。KiCad 同梱の Python で実行する:

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/check_board.py [--pcb head-sensor-board.kicad_pcb]

  1. J1/J2 の各パッドのネット名・形・位置が、回路図（ネットリスト）と上面の信号名の刻印に一致するか
     （ピン 1 = 四角いパッド。刻印の並びはピン 1 から VIN, GND, SCL, SDA, XSHUT, GPIO1）
  2. 上面の刻印（文字・線）が、ランド・ヘッダの樹脂部（2.54 mm 角）・ほかの刻印・基板の縁と重ならないか（枠どうしの重なり + 余裕 0.1 mm で判定）
終了コード: 問題があれば 1。
"""
import argparse
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import pcbnew
from pcbnew import ToMM

ROOT = pathlib.Path(__file__).resolve().parent.parent
KC = "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
ap = argparse.ArgumentParser()
ap.add_argument("--pcb", default=str(ROOT / "head-sensor-board.kicad_pcb"))
ap.add_argument("--margin", type=float, default=0.15, help="刻印と、ほかの部品のランド・ほかの刻印の最小のすきま [mm]（JLCPCB: ランドから 0.15 mm 以内の文字は消される。文字の線の間隔は 0.15 mm より大きく）")
ap.add_argument("--housing-margin", type=float, default=0.05, help="刻印とヘッダの樹脂部の最小のすきま [mm]")
ap.add_argument("--xiao-margin", type=float, default=0.225, help="刻印と XIAO の外形（枠線の中心）の最小のすきま [mm]。枠線の太さの半分 0.075 + 0.15")
args = ap.parse_args()

TOF_NAMES = ["VIN", "GND", "SCL", "SDA", "XSHUT", "GPIO1"]
EXPECT = {
    "J1": ["+3V3", "GND", "/SCL", "/SDA", "/XSHUT_L", "/TOF_L_INT"],
    "J2": ["+3V3", "GND", "/SCL", "/SDA", "/XSHUT_R", "/TOF_R_INT"],
}
problems = []


def schematic_nets():
    """回路図から kicad-cli で出したネットリストの (部品, ピン) → ネット名。"""
    with tempfile.TemporaryDirectory() as d:
        out = pathlib.Path(d) / "n.xml"
        subprocess.run([KC, "sch", "export", "netlist", "--format", "kicadxml", "--output", str(out), str(ROOT / "head-sensor-board.kicad_sch")],
                       check=True, capture_output=True)
        root = ET.parse(out).getroot()
    m = {}
    for n in root.find("nets"):
        for node in n.findall("node"):
            m[(node.get("ref"), node.get("pin"))] = n.get("name")
    pinnames = {}
    for c in root.find("libparts") if root.find("libparts") is not None else []:
        pass
    return m


def bbox(item):
    b = item.GetBoundingBox()
    return (ToMM(b.GetLeft()), ToMM(b.GetTop()), ToMM(b.GetRight()), ToMM(b.GetBottom()))


def gap(a, b):
    """2 つの枠（x0, y0, x1, y1）のすきま。重なっていれば負。"""
    dx = max(a[0] - b[2], b[0] - a[2])
    dy = max(a[1] - b[3], b[1] - a[3])
    if dx < 0 and dy < 0:
        return max(dx, dy)
    return max(dx, dy) if (dx >= 0) != (dy >= 0) else (dx * dx + dy * dy) ** 0.5


board = pcbnew.LoadBoard(args.pcb)
sch = schematic_nets()

# ------------------------------------------------------------------ 1. J1 / J2
print("== J1 / J2: パッド ↔ 回路図のネット ↔ 刻印 ==")
silk_texts = [d for d in board.GetDrawings() if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.F_SilkS]
for ref in ("J1", "J2"):
    fp = board.FindFootprintByReference(ref)
    pads = sorted(fp.Pads(), key=lambda p: int(p.GetNumber()))
    x1 = ToMM(pads[0].GetPosition().x)
    print(f"{ref}: ピン 1 の x = {x1 - ToMM(board.GetBoundingBox().GetX()):.2f} mm（基板の左端から）, 向き {fp.GetOrientationDegrees():.0f}°")
    for p in pads:
        n = int(p.GetNumber())
        net_pcb = p.GetNetname()
        net_sch = sch.get((ref, p.GetNumber()))
        shape = "四角" if p.GetShape() == pcbnew.PAD_SHAPE_RECTANGLE else "丸"
        px, py = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
        # このピンの刻印: 中心の x がピンの x に最も近い、J の近くの文字
        cand = [t for t in silk_texts if t.GetText() in TOF_NAMES and abs(ToMM(t.GetPosition().x) - px) < 0.2 and abs(ToMM(t.GetPosition().y) - py) < 4.0]
        label = cand[0].GetText() if cand else "（なし）"
        ok_net = net_pcb == net_sch == EXPECT[ref][n - 1]
        ok_label = label == TOF_NAMES[n - 1]
        ok_shape = (n == 1) == (p.GetShape() == pcbnew.PAD_SHAPE_RECTANGLE)
        print(f"  pin{n}: パッド {shape}  基板のネット {net_pcb:12s} 回路図のネット {str(net_sch):12s} 刻印 {label:6s}  "
              f"{'OK' if ok_net and ok_label and ok_shape else 'NG'}")
        if not (ok_net and ok_label and ok_shape):
            problems.append(f"{ref} pin{n}: net {net_pcb}/{net_sch} (expect {EXPECT[ref][n - 1]}), label {label} (expect {TOF_NAMES[n - 1]}), shape {shape}")
    xs = [ToMM(p.GetPosition().x) for p in pads]
    print(f"  ピン番号が増える向き: {'右 → 左（pin1 が右端）' if xs[0] > xs[-1] else '左 → 右（pin1 が左端）'}；刻印の並び（左から）: "
          + " ".join(t.GetText() for t in sorted([c for p in pads for c in silk_texts if c.GetText() in TOF_NAMES and abs(ToMM(c.GetPosition().x) - ToMM(p.GetPosition().x)) < 0.2 and abs(ToMM(c.GetPosition().y) - ToMM(p.GetPosition().y)) < 4.0],
                                                  key=lambda t: ToMM(t.GetPosition().x))))

# ------------------------------------------------------------------ 2. 刻印のすきま
# 刻印の形: 文字 = 実際の筆の跡の枠（KiCad の文字の枠より小さい）、線・四角・円弧 = 線分に分けて太さの半分をふくらませる。
# 相手: ランド（ほかの部品のもの）、ヘッダの樹脂部（2.54 mm 角）、ほかの刻印、XIAO の外形（上に載るので中の刻印は見えない）、基板の縁。
print("== 上面の刻印のすきま（ランド・刻印 %.2f mm、樹脂部 %.2f mm、XIAO の枠 %.3f mm）==" % (args.margin, args.housing_margin, args.xiao_margin))


def seg_points(a, b, step=0.05):
    n = max(1, int(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 / step))
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


def shape_prims(d):
    """PCB_SHAPE → [(点列, 半幅)]"""
    w = ToMM(d.GetWidth()) / 2
    kind = d.GetShape()
    S = lambda v: (ToMM(v.x), ToMM(v.y))                                   # noqa: E731
    if kind == pcbnew.SHAPE_T_SEGMENT:
        return [(seg_points(S(d.GetStart()), S(d.GetEnd())), w)]
    if kind == pcbnew.SHAPE_T_RECTANGLE:
        x0, y0, x1, y1 = bbox(d)
        x0, y0, x1, y1 = x0 + w, y0 + w, x1 - w, y1 - w
        c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return [(seg_points(c[i], c[(i + 1) % 4]), w) for i in range(4)]
    x0, y0, x1, y1 = bbox(d)                                               # 円弧など: 枠で代用（小さい）
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [(seg_points(c[i], c[(i + 1) % 4]), 0) for i in range(4)]


def text_box(t):
    b = t.GetEffectiveTextShape().BBox()
    return (ToMM(b.GetLeft()), ToMM(b.GetTop()), ToMM(b.GetRight()), ToMM(b.GetBottom()))


def pt_gap(pt, bb):
    dx = max(bb[0] - pt[0], 0, pt[0] - bb[2])
    dy = max(bb[1] - pt[1], 0, pt[1] - bb[3])
    return (dx * dx + dy * dy) ** 0.5


def prim_box_gap(prims, bb):
    return min(pt_gap(p, bb) - hw for pts, hw in prims for p in pts)


def prim_prim_gap(pa, pb):
    best = 9e9
    for ptsa, wa in pa:
        for ptsb, wb in pb:
            for p in ptsa[::2]:
                for q in ptsb[::2]:
                    best = min(best, ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 - wa - wb)
    return best


items = []                    # dict(name, owner, box=None | (x0,y0,x1,y1), prims=None | [...])
for d in board.GetDrawings():
    if d.GetLayer() != pcbnew.F_SilkS:
        continue
    if isinstance(d, pcbnew.PCB_TEXT):
        items.append(dict(name=f"文字 {d.GetText()}", owner="board", box=text_box(d), prims=None))
    elif isinstance(d, pcbnew.PCB_SHAPE):
        pr = shape_prims(d)
        x = ToMM(d.GetStart().x)
        items.append(dict(name=f"線({ToMM(d.GetStart().x) - ToMM(board.GetBoardEdgesBoundingBox().GetLeft()):.1f},{ToMM(d.GetStart().y) - ToMM(board.GetBoardEdgesBoundingBox().GetTop()):.1f})",
                          owner="board", box=None, prims=pr))
for fp in board.GetFootprints():
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_SilkS and isinstance(g, pcbnew.PCB_SHAPE):
            items.append(dict(name=f"{fp.GetReference()} の刻印", owner=fp.GetReference(), box=None, prims=shape_prims(g)))
    for f in fp.GetFields():
        if f.GetLayer() == pcbnew.F_SilkS and f.IsVisible():
            items.append(dict(name=f"{fp.GetReference()}.{f.GetName()}", owner=fp.GetReference(), box=text_box(f), prims=None))
obstacles = []
u1_outline = None
for fp in board.GetFootprints():
    for p in fp.Pads():
        obstacles.append((fp.GetReference(), f"{fp.GetReference()}.{p.GetNumber()}", bbox(p)))
    if fp.GetReference() in ("J1", "J2", "J3", "J4"):
        pts = [p.GetPosition() for p in fp.Pads()]
        xs, ys = [ToMM(q.x) for q in pts], [ToMM(q.y) for q in pts]
        obstacles.append((fp.GetReference(), f"{fp.GetReference()} の樹脂部", (min(xs) - 1.27, min(ys) - 1.27, max(xs) + 1.27, max(ys) + 1.27)))
    if fp.GetReference() == "U1":
        c = fp.GetPosition()
        u1_outline = (ToMM(c.x) - 10.5, ToMM(c.y) - 8.9, ToMM(c.x) + 10.5, ToMM(c.y) + 8.9)
eb = board.GetBoardEdgesBoundingBox()
edge = (ToMM(eb.GetLeft()), ToMM(eb.GetTop()), ToMM(eb.GetRight()), ToMM(eb.GetBottom()))


def inside_u1(it):
    """XIAO の下にある部品の刻印（上から見えない）は、XIAO の外形との比較から外す。"""
    if it["owner"] == "board" or u1_outline is None:
        return False
    fp = board.FindFootprintByReference(it["owner"])
    c = fp.GetPosition()
    return u1_outline[0] < ToMM(c.x) < u1_outline[2] and u1_outline[1] < ToMM(c.y) < u1_outline[3]


for it in items:
    def g_box(bb):
        return pt_gap_box(it, bb)

    def pt_gap_box(it, bb):
        if it["box"] is not None:
            return gap(it["box"], bb)
        return prim_box_gap(it["prims"], bb)

    for owner, oname, ob in obstacles:
        if owner == it["owner"]:
            continue
        g = pt_gap_box(it, ob)
        if g < (args.housing_margin if "樹脂部" in oname else args.margin):
            problems.append(f"{it['name']} ↔ {oname}: すきま {g:.2f} mm")
    if u1_outline is not None and it["owner"] != "U1" and not inside_u1(it):
        g = pt_gap_box(it, u1_outline)
        if g < args.xiao_margin:
            problems.append(f"{it['name']} ↔ XIAO の外形: すきま {g:.2f} mm")
    bbs = it["box"] or (min(p[0] for pts, _ in it["prims"] for p in pts), min(p[1] for pts, _ in it["prims"] for p in pts),
                        max(p[0] for pts, _ in it["prims"] for p in pts), max(p[1] for pts, _ in it["prims"] for p in pts))
    if bbs[0] < edge[0] + 0.2 or bbs[1] < edge[1] + 0.2 or bbs[2] > edge[2] - 0.2 or bbs[3] > edge[3] - 0.2:
        problems.append(f"{it['name']}: 基板の縁から 0.2 mm 未満")
for i in range(len(items)):
    for j in range(i + 1, len(items)):
        a_, b_ = items[i], items[j]
        if a_["owner"] == b_["owner"] and a_["owner"] != "board":
            continue
        if a_["box"] is not None and b_["box"] is not None:
            g = gap(a_["box"], b_["box"])
        elif a_["box"] is not None:
            g = prim_box_gap(b_["prims"], a_["box"])
        elif b_["box"] is not None:
            g = prim_box_gap(a_["prims"], b_["box"])
        else:
            if a_["owner"] == "board" and b_["owner"] == "board":
                continue                                                  # 矢印の線どうしは、つながっている
            if a_["owner"] != "board" and b_["owner"] != "board":
                continue                                                  # 部品どうしの刻印は標準ライブラリのまま
            g = prim_prim_gap(a_["prims"], b_["prims"])
        if g < args.margin:
            problems.append(f"{a_['name']} ↔ {b_['name']}: すきま {g:.2f} mm")
print(f"検査した刻印 {len(items)} 個、ランド・樹脂部 {len(obstacles)} 個")
for p in problems:
    print("  NG:", p)
print("RESULT:", "OK" if not problems else f"{len(problems)} 件の問題")
sys.exit(1 if problems else 0)
