#!/usr/bin/env python3
"""Stage 2 の成果物をまとめて作る（回路図からの派生物。手で編集しない）。

    python tools/make_outputs.py

作るもの
  docs/erc_report.txt                     ERC（プロジェクトの設定どおり）
  docs/erc_report_strict.txt              ERC（既定で無視される 4 種の検査も有効にした厳格版）
  docs/head-sensor-board_schematic.pdf    回路図 PDF
  docs/bom.csv / docs/bom.md              BOM（型番・パッケージ・定格つき）
  ../../head-sensor-board_upload.zip      BoardRepo 用の束（C:/2026/Serpens_Home AI/ に置く。Git には入れない）
"""
import csv
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
KC = "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
SCH = ROOT / "head-sensor-board.kicad_sch"
ZIP_OUT = ROOT.parent.parent / "head-sensor-board_upload.zip"


def run(args):
    return subprocess.run([KC] + [str(a) for a in args], capture_output=True)


def erc():
    r = run(["sch", "erc", "--format", "report", "--severity-all", "--exit-code-violations",
             "--output", DOCS / "erc_report.txt", SCH])
    ok = r.returncode == 0
    # 厳格版: 既定で無視される検査（footprint_filter など）を warning にして、別フォルダで実行する
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        for f in ("head-sensor-board.kicad_sch", "head-sensor-board.kicad_pcb", "sym-lib-table", "fp-lib-table"):
            shutil.copy(ROOT / f, d / f)
        shutil.copytree(ROOT / "libs", d / "libs")
        pro = json.loads((ROOT / "head-sensor-board.kicad_pro").read_text(encoding="utf-8"))
        ignored = [k for k, v in pro["erc"]["rule_severities"].items() if v == "ignore"]
        for k in ignored:
            pro["erc"]["rule_severities"][k] = "warning"
        (d / "head-sensor-board.kicad_pro").write_text(json.dumps(pro, indent=2, ensure_ascii=False), encoding="utf-8")
        r2 = run(["sch", "erc", "--format", "report", "--severity-all", "--exit-code-violations",
                  "--output", DOCS / "erc_report_strict.txt", d / "head-sensor-board.kicad_sch"])
    print(f"ERC: {'0 violations' if ok else 'VIOLATIONS (exit ' + str(r.returncode) + ')'}; strict (+{len(ignored)} normally-ignored checks): "
          f"{'0 violations' if r2.returncode == 0 else 'VIOLATIONS'}")
    return ok and r2.returncode == 0


def pdf():
    run(["sch", "export", "pdf", "--output", DOCS / "head-sensor-board_schematic.pdf", SCH])
    print("PDF:", (DOCS / "head-sensor-board_schematic.pdf").stat().st_size, "bytes")


# 基板の外にある部品（回路図には出ないが、組み立てに要る）
EXTRAS = [
    ("U1 用", "2", "ピンソケット 1×7（メス）", "2.54 mm ピッチ、スルーホール", "高さ 8.5 mm と仮定（購入品で確認）", "—",
     "XIAO を載せる。ピンヘッダ（オス）に替えてもよい（同じパッド）"),
    ("XIAO 側", "2", "ピンヘッダ 1×7（オス）", "2.54 mm ピッチ", "Seeed の 7 pin ヘッダ SKU 320020159 は全長 10.34 / 上 6.00 / 下 1.80 mm",
     "—", "XIAO に同梱かは**未確認**。無ければ購入"),
    ("J1, J2 用", "12", "ジャンパー線（ToF 小基板との接続）", "ToF 小基板のピンの種類による（メス–メス / メス–オス）", "—", "—",
     "ToF のピン配置・コネクタは**未確認**。候補: 秋月 100288「ブレッドボード・ジャンパーワイヤ 14 種類×10 本」（`秋月_購入リスト_20260930.md` に記載。**xlsx の購入リストには無い**）"),
    ("H1, H2 用", "2", "M2 ねじ（+ スペーサ）", "M2、取付穴 φ2.2", "—", "—", "頭への取り付け方法が未定のため**未決**（任意）"),
]


def bom():
    csv_path = DOCS / "bom.csv"
    r = run(["sch", "export", "bom", "--output", csv_path,
             "--fields", "Reference,Value,Footprint,MPN,Manufacturer,Rating,Notes,${QUANTITY},${DNP}",
             "--labels", "Refs,Value,Footprint,MPN,Manufacturer,Rating,Notes,Qty,DNP",
             "--group-by", "Value,Footprint,MPN,Notes,${DNP}", "--sort-field", "Reference", "--ref-range-delimiter", "", SCH])
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    groups = {}
    for row in rows:
        key = (row["Footprint"], row["MPN"], row["Rating"], bool(row["DNP"].strip()), row["Value"] if row["MPN"].startswith("chip resistor") else "")
        g = groups.setdefault(key, dict(refs=[], qty=0, notes=[], mfr=row["Manufacturer"], values=[]))
        g["refs"].append(row["Refs"])
        g["qty"] += int(row["Qty"])
        if row["Value"] not in g["values"]:
            g["values"].append(row["Value"])
        for n in row["Notes"].split(" / "):
            if n not in g["notes"]:
                g["notes"].append(n)

    def order(k):
        ref = groups[k]["refs"][0].split(",")[0].strip()      # KiCad が "D1,D2" のように束ねる
        pre = "".join(c for c in ref if c.isalpha())
        num = int("".join(c for c in ref if c.isdigit()) or 0)
        return ({"U": 0, "J": 1, "SJ": 2, "D": 3, "Q": 4, "R": 5, "C": 6}.get(pre, 9), num)

    lines = [
        "# BOM（部品表）— head-sensor-board Rev A（Stage 2）",
        "",
        "**回路図から `tools/make_outputs.py` が作る。手で直さない**（直すときは回路図 → 再生成）。生の書き出しは [bom.csv](bom.csv)。",
        "DNP = 既定で実装しない（フットプリントだけ置く）。**購入先・品番・価格の列は、User が秋月などで調べて埋める**（ここでは仕様だけ）。",
        "抵抗・コンデンサは汎用品（型番の指定なし）。**仕様（値・パッケージ・定格）を満たせばよい。** 許容差: R9/R10（電流検出 1 Ω）は ±1 %、ほかの抵抗は ±5 % 以内、"
        "R15/R16 は 0 Ω ジャンパー。コンデンサは C1 が X5R 以上・10 V 以上、C2/C3 が X7R・16 V 以上。",
        "",
        "## 1. 基板に載せる部品（回路図から）",
        "",
        "| 記号 | 数量 | 値 | パッケージ（フットプリント） | 型番・種類 | 定格 | DNP | 備考 | 購入先・品番・価格 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for k in sorted(groups, key=order):
        fp, mpn, rating, dnp, _ = k
        g = groups[k]
        v = " / ".join(g["values"])
        refs = ", ".join(g["refs"])
        mf = f"（{g['mfr']}）" if g["mfr"] else ""
        note = " / ".join(g["notes"]).replace("|", "/")
        lines.append(f"| {refs} | {g['qty']} | {v} | `{fp}` | {mpn}{mf} | {rating} | {'**DNP**' if dnp else ''} | {note} | （User が調査） |")
    lines += [
        "",
        "回路図に出るが部品ではないもの: **TP1〜TP8**（テストポイントのパッド φ1.5 mm、`TestPoint:TestPoint_Pad_D1.5mm`）、"
        "**H1, H2**（M2 取付穴 φ2.2、`MountingHole:MountingHole_2.2mm_M2`）、**SJ1, SJ2**（半田ジャンパーのパッド。部品なし）。",
        "",
        "## 2. 基板の外の部品（組み立てに必要）",
        "",
        "| 用途 | 数量 | 品名 | パッケージ・寸法 | 定格・メモ | DNP | 備考 |",
        "|---|---|---|---|---|---|---|",
    ]
    for use, qty, name, pkg, spec, dnp, note in EXTRAS:
        lines.append(f"| {use} | {qty} | {name} | {pkg} | {spec} | {dnp} | {note} |")
    lines += [
        "",
        "## 3. 仕様の根拠（主なもの）",
        "",
        "- **NSSW157T**: Nichia STS-DA1-1913（秋月配布）— IF max 150 mA、VF 2.8〜3.4 V @80 mA、3.0×1.4×0.52 mm。",
        "- **AO3400A**: Alpha & Omega Rev 3.1（2023-07）— 30 V / 5.7 A、VGS(th) 0.65〜1.45 V、RDS(on) < 48 mΩ @VGS=2.5 V、VGS 最大 ±12 V、SOT-23。"
        "**Si2302CDS**（Vishay S12-2336 Rev D）— 20 V / 2.6 A、VGS(th) 0.40〜0.85 V、RDS(on) < 75 mΩ @2.5 V、VGS 最大 ±8 V、SOT-23（1=G, 2=S, 3=D）。"
        "どちらも 3.3 V ロジックで駆動できる（ESP32-S3 の VOH 最小 2.64 V でも VGS(th) 最大の 1.8 倍以上）。",
        "- **R3/R4（5V 用 33 Ω 2010）**: 最悪時 176 mW = 0.5 W の 35 %（`tools/led_budget.py`）。0603/0805 では足りない（1206 でも 70 % で 50 % 基準を超える）。",
        "- **R1/R2（3V3 用 20 Ω 0603）**: 最悪時 30 mW = 0.1 W の 30 %。",
        "- **C1（10 µF）**: 3V3 電源だめ。X5R の 10 µF は DC バイアスで容量が下がるので、10 V 以上を選ぶ。",
        "",
    ]
    (DOCS / "bom.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"BOM: {len(rows)} line(s) in csv, {len(groups)} group(s) in bom.md")


def upload_zip():
    files = [".gitignore", "README.md", "head-sensor-board.kicad_pro", "head-sensor-board.kicad_sch", "head-sensor-board.kicad_pcb",
             "sym-lib-table", "fp-lib-table", "libs/head-sensor-board.kicad_sym"]
    files += [f"libs/head-sensor-board.pretty/{p.name}" for p in sorted((ROOT / "libs" / "head-sensor-board.pretty").glob("*.kicad_mod"))]
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(ROOT / f, f)
    print("ZIP:", ZIP_OUT, ZIP_OUT.stat().st_size, "bytes,", len(files), "files")


if __name__ == "__main__":
    ok = erc()
    pdf()
    bom()
    upload_zip()
    sys.exit(0 if ok else 1)
