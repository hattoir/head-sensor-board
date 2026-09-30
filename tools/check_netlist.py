#!/usr/bin/env python3
"""回路図のネットリストを、設計意図から書いた「期待するネット」と突き合わせる（生成スクリプトとは独立の検証）。

    python tools/check_netlist.py            # kicad-cli でネットリストを出力して照合する

ERC が 0 件でも、配線の取り違えは見つからない。この照合で「どのピンがどのピンにつながっているか」を確かめる。
"""
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
KC = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

# 期待するネット（名前はどうでもよい。ピンの集合が一致するか）。ピン番号は部品の実物（フットプリント）の番号。
EXPECTED = {
    "+3V3": ["U1.12", "R1.1", "R2.1", "J1.1", "J2.1", "R11.1", "R12.1", "R13.1", "R14.1", "TP1.1", "C1.1", "C2.1", "C3.1"],
    "+5V": ["U1.14", "R3.1", "R4.1"],
    "GND": ["U1.13", "J1.2", "J2.2", "R7.2", "R8.2", "R9.2", "R10.2", "TP2.1", "C1.2", "C2.2", "C3.2"],
    "SDA": ["U1.5", "J1.4", "J2.4", "R13.2", "TP4.1"],
    "SCL": ["U1.6", "J1.3", "J2.3", "R14.2", "TP3.1"],
    "XSHUT_L": ["U1.1", "J1.5", "R11.2", "TP5.1"],
    "XSHUT_R": ["U1.2", "J2.5", "R12.2", "TP6.1"],
    "LED_PWM_L": ["U1.3", "R5.1"],
    "LED_PWM_R": ["U1.4", "R6.1"],
    "GATE_L": ["R5.2", "Q1.1", "R7.1"],
    "GATE_R": ["R6.2", "Q2.1", "R8.1"],
    "N3V3_L": ["R1.2", "SJ1.1"],
    "N5V_L": ["R3.2", "SJ1.3"],
    "N3V3_R": ["R2.2", "SJ2.1"],
    "N5V_R": ["R4.2", "SJ2.3"],
    "LEDA_L": ["SJ1.2", "D1.2", "J3.1"],
    "LEDA_R": ["SJ2.2", "D2.2", "J4.1"],
    "LEDK_L": ["D1.1", "Q1.3", "J3.2"],
    "LEDK_R": ["D2.1", "Q2.3", "J4.2"],
    "SENSE_L": ["Q1.2", "R9.1", "TP7.1"],
    "SENSE_R": ["Q2.2", "R10.1", "TP8.1"],
    "TOF_L_INT": ["J1.6", "R15.2"],
    "TOF_R_INT": ["J2.6", "R16.2"],
    "D8_GPIO7": ["R15.1", "U1.9"],
    "D9_GPIO8": ["R16.1", "U1.10"],
}
NOT_CONNECTED = ["U1.7", "U1.8", "U1.11"]       # 予約・未使用（no_connect フラグ）


def netlist():
    with tempfile.TemporaryDirectory() as d:
        out = pathlib.Path(d) / "n.xml"
        subprocess.run([KC, "sch", "export", "netlist", "--format", "kicadxml", "--output", str(out),
                        str(ROOT / "head-sensor-board.kicad_sch")], check=True, capture_output=True)
        tree = ET.parse(out)
    nets = {}
    for net in tree.getroot().find("nets"):
        pins = sorted(f'{n.get("ref")}.{n.get("pin")}' for n in net.findall("node") if not n.get("ref").startswith("#"))
        nets[net.get("name")] = pins
    comps = {c.get("ref"): c for c in tree.getroot().find("components")}
    return nets, comps


def footprint_pads(fp_id):
    """'Lib:Name' のフットプリントファイルからパッド番号の集合を返す（標準ライブラリ or libs/）。"""
    import re
    lib, name = fp_id.split(":")
    std = pathlib.Path("C:/Program Files/KiCad/10.0/share/kicad/footprints")
    base = ROOT / "libs" / f"{lib}.pretty" if lib == "head-sensor-board" else std / f"{lib}.pretty"
    text = (base / f"{name}.kicad_mod").read_text(encoding="utf-8")
    return set(re.findall(r'\(pad "([^"]*)"', text))


def check_footprints(nets, comps):
    """回路図の各ピン番号が、割り当てたフットプリントのパッドに存在するか（Stage 3 の基板への取り込みで不一致にならないか）。"""
    bad = 0
    used = {}
    for net, pins in nets.items():
        for p in pins:
            ref, pin = p.split(".")
            used.setdefault(ref, set()).add(pin)
    for ref, comp in sorted(comps.items()):
        fp = comp.findtext("footprint")
        if not fp:
            bad += 1
            print(f"FAIL {ref}: no footprint assigned")
            continue
        pads = footprint_pads(fp)
        missing = sorted(used.get(ref, set()) - pads)
        if missing:
            bad += 1
            print(f"FAIL {ref} ({fp}): schematic pins {missing} not in footprint pads {sorted(pads)}")
    print(f"footprint check: {len(comps)} parts, {'all schematic pins exist as pads' if not bad else str(bad) + ' problem(s)'}")
    return bad


def main():
    nets, comps = netlist()
    by_pins = {tuple(v): k for k, v in nets.items() if v}
    bad = 0
    for name, pins in EXPECTED.items():
        key = tuple(sorted(pins))
        if key in by_pins:
            print(f"OK   {name:10s} = {by_pins[key]}")
        else:
            bad += 1
            # 近いネットを探して差分を見せる
            best = max(nets.items(), key=lambda kv: len(set(kv[1]) & set(pins)))
            miss, extra = sorted(set(pins) - set(best[1])), sorted(set(best[1]) - set(pins))
            print(f"FAIL {name:10s} expected {pins}\n     closest net {best[0]}: missing {miss}, extra {extra}")
    expected_pins = {p for v in EXPECTED.values() for p in v}
    for n, pins in nets.items():
        for p in pins:
            if p not in expected_pins and p not in NOT_CONNECTED:
                bad += 1
                print(f"FAIL pin {p} is on net {n} but not expected anywhere")
    for p in NOT_CONNECTED:
        if any(p in v and len(v) > 1 for v in nets.values()):
            bad += 1
            print(f"FAIL {p} should be unconnected")
    bad += check_footprints(nets, comps)
    # 部品: 参照・値・フットプリント・DNP
    print(f"\n{len(comps)} components: " + " ".join(sorted(comps, key=lambda r: (r.rstrip('0123456789'), int(''.join(c for c in r if c.isdigit()) or 0)))))
    print("RESULT:", "ALL NETS MATCH" if bad == 0 else f"{bad} PROBLEM(S)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
