#!/usr/bin/env python
"""Stage 3: 基板の外形と部品配置（配線なし）を作る。KiCad 同梱の Python で実行する:

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/gen_pcb.py [--width 40] [--height 25] [--corner 1.0] [--hole-inset 2.4]

- 外形（Edge.Cuts）と M2 穴は、幅・高さ・角 R・穴の位置から作り直せる（変数）。
- 部品は「左端からの距離」「右端からの距離」「中心線からの距離」で置く（placement()）。幅・高さを変えると、右の縁・上下の縁に寄せた部品は縁についてくる。
  小さくしすぎると部品が重なる → 実行後に DRC（courtyards_overlap）で確かめる。
- 回路図（head-sensor-board.kicad_sch）から kicad-cli でネットリストを出し、フットプリントの割り当て・ネット・フィールド・回路図との対応（path）を付ける。
- **既存の配線・部品は消して作り直す**（空の雛形 tools/pcb_template.kicad_pcb から。Stage 4 で配線した後は実行しない）。
- 配置図 PNG（docs/placement_annotated.png）も作る（PIL。tools/render_placement.py）。
"""
import argparse
import json
import math
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import pcbnew
from pcbnew import FromMM, ToMM, VECTOR2I

ROOT = pathlib.Path(__file__).resolve().parent.parent
KC = "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
STD_FP = pathlib.Path("C:/Program Files/KiCad/10.0/share/kicad/footprints")
SCH = ROOT / "head-sensor-board.kicad_sch"
PCB = ROOT / "head-sensor-board.kicad_pcb"
_out = None

ap = argparse.ArgumentParser()
ap.add_argument("--width", type=float, default=40.0)
ap.add_argument("--height", type=float, default=25.0)
ap.add_argument("--corner", type=float, default=1.0, help="角 R [mm]")
ap.add_argument("--hole-inset", type=float, default=2.1, help="M2 穴の中心から縁までの距離 [mm]")
ap.add_argument("--xiao-inset", type=float, default=0.6, help="XIAO の USB-C 側の端と基板の左端の距離 [mm]（銀色の枠が縁にかからないように）")
ap.add_argument("--no-render", action="store_true")
ap.add_argument("--out", default=None, help="出力先の .kicad_pcb（既定: プロジェクトの基板。試すときは別フォルダにして、配置図・JSON は作らない）")
args = ap.parse_args()
W, H, CR, HI, XO = args.width, args.height, args.corner, args.hole_inset, args.xiao_inset
if args.out:
    PCB = pathlib.Path(args.out)
YC = H / 2.0
X0, Y0 = (297.0 - W) / 2.0, (210.0 - H) / 2.0          # A4 の中央に置く


def P(x, y):
    return VECTOR2I(FromMM(X0 + x), FromMM(Y0 + y))


# ---------------------------------------------------------------------------------------------- 配置
# 座標は基板の左上を (0, 0)、x は右、y は下（KiCad と同じ）。rot は反時計回り [度]。
# 下半分 = L チャンネル（XIAO の D0〜D6 の列に近い側）、上半分 = R チャンネル。R は L の鏡像（中心線 YC で反転）。
def mirror(y):
    return 2 * YC - y


def col(i):
    """XIAO のピン列の x 座標（i = 0..6。USB-C 側から）。"""
    return XO + 2.88 + 2.54 * i


def placement():
    p = {}
    # --- XIAO: USB-C を左の縁に向ける（ケーブルは左に出る）。
    #     ピン列: 下の列 = pin1〜7（D0〜D6）、上の列 = pin14〜8（5V, GND, 3V3, D10, D9, D8, D7）
    p["U1"] = dict(x=XO + 10.5, y=YC, rot=90)
    # --- M2 穴: 右の 2 つの角（LED の縁側）。左の角は XIAO のピン列の帯と重なるので使わない
    p["H1"] = dict(x=W - HI, y=HI, rot=0)
    p["H2"] = dict(x=W - HI, y=H - HI, rot=0)
    # --- ToF ヘッダ: 上下の長辺の縁（ジャンパー線を縁から出す）。pin1 が左
    p["J1"] = dict(x=14.4, y=H - 1.7, rot=90)
    p["J2"] = dict(x=14.4, y=1.7, rot=90)
    # --- LED: 右の縁（LED の縁）。外付け LED ヘッダ J3/J4: 上下の長辺の縁の右寄り（pin1 = +、pin2 = −。左から右）
    p["D1"] = dict(x=W - 3.0, y=YC + 5.1, rot=0)          # 左がカソード、右がアノード
    p["J3"] = dict(x=W - 9.3, y=H - 1.7, rot=90)
    p["Q1"] = dict(x=W - 7.4, y=YC + 3.0, rot=0)
    p["R9"] = dict(x=W - 8.4, y=YC + 6.3, rot=270)
    p["SJ1"] = dict(x=W - 12.4, y=YC + 7.1, rot=0)
    p["R1"] = dict(x=W - 16.6, y=YC + 7.1, rot=0)
    p["TP7"] = dict(x=W - 11.8, y=YC + 2.6, rot=0)
    for a, b in (("D2", "D1"), ("J4", "J3"), ("Q2", "Q1"), ("R10", "R9"), ("SJ2", "SJ1"), ("R2", "R1"), ("TP8", "TP7")):
        q = dict(p[b])
        q["y"] = mirror(q["y"])
        q["rot"] = q["rot"] if a == "J4" else (-q["rot"]) % 360      # ヘッダは向きをそろえる（pin1 が左）
        p[a] = q
    p["TP2"] = dict(x=W - 11.8, y=YC, rot=0)             # GND: ILED の TP（TP7 / TP8）のすぐ隣
    # --- XIAO の下（ソケットの内側。高さ 0.9 mm 以下の 0603 / 2010 だけ）
    p["R3"] = dict(x=XO + 3.6, y=YC - 4.2, rot=0)
    p["R4"] = dict(x=XO + 3.6, y=YC - 0.7, rot=0)
    p["C1"] = dict(x=XO + 10.5, y=YC - 4.3, rot=270)
    for ref, i, rot in (("R11", 0, 270), ("R12", 1, 270), ("R5", 2, 90), ("R6", 3, 90), ("R13", 4, 270), ("R14", 5, 270)):
        p[ref] = dict(x=col(i), y=YC + 4.4, rot=rot)                     # 下の列（D0〜D5）の真上
    p["R7"] = dict(x=col(2), y=YC + 1.1, rot=90)
    p["R8"] = dict(x=col(3), y=YC + 1.1, rot=90)
    p["R16"] = dict(x=col(4), y=YC - 4.6, rot=270)                       # 上の列の D9 の真下
    p["R15"] = dict(x=col(5), y=YC - 4.6, rot=270)                       # D8
    p["C2"] = dict(x=col(6), y=YC - 4.6, rot=270)
    p["C3"] = dict(x=col(6), y=YC + 4.4, rot=270)
    # --- テストポイント: 上の縁 = 電源と I2C（3V3・SCL・SDA）、下の縁 = XSHUT、右ゾーン = 電流（ILED）と GND
    for ref, x in (("TP1", 1.6), ("TP3", 4.9), ("TP4", 8.2)):
        p[ref] = dict(x=x, y=1.8, rot=0)
    for ref, x in (("TP5", 1.6), ("TP6", 4.9)):
        p[ref] = dict(x=x, y=H - 1.8, rot=0)
    return p


# 部品名を上面の刻印に出すもの（ほかは Fab 層。小さい部品の刻印は重なって読めないため）。値は (dx, dy) = 部品の中心からの位置
SILK_REF = {"J1": (9.6, -2.4), "J2": (9.6, 2.4)}

# 上面の刻印: (文字, x, y, 大きさ, 配置, 角度)。配置 = "l" 左寄せ / "r" 右寄せ / "c" 中央
def silk_items(pl):
    it = []
    tp = lambda ref: (pl[ref]["x"], pl[ref]["y"])                        # noqa: E731
    # 上下の縁の TP（3.3 mm ピッチ）は、名前を縦書き（90°）にして、ランドの右に置く
    for ref, name in (("TP1", "3V3"), ("TP3", "SCL"), ("TP4", "SDA"), ("TP5", "XSL"), ("TP6", "XSR")):
        x, y = tp(ref)
        it.append((name, x + 1.65, y, 0.8, "c", 90))
    for ref, name in (("TP2", "GND"), ("TP7", "ILL"), ("TP8", "ILR")):
        x, y = tp(ref)
        it.append((name, x - 1.25, y, 0.8, "r", 0))
    for sj in ("SJ1", "SJ2"):
        x, y = tp(sj)
        dy = -2.6 if sj == "SJ1" else 2.6
        it.append(("3V3", x - 1.3, y + dy, 0.8, "c", 0))
        it.append(("5V", x + 1.3, y + dy, 0.8, "c", 0))
    for j, dy in (("J3", -2.4), ("J4", 2.4)):
        x, y = tp(j)
        it.append(("+", x, y + dy, 0.8, "c", 0))
        it.append(("-", x + 2.54, y + dy, 0.8, "c", 0))
    it.append(("L", pl["D1"]["x"], pl["D1"]["y"] + 1.75, 0.8, "c", 0))
    it.append(("R", pl["D2"]["x"], pl["D2"]["y"] - 1.75, 0.8, "c", 0))
    return it


# 裏面の凡例（B.SilkS、鏡文字）: 右のゾーン中央。裏から読める
BACK_LEGEND = ["HSB REV A", "L=LOWER", "R=UPPER", "TOF ORDER", "TBD"]


# ---------------------------------------------------------------------------------------------- ネットリスト
def read_netlist():
    with tempfile.TemporaryDirectory() as d:
        out = pathlib.Path(d) / "n.xml"
        subprocess.run([KC, "sch", "export", "netlist", "--format", "kicadxml", "--output", str(out), str(SCH)],
                       check=True, capture_output=True)
        root = ET.parse(out).getroot()
    comps = {}
    for c in root.find("components"):
        ref = c.get("ref")
        if ref.startswith("#"):
            continue
        props = {p.get("name"): p.get("value") for p in c.findall("property")}
        fields = {f.get("name"): (f.text or "") for f in c.find("fields")} if c.find("fields") is not None else {}
        comps[ref] = dict(value=c.findtext("value"), fp=c.findtext("footprint"), uuid=c.findtext("tstamps"),
                          props=props, fields=fields, dnp="dnp" in props)
    nets = {}
    for n in root.find("nets"):
        nodes = [(x.get("ref"), x.get("pin")) for x in n.findall("node") if not x.get("ref").startswith("#")]
        if nodes:
            name = n.get("name")
            if name.startswith("unconnected-("):
                name = name.replace("/", "{slash}")           # KiCad が自動でつける名前の書き方に合わせる
            nets[name] = nodes
    return comps, nets


def fp_dir_and_name(fp_id):
    lib, name = fp_id.split(":")
    d = ROOT / "libs" / f"{lib}.pretty" if lib == "head-sensor-board" else STD_FP / f"{lib}.pretty"
    return lib, name, str(d)


# ---------------------------------------------------------------------------------------------- 外形
def edge_cuts(board):
    L = pcbnew.Edge_Cuts
    seg_w = FromMM(0.05)

    def seg(a, b):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(L)
        s.SetStart(P(*a))
        s.SetEnd(P(*b))
        s.SetWidth(seg_w)
        board.Add(s)

    def arc(c, start, end):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetLayer(L)
        ang = lambda p: math.atan2(p[1] - c[1], p[0] - c[0])            # noqa: E731
        a0, a1 = ang(start), ang(end)
        d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi                 # -π..π
        am = a0 + d / 2
        mid = (c[0] + CR * math.cos(am), c[1] + CR * math.sin(am))
        s.SetArcGeometry(P(*start), P(*mid), P(*end))
        s.SetWidth(seg_w)
        board.Add(s)

    r = CR
    seg((r, 0), (W - r, 0))
    seg((W, r), (W, H - r))
    seg((W - r, H), (r, H))
    seg((0, H - r), (0, r))
    arc((r, r), (0, r), (r, 0))
    arc((W - r, r), (W - r, 0), (W, r))
    arc((W - r, H - r), (W, H - r), (W - r, H))
    arc((r, H - r), (r, H), (0, H - r))


def add_text(board, text, x, y, rot, size, layer, just="c", mirrored=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetLayer(layer)
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
    t.SetTextThickness(FromMM(0.12))
    t.SetPosition(P(x, y))
    t.SetTextAngleDegrees(rot)
    t.SetHorizJustify({"l": pcbnew.GR_TEXT_H_ALIGN_LEFT, "r": pcbnew.GR_TEXT_H_ALIGN_RIGHT, "c": pcbnew.GR_TEXT_H_ALIGN_CENTER}[just])
    t.SetMirrored(mirrored)
    board.Add(t)
    return t


# ---------------------------------------------------------------------------------------------- 本体
def build():
    comps, nets = read_netlist()
    # 空の雛形（層・設定だけ）から作り直す。board.Remove() で消す方式は SWIG が壊れるので使わない
    PCB.write_text((ROOT / "tools" / "pcb_template.kicad_pcb").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    board = pcbnew.LoadBoard(str(PCB))
    netobj = {}
    for name in sorted(nets):
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        netobj[name] = n
    pad_net = {}
    for name, nodes in nets.items():
        for ref, pin in nodes:
            pad_net[(ref, pin)] = name
    place = placement()
    for ref, c in sorted(comps.items()):
        lib, name, d = fp_dir_and_name(c["fp"])
        fp = pcbnew.FootprintLoad(d, name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))                     # 'ライブラリ:名前'（回路図の割り当てと一致させる）
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        pos = place[ref]
        fp.SetPosition(P(pos["x"], pos["y"]))
        fp.SetOrientationDegrees(pos["rot"])
        fp.SetPath(pcbnew.KIID_PATH("/" + c["uuid"]))
        fp.SetSheetname("/")
        fp.SetSheetfile(SCH.name)
        if "dnp" in c["props"] or ref in ("R13", "R14", "R15", "R16"):
            fp.SetDNP(True)
        attrs = fp.GetAttributes()                               # 「BOM から除外」は回路図のシンボルに合わせる
        attrs = (attrs | pcbnew.FP_EXCLUDE_FROM_BOM) if "exclude_from_bom" in c["props"] else (attrs & ~pcbnew.FP_EXCLUDE_FROM_BOM)
        fp.SetAttributes(attrs)
        # 回路図のシンボルのフィールド（MPN・Rating など）を基板側にも持たせる（回路図との対応の検査で要る）
        for k, v in c["fields"].items():
            if k == "Footprint":
                continue
            fp.SetField(k, v)
            for f in fp.GetFields():
                if f.GetName() == k and k not in ("Reference", "Value"):
                    f.SetVisible(False)
                    f.SetLayer(pcbnew.F_Fab)
        # 部品名: 大きめの部品だけ上面の刻印、ほかは Fab 層
        r = fp.Reference()
        r.SetTextSize(VECTOR2I(FromMM(0.8), FromMM(0.8)))
        r.SetTextThickness(FromMM(0.12))
        if ref in SILK_REF:
            r.SetLayer(pcbnew.F_SilkS)
            r.SetPosition(P(pos["x"] + SILK_REF[ref][0], pos["y"] + SILK_REF[ref][1]))
            r.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
            r.SetTextAngleDegrees(0)                             # 部品が回転していても、文字は横書き
        else:
            r.SetLayer(pcbnew.F_Fab)
            r.SetPosition(P(pos["x"], pos["y"]))
        if ref.startswith("TP") or ref == "U1":
            r.SetVisible(False) if ref.startswith("TP") else None
        fp.Value().SetLayer(pcbnew.F_Fab)
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            if key in pad_net:
                pad.SetNet(netobj[pad_net[key]])
        board.Add(fp)
    edge_cuts(board)
    for text, x, y, size, just, rot in silk_items(place):
        add_text(board, text, x, y, rot, size, pcbnew.F_SilkS, just)
    for i, line in enumerate(BACK_LEGEND):                          # 裏面の凡例（鏡文字）
        add_text(board, line, W - 6.0, YC - 2.4 + i * 1.2, 0, 0.8, pcbnew.B_SilkS, "c", mirrored=True)
    board.Save(str(PCB))
    return board, comps, nets


def geometry(board, nets):
    """配置図用の幾何（基板左上を原点とする mm）。"""
    out = dict(W=W, H=H, CR=CR, fps=[], nets={k: [] for k in nets}, silk=[])

    def rel(v):
        return (ToMM(v.x) - X0, ToMM(v.y) - Y0)

    for fp in board.GetFootprints():
        fp.BuildCourtyardCaches()
        cy = []
        poly = fp.GetCourtyard(pcbnew.F_CrtYd)
        for i in range(poly.OutlineCount()):
            ol = poly.Outline(i)
            cy.append([rel(ol.CPoint(j)) for j in range(ol.PointCount())])
        pads = []
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            c = rel(pad.GetPosition())
            pads.append(dict(n=pad.GetNumber(), c=c, w=ToMM(bb.GetWidth()), h=ToMM(bb.GetHeight()),
                             drill=ToMM(pad.GetDrillSize().x) if pad.HasHole() else 0, net=pad.GetNetname(),
                             shape="round" if pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE else "rect"))
            if pad.GetNetname():
                out["nets"].setdefault(pad.GetNetname(), []).append(dict(ref=fp.GetReference(), n=pad.GetNumber(), c=c))
        out["fps"].append(dict(ref=fp.GetReference(), value=fp.GetValue(), c=rel(fp.GetPosition()), rot=fp.GetOrientationDegrees(),
                               court=cy, pads=pads, dnp=fp.IsDNP()))
    for d in board.GetDrawings():
        if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.F_SilkS:
            out["silk"].append(dict(text=d.GetText(), c=rel(d.GetPosition()), rot=d.GetTextAngleDegrees(), h=ToMM(d.GetTextHeight())))
    return out


if __name__ == "__main__":
    board, comps, nets = build()
    print(f"PCB saved: {PCB}  board {W} x {H} mm, corner R{CR}, {len(comps)} footprints")
    if args.out:
        sys.exit(0)                      # 試作の出力では配置図・JSON は作らない
    geo = geometry(board, nets)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "placement_geometry.json").write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    if not args.no_render:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import render_placement
        render_placement.render(geo, ROOT / "docs" / "placement_annotated.png")
