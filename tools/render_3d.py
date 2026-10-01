#!/usr/bin/env python3
"""KiCad の 3D ビューを PNG にする（kicad-cli pcb render）。システムの Python で実行する:

    python tools/render_3d.py

  docs/board_3d_iso.png       斜め上から（XIAO と Sense 拡張ボードの簡易モデルつき。高さは仮）
  docs/board_3d_top.png       真上から（XIAO つき）
  docs/board_3d_top_noxiao.png  真上から（XIAO を外した状態。配線・刻印・部品が見える）
  docs/board_3d_bottom.png    裏面（GND ベタ）

XIAO・LED の 3D モデルは tools/gen_3d.py の簡易モデル。J1〜J4 は KiCad 標準のピンヘッダのモデル。
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
KC = "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
KPY = "C:/Program Files/KiCad/10.0/bin/python.exe"
DOCS = ROOT / "docs"


def render(pcb, out, *extra, width=1800, height=1200):
    cmd = [KC, "pcb", "render", "--quality", "basic", "--width", str(width), "--height", str(height), "--output", str(out), *extra, str(pcb)]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(r.stdout.decode("cp932", "replace"), r.stderr.decode("cp932", "replace"))
        sys.exit(1)
    print("PNG:", out)


def main():
    pcb = ROOT / "head-sensor-board.kicad_pcb"
    render(pcb, DOCS / "board_3d_iso.png", "--side", "top", "--rotate", "-50,0,25", "--perspective", "--zoom", "0.9")
    render(pcb, DOCS / "board_3d_top.png", "--side", "top")
    render(pcb, DOCS / "board_3d_bottom.png", "--side", "bottom")
    # XIAO の 3D モデルだけ外した複製（ランド・穴は残る）
    with tempfile.TemporaryDirectory() as d:
        t = pathlib.Path(d)
        for f in ("head-sensor-board.kicad_pcb", "head-sensor-board.kicad_pro", "fp-lib-table", "sym-lib-table"):
            shutil.copy(ROOT / f, t / f)
        shutil.copytree(ROOT / "libs", t / "libs")
        shutil.copytree(ROOT / "3dmodels", t / "3dmodels")
        script = t / "strip.py"
        script.write_text(
            "import pcbnew\n"
            "b = pcbnew.LoadBoard(r'" + str(t / "head-sensor-board.kicad_pcb") + "')\n"
            "fp = b.FindFootprintByReference('U1')\n"
            "fp.Models().clear()\n"
            "b.Save(r'" + str(t / "head-sensor-board.kicad_pcb") + "')\n", encoding="utf-8")
        subprocess.run([KPY, str(script)], check=True)
        render(t / "head-sensor-board.kicad_pcb", DOCS / "board_3d_top_noxiao.png", "--side", "top")


if __name__ == "__main__":
    main()
