# gerbers/ — head-sensor-board Rev A の製造データ

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
| 穴 | PTH φ0.3 mm × 28、PTH φ1 mm × 16、PTH φ1.02 mm × 14、NPTH φ2.2 mm × 2 |
| レジスト | 開口はランドと同寸（拡張 0）。多くの発注先は自分で拡張をかける。色は任意 |
| シルク | 線幅 **0.15 mm**（部品の枠を含む全部）、文字の高さ **0.8 mm**。**JLCPCB の標準は文字の高さ 1.0 mm 以上なので、JLCPCB で発注するときは注文画面の「高精度の文字」（0.8 mm 以上）を選ぶ**（追加費用の有無は未確認）。PCBWay・Elecrow・Seeed Fusion は 0.8 mm・0.15 mm で可。**4 社の公開仕様との照合は `docs/fab_check.md`**（2026-10-05 に公開ページから取った値。注文して確かめたものではない） |
| 数量 | User が決める |

## 注意

- **NSSW157T（D1/D2）はリフローかホットエアで付ける部品**（フットプリントの注意書きどおり。樹脂を押さない）。
- J1/J2 は ToF 小基板へのジャンパー線用のヘッダ。**小基板のピン配置は未確認**（README の対応表を現物で埋める）。信号名のシルクと基板の配線は、回路図と一致することを確認済み（`tools/check_board.py`）。
- 検証: `python tools/verify_gerbers.py`（KiCad とは別の gerbonara で、zip の中身を読み直して、外形・ドリルの位置と径・銅の抜けを基板と照合する。`pip install gerbonara` が要る）。`python tools/compare_gerbers.py --current` は、このフォルダが今の基板から作り直したものと同じ図形か（古くなっていないか）を確かめる。`python tools/run_all_checks.py` で全検査をまとめて回せる。結果は `docs/spec.md` §7。
- 届いてからの手順（外観・導通・初回通電・LED 電流・ToF）は `docs/bringup_plan.md`。
