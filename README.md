# head-sensor-board

**蛇ロボット（Serpens）Floor Watch の「頭のセンサー基板（試作用）」**の KiCad プロジェクト。

- 用途: ToF の崖判定（HG-H2 の T6-1〜T6-4）と、斜め LED の追試（T4）。**本番の基板ではない。**
- 載せるもの: XIAO ESP32S3 Sense（ソケット）、VL53L1X 小基板 ×2（**1×6 ヘッダからジャンパー線で引き出す**）、白色チップ LED NSSW157T ×2（MOSFET + PWM。外付け LED 用ヘッダつき）、I2C プルアップ（未実装可）、テストポイント
- 電源は既定で XIAO の **3V3 だけ**。LED の電源だけ、半田ジャンパーで **5V** に切り替えられる。電流の計算は [docs/spec.md](docs/spec.md) §4
- KiCad 10.0.1（回路図 `20260306` / 基板 `20260206`）
- バージョン管理: GitHub（**プライベート** `hattoir/head-sensor-board`）+ [BoardRepo](https://boardrepo.com)

> ## ⚠ ToF 小基板のピン配置は**未確認**（ヘッダの並びは仮）
> VL53L1X 小基板（Amazon B083Z316NC）のピン配置・基板上のプルアップ・I2C アドレスは、販売ページに記載がなく、現物も手元にない。
> J1/J2 の並び（1 VIN, 2 GND, 3 SCL, 4 SDA, 5 XSHUT, 6 GPIO1）は**仮**（PLACEHOLDER）。**現物のピン配置を確認するまで、ガーバーは出さない。**
> ジャンパー線でつなぐので、並びが違っても基板の作り直しは要らない（線でつなぎ替える）。

## 進み具合

| Stage | 内容 | 状態 |
|---|---|---|
| 1 | 仕様と部品表 | 完了（2026-10-01、承認済み） |
| 2 | 回路図と ERC（エラー 0） | **完了・User の確認待ち**（2026-10-01。ERC 0 件、[docs/spec.md](docs/spec.md) §7） |
| 3 | 外形と部品配置案（配置図 PNG。配線なし） | 未着手 |
| 4 | 配線、DRC（エラー 0・未接続 0・回路図との不一致 0）、**ガーバー（ToF のピン配置の確認後）**、push | 未着手 |

## フォルダ構成

| 場所 | 中身 |
|---|---|
| （直下） | KiCad プロジェクト（`.kicad_pro` / `.kicad_sch` / `.kicad_pcb`、`sym-lib-table` / `fp-lib-table`） |
| `docs/` | [spec.md](docs/spec.md)（仕様・計算・検証）、[bom.md](docs/bom.md)・`bom.csv`（部品表）、`erc_report*.txt`、回路図 PDF、`led_budget_output.txt` |
| `libs/` | 自作のシンボル・フットプリント（**KiCad 標準ライブラリに無いものだけ**。下の「ライブラリの出典」） |
| `3dmodels/` | 3D モデル（`.step`）。まだ無い |
| `fabrication/` | 製造データ（ガーバー、ドリル、BOM、部品配置ファイル）。Stage 4 |
| `tools/` | 計算・生成・検証のスクリプト（下の「再生成と検証」） |

## 数値・部品名の出典

確認状態: ✅ 原本（データシート・公式図面）で確認 ／ 🟡 販売ページ・Wiki で確認 ／ 🔴 未確認・仮定。**確認できていないものは、`docs/spec.md` の各表に「未確認」と書いてある。**

| 対象 | 出典 | 確認 |
|---|---|---|
| NSSW157T（Nichia）: 外形 3.0×1.4×0.52、VF、IF max、推奨ランド | [Nichia STS-DA1-1913（秋月配布 PDF）](https://akizukidenshi.com/goodsaffix/nssw157t.pdf)、[秋月 116884](https://akizukidenshi.com/catalog/g/g116884/) | ✅ |
| AO3400A（Alpha & Omega）: VGS(th)、RDS(on) @2.5 V、SOT-23 | [AOS データシート Rev 3.1](https://www.aosmd.com/res/data_sheets/AO3400A.pdf) | ✅ |
| Si2302CDS（Vishay）: VGS(th)、RDS(on) @2.5 V、1=G 2=S 3=D | [Vishay 68645（S12-2336 Rev D）](https://www.vishay.com/docs/68645/si2302cds.pdf) | ✅ |
| VL53L1X（ST）: AVDD 2.6〜3.5 V、消費電流、XSHUT・I2C・既定アドレス、最短 4 cm | ST DS12385 Rev 8（[複製 PDF](https://www.makerguides.com/wp-content/uploads/2024/10/VL53L1X-Datasheet.pdf)。ST 公式サイトの版では未照合） | ✅（複製） |
| ESP32-S3: Wi-Fi 送信ピーク 340 mA、GPIO の IOH/IOL、VOH、GPIO3 ストラッピング | [Espressif ESP32-S3 Datasheet v2.2](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf)（表 5-7・表 5-4・§3.4） | ✅ |
| XIAO ESP32S3: ピン配置、GPIO 番号、3V3 出力 700 mA、Webcam の消費電流、Sense が使う GPIO | [Seeed wiki](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/)（PDF のデータシートは見つからず） | 🟡 |
| XIAO の穴パターン（ピッチ 2.54、行間隔 15.25、穴 φ1.02、外形 21×17.8） | [Seeed "XIAO Series Package and PCB Design" p.7](https://www.seeedstudio.com/blog/wp-content/uploads/2022/08/Seeed-Studio-XIAO-Series-Package-and-PCB-Design.pdf)（シリーズ共通図。S3 個別ではない） | ✅（共通図） |
| VL53L1X 小基板（Amazon B083Z316NC）: 12×17×3.2 mm、3.3〜5 V | [商品ページ](https://www.amazon.co.jp/dp/B083Z316NC)。**ピン配置・プルアップ・アドレスの記載なし** | 🔴 |
| 頭の外形 幅 100 / 高さ 74 / 長さ 78 mm、ToF・LED の位置 | `serpens/ai-shared/design-state.md`、`serpens/docs/design/tof_board_placement_2026-09-30.md`（Design の概念値 = CAD_CONCEPT / ASSUMED） | 🔴（概念値） |
| T6 / T4 の試験の内容 | `serpens/ai-shared/HARDWARE_TODO.md` HT-005 / HT-011、HG-H2 の `hardware_test_plan.md`・`tof_cliff.md`（Engineering の worktree `agent/engineering-h1-j1`、未マージ） | 🟡 |

## ライブラリの出典

`libs/` にあるのは、KiCad 標準ライブラリに無い 5 点だけ（`python tools/gen_libs.py` で生成）。

| 名前 | 種類 | 理由 | 出典 |
|---|---|---|---|
| `XIAO_ESP32S3` | シンボル（14 ピン。電源ピンを上下に置いた表示。ピン番号は実物のまま） | 標準ライブラリに XIAO ESP32S3 が無い | ピン配置は Seeed wiki |
| `ToF_Header_1x06` | シンボル（ピン名つき。**並びは仮 = 未確認**） | ピン名（VIN, GND, SCL, SDA, XSHUT, GPIO1）を回路図に出すため | 自作 |
| `Q_NMOS_GSD` | シンボル（SOT-23 の 1=G 2=S 3=D） | 標準の `Device:Q_NMOS` はピン番号が D/G/S の文字で、SOT-23 のパッド番号と合わない | 図形は KiCad 標準 `Device:Q_NMOS` を流用、ピン番号だけ数字に |
| `XIAO_ESP32S3_THT_2x7_P2.54mm` | フットプリント（穴パターン） | 標準には表面実装用の `RF_Module:MCU_Seeed_ESP32C3` しか無く、2.54 mm の穴パターンが無い | Seeed 公式図面 p.7（行間隔 15.24 mm = 図面の 15.25 を 0.6 in に丸めた、穴 φ1.02、パッド φ1.8） |
| `LED_Nichia_NSSW157T` | フットプリント（T 字のランド） | 標準ライブラリに同寸法のものが無い | Nichia STS-DA1-1913 p.4–5（全長 4.0、カソード 0.6+1.66、ギャップ 0.5、アノード 0.64+0.6、高さ 1.55/0.86） |

3D モデルはまだ無い。

## 再生成と検証

```bash
python tools/led_budget.py        # LED 電流・3V3/5V の総電流の計算（docs/led_budget_output.txt）
python tools/gen_libs.py          # 自作ライブラリ（libs/）と sym-lib-table / fp-lib-table
python tools/gen_schematic.py     # 回路図（※KiCad で手直しした後は実行しない。手直しが消える）
python tools/check_netlist.py     # ネットリストを期待と照合、回路図のピン番号がフットプリントのパッドに存在するか
python tools/make_outputs.py      # ERC・PDF・BOM・BoardRepo 用 zip
```
KiCad は `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe`（PATH には入っていない）。

## BoardRepo について

- BoardRepo は「アップロードのたびに番号つきの版ができる」方式で、閲覧・MCP は OAuth のサインインが要る（[boardrepo.com](https://boardrepo.com)）。**Agent 側からは取り込みを確認できない。User が手動でアップロードする。**
- `snake-main-board` の GitHub リポジトリにも、BoardRepo の Webhook・チェック・コミットステータスは残っていない（確認済み）。
- **アップロード用の束**: `C:\2026\Serpens_Home AI\head-sensor-board_upload.zip`（`tools/make_outputs.py` が作る。Git には入れない）。中身: `.gitignore`、`README.md`、`.kicad_pro`、`.kicad_sch`、`.kicad_pcb`（**Stage 2 では空**）、`sym-lib-table`、`fp-lib-table`、`libs/`（自作ライブラリ 5 点）。
- **アップロードして表示できたかは User の確認が要る。**

## 注意

- `*-backups/`、`fp-info-cache`、`*.kicad_prl`、ロックファイル、自動保存、`*_upload.zip` は Git に入れない（`.gitignore`）。
- 空のフォルダを Git に残すため `3dmodels/` `fabrication/` に `.gitkeep` を置いてある（中身が入ったら消してよい）。
- このフォルダは、親の `serpens`（ロボット制御のリポジトリ）とは**別の Git リポジトリ**（入れ子）。親側は `.git/info/exclude` で無視している。`snake-main-board` とも別。
