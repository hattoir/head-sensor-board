#!/usr/bin/env python3
"""製造データ（ガーバー・ドリル・位置ファイル・BOM）を gerbers/ にまとめ、ZIP を作る。システムの Python で実行する:

    python tools/make_fabrication.py

**User が配線後の PNG を確認したあとにだけ実行する**（User 指示）。発注はしない。
  gerbers/*.gtl .gbl .gts .gbs .gto .gbo .gtp .gm1   ガーバー（表銅・裏銅・表/裏レジスト・表/裏シルク・表ペースト・外形）
  gerbers/*.drl                                      ドリル（Excellon、PTH と NPTH を別ファイル、mm）
  gerbers/head-sensor-board_gerbers.zip              上の製造データだけの ZIP（発注先へ渡す束）
  gerbers/head-sensor-board_pos.csv                  位置ファイル（表面実装・実装するものだけ。原点 = 基板の左下）
  gerbers/head-sensor-board_BOM.csv                  BOM（docs/bom.csv と同じ。docs/bom.md が読みやすい版）
  gerbers/drill_map（PDF）、README.md、SHA256SUMS.txt
原点: 基板の左下（gen_pcb.py が「ドリル/配置ファイルの原点」に設定）。ガーバー・ドリル・位置ファイルは同じ原点。
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "gerbers"
KC = "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
PCB = ROOT / "head-sensor-board.kicad_pcb"
NAME = "head-sensor-board"
LAYERS = "F.Cu,B.Cu,F.Paste,F.Mask,B.Mask,F.SilkS,B.SilkS,Edge.Cuts"


def run(args):
    r = subprocess.run([KC] + [str(a) for a in args], capture_output=True)
    txt = (r.stdout + r.stderr).decode("cp932", "replace")
    if r.returncode != 0:
        print(txt)
        sys.exit(f"kicad-cli failed: {' '.join(str(a) for a in args[:4])}")
    return txt


def drill_summary(path):
    """Excellon ファイルの (工具の径, 穴の数) の一覧。"""
    tools, cur, count = {}, None, {}
    in_body = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("T") and "C" in line and not in_body:
            num, dia = line[1:].split("C")
            tools[num] = float(dia)
        elif line.strip() == "%":
            in_body = True
        elif in_body and line.startswith("T") and line[1:].isdigit():
            cur = line[1:]
            count.setdefault(cur, 0)
        elif in_body and line.startswith("X") and cur:
            count[cur] += 1
    return sorted((tools[k], count.get(k, 0)) for k in tools)


README = """# gerbers/ — head-sensor-board Rev A の製造データ

**未発注。User の最終確認のあとに発注する**（発注は Agent はしない）。Stage 4 の PNG を User が確認した後に `python tools/make_fabrication.py` で作った（KiCad 10.0.1 の `kicad-cli`）。
基板を直したら、`python tools/make_board.py` → `python tools/make_outputs.py --bom` → `python tools/make_fabrication.py` の順で作り直す（このフォルダのファイルは毎回消して作り直される。手で直さない）。

## 発注先に渡すもの

**`head-sensor-board_gerbers.zip`**（ガーバー 8 層 + ジョブファイル + ドリル 2 本 = 11 ファイル）。

## ファイル

| ファイル | 内容 |
|---|---|
| `*-F_Cu.gtl` / `*-B_Cu.gbl` | 表・裏の銅（GND のベタを含む） |
| `*-F_Mask.gts` / `*-B_Mask.gbs` | 表・裏のレジスト開口（ランドと同寸。ビアはふさぐ） |
| `*-F_Silkscreen.gto` / `*-B_Silkscreen.gbo` | 表・裏のシルク（表: 部品の枠・信号名・L/R・USB-C、裏: 凡例） |
| `*-F_Paste.gtp` | 表のはんだペースト（ステンシルを作るときだけ。手はんだなら不要） |
| `*-Edge_Cuts.gm1` | 外形（角 R1 の長方形） |
| `*-PTH.drl` / `*-NPTH.drl` | ドリル（Excellon、mm）。PTH = めっきあり、NPTH = めっきなし（M2 の取付穴） |
| `*-job.gbrjob` | ジョブファイル（層の構成・寸法） |
| `*-PTH-drl_map.pdf` / `*-NPTH-drl_map.pdf` | ドリルの位置図（目で確かめる用。発注先には要らない） |
| `head-sensor-board_pos.csv` | 位置ファイル（**表面実装で、実装するもの**だけ。DNP の R13〜R16 は含まない。mm、原点は基板の左下、Y は上が +） |
| `head-sensor-board_BOM.csv` | BOM（`docs/bom.csv` と同じ。読みやすい版は `docs/bom.md`） |
| `SHA256SUMS.txt` | 各ファイルのハッシュ（手元で改変していないことの確認用） |

**原点はすべて基板の左下**（ガーバー・ドリル・位置ファイルで共通）。

## 基板の仕様（発注フォームに入れる値。**発注先の仕様との照合は User が行う**）

| 項目 | 値 |
|---|---|
| 層数 | 2 層 |
| 寸法 | 44.0 × 28.0 mm（角 R1.0） |
| 厚み | 1.6 mm |
| 銅厚 | 基板データには指定なし。標準の 1 oz（35 µm）を想定（線の許容電流の目安もこれ） |
| 表面処理 | 指定なし（はんだ付けは手作業。XIAO・ヘッダのスルーホールと 0603 / 2010 / SOT-23 / NSSW157T） |
| 最小線幅 / 最小間隔 | 使った線幅は 0.25 / 0.4 / 0.5 mm（設計の下限 0.2）、間隔 0.2 mm 以上 |
| 銅と外形の距離 | 0.5 mm 以上 |
| ビア | 外径 0.6 mm / 穴 0.3 mm、レジストでふさぐ（テンティング） |
| 穴 | {holes} |
| レジスト | 開口はランドと同寸（拡張 0）。多くの発注先は自分で拡張をかける。色は任意 |
| シルク | 線幅 **0.15 mm**（部品の枠を含む全部）、文字の高さ **0.8 mm**。**JLCPCB の標準は文字の高さ 1.0 mm 以上なので、JLCPCB で発注するときは注文画面の「高精度の文字」（0.8 mm 以上）を選ぶ**（追加費用の有無は未確認）。PCBWay・Elecrow・Seeed Fusion は 0.8 mm・0.15 mm で可。**4 社の公開仕様との照合は `docs/fab_check.md`**（2026-10-05 に公開ページから取った値。注文して確かめたものではない） |
| 数量 | User が決める |

## 注意

- **NSSW157T（D1/D2）はリフローかホットエアで付ける部品**（フットプリントの注意書きどおり。樹脂を押さない）。
- J1/J2 は ToF 小基板へのジャンパー線用のヘッダ。**小基板のピン配置は未確認**（README の対応表を現物で埋める）。信号名のシルクと基板の配線は、回路図と一致することを確認済み（`tools/check_board.py`）。
- 検証: `python tools/verify_gerbers.py`（KiCad とは別の gerbonara で、zip の中身を読み直して、外形・ドリルの位置と径・銅の抜けを基板と照合する。`pip install gerbonara` が要る）。`python tools/compare_gerbers.py --current` は、このフォルダが今の基板から作り直したものと同じ図形か（古くなっていないか）を確かめる。`python tools/run_all_checks.py` で全検査をまとめて回せる。結果は `docs/spec.md` §7。
- 届いてからの手順（外観・導通・初回通電・LED 電流・ToF）は `docs/bringup_plan.md`。
"""


def main():
    if OUT.exists():
        for f in OUT.iterdir():
            if f.is_file() and f.name != ".gitkeep":
                f.unlink()
    OUT.mkdir(exist_ok=True)
    run(["pcb", "export", "gerbers", "--layers", LAYERS, "--subtract-soldermask", "--use-drill-file-origin", "--check-zones", "--output", str(OUT) + "/", PCB])
    run(["pcb", "export", "drill", "--format", "excellon", "--drill-origin", "plot", "--excellon-units", "mm", "--excellon-separate-th",
         "--generate-map", "--map-format", "pdf", "--output", str(OUT) + "/", PCB])
    run(["pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both", "--smd-only", "--exclude-dnp", "--use-drill-file-origin",
         "--output", OUT / f"{NAME}_pos.csv", PCB])
    bom = ROOT / "docs" / "bom.csv"
    if not bom.exists():
        sys.exit("docs/bom.csv が無い。先に python tools/make_outputs.py --bom")
    shutil.copy(bom, OUT / f"{NAME}_BOM.csv")
    holes = []
    for f, plated in (("head-sensor-board-PTH.drl", "PTH"), ("head-sensor-board-NPTH.drl", "NPTH")):
        for dia, n in drill_summary(OUT / f):
            holes.append(f"{plated} φ{dia:g} mm × {n}")
    (OUT / "README.md").write_text(README.replace("{holes}", "、".join(holes)), encoding="utf-8", newline=chr(10))
    fab = sorted(p for p in OUT.iterdir() if p.suffix.lower() in (".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".gtp", ".gm1", ".gko", ".drl", ".gbrjob"))
    zip_path = OUT / f"{NAME}_gerbers.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in fab:
            z.write(p, p.name)
    sums = []
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    print("gerbers/:", ", ".join(p.name for p in sorted(OUT.iterdir())))
    print("zip:", zip_path.name, zip_path.stat().st_size, "bytes,", len(fab), "files")


if __name__ == "__main__":
    main()
