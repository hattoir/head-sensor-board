# 発注先の公開仕様との照合（`tools/check_fab_rules.py` が作る。手で直さない）

公開仕様の取得日 2026-10-05。**公開ページの値との机上の照合であって、注文して確かめたものではない。** 発注の前に、発注ページの最新の値と照合すること。値は mm。括弧 = 発注先の最小（推奨）。

| 項目 | 基板 | JLCPCB | PCBWay | Seeed Fusion | Elecrow |
|---|---|---|---|---|---|
| 配線の最小幅 | 0.250 | PASS (0.1) | PASS (0.1) | PASS (0.1016) | PASS (0.1524) |
| 配線の間隔 | 0.200 | PASS (0.1) | PASS (0.1) | PASS (0.1016) | WARN (0.1524) |
| ビアの穴径 | 0.300 | PASS (0.15) | PASS (0.15) | PASS (0.2) | PASS (0.3) |
| ビアの外径 | 0.600 | PASS (0.25) | - | - | - |
| 最小の穴径（ビア・スルーホール） | 0.300 | PASS (0.15) | PASS (0.15) | PASS (0.2) | PASS (0.3) |
| 部品のスルーホールのアニュラリング | 0.350 | PASS (0.2) | PASS (0.15) | - | - |
| シルクの線の太さ | 0.150 | PASS (0.15) | PASS (0.15) | PASS (0.1016) | PASS (0.15) |
| シルクの文字の高さ | 0.800 | FAIL* (1) | PASS (0.8) | PASS (0.5842) | PASS (0.8) |
| 基板上の刻印とランドのすきま | 0.197 | PASS (0.15) | - | - | - |
| ランドどうしのすきま（マスクのブリッジ） | 0.250 | PASS (0.1) | PASS (0.1) | PASS (0.1) | - |
| 銅と縁の距離 | 0.500 | PASS (0.2) | PASS (0.25) | PASS (0.3) | - |

- `FAIL*` = 上位オプション（JLCPCB の「高精度の文字」: 線幅 0.10 以上・高さ 0.8 以上）なら通る。`WARN` = 最小は満たすが推奨値に届かない。`-` = 仕様に記載なし。
- 基板の値の出し方: 配線・ビア・穴・シルクの太さと文字の高さは基板から直接。間隔と銅と縁はプロジェクトの規則（DRC が守る値）。ランドとのすきまは基板上の刻印について。ランドどうしのすきま 0.25 mm は半田ジャンパーの 3 パッドの間（わざとはんだでつなぐ）。
- 部品の標準の枠（ライブラリのシルク）には、ランドに触れるものがある（最小 −0.075 mm）。ガーバーは `--subtract-soldermask` で、ランドの上のシルクを除いてある。JLCPCB は 0.15 mm 以内の文字を消すので、その部分の枠は欠ける（機能には影響しない）。

## 板厚・外形

- JLCPCB: 板厚 1.6 mm PASS、外形の大きさ PASS
- PCBWay: 板厚 1.6 mm PASS、外形の大きさ PASS
- Seeed Fusion: 板厚 1.6 mm PASS、外形の大きさ PASS
- Elecrow: 板厚 1.6 mm PASS、外形の大きさ PASS

## 出典（2026-10-05 取得）

- JLCPCB: https://jlcpcb.com/capabilities/pcb-capabilities、https://jlcpcb.com/blog/character-design-specifications
  - 注: 標準の文字は線幅 0.15 / 高さ 1.0 以上。注文画面の「高精度の文字」を選ぶと 0.10 / 0.8 まで（追加費用の有無は未確認）。ランドから 0.15 mm 以内の文字は消される。PTH のアニュラリング 0.20 以上（推奨 0.25）がビアにも当たるかは資料からは不明
- PCBWay: https://www.pcbway.com/capabilities.html
  - 注: ソルダーマスクのブリッジ 4 mil（緑）
- Seeed Fusion: https://wiki.seeedstudio.com/ja/Service_for_Fusion_PCB/
  - 注: 1 oz の最小パターン幅/間隔 4/4 mil。ソルダーマスクダム: 緑 0.10、その他 0.13 mm 以上
- Elecrow: https://www.elecrow.com/pcb-manufacturing.html
  - 注: 最小 6 mil（推奨は 8 mil より大きく）。最小パッド間隔 8 mil。ドリル最小 0.3 mm。銅と縁の距離・マスクのブリッジは資料に記載なし
