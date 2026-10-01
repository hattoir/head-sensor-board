#!/usr/bin/env python3
"""head-sensor-board の回路図（KiCad 10 形式）を生成する。

    python tools/gen_schematic.py          # head-sensor-board.kicad_sch を上書きする

注意: KiCad で回路図を手で直した後にこれを実行すると、手直しが消える。
      手で直したら、このスクリプトは「再生成用の参考」として使い、上書きしない。
電流の数値は tools/led_budget.py から取り込む（注記と計算が食い違わないように）。
"""
import math
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import led_budget as lb                       # noqa: E402
from kicad_sexpr import SymbolLibrary          # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "head-sensor-board.kicad_sch"
STD = pathlib.Path(r"C:\Program Files\KiCad\10.0\share\kicad\symbols")
PROJECT = "head-sensor-board"
NS = uuid.UUID("6f1c2f0e-8c1e-4f5e-9d3a-5a1b7c0de001")
G = 1.27


def g(n):
    return round(n * G, 4)


def fmt(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


_root_uuid = re.search(r'\(uuid "([^"]+)"\)', OUT.read_text(encoding="utf-8")).group(1)


def uid(key):
    return str(uuid.uuid5(NS, key))


LIBS = {}


def lib(nick):
    if nick not in LIBS:
        path = ROOT / "libs" / "head-sensor-board.kicad_sym" if nick == "head-sensor-board" else STD / f"{nick}.kicad_sym"
        LIBS[nick] = SymbolLibrary(path)
    return LIBS[nick]


DIRV = {"E": (1, 0), "W": (-1, 0), "N": (0, -1), "S": (0, 1)}      # 画面座標（y は下向き）


def rotate(v, rot):
    x, y = v
    for _ in range((rot // 90) % 4):
        x, y = -y, x
    return x, y


class Sch:
    def __init__(self):
        self.items = []            # 回路図の本体に出す要素（テキスト）
        self.used = {}             # lib_id -> True
        self.parts = {}            # ref -> dict
        self.pwr_n = 0
        self.seq = 0

    # ---------------------------------------------------------------- 基本要素
    def _id(self, what):
        self.seq += 1
        return uid(f"{what}:{self.seq}")

    def wire(self, p1, p2):
        self.items.append(
            f'\t(wire\n\t\t(pts\n\t\t\t(xy {fmt(p1[0])} {fmt(p1[1])}) (xy {fmt(p2[0])} {fmt(p2[1])})\n\t\t)\n'
            f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{self._id("wire")}")\n\t)\n')

    def path(self, *pts):
        for a, b in zip(pts, pts[1:]):
            self.wire(a, b)

    def junction(self, p):
        self.items.append(f'\t(junction\n\t\t(at {fmt(p[0])} {fmt(p[1])})\n\t\t(diameter 0)\n\t\t(color 0 0 0 0)\n\t\t(uuid "{self._id("jn")}")\n\t)\n')

    def no_connect(self, p):
        self.items.append(f'\t(no_connect\n\t\t(at {fmt(p[0])} {fmt(p[1])})\n\t\t(uuid "{self._id("nc")}")\n\t)\n')

    def label(self, net, p, direction="E"):
        ang, just = {"E": (0, "left bottom"), "W": (180, "right bottom"), "N": (90, "left bottom"), "S": (270, "right bottom")}[direction]
        self.items.append(
            f'\t(label "{net}"\n\t\t(at {fmt(p[0])} {fmt(p[1])} {ang})\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
            f'\t\t\t(justify {just})\n\t\t)\n\t\t(uuid "{self._id("lbl")}")\n\t)\n')

    def text(self, s, p, size=1.27, bold=False):
        s = s.replace("\\", "/").replace('"', "'").replace("\n", "\\n")
        b = "\n\t\t\t\t(bold yes)" if bold else ""
        self.items.append(
            f'\t(text "{s}"\n\t\t(exclude_from_sim no)\n\t\t(at {fmt(p[0])} {fmt(p[1])} 0)\n\t\t(effects\n\t\t\t(font\n'
            f'\t\t\t\t(size {size} {size}){b}\n\t\t\t)\n\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "{self._id("txt")}")\n\t)\n')

    def box(self, p1, p2, title=None):
        self.items.append(
            f'\t(rectangle\n\t\t(start {fmt(p1[0])} {fmt(p1[1])})\n\t\t(end {fmt(p2[0])} {fmt(p2[1])})\n\t\t(stroke\n'
            f'\t\t\t(width 0.2)\n\t\t\t(type dash)\n\t\t)\n\t\t(fill\n\t\t\t(type none)\n\t\t)\n\t\t(uuid "{self._id("box")}")\n\t)\n')
        if title:
            self.text(title, (p1[0] + 1.27, p1[1] + 3.0), 1.5, bold=True)

    # ---------------------------------------------------------------- 部品
    @staticmethod
    def _prop(name, value, x, y, rot=0, hide=False, justify=None):
        value = str(value).replace('"', "'")
        h = "\n\t\t\t(hide yes)" if hide else ""
        j = f"\n\t\t\t\t(justify {justify})" if justify and justify != "center" else ""   # 中央寄せは指定なし
        return (f'\t\t(property "{name}" "{value}"\n\t\t\t(at {fmt(x)} {fmt(y)} {rot}){h}\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n'
                f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t){j}\n\t\t\t)\n\t\t)\n')

    def place(self, lib_id, ref, value, at, rot=0, footprint="", fields=None, dnp=False, in_bom=True, on_board=True,
              ref_off=None, val_off=None, hide_ref=False, hide_val=False, datasheet="", description=""):
        nick, name = lib_id.split(":")
        self.used[lib_id] = True
        pins = lib(nick).pins(name)
        x, y = at
        pos = {}
        for num, p in pins.items():
            rx, ry = rotate((round(p["x"], 4), round(p["y"], 4)), rot)            # y 上向き系で回転
            a = math.radians(p["angle"])                                           # ピン端 → 本体 の向き（y 上向き系）
            ox, oy = rotate((-round(math.cos(a)), -round(math.sin(a))), rot)       # 外向き（y 上向き系）
            d = {(1, 0): "E", (-1, 0): "W", (0, 1): "N", (0, -1): "S"}[(ox, oy)]   # 画面では y が下向き: 上 = N
            pos[num] = dict(xy=(round(x + rx, 4), round(y - ry, 4)), dir=d, name=p["name"])
        self.parts[ref] = dict(at=at, rot=rot, pins=pos)
        ro = ref_off or (2.54, -1.27, "left")
        vo = val_off or (2.54, 1.27, "left")
        fa = 90 if rot in (90, 270) else 0          # 回転した部品のフィールドは相対角で書かれる
        props = ""
        props += self._prop("Reference", ref, x + ro[0], y + ro[1], fa, hide_ref, ro[2])
        props += self._prop("Value", value, x + vo[0], y + vo[1], fa, hide_val, vo[2])
        props += self._prop("Footprint", footprint, x, y, 0, True)
        props += self._prop("Datasheet", datasheet, x, y, 0, True)
        props += self._prop("Description", description, x, y, 0, True)
        for k, v in (fields or {}).items():
            props += self._prop(k, v, x, y, 0, True)
        pin_txt = "".join(f'\t\t(pin "{n}"\n\t\t\t(uuid "{uid(f"pin:{ref}:{n}")}")\n\t\t)\n' for n in sorted(pins, key=lambda s: (len(s), s)))
        blk = (f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {fmt(x)} {fmt(y)} {rot})\n\t\t(unit 1)\n\t\t(body_style 1)\n\t\t(exclude_from_sim no)\n'
               f'\t\t(in_bom {"yes" if in_bom else "no"})\n\t\t(on_board {"yes" if on_board else "no"})\n\t\t(in_pos_files yes)\n'
               f'\t\t(dnp {"yes" if dnp else "no"})\n\t\t(fields_autoplaced yes)\n\t\t(uuid "{uid("sym:" + ref)}")\n{props}{pin_txt}'
               f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t(path "/{_root_uuid}"\n\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit 1)\n'
               f'\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')
        self.items.append(blk)
        return ref

    def pin(self, ref, num):
        return self.parts[ref]["pins"][str(num)]["xy"]

    def dir(self, ref, num):
        return self.parts[ref]["pins"][str(num)]["dir"]

    def power(self, sym, at, hide_val=False):
        """電源シンボルを at（= ピンの位置）に置く。"""
        self.pwr_n += 1
        ref = f"#PWR{self.pwr_n:02d}" if sym != "PWR_FLAG" else f"#FLG{self.pwr_n:02d}"
        name = sym
        x, y = at
        val_off = (0, -3.0) if sym in ("+3V3", "+5V", "PWR_FLAG") else (0, 3.0)
        lib_id = f"power:{name}"
        self.used[lib_id] = True
        self.parts[ref] = dict(at=at, rot=0, pins={"1": dict(xy=at, dir="N" if sym != "GND" else "S", name="")})
        props = (self._prop("Reference", ref, x, y + 3.81 if sym != "GND" else y - 3.81, 0, True)
                 + self._prop("Value", sym, x + val_off[0], y + val_off[1], 0, hide_val)
                 + self._prop("Footprint", "", x, y, 0, True) + self._prop("Datasheet", "", x, y, 0, True)
                 + self._prop("Description", f'Power symbol creates a global label with name "{sym}"', x, y, 0, True))
        self.items.append(
            f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {fmt(x)} {fmt(y)} 0)\n\t\t(unit 1)\n\t\t(body_style 1)\n\t\t(exclude_from_sim no)\n'
            f'\t\t(in_bom no)\n\t\t(on_board no)\n\t\t(in_pos_files no)\n\t\t(dnp no)\n\t\t(fields_autoplaced yes)\n\t\t(uuid "{uid("pwr:" + ref)}")\n{props}'
            f'\t\t(pin "1"\n\t\t\t(uuid "{uid("pwrpin:" + ref)}")\n\t\t)\n'
            f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t(path "/{_root_uuid}"\n\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')
        return at

    # ---------------------------------------------------------------- 接続の補助
    def stub(self, ref, num, net, length=2.54):
        """ピンの端から外向きに短い線を引き、ラベルを付ける。上下向きのピンは L 字にして文字を横向きにする。"""
        p = self.pin(ref, num)
        d = self.dir(ref, num)
        vx, vy = DIRV[d]
        if d in ("E", "W"):
            e = (round(p[0] + vx * length, 4), p[1])
            self.wire(p, e)
            self.label(net, e, d)
        else:
            m = (p[0], round(p[1] + vy * 2.54, 4))
            e = (round(m[0] + 2.54, 4), m[1])
            self.path(p, m, e)
            self.label(net, e, "E")
        return e

    def lib_symbols_text(self):
        out = []
        for lib_id in sorted(self.used):
            nick, name = lib_id.split(":")
            out.append(lib(nick).lib_symbol_text(nick, name, 2))
        return "\t(lib_symbols\n" + "\n".join(out) + "\n\t)\n"


def build():
    s = Sch()
    today = "2026-10-01"

    # ------------------------------------------------------------------ 数値（led_budget.py から）
    lo3, nom3, hi3 = lb.stats(lb.VCC3, 20)
    lo5, nom5, hi5 = lb.stats(lb.VCC5, 33)
    led3 = lb.N_LED * hi3
    tof_pk = lb.N_TOF * lb.TOF_PEAK
    ext3 = led3 + tof_pk + 2 * lb.XSHUT_PU
    ext5 = tof_pk + 2 * lb.XSHUT_PU
    tB = lb.XIAO_WEBCAM_PEAK_BAT + ext3
    tC = lb.XIAO_CAM_TABLE_MAX + ext3
    sens = lb.R_SENSE + lb.R_DS
    short3 = 3.3 / (20 + sens)
    short5 = 5.0 / (33 + sens)
    mA = lambda a: f"{a * 1e3:.1f}"            # noqa: E731
    I0 = lambda a: f"{a * 1e3:.0f}"            # noqa: E731

    # ------------------------------------------------------------------ 共通の属性
    R0603 = "Resistor_SMD:R_0603_1608Metric"
    R2010 = "Resistor_SMD:R_2010_5025Metric"

    def res(ref, value, at, rot, fp, note, rating, dnp=False, **kw):
        return s.place("Device:R", ref, value, at, rot, fp,
                       fields={"MPN": f"chip resistor {value} ohm", "Rating": rating, "Notes": note}, dnp=dnp, **kw)

    # ------------------------------------------------------------------ U1（XIAO）
    U = (g(65), g(88))
    s.box((g(33), g(68)), (g(97), g(116)), "MCU: XIAO ESP32S3 Sense (2x7 sockets or pin headers)")
    s.place("head-sensor-board:XIAO_ESP32S3", "U1", "XIAO_ESP32S3_Sense", U, 0,
            "head-sensor-board:XIAO_ESP32S3_THT_2x7_P2.54mm",
            fields={"MPN": "Seeed XIAO ESP32S3 Sense", "Rating": "3V3 out 700 mA (Seeed wiki, condition not stated)",
                    "Notes": "Akizuki 118079. Mount on 2x 1x7 sockets (or pin headers). USB-C side = up in the drawing"},
            ref_off=(0, -19.0, "left"), val_off=(16.0, 24.0, "left"), datasheet="https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/")
    for num, net in ((1, "XSHUT_L"), (2, "XSHUT_R"), (3, "LED_PWM_L"), (4, "LED_PWM_R"), (5, "SDA"), (6, "SCL")):
        s.stub("U1", num, net, 7.62)
    s.no_connect(s.pin("U1", 7))
    s.text("D6/TX, D7/RX: reserved (UART to body XIAO)", (g(36), g(113)), 1.0)
    s.no_connect(s.pin("U1", 11))                                   # D10 unused
    s.stub("U1", 10, "D9_GPIO8", 7.62)
    s.stub("U1", 9, "D8_GPIO7", 7.62)
    s.no_connect(s.pin("U1", 8))                                     # D7/RX reserved
    s.power("+5V", s.pin("U1", 14))
    s.power("+3V3", s.pin("U1", 12))
    g13 = s.pin("U1", 13)
    gnd_end = (g13[0], round(g13[1] + 2.54, 4))
    s.wire(g13, gnd_end)
    s.power("GND", gnd_end)
    flg = (round(gnd_end[0] + 7.62, 4), gnd_end[1])
    s.wire(gnd_end, flg)
    s.junction(gnd_end)
    s.power("PWR_FLAG", flg)

    # ------------------------------------------------------------------ ToF ヘッダ（ジャンパー線で離して置く）
    s.box((g(124), g(30)), (g(166), g(108)), "ToF modules (jumper wires)")
    s.text("Header pin order = PLACEHOLDER (UNVERIFIED)", (g(126), g(34) + 1.0), 1.0)
    tof_fields = {"MPN": "PinHeader 1x06 2.54 mm", "Rating": "2.54 mm pitch",
                  "Notes": "VL53L1X small module (Amazon B083Z316NC) on jumper wires. PIN ORDER IS A PLACEHOLDER - UNVERIFIED (module not in hand)"}
    for ref, val, at, sh, inte, dnet in (("J1", "ToF_L (PLACEHOLDER)", (g(158), g(52)), "XSHUT_L", "TOF_L_INT", "D8_GPIO7"),
                                          ("J2", "ToF_R (PLACEHOLDER)", (g(158), g(88)), "XSHUT_R", "TOF_R_INT", "D9_GPIO8")):
        s.place("head-sensor-board:ToF_Header_1x06", ref, val, at, 0, "head-sensor-board:PinHeader_1x06_P2.54mm_NoSilk",
                fields=tof_fields, ref_off=(0, -16.0, "center"), val_off=(-4.0, 18.0, "center"))
        s.power("+3V3", s.pin(ref, 1))
        s.power("GND", s.pin(ref, 2))
        s.stub(ref, 3, "SCL", 7.62)
        s.stub(ref, 4, "SDA", 7.62)
        s.stub(ref, 5, sh, 7.62)
        # GPIO1 -> 0 ohm link (DNP) -> XIAO D8 / D9
        p6 = s.pin(ref, 6)
        lref = "R15" if ref == "J1" else "R16"
        lx = round(p6[0] - 12.7 - 3.81, 4)
        res(lref, "0", (lx, p6[1]), 90, R0603, "GPIO1 link to XIAO D8/D9 (shares the Sense microSD SPI pins). Default: not fitted",
            "0 ohm jumper", dnp=True, ref_off=(0, 3.0, "center"), val_off=(0, 5.8, "center"))
        s.wire(p6, s.pin(lref, 2))
        s.stub(lref, 1, dnet, 2.54)
        s.label(inte, (round(s.pin(lref, 2)[0] + 1.27, 4), p6[1]), "E")

    # ------------------------------------------------------------------ プルアップ（XSHUT は実装、I2C は DNP）
    s.box((g(168), g(30)), (g(196), g(108)), "Pull-ups")
    px = g(173)
    for i, (ref, val, net, dnp, note) in enumerate((
            ("R11", "10k", "XSHUT_L", False, "XSHUT pull-up (ST DS12385 2.4: XSHUT must always be driven; 10k recommended)"),
            ("R12", "10k", "XSHUT_R", False, "XSHUT pull-up (ST DS12385 2.4)"),
            ("R13", "3.3k", "SDA", True, "I2C pull-up. DNP: fit only if the module has none (ST Table 4: 3.6k for CL<=90 pF)"),
            ("R14", "3.3k", "SCL", True, "I2C pull-up. DNP: fit only if the module has none"))):
        y = g(40) + i * g(10)
        res(ref, val, (round(px + 3.81, 4), y), 90, R0603, note, "0.1 W (0603)", dnp=dnp, ref_off=(3.5, -3.0, "center"), val_off=(3.5, 3.3, "center"))
        s.power("+3V3", s.pin(ref, 1))
        s.stub(ref, 2, net, 2.54)
    s.text("R13/R14: DNP (I2C pull-ups)", (px - 2.5, g(40) + 4 * g(10) - 3), 1.0)

    # ------------------------------------------------------------------ LED チャンネル（L / R）
    def led_channel(ch, cx, cy):
        L = ch                                  # "L" or "R"
        n = 0 if L == "L" else 1
        s.box((cx - 15.5, cy - 12.5), (cx + 52, cy + 78), f"LED channel {L}")
        # 3V3 側と 5V 側の抵抗 → 半田ジャンパー
        s.power("+3V3", (cx, cy))
        s.power("+5V", (cx + 20.32, cy))
        r3 = f"R{1 + n}"
        r5 = f"R{3 + n}"
        res(r3, "20", (cx, cy + 10.16), 0, R0603, "LED current limit @3V3 (20 ohm: 8.5/23.6/38.8 mA min/nom/max)", "0.1 W (0603)",
            ref_off=(-2.54, -1.27, "right"), val_off=(-2.54, 1.27, "right"))
        res(r5, "33", (cx + 20.32, cy + 10.16), 0, R2010, "LED current limit @5V (33 ohm 2010: 45/59/73 mA min/nom/max). Fitted, used only when SJ is set to 5V", "0.5 W (2010)",
            ref_off=(2.54, -1.27, "left"), val_off=(2.54, 1.27, "left"))
        s.wire((cx, cy), s.pin(r3, 1))
        s.wire((cx + 20.32, cy), s.pin(r5, 1))
        sj = f"SJ{1 + n}"
        s.place("Jumper:SolderJumper_3_Bridged12", sj, f"LED_{L}_SUPPLY", (cx + 10.16, cy + 22.86), 0,
                "Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm",
                fields={"MPN": "solder jumper (PCB pads)", "Rating": "-",
                        "Notes": "Default: pads 1-2 bridged = 3V3 via R1/R2. For 5V: cut the 1-2 bridge, bridge 2-3 (via R3/R4)"},
                ref_off=(0, -8.0, "center"), val_off=(0, -5.0, "center"))
        s.path(s.pin(r3, 2), (cx, cy + 22.86), s.pin(sj, 1))
        s.path(s.pin(r5, 2), (cx + 20.32, cy + 22.86), s.pin(sj, 3))
        s.text("3V3", (cx - 1.0, cy + 21.3), 1.0)
        s.text("5V", (cx + 17.8, cy + 21.3), 1.0)
        # LED と MOSFET
        d = f"D{1 + n}"
        q = f"Q{1 + n}"
        s.place("Device:LED", d, "NSSW157T", (cx + 10.16, cy + 38.1), 90, "head-sensor-board:LED_Nichia_NSSW157T",
                fields={"MPN": "NSSW157T", "Manufacturer": "Nichia", "Rating": "IF 150 mA max; VF 2.8-3.4 V @80 mA; 3.0x1.4x0.52 mm",
                        "Notes": "Akizuki 116884. White chip LED, height 0.52 mm"},
                ref_off=(-8.0, -1.27, "center"), val_off=(-9.5, 1.27, "center"), datasheet="https://akizukidenshi.com/goodsaffix/nssw157t.pdf")
        s.place("head-sensor-board:Q_NMOS_GSD", q, "AO3400A", (cx + 7.62, cy + 53.34), 0, "Package_TO_SOT_SMD:SOT-23",
                fields={"MPN": "AO3400A (alt. Si2302CDS)", "Manufacturer": "Alpha & Omega (alt. Vishay)",
                        "Rating": "30 V 5.7 A VGS(th) 0.65-1.45 V RDS(on)<48 mohm @2.5 V (alt. Si2302CDS 20 V 2.6 A 0.40-0.85 V <75 mohm)",
                        "Notes": "SOT-23 pin 1=G 2=S 3=D. Gate driven by 3.3 V logic"},
                ref_off=(6.0, -1.27, "left"), val_off=(6.0, 1.27, "left"),
                datasheet="https://www.aosmd.com/res/data_sheets/AO3400A.pdf")
        s.wire(s.pin(sj, 2), s.pin(d, 2))
        s.label(f"LEDA_{L}", (cx + 10.16, cy + 30.48), "E")
        s.wire(s.pin(d, 1), s.pin(q, 3))
        s.label(f"LEDK_{L}", (cx + 10.16, cy + 44.45), "E")
        # ゲート: PWM -> 220 -> G、100k で GND
        rg, rpd, rs = f"R{5 + n}", f"R{7 + n}", f"R{9 + n}"
        res(rg, "220", (cx - 7.62, cy + 53.34), 90, R0603, "Gate series resistor (limits the gate charge peak to 15 mA)", "0.1 W (0603)",
            ref_off=(0, -3.0, "center"), val_off=(0, 3.3, "center"))
        s.wire(s.pin(rg, 2), s.pin(q, 1))
        s.label(f"GATE_{L}", (cx - 1.27, cy + 53.34), "E")
        s.stub(rg, 1, f"LED_PWM_{L}", 2.54)
        res(rpd, "100k", (cx + 2.54, cy + 62.23), 0, R0603, "Gate pull-down: LED off during reset/boot (GPIO3 is a strapping pin)", "0.1 W (0603)",
            ref_off=(-2.54, -1.27, "right"), val_off=(-2.54, 1.27, "right"))
        s.wire(s.pin(q, 1), s.pin(rpd, 1))
        s.junction(s.pin(q, 1))
        s.power("GND", s.pin(rpd, 2))
        # ソース: 1 ohm で電流検出 -> GND。TP は ILED
        res(rs, "1", (cx + 10.16, cy + 66.04), 0, R0603, "Current sense: TP ILED voltage = 1 mV per mA (1 %)", "0.1 W (0603) 1 %",
            ref_off=(2.54, -1.27, "left"), val_off=(2.54, 1.27, "left"))
        s.wire(s.pin(q, 2), s.pin(rs, 1))
        s.label(f"SENSE_{L}", (cx + 10.16, cy + 59.69), "E")
        s.power("GND", s.pin(rs, 2))
        tp = f"TP{7 + n}"
        s.place("Connector:TestPoint", tp, f"ILED_{L}", (cx + 25.4, cy + 66.04), 0, "head-sensor-board:TestPoint_Pad_D1.5mm_NoSilk",
                fields={"MPN": "test point pad", "Notes": "LED current sense node: 1 mV = 1 mA"}, in_bom=False,
                ref_off=(2.0, -5.0, "left"), val_off=(2.0, -2.6, "left"))
        s.stub(tp, 1, f"SENSE_{L}", 2.54)
        # 外付け LED 用ヘッダ
        jx = f"J{3 + n}"
        s.place("Connector_Generic:Conn_01x02", jx, f"LED_{L}_EXT (1:+ 2:-)", (cx + 36.83, cy + 38.1), 0,
                "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                fields={"MPN": "PinHeader 1x02 2.54 mm", "Rating": "current-limited node (after R1/R3)",
                        "Notes": "External LED: pin 1 = + (LEDA, after the series resistor), pin 2 = - (LEDK). Do NOT short + to -"},
                ref_off=(3.0, -3.5, "left"), val_off=(3.0, 6.5, "left"))
        s.stub(jx, 1, f"LEDA_{L}", 2.54)
        s.stub(jx, 2, f"LEDK_{L}", 2.54)

    led_channel("L", g(216), g(25))
    led_channel("R", g(216) + 82.55, g(25))

    # ------------------------------------------------------------------ テストポイント
    s.box((g(33), g(118)), (g(132), g(138)), "Test points")
    tps = [("TP1", "3V3", None), ("TP2", "GND", None), ("TP3", "SCL", "SCL"), ("TP4", "SDA", "SDA"),
           ("TP5", "XSHUT_L", "XSHUT_L"), ("TP6", "XSHUT_R", "XSHUT_R")]
    for i, (ref, val, net) in enumerate(tps):
        x = g(37) + i * 15.24
        s.place("Connector:TestPoint", ref, val, (x, g(128)), 0, "head-sensor-board:TestPoint_Pad_D1.5mm_NoSilk",
                fields={"MPN": "test point pad", "Notes": f"Test point {val}"}, in_bom=False,
                ref_off=(2.0, -5.0, "left"), val_off=(2.0, -2.6, "left"))
        p = s.pin(ref, 1)
        if net:
            s.stub(ref, 1, net, 2.54)
        else:
            m = (p[0], round(p[1] + 2.54, 4))
            e = (round(m[0] + 10.16, 4), m[1])
            s.path(p, m, e)
            s.power("+3V3" if val == "3V3" else "GND", e)

    # ------------------------------------------------------------------ デカップリング（3V3 と GND の間）
    s.box((g(136), g(118)), (g(194), g(138)), "Decoupling (3V3)")
    for i, (ref, val, fp, rating, note) in enumerate((
            ("C1", "10u", "Capacitor_SMD:C_0805_2012Metric", "10 V X5R 0805", "3V3 bulk: LED PWM + ToF peaks (2 x 40 mA)"),
            ("C2", "100n", "Capacitor_SMD:C_0603_1608Metric", "16 V X7R 0603", "Bypass near ToF header J1"),
            ("C3", "100n", "Capacitor_SMD:C_0603_1608Metric", "16 V X7R 0603", "Bypass near ToF header J2"))):
        x = g(142) + i * 15.24
        s.place("Device:C", ref, val, (x, g(129)), 0, fp, fields={"MPN": f"ceramic capacitor {val}F", "Rating": rating, "Notes": note},
                ref_off=(2.54, -1.27, "left"), val_off=(2.54, 1.27, "left"))
        s.power("+3V3", s.pin(ref, 1))
        s.power("GND", s.pin(ref, 2))

    # ------------------------------------------------------------------ 取付穴（基板上の位置は Stage 3 で決める）
    for i, ref in enumerate(("H1", "H2")):
        s.place("Mechanical:MountingHole", ref, "MountingHole_2.2mm_M2", (g(265) + i * 12.7, g(123)), 0,
                "MountingHole:MountingHole_2.2mm_M2", fields={"MPN": "M2 mounting hole (no part)", "Notes": "Stage 3 places the holes on the board diagonal"},
                in_bom=False, ref_off=(-1.5, -4.0, "left"), val_off=(0, 6, "center"), hide_val=True)
    s.text("M2 mounting holes x2 (placed on the board in Stage 3)", (g(258), g(131)), 1.0)

    # ------------------------------------------------------------------ 注記（電流の計算結果・GPIO・未確認）
    y0 = 182
    s.text("NOTES (full calculation: docs/spec.md, tools/led_budget.py)", (g(18), y0), 1.8, bold=True)
    col1 = [
        ("A. POWER", [
            "Everything is powered from the XIAO 3V3 pin. XIAO 5V pin is wired ONLY to R3/R4 -> solder jumper pad 3 (open by default).",
            "LED supply per channel: SJ1/SJ2 default = pads 1-2 bridged = 3V3 via R1/R2 (20 ohm).",
            "For 5V: cut the 1-2 bridge, bridge 2-3 (R3/R4 33 ohm 2010 are already fitted). 5V = USB VBUS (no voltage on battery power).",
        ]),
        ("B. LED @3V3 (R1/R2 20 ohm 0603)", [
            "Vf(I) = 2.677 V + 5.29 ohm*I  (Nichia STS-DA1-1913: 3.1 V typ and 2.8-3.4 V @80 mA; 2.73 V @10 mA read from the graph = reference only).",
            f"Vcc 3.2-3.4 V (assumed), Rds(on) <= 75 mohm. Per LED min/nom/max = {mA(lo3)} / {mA(nom3)} / {mA(hi3)} mA",
            f"= {lo3/lb.IF_MAX*100:.0f} / {nom3/lb.IF_MAX*100:.0f} / {hi3/lb.IF_MAX*100:.0f} % of IF max 150 mA = {lo3/lb.I_RATED*100:.0f} / {nom3/lb.I_RATED*100:.0f} / {hi3/lb.I_RATED*100:.0f} % of the 80 mA rated flux.",
            f"R1/R2 dissipation <= {hi3**2*20*1e3:.0f} mW ({hi3**2*20/0.1*100:.0f} % of 0.1 W). Both LEDs at 100 % duty, max: {mA(led3)} mA.",
        ]),
        ("C. LED @5V (R3/R4 33 ohm 2010 0.5 W)", [
            f"Vcc 4.75-5.25 V: {mA(lo5)} / {mA(nom5)} / {mA(hi5)} mA per LED ({hi5/lb.IF_MAX*100:.0f} % of IF max). R3/R4 dissipation <= {hi5**2*33*1e3:.0f} mW ({hi5**2*33/0.5*100:.0f} % of 0.5 W).",
            f"5V total with the XIAO webcam capture peak 347 mA (Seeed wiki) = {(lb.N_LED*hi5+lb.XIAO_WEBCAM_PEAK_5V)*1e3:.0f} mA (< 500 mA USB 2.0). XIAO 5V pin current capability: UNVERIFIED.",
            f"With the wrong resistor (20 ohm on 5V) a LED would get {lb.stats(lb.VCC5, 20)[2]*1e3:.0f} mA and R1 {lb.stats(lb.VCC5, 20)[2]**2*20*1e3:.0f} mW -> always keep SJ and R1/R3 as drawn.",
        ]),
    ]
    col2 = [
        ("D. 3V3 TOTAL (Seeed: 'You can draw 700mA', condition not stated)", [
            f"External: LEDs {mA(led3)} + ToF peak 2 x 40 + XSHUT pull-ups 0.7 = {ext3*1e3:.0f} mA ({ext5*1e3:.0f} mA if the LEDs are on 5V).",
            f"XIAO Sense (Seeed wiki): webcam average 140 mA, capture peak {lb.XIAO_WEBCAM_PEAK_BAT*1e3:.0f} mA -> total {tB*1e3:.0f} mA ({tB/0.7*100:.0f} % of 700 mA).",
            f"Seeed camera table MAX ~0.65 A (conditions not stated = UNVERIFIED) -> {tC*1e3:.0f} mA ({tC/0.7*100:.0f} %). ESP32-S3 Wi-Fi TX peak 340 mA (chip only, Datasheet v2.2 Table 5-7).",
            "=> Measure the real 5V input current before running Wi-Fi TX + capture + LEDs 100 % + ToF peak together.",
        ]),
        ("E. GPIO and MOSFET gate drive", [
            "GPIO carries no LED current (gate only). Gate charge peak 3.3 V / 220 ohm = 15 mA; XSHUT low sinks 0.33 mA. ESP32-S3: IOH 40 mA / IOL 28 mA (Datasheet v2.2 Table 5-4).",
            "3.3 V gate drive is enough: ESP32-S3 VOH >= 0.8*VDD = 2.64 V. AO3400A (AOS Rev 3.1): VGS(th) 0.65-1.45 V, Rds(on) < 48 mohm @2.5 V.",
            "Si2302CDS (Vishay S12-2336 Rev D): VGS(th) 0.40-0.85 V, Rds(on) < 75 mohm @2.5 V, VGS max +-8 V. Both SOT-23, pin 1=G 2=S 3=D.",
        ]),
        ("F. GPIO assignment (approved 2026-10-01)", [
            "D0=GPIO1 XSHUT_L | D1=GPIO2 XSHUT_R | D2=GPIO3 LED_L PWM (strapping pin, gate pulled low) | D3=GPIO4 LED_R PWM",
            "D4=GPIO5 SDA | D5=GPIO6 SCL | D6/D7=GPIO43/44 reserved UART | D8/D9=GPIO7/8 = ToF GPIO1 via DNP links R15/R16 (shared with Sense microSD) | 5V: SJ option only",
            "Firmware: drive both XSHUT low first, release one at a time and change the VL53L1X address (default 0x29 7-bit = 0x52 8-bit).",
        ]),
        ("G. UNVERIFIED / WARNINGS", [
            "ToF header pin order is a PLACEHOLDER (module not in hand). Gerbers are NOT released until the real pinout is checked. ToF modules are wired with jumper wires.",
            f"J3/J4 external LED: pin 1 = + (after the series resistor), pin 2 = -. Fit EITHER D1/D2 or an external LED (both = they share the current).",
            f"Do NOT short J3/J4 + to -: R1 would dissipate {short3**2*20:.2f} W (0603 = 0.1 W), R3 {short5**2*33:.2f} W (2010 = 0.5 W).",
        ]),
        ("H. OPERATING CAUTIONS (user, 2026-10-01)", [
            f"5V is a TEST OPTION only. The default is 3V3 (SJ1/SJ2 pads 1-2 bridged). The 5V total of {(lb.N_LED*hi5+lb.XIAO_WEBCAM_PEAK_5V)*1e3:.0f} mA is right at the USB 2.0 limit of 500 mA (margin {(0.5-(lb.N_LED*hi5+lb.XIAO_WEBCAM_PEAK_5V))*1e3:.0f} mA).",
            "3V3: do NOT run Wi-Fi TX, camera capture, LEDs at 100 % and ToF peaks at the same time, until the real 5V input current of the XIAO has been measured.",
        ]),
    ]

    def block(col, x, y, width):
        import textwrap
        for title, lines in col:
            s.text(title, (x, y), 1.4, bold=True)
            y += 4.6
            for ln in lines:
                for k, piece in enumerate(textwrap.wrap(ln, width, subsequent_indent="   ")):
                    s.text(piece, (x, y), 1.1)
                    y += 3.9
            y += 3.0
        return y

    blk_a, blk_b, blk_c = col1
    blk_d, blk_e, blk_f, blk_g, blk_h = col2
    block([blk_a, blk_b, blk_c, blk_g], g(18), y0 + 8, 150)
    y_next = block([blk_d, blk_e], g(18) + 185, y0 + 8, 100)
    block([blk_h], g(18) + 185, y_next, 72)            # タイトルブロック（x ≥ 300 mm、y ≥ 245 mm）にかからない幅
    block([blk_f], g(203), g(93), 130)

    # ------------------------------------------------------------------ 出力
    title_block = (
        f'\t(title_block\n\t\t(title "head-sensor-board")\n\t\t(date "{today}")\n\t\t(rev "A")\n\t\t(company "Serpens / Floor Watch")\n'
        '\t\t(comment 1 "Prototype for T6 (ToF cliff) / T4 (LED) tests")\n'
        '\t\t(comment 2 "Power: XIAO 3V3; LED 3V3 or 5V by solder jumper")\n'
        '\t\t(comment 3 "ToF pin order: PLACEHOLDER (UNVERIFIED)")\n\t)\n')
    body = "".join(s.items)
    text = (f'(kicad_sch\n\t(version 20260306)\n\t(generator "eeschema")\n\t(generator_version "10.0")\n\t(uuid "{_root_uuid}")\n'
            f'\t(paper "A3")\n{title_block}{s.lib_symbols_text()}{body}'
            f'\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    OUT.write_text(text, encoding="utf-8", newline="\n")
    return s


if __name__ == "__main__":
    sch = build()
    print(f"wrote {OUT.name}: {len(sch.items)} items, {len([r for r in sch.parts if not r.startswith('#')])} parts")
