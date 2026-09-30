# head-sensor-board

**蛇ロボット（Serpens）Floor Watch の「頭のセンサー基板（試作用）」**の KiCad プロジェクト。

- 用途: ToF の崖判定（HG-H2 の T6-1〜T6-4）と、斜め LED の追試（T4）。**本番の基板ではない。**
- 載せるもの: XIAO ESP32S3 Sense（ソケット）、VL53L1X 小基板 ×2（1×6 ヘッダ）、白色チップ LED NSSW157T ×2（MOSFET + PWM）、I2C プルアップ（未実装可）、テストポイント
- 電源は XIAO の **3V3 だけ**（5V は使わない）。LED の電流の計算は [docs/spec.md](docs/spec.md) §4
- KiCad 10.0.1（回路図 `20260306` / 基板 `20260206`）
- バージョン管理: GitHub（**プライベート** `hattoir/head-sensor-board`）+ [BoardRepo](https://boardrepo.com)

## 進み具合

| Stage | 内容 | 状態 |
|---|---|---|
| 1 | 仕様と部品表 → [docs/spec.md](docs/spec.md) | **完了・User の確認待ち**（2026-10-01） |
| 2 | 回路図と ERC（エラー 0） | 未着手 |
| 3 | 外形と部品配置案（配置図 PNG。配線なし） | 未着手 |
| 4 | 配線、DRC（エラー 0・未接続 0・回路図との不一致 0）、ガーバー、push | 未着手 |

## フォルダ構成

| 場所 | 中身 |
|---|---|
| （直下） | KiCad プロジェクト（`.kicad_pro` / `.kicad_sch` / `.kicad_pcb`） |
| `docs/` | 仕様・部品表・計算（`spec.md`）、ERC/DRC の結果、配置図 |
| `libs/` | 自作のシンボル・フットプリント（**KiCad 標準ライブラリに無いものだけ**。下の「ライブラリの出典」に出典を書く） |
| `3dmodels/` | 3D モデル（`.step`） |
| `fabrication/` | 製造データ（ガーバー、ドリル、BOM、部品配置ファイル） |
| `tools/` | 計算・作図・外形の再生成用スクリプト（`led_budget.py` ほか） |

## 数値・部品名の出典

確認状態: ✅ 原本（データシート・公式図面）で確認 ／ 🟡 販売ページ・Wiki で確認 ／ 🔴 未確認・仮定。**確認できていないものは、`docs/spec.md` の各表に「未確認」と書いてある。**

| 対象 | 出典 | 確認 |
|---|---|---|
| NSSW157T（Nichia）: 外形 3.0×1.4×0.52、VF、IF max、推奨ランド | [Nichia STS-DA1-1913（秋月配布 PDF）](https://akizukidenshi.com/goodsaffix/nssw157t.pdf)、[秋月 116884](https://akizukidenshi.com/catalog/g/g116884/) | ✅ |
| VL53L1X（ST）: AVDD 2.6〜3.5 V、消費電流、XSHUT・I2C・既定アドレス、最短 4 cm | ST DS12385 Rev 8（[複製 PDF](https://www.makerguides.com/wp-content/uploads/2024/10/VL53L1X-Datasheet.pdf)。ST 公式サイトの版では未照合） | ✅（複製） |
| XIAO ESP32S3: ピン配置、GPIO 番号、3V3 出力、Sense が使う GPIO | [Seeed wiki](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/) | 🟡 |
| XIAO の穴パターン（ピッチ 2.54、行間隔 15.25、穴 φ1.02、外形 21×17.8） | [Seeed "XIAO Series Package and PCB Design" p.7](https://www.seeedstudio.com/blog/wp-content/uploads/2022/08/Seeed-Studio-XIAO-Series-Package-and-PCB-Design.pdf)（シリーズ共通図。S3 個別ではない） | ✅（共通図） |
| ESP32-S3 のストラッピング ピン（GPIO0/3/45/46）、GPIO 電流 | [ESP-IDF GPIO ドキュメント](https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32s3/api-reference/peripherals/gpio.html) ほか。電流は ESP32 系の公表値 | 🟡（S3 の電流値は未照合） |
| VL53L1X 小基板（Amazon B083Z316NC）: 12×17×3.2 mm、3.3〜5 V | [商品ページ](https://www.amazon.co.jp/dp/B083Z316NC)。**ピン配置・プルアップ・アドレスの記載なし** | 🔴 |
| 頭の外形 幅 100 / 高さ 74 / 長さ 78 mm、ToF・LED の位置 | `serpens/ai-shared/design-state.md`、`serpens/docs/design/tof_board_placement_2026-09-30.md`（Design の概念値 = CAD_CONCEPT / ASSUMED。基板の寸法制限ではない） | 🔴（概念値） |
| T6 / T4 の試験の内容 | `serpens/ai-shared/HARDWARE_TODO.md` HT-005 / HT-011、HG-H2 の `hardware_test_plan.md`・`tof_cliff.md`（Engineering の worktree `agent/engineering-h1-j1`、未マージ） | 🟡 |

## ライブラリの出典

**現時点で自作のシンボル・フットプリントは無い**（Stage 1）。Stage 2 で次を `libs/` に追加する予定（追加したらここに出典を書く）:

| 予定 | 理由 | 出典（予定） |
|---|---|---|
| XIAO ESP32S3 のシンボルとフットプリント | KiCad 標準ライブラリには表面実装用の `RF_Module:MCU_Seeed_ESP32C3` しか無く、2.54 mm の穴パターンが無い | 寸法は Seeed 公式図面（上表） |
| NSSW157T のフットプリント | 標準ライブラリに同寸法のものが無い | Nichia STS-DA1-1913 p.4–5（推奨ランド） |
| ToF 小基板用ヘッダのシンボル（ピン名つき） | ピン名（VIN, GND, SCL, SDA, XSHUT, GPIO1）を回路図に出すため | 自作 |

## BoardRepo について（**2026-10-01 時点: こちらからは取り込みを確認できない**）

- BoardRepo は「アップロードのたびに番号つきの版ができる」方式で、閲覧・MCP は **OAuth のサインインが要る**（[boardrepo.com](https://boardrepo.com)）。Agent 側からはサインインできない。
- 既存の `snake-main-board` の GitHub リポジトリにも、BoardRepo の Webhook・チェック・コミットステータスは**残っていない**（確認済み）。取り込みは、GitHub から自動ではなく、アップロード（`snake-main-board_upload.zip` と同じ形の束）で行っていたと読める（推測）。
- Stage 2 以降、`*_upload.zip`（`.gitignore` / README / `.kicad_pro` / `.kicad_sch` / `.kicad_pcb`）を作って User に渡す。**アップロードして表示できたかは User の確認が要る。**

## 注意

- `*-backups/`、`fp-info-cache`、`*.kicad_prl`、ロックファイル、自動保存、`*_upload.zip` は Git に入れない（`.gitignore`）。
- 空のフォルダを Git に残すため `libs/` `3dmodels/` `fabrication/` に `.gitkeep` を置いてある（中身が入ったら消してよい）。
- このフォルダは、親の `serpens`（ロボット制御のリポジトリ）とは**別の Git リポジトリ**（入れ子）。親側は `.git/info/exclude` で無視している。`snake-main-board` とも別。
