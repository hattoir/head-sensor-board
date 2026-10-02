#!/usr/bin/env python3
"""基板を最初から作り直す（Stage 4 の一括実行）。システムの Python で実行する:

    python tools/make_board.py [--width 44] [--height 28] [--no-route] [--attempts 6]

  1. gen_pcb.py     外形・部品配置・刻印（KiCad の Python）  ← 既存の配線は消える
  2. route.py       配線（numpy + scipy。docs/routes.json）
  3. apply_routes.py  トラック・ビア・GND ベタを基板へ（KiCad の Python）
  4. kicad-cli で DRC（回路図との対応つき）→ docs/drc_report.txt
"""
import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KPY = "C:/Program Files/KiCad/10.0/bin/python.exe"
KC = "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"


def run(cmd, **kw):
    print("$", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, **kw)
    return r


def drc(report):
    run([KC, "pcb", "drc", "--schematic-parity", "--severity-all", "--format", "report", "--output", report, "head-sensor-board.kicad_pcb"],
        capture_output=True)
    text = pathlib.Path(report).read_text(encoding="utf-8", errors="replace")
    counts = {}
    for m in re.finditer(r"^\[(\w+)\]", text, re.M):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", default="44")
    ap.add_argument("--height", default="28")
    ap.add_argument("--no-route", action="store_true")
    ap.add_argument("--reuse-routes", action="store_true", help="docs/routes.json をそのまま使う（ランドの位置を変えていないとき = 刻印だけ直したとき）。DRC で整合を確かめる")
    ap.add_argument("--attempts", default="6")
    ap.add_argument("--no-render", action="store_true", default=True)
    args = ap.parse_args()
    run([KPY, "tools/gen_pcb.py", "--width", args.width, "--height", args.height, "--no-render"], check=True)
    if not args.no_route:
        if not args.reuse_routes:
            run([sys.executable, "tools/route.py", "--attempts", args.attempts], check=True)
        run([KPY, "tools/apply_routes.py"], check=True)
    counts, text = drc(str(ROOT / "docs" / "drc_report.txt"))
    print("DRC:", counts if counts else "0 violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
