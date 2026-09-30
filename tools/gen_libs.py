#!/usr/bin/env python3
"""自作ライブラリ（libs/）を生成する。標準ライブラリに無い 5 点だけ。

    python tools/gen_libs.py

作るもの
  libs/head-sensor-board.kicad_sym   XIAO_ESP32S3 / ToF_Header_1x06 / Q_NMOS_GSD
  libs/head-sensor-board.pretty/     XIAO_ESP32S3_THT_2x7_P2.54mm / LED_Nichia_NSSW157T
  sym-lib-table, fp-lib-table        プロジェクトのライブラリ表（${KIPRJMOD} 相対）

出典は README「ライブラリの出典」。寸法の根拠:
  XIAO 穴パターン … Seeed "XIAO Series Package and PCB Design" p.7（ピッチ 2.54、行間隔 15.25→15.24、穴 φ1.02、外形 17.8×21）
  NSSW157T ランド … Nichia STS-DA1-1913 p.4-5（パッド全長 4.0、カソード 0.6+1.66、ギャップ 0.5、アノード 0.64+0.6、高さ 1.55/0.86）
  Q_NMOS_GSD   … KiCad 標準 Device:Q_NMOS の図形を流用（ピン番号だけ SOT-23 の 1=G 2=S 3=D に直した）
"""
import pathlib
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIBS = ROOT / "libs"
KICAD_SYM_DIR = pathlib.Path(r"C:\Program Files\KiCad\10.0\share\kicad\symbols")


def uid():
    return str(uuid.uuid4())


# ------------------------------------------------------------------ シンボル
def sym_prop(name, value, at, hide=False):
    x, y, a = at
    h = "\n\t\t\t(hide yes)" if hide else ""
    return (f'\t\t(property "{name}" "{value}"\n\t\t\t(at {x} {y} {a})\n\t\t\t(show_name no)\n'
            f'\t\t\t(do_not_autoplace no){h}\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t\t)\n\t\t\t)\n\t\t)\n')


def sym_pin(etype, x, y, ang, name, num, length=2.54):
    return (f'\t\t\t(pin {etype} line\n\t\t\t\t(at {x} {y} {ang})\n\t\t\t\t(length {length})\n'
            f'\t\t\t\t(name "{name}"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n'
            f'\t\t\t\t(number "{num}"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n\t\t\t)\n')


def sym_rect(x1, y1, x2, y2):
    return (f'\t\t\t(rectangle\n\t\t\t\t(start {x1} {y1})\n\t\t\t\t(end {x2} {y2})\n\t\t\t\t(stroke\n'
            f'\t\t\t\t\t(width 0.254)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n\t\t\t\t(fill\n'
            f'\t\t\t\t\t(type background)\n\t\t\t\t)\n\t\t\t)\n')


def sym_head(name):
    return (f'\t(symbol "{name}"\n\t\t(pin_numbers\n\t\t\t(hide no)\n\t\t)\n\t\t(pin_names\n'
            f'\t\t\t(offset 1.016)\n\t\t)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n'
            f'\t\t(in_pos_files yes)\n\t\t(duplicate_pin_numbers_are_jumpers no)\n')


def sym_xiao():
    # 信号ピンは左右、電源ピンは上（5V, 3V3）と下（GND）。ピン番号は実物（左列 1〜7、右列 8〜14）のまま。
    left = [("D0", "1"), ("D1", "2"), ("D2", "3"), ("D3", "4"), ("D4/SDA", "5"), ("D5/SCL", "6"), ("D6/TX", "7")]
    right = [("D10/MOSI", "11"), ("D9/MISO", "10"), ("D8/SCK", "9"), ("D7/RX", "8")]
    w = 12.7
    pins = ""
    for i, (nm, num) in enumerate(left):
        pins += sym_pin("bidirectional", -w - 2.54, 7.62 - 2.54 * i, 0, nm, num)
    for i, (nm, num) in enumerate(right):
        pins += sym_pin("bidirectional", w + 2.54, 3.81 - 2.54 * i, 180, nm, num)
    pins += sym_pin("power_out", -3.81, 12.7, 270, "5V", "14")
    pins += sym_pin("power_out", 3.81, 12.7, 270, "3V3", "12")
    pins += sym_pin("power_in", 0, -12.7, 90, "GND", "13")
    s = sym_head("XIAO_ESP32S3")
    s += sym_prop("Reference", "U", (0, 15.24, 0)) + sym_prop("Value", "XIAO_ESP32S3", (0, -15.24, 0))
    s += sym_prop("Footprint", "head-sensor-board:XIAO_ESP32S3_THT_2x7_P2.54mm", (0, 0, 0), True)
    s += sym_prop("Datasheet", "https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/", (0, 0, 0), True)
    s += sym_prop("Description", "Seeed Studio XIAO ESP32S3 (Sense). 2x7 through-hole pins 2.54 mm, rows 15.24 mm apart, USB-C at top. "
                  "5V pin = USB VBUS (no voltage when battery powered); 3V3 = regulated output (Seeed: 700 mA)", (0, 0, 0), True)
    s += sym_prop("ki_keywords", "XIAO ESP32S3 Seeed", (0, 0, 0), True)
    s += (f'\t\t(symbol "XIAO_ESP32S3_0_1"\n{sym_rect(-w, 10.16, w, -10.16)}\t\t)\n'
          f'\t\t(symbol "XIAO_ESP32S3_1_1"\n{pins}\t\t)\n\t\t(embedded_fonts no)\n\t)\n')
    return s


def sym_tof_header():
    sig = [("SCL", "3"), ("SDA", "4"), ("XSHUT", "5"), ("GPIO1", "6")]
    pins = "".join(sym_pin("passive", -7.62, 3.81 - 2.54 * i, 0, nm, num) for i, (nm, num) in enumerate(sig))
    pins += sym_pin("passive", 5.08, 10.16, 270, "VIN", "1")
    pins += sym_pin("passive", 5.08, -10.16, 90, "GND", "2")
    s = sym_head("ToF_Header_1x06")
    s += sym_prop("Reference", "J", (0, 13.97, 0)) + sym_prop("Value", "ToF_Header_1x06", (0, -13.97, 0))
    s += sym_prop("Footprint", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", (0, 0, 0), True)
    s += sym_prop("Datasheet", "", (0, 0, 0), True)
    s += sym_prop("Description", "VL53L1X small module header 1x06 2.54 mm. PIN ORDER IS A PLACEHOLDER - UNVERIFIED (module not in hand yet). "
                  "Placeholder order: 1 VIN, 2 GND, 3 SCL, 4 SDA, 5 XSHUT, 6 GPIO1", (0, 0, 0), True)
    s += sym_prop("ki_keywords", "VL53L1X ToF header", (0, 0, 0), True)
    s += (f'\t\t(symbol "ToF_Header_1x06_0_1"\n{sym_rect(-5.08, 7.62, 7.62, -7.62)}\t\t)\n'
          f'\t\t(symbol "ToF_Header_1x06_1_1"\n{pins}\t\t)\n\t\t(embedded_fonts no)\n\t)\n')
    return s


def sym_q_nmos_gsd():
    dev = (KICAD_SYM_DIR / "Device.kicad_sym").read_text(encoding="utf-8")
    i = dev.index('\t(symbol "Q_NMOS"\n')
    depth, j = 0, i
    while True:
        c = dev[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    q = dev[i:j + 1]
    q = q.replace('(symbol "Q_NMOS"', '(symbol "Q_NMOS_GSD"').replace('"Q_NMOS_0_1"', '"Q_NMOS_GSD_0_1"').replace('"Q_NMOS_1_1"', '"Q_NMOS_GSD_1_1"')
    q = q.replace('(property "Value" "Q_NMOS"', '(property "Value" "Q_NMOS_GSD"')
    q = q.replace('(number "D"', '(number "3"').replace('(number "G"', '(number "1"').replace('(number "S"', '(number "2"')
    q = q.replace('(property "Description" "N-MOSFET transistor"',
                  '(property "Description" "N-MOSFET in SOT-23, pin order 1=G 2=S 3=D (AO3400A, Si2302CDS)"')
    q = q.replace('(property "Footprint" ""', '(property "Footprint" "Package_TO_SOT_SMD:SOT-23"')
    # 端子名を表示する（回路図で G/S/D が読めるように）
    q = q.replace("(pin_names\n\t\t\t(offset 0)\n\t\t\t(hide yes)\n\t\t)", "(pin_names\n\t\t\t(offset 0)\n\t\t\t(hide yes)\n\t\t)")
    return q + "\n"


def write_symbols():
    # シンボルライブラリの形式番号は標準ライブラリ（10.0.1）の 20251024。回路図の 20260306 を使うと読み込めない
    lib = ('(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "kicad_symbol_editor")\n\t(generator_version "10.0")\n'
           + sym_xiao() + sym_tof_header() + sym_q_nmos_gsd() + ")\n")
    (LIBS / "head-sensor-board.kicad_sym").write_text(lib, encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ フットプリント
def fp_text(kind, text, x, y, layer, size=1.0, thick=0.15, hide=False):
    h = "\n\t\t(hide yes)" if hide else ""
    return (f'\t(property "{kind}" "{text}"\n\t\t(at {x} {y} 0)\n\t\t(layer "{layer}"){h}\n\t\t(effects\n\t\t\t(font\n'
            f'\t\t\t\t(size {size} {size})\n\t\t\t\t(thickness {thick})\n\t\t\t)\n\t\t)\n\t)\n')


def fp_line(x1, y1, x2, y2, layer, width=0.12):
    return (f'\t(fp_line\n\t\t(start {x1} {y1})\n\t\t(end {x2} {y2})\n\t\t(stroke\n\t\t\t(width {width})\n\t\t\t(type solid)\n'
            f'\t\t)\n\t\t(layer "{layer}")\n\t)\n')


def fp_rect(x1, y1, x2, y2, layer, width=0.12):
    return (f'\t(fp_rect\n\t\t(start {x1} {y1})\n\t\t(end {x2} {y2})\n\t\t(stroke\n\t\t\t(width {width})\n\t\t\t(type solid)\n'
            f'\t\t)\n\t\t(fill no)\n\t\t(layer "{layer}")\n\t)\n')


def fp_poly_text(text, x, y, layer, size=0.8, thick=0.12):
    return (f'\t(fp_text user "{text}"\n\t\t(at {x} {y} 0)\n\t\t(layer "{layer}")\n\t\t(effects\n\t\t\t(font\n'
            f'\t\t\t\t(size {size} {size})\n\t\t\t\t(thickness {thick})\n\t\t\t)\n\t\t)\n\t)\n')


def write_xiao_footprint():
    pitch, half_row = 2.54, 7.62            # 行間隔 15.24 = 2 × 7.62
    s = ('(footprint "XIAO_ESP32S3_THT_2x7_P2.54mm"\n\t(version 20260206)\n\t(generator "kicad-footprint-generator")\n'
         '\t(layer "F.Cu")\n'
         '\t(descr "Seeed Studio XIAO ESP32S3 (Sense) through-hole, 2x7 pins 2.54 mm, rows 15.24 mm apart (Seeed drawing: 15.25), '
         'drill 1.02, outline 17.8 x 21 mm, USB-C at top. Source: Seeed XIAO Series Package and PCB Design p.7")\n'
         '\t(tags "XIAO ESP32S3 Seeed module")\n')
    s += fp_text("Reference", "REF**", 0, -12.9, "F.SilkS") + fp_text("Value", "XIAO_ESP32S3_THT_2x7_P2.54mm", 0, 12.9, "F.Fab")
    s += '\t(attr through_hole)\n\t(duplicate_pad_numbers_are_jumpers no)\n'
    # 外形（シルク）と USB-C 側の印
    s += fp_rect(-8.9, -10.5, 8.9, 10.5, "F.SilkS")
    s += fp_rect(-8.9, -10.5, 8.9, 10.5, "F.Fab", 0.1)
    s += fp_rect(-4.5, -10.5, 4.5, -8.3, "F.Fab", 0.1)
    s += fp_poly_text("USB-C", 0, -9.3, "F.Fab", 0.8)
    # コートヤード = ピンソケットの 2 列の帯だけ（ソケットの内側は、XIAO の下の空間。高さ 0.9 mm 以下の 0603 / 2010 を置いてよい）
    s += fp_rect(-9.0, -8.9, -6.25, 8.9, "F.CrtYd", 0.05)
    s += fp_rect(6.25, -8.9, 9.0, 8.9, "F.CrtYd", 0.05)
    # パッド: 左列 1〜7（上→下）、右列 8〜14（下→上）
    pads = []
    for i in range(7):
        pads.append((str(i + 1), -half_row, -7.62 + pitch * i))
    for i in range(7):
        pads.append((str(8 + i), half_row, 7.62 - pitch * i))
    for num, x, y in pads:
        shape = "rect" if num == "1" else "circle"
        s += (f'\t(pad "{num}" thru_hole {shape}\n\t\t(at {x} {y})\n\t\t(size 1.8 1.8)\n\t\t(drill 1.02)\n'
              f'\t\t(layers "*.Cu" "*.Mask")\n\t\t(remove_unused_layers no)\n\t)\n')
    s += '\t(embedded_fonts no)\n)\n'
    (LIBS / "head-sensor-board.pretty" / "XIAO_ESP32S3_THT_2x7_P2.54mm.kicad_mod").write_text(s, encoding="utf-8", newline="\n")


def write_led_footprint():
    # Nichia STS-DA1-1913 p.5 推奨ランド。中心は LED 本体（3.0 x 1.4）の中心。左 = カソード、右 = アノード
    # カソード: 耳 x[-2.0,-1.4] 高さ 1.55 + 本体側 x[-1.4, 0.26] 高さ 0.86
    # アノード: 本体側 x[0.76, 1.40] 高さ 0.86 + 耳 x[1.40, 2.0] 高さ 1.55   （ギャップ 0.5）
    def pad(num, cx, tab_w, tab_h, poly):
        pts = " ".join(f"(xy {x} {y})" for x, y in poly)
        return (f'\t(pad "{num}" smd custom\n\t\t(at {cx} 0)\n\t\t(size {tab_w} {tab_h})\n'
                f'\t\t(layers "F.Cu" "F.Mask" "F.Paste")\n\t\t(options\n\t\t\t(clearance outline)\n\t\t\t(anchor rect)\n\t\t)\n'
                f'\t\t(primitives\n\t\t\t(gr_poly\n\t\t\t\t(pts\n\t\t\t\t\t{pts}\n\t\t\t\t)\n\t\t\t\t(width 0)\n'
                f'\t\t\t\t(fill yes)\n\t\t\t)\n\t\t)\n\t)\n')
    s = ('(footprint "LED_Nichia_NSSW157T"\n\t(version 20260206)\n\t(generator "kicad-footprint-generator")\n\t(layer "F.Cu")\n'
         '\t(descr "Nichia NSSW157T white chip LED, body 3.0 x 1.4 x 0.52 mm, pad 1 = cathode (large, left), pad 2 = anode (right). '
         'Land pattern from Nichia STS-DA1-1913 p.5 (overall 4.0 x 1.55). Reflow only; do not press the resin.")\n'
         '\t(tags "LED Nichia NSSW157T")\n')
    s += fp_text("Reference", "REF**", 0, -1.9, "F.SilkS", 0.8, 0.12) + fp_text("Value", "NSSW157T", 0, 1.9, "F.Fab", 0.8, 0.12)
    s += '\t(attr smd)\n\t(duplicate_pad_numbers_are_jumpers no)\n'
    s += fp_rect(-1.5, -0.7, 1.5, 0.7, "F.Fab", 0.1)
    s += fp_line(-0.5, -0.7, -0.5, 0.7, "F.Fab", 0.1)                      # カソード側のマーク（本体図）
    s += fp_rect(-2.25, -1.05, 2.25, 1.05, "F.CrtYd", 0.05)
    # シルク: パッドの上下に短い線（重ならない位置）。カソード側に縦線
    s += fp_line(-2.25, -1.0, 2.25, -1.0, "F.SilkS", 0.12) + fp_line(-2.25, 1.0, 2.25, 1.0, "F.SilkS", 0.12)
    s += fp_line(-2.25, -1.0, -2.25, 1.0, "F.SilkS", 0.12)
    s += pad("1", -1.7, 0.6, 1.55, [(0.0, -0.43), (1.96, -0.43), (1.96, 0.43), (0.0, 0.43)])
    s += pad("2", 1.7, 0.6, 1.55, [(0.0, -0.43), (-0.94, -0.43), (-0.94, 0.43), (0.0, 0.43)])   # 本体側 x[0.76, 1.40]
    s += '\t(embedded_fonts no)\n)\n'
    (LIBS / "head-sensor-board.pretty" / "LED_Nichia_NSSW157T.kicad_mod").write_text(s, encoding="utf-8", newline="\n")


TP_FOOTPRINT = """(footprint "TestPoint_Pad_D1.5mm_NoSilk"
	(version 20260206)
	(generator "kicad-footprint-generator")
	(layer "F.Cu")
	(descr "SMD pad as test point, diameter 1.5 mm, no silkscreen ring (derived from KiCad TestPoint_Pad_D1.5mm)")
	(tags "test point SMD pad")
	(property "Reference" "REF**"
		(at 0 -1.65 0)
		(layer "F.SilkS")
		(effects
			(font
				(size 1 1)
				(thickness 0.15)
			)
		)
	)
	(property "Value" "TestPoint_Pad_D1.5mm_NoSilk"
		(at 0 1.75 0)
		(layer "F.Fab")
		(effects
			(font
				(size 1 1)
				(thickness 0.15)
			)
		)
	)
	(attr exclude_from_pos_files exclude_from_bom)
	(duplicate_pad_numbers_are_jumpers no)
	(fp_circle
		(center 0 0)
		(end 1.05 0)
		(stroke
			(width 0.05)
			(type solid)
		)
		(fill no)
		(layer "F.CrtYd")
	)
	(pad "1" smd circle
		(at 0 0)
		(size 1.5 1.5)
		(layers "F.Cu" "F.Mask")
	)
	(embedded_fonts no)
)
"""


def write_tp_footprint():
    # 標準の TestPoint_Pad_D1.5mm から銀色の輪（半径 0.95）だけ除いたもの。名前の刻印を近くに置けるように。
    (LIBS / "head-sensor-board.pretty" / "TestPoint_Pad_D1.5mm_NoSilk.kicad_mod").write_text(TP_FOOTPRINT, encoding="utf-8", newline="\n")


def write_tables():
    sym = ('(sym_lib_table\n\t(version 7)\n\t(lib\n\t\t(name "head-sensor-board")\n\t\t(type "KiCad")\n'
           '\t\t(uri "${KIPRJMOD}/libs/head-sensor-board.kicad_sym")\n\t\t(options "")\n'
           '\t\t(descr "head-sensor-board: custom symbols (XIAO ESP32S3, ToF header, Q_NMOS_GSD)")\n\t)\n)\n')
    fp = ('(fp_lib_table\n\t(version 7)\n\t(lib\n\t\t(name "head-sensor-board")\n\t\t(type "KiCad")\n'
          '\t\t(uri "${KIPRJMOD}/libs/head-sensor-board.pretty")\n\t\t(options "")\n'
          '\t\t(descr "head-sensor-board: custom footprints (XIAO ESP32S3 THT, NSSW157T)")\n\t)\n)\n')
    (ROOT / "sym-lib-table").write_text(sym, encoding="utf-8", newline="\n")
    (ROOT / "fp-lib-table").write_text(fp, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    (LIBS / "head-sensor-board.pretty").mkdir(parents=True, exist_ok=True)
    write_symbols()
    write_xiao_footprint()
    write_led_footprint()
    write_tp_footprint()
    write_tables()
    print("ok: libs/head-sensor-board.kicad_sym, .pretty (3 footprints), sym-lib-table, fp-lib-table")
