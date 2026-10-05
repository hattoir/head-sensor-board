# Current Handoff — head-sensor-board (KiCad Agent)

更新: 2026-10-05。次のセッションは、この 1 枚と `PROJECT_STATE.json` / `TASK_GRAPH.json` / `*.jsonl` から、過去の会話なしで再開できる。
ルール: **発注しない**（人の操作）。**測定値を作り話で埋めない**。`ai-shared/` と `ai-outbox/` は追記専用。他の Agent の worktree に触れない。

## Completed

- Stage 1〜4（仕様、回路図 ERC 0、外形 44×28 mm と配置、配線、DRC 0、3D ビュー）。
- 製造データ `gerbers/`（ガーバー 8 層 + ドリル + pos + BOM + ZIP）。2026-10-02 に出力、2026-10-05 にシルクを修正して再出力（commit 63e2481）。
- 2026-10-05 の閉ループ（EXP-K-0001）: 発注先 4 社の公開仕様（JLCPCB・PCBWay・Seeed Fusion・Elecrow）を取得 → **シルクの線幅 0.12 mm が JLCPCB 標準・PCBWay・Elecrow の最小 0.15 mm 未満**と判明 → 全シルク 0.15 mm に修正 → **銅・レジスト・ペースト・外形・ドリルは図形として同一、シルクだけが違う**ことを確認 → KEEP。
- 自動化: `tools/run_all_checks.py`（全検査）、`check_fab_rules.py` + `fab_rules.json`（発注先との照合）、`compare_gerbers.py`（図形比較。`--current` で gerbers/ が古くなっていないか）、`check_board.py`（J1/J2 のネット・パッド・刻印、刻印のすきま 0.15 mm）、`gen_bringup_tables.py`。
- 人の作業の手順書 `docs/bringup_plan.md`（HG-K-01〜09、期待値は設計の計算値）+ `docs/bringup_nets.md`。

## Current State（検証の梯子。`PROJECT_STATE.json`）

| 対象 | 状態 |
|---|---|
| 回路図・基板の幾何（DRC / ERC / ネットリスト / J1・J2 / 刻印） | SOFTWARE_VERIFIED |
| 配置図 PNG | HUMAN_INSPECTED（2026-10-02 の PNG。その後のシルクの微修正は User 未確認） |
| ガーバー | SOFTWARE_VERIFIED（別ライブラリで読み直し）。User 未確認、製造所のビューア未確認 |
| 発注先との適合 | SOFTWARE_VERIFIED（公開仕様との机上照合。**注文して確かめていない**）。JLCPCB の標準の文字高さ 1.0 mm だけ未達（高精度の文字オプションなら可） |
| 3D モデル | IMPLEMENTED（簡易な箱、高さは仮） |
| 実機 | **なし（HARDWARE_VERIFIED = 0）。未発注** |

## Evidence

`EVIDENCE.jsonl`（EV-K-0001〜0013）。主なもの: gerbonara による ZIP の読み直し（EV-K-0003）、シルク修正の前後の図形比較（EV-K-0009）、発注先の仕様（EV-K-0005/0006。URL と取得日つき）、`run_all_checks.py` の結果（EV-K-0011）。

## Experiments

- EXP-K-0001 シルクの線幅 → **KEEP**（commit 63e2481）。
- EXP-K-0002 基板の高さ 29 mm + 文字 1.0 mm（JLCPCB の標準のシルク）→ **NOT_RUN**（承認済みの 44×28 を変える。JLCPCB の高精度オプションが使えないときだけ）。

## Decisions

DEC-K-0001〜0005（`DECISIONS.jsonl`）。**DEC-K-0004 が OPEN（User）**: JLCPCB で発注するなら「高精度の文字」を選ぶ（費用は未確認）か、高さ 29 mm + 文字 1.0 mm を承認するか。ほかの 3 社は現状のままで通る。

## Failed Attempts / 自分の誤り

- 最初の J1/J2 の信号名はヘッダの樹脂部に食い込んでいた（DRC は樹脂部を知らない）→ `check_board.py` を作った。
- シルクの線幅 0.12 mm が発注先の最小に届いていなかった（発注先との照合を最後まで先送りしていた）→ 照合を自動化した。
- ガーバーを文字列で比べると、同じ図形でも「違う」と出る（KiCad が出力のたびに順序を変える）→ 図形比較にした。
- スクリプトに `\n` を含む文字列をシェルから流し込むと化ける問題が再発（ファイル編集ツールか `chr(10)` を使う）。

## Open Questions

1. DEC-K-0004（上）。 2. ToF 小基板のピン配置（README の対応表。現物が要る）。 3. M2 穴の位置（頭への取り付け未定）。 4. ソケットの高さ・カメラ/microSD の出っ張り（HG-K-08）。 5. BoardRepo の表示（User が zip を手動アップロード。未確認）。

## Human Gates

`docs/bringup_plan.md` の HG-K-01〜09（目的・必要な物・手順・測定項目・期待値・失敗時・証拠・合格基準・安全・所要時間）。要約は `serpens/ai-outbox/human-actions/HUMAN-ACTIONS-KICAD-2026-10-05.md`。**HG-K-01（発注の前の確認）が最初**。

## Next Best Tasks

1. （人）HG-K-01: 発注先を決め、プレビューでシルク・外形・穴を確認、発注。DEC-K-0004 を決める。
2. （Agent）発注先が JLCPCB で高精度オプションが使えないとき: EXP-K-0002 を実行（`gen_pcb.py` の文字の大きさと GLYPH 定数を 1.0 mm で測り直し、高さ 29 mm、再配線、`run_all_checks.py`）。
3. （人）基板・小基板・XIAO Sense が届いたら HG-K-02〜09。測定値を `docs/bringup_log_YYYYMMDD.csv` に返す → Agent が spec/README を更新し、必要なら Rev B。
4. 基板を直したら必ず: `tools/check_board.py` → `tools/make_fabrication.py` → `tools/run_all_checks.py`。
