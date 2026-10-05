#!/usr/bin/env python
"""基板の外形・部品配置・刻印（配線なし）を作る。KiCad 同梱の Python で実行する（普通は tools/make_board.py が呼ぶ）:

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/gen_pcb.py [--width 44] [--height 28] [--corner 1.0] [--hole-inset 2.1]

- 外形（Edge.Cuts）と M2 穴は、幅・高さ・角 R・穴の位置から作り直せる（変数）。
- 部品は「左端からの距離」「右端からの距離」「中心線からの距離」で置く（placement()）。幅・高さを変えると、右の縁・上下の縁に寄せた部品は縁についてくる。
  小さくしすぎると部品が重なる → 実行後に DRC（courtyards_overlap）で確かめる。
- 回路図（head-sensor-board.kicad_sch）から kicad-cli でネットリストを出し、フットプリントの割り当て・ネット・フィールド・回路図との対応（path）を付ける。
- **既存の配線・部品は消して作り直す**（空の雛形 tools/pcb_template.kicad_pcb から）。配線は tools/route.py + tools/apply_routes.py が付け直す（make_board.py）。
- 配置図 PNG（docs/placement_annotated.png。配線なしの図。PIL、tools/render_placement.py）は --no-render で省く（make_board.py は省く）。
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
ap.add_argument("--width", type=float, default=44.0)
ap.add_argument("--height", type=float, default=28.0)
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


JEDGE = 1.45                  # ToF ヘッダのピンの中心から基板の縁までの距離 [mm]（ランドの縁から 0.6 mm。配線 routes.json はこの位置で作ってある）


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
    # --- ToF ヘッダ: 上下の長辺の縁（ジャンパー線を縁から出す）。180° 回して pin1 を右にする
    #     （XIAO の SDA（D4）が SCL（D5）の左にあるのと、ヘッダの SDA が SCL の左にある向きをそろえて、配線を交差させない）。
    #     ピンの x は XIAO のピン列と同じ 2.54 mm の格子に乗せる（col(7) = 21.26 の 1 つ右 = col(8)）
    p["J1"] = dict(x=col(8), y=H - JEDGE, rot=270)                     # 縁寄り（ランドの縁から 0.6 mm）。内側に信号名の 2 段を置く余地をつくる
    p["J2"] = dict(x=col(8), y=JEDGE, rot=270)
    # --- LED: 右の縁（LED の縁）。外付け LED ヘッダ J3/J4: 上下の長辺の縁の右寄り（pin1 = +、pin2 = −。左から右）
    #     L チャンネル（下半分）の流れ: 3V3 → R1 → SJ1 の pad1、5V → R3 → SJ1 の pad3、pad2 → LED のアノード
    p["D1"] = dict(x=W - 3.0, y=YC + 5.6, rot=0)          # 左がカソード、右がアノード
    p["J3"] = dict(x=W - 9.3, y=H - 1.7, rot=90)
    p["Q1"] = dict(x=W - 7.6, y=YC + 3.6, rot=0)
    p["R9"] = dict(x=W - 8.6, y=YC + 7.0, rot=270)
    p["SJ1"] = dict(x=W - 12.8, y=YC + 7.0, rot=270)      # 縦並び（pad1 が上、pad3 が下）。pad2 は右へ出る
    p["R1"] = dict(x=W - 17.4, y=YC + 5.7, rot=0)
    p["TP7"] = dict(x=W - 12.2, y=YC + 2.6, rot=0)
    for a, b in (("D2", "D1"), ("J4", "J3"), ("Q2", "Q1"), ("R10", "R9"), ("SJ2", "SJ1"), ("R2", "R1"), ("TP8", "TP7")):
        q = dict(p[b])
        q["y"] = mirror(q["y"])
        q["rot"] = q["rot"] if a == "J4" else (-q["rot"]) % 360      # ヘッダは向きをそろえる（pin1 が左）
        p[a] = q
    p["TP2"] = dict(x=W - 12.2, y=YC, rot=0)             # GND: ILED の TP（TP7 / TP8）のすぐ隣
    # --- XIAO の下（ソケットの内側。高さ 0.9 mm 以下の 0603 / 2010 だけ）
    p["R4"] = dict(x=XO + 3.6, y=YC - 3.9, rot=0)         # 5V の 33 Ω（R チャンネル = 上）
    p["R3"] = dict(x=XO + 3.6, y=YC + 0.5, rot=0)         # 5V の 33 Ω（L チャンネル = 下）
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
    for ref, x in (("TP1", 1.5), ("TP3", 4.6), ("TP4", 7.7)):
        p[ref] = dict(x=x, y=1.8, rot=0)
    p["TP5"] = dict(x=27.4, y=H - 1.8, rot=0)             # XSHUT_L: 下の縁（J1 の右）
    p["TP6"] = dict(x=27.4, y=1.8, rot=0)                 # XSHUT_R: 上の縁（J2 の右）
    return p


# 部品名を上面の刻印に出すもの（ほかは Fab 層。小さい部品の刻印は重なって読めないため）
SILK_REF = {}

TOF_PINS = ["VIN", "GND", "SCL", "SDA", "XSHUT", "GPIO1"]       # J1 / J2 のピン 1〜6（仮。ToF 小基板の実物で確かめる）


# シルクの線の太さ: 発注先の最小値（JLCPCB の標準 0.15、PCBWay 0.15、Elecrow 0.15、Seeed Fusion 0.10 mm）に合わせて 0.15 mm（EXP-K-0001）。文字の高さ 0.8 mm のまま
SILK_THK = 0.15
# 文字の筆の跡の枠（KiCad で測った値。大きさ 0.8 mm・太さ 0.15 mm の英大文字・数字）: 高さ 0.95 mm、中心からの上端 -0.51 / 下端 +0.44
GLYPH_UP, GLYPH_DN = 0.51, 0.44
HOUSING = 1.27                # ピンヘッダの樹脂部（2.54 mm 角）の半分
SILK_GAP = 0.20               # 刻印とランドのすきま（JLCPCB は 0.15 mm 以内の文字を消す）
HOUSING_GAP = 0.08            # 刻印と樹脂部のすきま（樹脂部は印刷ではないので小さくてよい）
ROW_GAP = 0.16                # 文字の行どうしのすきま（JLCPCB: 文字の線の間隔 0.15 mm より大きく）
XIAO_GAP = 0.15               # 刻印と XIAO の枠線（シルク）のすきま
SJ_SILK = 2.30                # 縦並びの半田ジャンパーの中心から、名前の文字の端までの距離（SJ の標準の枠は中心線が約 2.05 mm、線の太さ 0.15 mm で外縁 2.125 mm）


def tof_rows(jy, sgn):
    """ToF ヘッダの信号名 2 段の文字の中心 y（手前 = ピンに近い段 A、奥 = 段 B）。樹脂部の外に置く。sgn = +1: 内側が +y（J2）、-1: 内側が -y（J1）。"""
    edge = jy + sgn * HOUSING                                       # 樹脂部の内側の端
    if sgn > 0:
        a = edge + HOUSING_GAP + GLYPH_UP                           # 文字の上端 = 端 + すきま
        b = a + GLYPH_DN + ROW_GAP + GLYPH_UP
    else:
        a = edge - HOUSING_GAP - GLYPH_DN                           # 文字の下端 = 端 - すきま
        b = a - GLYPH_UP - ROW_GAP - GLYPH_DN
    return a, b


# 上面の刻印: (文字, x, y, 大きさ, 配置, 角度)。配置 = "l" 左寄せ / "r" 右寄せ / "c" 中央
def silk_items(pl):
    it = []
    tp = lambda ref: (pl[ref]["x"], pl[ref]["y"])                        # noqa: E731
    # 縁の TP は、名前をランドの内側（基板の中心側）に横書きで置く
    for ref, name in (("TP1", "3V3"), ("TP3", "SCL"), ("TP4", "SDA"), ("TP5", "XSL"), ("TP6", "XSR")):
        x, y = tp(ref)
        if y < H / 2:
            it.append((name, x, y + 0.75 + SILK_GAP + GLYPH_UP, 0.8, "c", 0))        # 上の縁: ランドの下
        else:
            it.append((name, x, y - 0.75 - SILK_GAP - GLYPH_DN, 0.8, "c", 0))        # 下の縁: ランドの上
    for ref, name in (("TP2", "GND"), ("TP7", "ILL"), ("TP8", "ILR")):
        x, y = tp(ref)
        it.append((name, x - 1.25, y, 0.8, "r", 0))
    # SJ（縦並び）: 3V3 側（pad1）の名前はパッドの積み重ねの中心線寄りの外、5V 側（pad3）の名前は縁寄りの外。SJ の枠（中心から 2.0 mm）の外に出す
    for sj, s1 in (("SJ1", -1), ("SJ2", +1)):
        x, y = tp(sj)
        if s1 < 0:      # SJ1（下半分）: pad1 が上、pad3 が下
            it.append(("3V3", x, y - SJ_SILK - GLYPH_DN, 0.8, "c", 0))
            it.append(("5V", x, y + SJ_SILK + GLYPH_UP, 0.8, "c", 0))
        else:           # SJ2（上半分）: pad1 が下、pad3 が上
            it.append(("3V3", x, y + SJ_SILK + GLYPH_UP, 0.8, "c", 0))
            it.append(("5V", x, y - SJ_SILK - GLYPH_DN, 0.8, "c", 0))
    for j, dy in (("J3", -2.4), ("J4", 2.4)):
        x, y = tp(j)
        it.append(("+", x, y + dy, 0.8, "c", 0))
        it.append(("-", x + 2.54, y + dy, 0.8, "c", 0))
    # ToF ヘッダ J1 / J2 の 6 本の信号名（ピン 1 = 右）。樹脂部（2.54 mm 角）の外に、2 段を互い違いに置く（隣のピンの名前とぶつからない）
    for j, sgn, tag in (("J1", -1, "J1 ToF-L"), ("J2", +1, "J2 ToF-R")):
        jx, jy = tp(j)
        ya, yb = tof_rows(jy, sgn)
        for k, name in enumerate(TOF_PINS):
            it.append((name, jx - 2.54 * k, ya if k % 2 == 0 else yb, 0.8, "c", 0))
        it.append((tag, jx - 2.54 * 5 - 2.2, yb, 0.8, "r", 0))
    # 左右: 大きく（LED の隣）。USB-C の向き: 左下の矢印と文字
    it.append(("L", pl["D1"]["x"], pl["D1"]["y"] + 3.0, 1.5, "c", 0))
    it.append(("R", pl["D2"]["x"], pl["D2"]["y"] - 3.0, 1.5, "c", 0))
    it.append(("USB-C", 4.4, H - 1.7, 0.8, "l", 0))
    return it


def silk_lines(pl):
    """上面の刻印の線: (x1, y1, x2, y2)。ToF ヘッダの奥の段（段 B）の名前からピンへの引き出し線（樹脂部の手前まで）、USB-C の矢印。"""
    ln = []
    for j, sgn in (("J1", -1), ("J2", +1)):
        jx, jy = pl[j]["x"], pl[j]["y"]
        ya, yb = tof_rows(jy, sgn)
        y0 = yb + (GLYPH_DN + 0.25 if sgn < 0 else -GLYPH_UP - 0.25)       # 文字の端 + 0.25
        y1 = jy + sgn * (HOUSING + 0.25)                                    # 樹脂部の端の手前
        for k in range(1, 6, 2):
            x = jx - 2.54 * k
            ln.append((x, y0, x, y1))
    y = H - 1.7
    ln.append((0.9, y, 3.9, y))
    ln.append((0.9, y, 1.7, y - 0.5))
    ln.append((0.9, y, 1.7, y + 0.5))
    return ln


# 裏面の凡例（B.SilkS、鏡文字）: 右のゾーン中央。裏から読める
BACK_LEGEND = ["HSB REV A", "L=LOWER", "R=UPPER", "TOF PINS", "TBC"]


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


def add_line(board, x1, y1, x2, y2, layer, width=SILK_THK):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(layer)
    s.SetStart(P(x1, y1))
    s.SetEnd(P(x2, y2))
    s.SetWidth(FromMM(width))
    board.Add(s)


def add_text(board, text, x, y, rot, size, layer, just="c", mirrored=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetLayer(layer)
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
    t.SetTextThickness(FromMM(SILK_THK if size < 1.2 else 0.2))
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
        r.SetTextThickness(FromMM(SILK_THK))
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
        for g in fp.GraphicalItems():                              # 部品のシルクの線も、発注先の最小の太さ（SILK_THK）以上にする
            if g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) and isinstance(g, pcbnew.PCB_SHAPE) and g.GetWidth() < FromMM(SILK_THK):
                g.SetWidth(FromMM(SILK_THK))
        board.Add(fp)
    edge_cuts(board)
    board.GetDesignSettings().SetAuxOrigin(P(0, H))                  # ドリル・配置ファイルの原点 = 基板の左下（ガーバーもこの原点で出す）
    for text, x, y, size, just, rot in silk_items(place):
        add_text(board, text, x, y, rot, size, pcbnew.F_SilkS, just)
    for x1, y1, x2, y2 in silk_lines(place):
        add_line(board, x1, y1, x2, y2, pcbnew.F_SilkS)
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
            poly = None
            if pad.GetShape() == pcbnew.PAD_SHAPE_CUSTOM:                  # 自作形状のランド（NSSW157T）: 外形の多角形
                pp = pad.GetEffectivePolygon(pcbnew.F_Cu)
                poly = [rel(pp.Outline(0).CPoint(k)) for k in range(pp.Outline(0).PointCount())]
            pads.append(dict(n=pad.GetNumber(), c=c, bc=rel(bb.GetCenter()), poly=poly, w=ToMM(bb.GetWidth()), h=ToMM(bb.GetHeight()),
                             drill=ToMM(pad.GetDrillSize().x) if pad.HasHole() else 0, net=pad.GetNetname(),
                             shape="round" if pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE else "rect",
                             kind={pcbnew.PAD_SHAPE_CIRCLE: "circle", pcbnew.PAD_SHAPE_OVAL: "oval", pcbnew.PAD_SHAPE_ROUNDRECT: "roundrect"}.get(pad.GetShape(), "rect"),
                             thru=pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH),
                             npth=pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH))
            if pad.GetNetname():
                out["nets"].setdefault(pad.GetNetname(), []).append(dict(ref=fp.GetReference(), n=pad.GetNumber(), c=c))
        out["fps"].append(dict(ref=fp.GetReference(), value=fp.GetValue(), c=rel(fp.GetPosition()), rot=fp.GetOrientationDegrees(),
                               court=cy, pads=pads, dnp=fp.IsDNP()))
    out["silk_lines"] = []
    for d in board.GetDrawings():
        if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.F_SilkS:
            out["silk"].append(dict(text=d.GetText(), c=rel(d.GetPosition()), rot=d.GetTextAngleDegrees(), h=ToMM(d.GetTextHeight()),
                                    just={pcbnew.GR_TEXT_H_ALIGN_LEFT: "l", pcbnew.GR_TEXT_H_ALIGN_RIGHT: "r"}.get(d.GetHorizJustify(), "c")))
        elif isinstance(d, pcbnew.PCB_SHAPE) and d.GetLayer() == pcbnew.F_SilkS:
            out["silk_lines"].append([rel(d.GetStart()), rel(d.GetEnd())])
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
