#!/usr/bin/env python3
"""回路図のネットリストから、組み立て後の導通・短絡の確認表（docs/bringup_nets.md）を作る。

    python tools/gen_bringup_tables.py

各ネットについて、つながるべきパッド（部品.ピン）と、テスターを当てやすい点（TP・ヘッダ）を並べる。
「同じネットのパッドどうしは導通する（部品を介さない場合）」「違うネットどうしは導通しない」を、人が確かめるための表。
回路図が変わったら作り直す（手で直さない）。
"""
import pathlib
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
KC = "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
SCH = ROOT / "head-sensor-board.kicad_sch"

# 部品を介さずに同じ電位になるもの（導通するはず）と、部品を介すもの（値で判断）の区別は、ここでは付けない。
# 測りやすい点: TP とヘッダのピン、XIAO のソケットのパッド（上面の穴）
HANDY = ("TP", "J")
ORDER = ["+3V3", "GND", "+5V"]


def netlist():
    with tempfile.TemporaryDirectory() as d:
        out = pathlib.Path(d) / "n.xml"
        subprocess.run([KC, "sch", "export", "netlist", "--format", "kicadxml", "--output", str(out), str(SCH)], check=True, capture_output=True)
        root = ET.parse(out).getroot()
    vals = {c.get("ref"): c.findtext("value") for c in root.find("components")}
    nets = {}
    for n in root.find("nets"):
        nodes = [(x.get("ref"), x.get("pin")) for x in n.findall("node") if not x.get("ref").startswith("#")]
        if nodes and not n.get("name").startswith("unconnected-"):
            nets[n.get("name")] = nodes
    return vals, nets


def main():
    vals, nets = netlist()

    def key(name):
        return (ORDER.index(name) if name in ORDER else 9, name)

    lines = [
        "# 導通・短絡の確認表（回路図から `tools/gen_bringup_tables.py` が作る。手で直さない）",
        "",
        "部品の実装前（基板だけ）と実装後に、テスターで確かめる（[bringup_plan.md](bringup_plan.md) の HG-K-03 / HG-K-04）。",
        f"ネット {len(nets)} 本。「測りやすい点」= テストポイント（TPn）・ヘッダ（J1〜J4）のピン。XIAO は U1.n = ソケットのパッド（n = XIAO のピン番号。1〜7 が D0〜D6、8〜14 が D7, D8, D9, D10, 3V3, GND, 5V）。",
        "**同じネットのパッドどうしは、間に部品が無ければ導通する。違うネットどうしは導通しない**（半田ジャンパー SJ の 1-2 は既定で橋渡しなので、SJ の A と LEDA は導通する）。",
        "",
        "| ネット | パッド数 | つながるパッド（部品.ピン） | 測りやすい点 |",
        "|---|---|---|---|",
    ]
    for name in sorted(nets, key=key):
        nodes = nets[name]
        pads = ", ".join(f"{r}.{p}" for r, p in sorted(nodes, key=lambda x: (x[0][0] != "U", x[0], int(x[1]) if x[1].isdigit() else 0)))
        handy = ", ".join(f"{r}.{p}" if r.startswith("J") else r for r, p in nodes if r.startswith(HANDY))
        lines.append(f"| `{name}` | {len(nodes)} | {pads} | {handy or '（部品のパッドだけ）'} |")
    lines += [
        "",
        "## 当たりをつける値（部品の実装後。電源を入れずに測る。値は回路図の部品表から）",
        "",
        "| 測る 2 点 | 期待 | 外れたら |",
        "|---|---|---|",
        "| TP1（3V3）↔ TP2（GND） | **短絡していない**（数 kΩ 以上。コンデンサの充電で最初は低く見えて上がる） | 1 kΩ 未満 = はんだブリッジ。SJ・R1/R2・C1〜C3 まわりを見る |",
        "| ゲート（Q1.1 / Q2.1）↔ GND | 約 100 kΩ（R7 / R8） | 開放 = R7/R8 の未はんだ。0 Ω = ブリッジ |",
        "| XIAO の D2 / D3 のパッド（U1.3 / U1.4）↔ ゲート（Q1.1 / Q2.1） | 約 220 Ω（R5 / R6） | 開放 = R5/R6 の未はんだ |",
        "| TP5 / TP6（XSHUT）↔ TP1（3V3） | 約 10 kΩ（R11 / R12） | 開放 = R11/R12 の未はんだ |",
        "| TP7 / TP8（SENSE）↔ GND | 約 1 Ω（R9 / R10。テスターの導線の抵抗を引く） | 開放 = R9/R10 の未はんだ。数十 Ω 以上 = 接触不良 |",
        "| SJ1 / SJ2 の pad1 ↔ pad2 | **導通（既定: はんだで橋渡し済み = 3V3）** | 開放 = 橋が切れている（5V 用に切った後なら正常） |",
        "| SJ1 / SJ2 の pad2 ↔ pad3 | **開放**（既定） | 導通 = 3V3 と 5V がつながっている。**通電しない** |",
        "| J3 / J4 の pin1（+）↔ pin2（−） | 抵抗レンジで**開放に見える**（間に D1 / D2 のダイオードがあるだけ） | 0 Ω に近い = **+ と − の短絡。R1 が約 0.5 W、R3 が約 0.7 W を消費して焼ける**。通電しない |",
        "| J1 / J2 の各ピン ↔ 対応する TP・ソケットのパッド | 上の表のとおり導通 | 開放 = 配線・はんだの不良 |",
        "",
    ]
    (ROOT / "docs" / "bringup_nets.md").write_text("\n".join(lines), encoding="utf-8", newline=chr(10))
    print(f"docs/bringup_nets.md: {len(nets)} nets")


if __name__ == "__main__":
    main()
