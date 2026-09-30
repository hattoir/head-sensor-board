# BOM（部品表）— head-sensor-board Rev A（Stage 2）

**回路図から `tools/make_outputs.py` が作る。手で直さない**（直すときは回路図 → 再生成）。生の書き出しは [bom.csv](bom.csv)。
DNP = 既定で実装しない（フットプリントだけ置く）。**購入先・品番・価格の列は、User が秋月などで調べて埋める**（ここでは仕様だけ）。
抵抗・コンデンサは汎用品（型番の指定なし）。**仕様（値・パッケージ・定格）を満たせばよい。** 許容差: R9/R10（電流検出 1 Ω）は ±1 %、ほかの抵抗は ±5 % 以内、R15/R16 は 0 Ω ジャンパー。コンデンサは C1 が X5R 以上・10 V 以上、C2/C3 が X7R・16 V 以上。

## 1. 基板に載せる部品（回路図から）

| 記号 | 数量 | 値 | パッケージ（フットプリント） | 型番・種類 | 定格 | DNP | 備考 | 購入先・品番・価格 |
|---|---|---|---|---|---|---|---|---|
| U1 | 1 | XIAO_ESP32S3_Sense | `head-sensor-board:XIAO_ESP32S3_THT_2x7_P2.54mm` | Seeed XIAO ESP32S3 Sense | 3V3 out 700 mA (Seeed wiki, condition not stated) |  | Akizuki 118079. Mount on 2x 1x7 sockets (or pin headers). USB-C side = up in the drawing | （User が調査） |
| J1, J2 | 2 | ToF_L (PLACEHOLDER) / ToF_R (PLACEHOLDER) | `Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical` | PinHeader 1x06 2.54 mm | 2.54 mm pitch |  | VL53L1X small module (Amazon B083Z316NC) on jumper wires. PIN ORDER IS A PLACEHOLDER - UNVERIFIED (module not in hand) | （User が調査） |
| J3, J4 | 2 | LED_L_EXT (1:+ 2:-) / LED_R_EXT (1:+ 2:-) | `Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical` | PinHeader 1x02 2.54 mm | current-limited node (after R1/R3) |  | External LED: pin 1 = + (LEDA, after the series resistor), pin 2 = - (LEDK). Do NOT short + to - | （User が調査） |
| SJ1, SJ2 | 2 | LED_L_SUPPLY / LED_R_SUPPLY | `Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm` | solder jumper (PCB pads) | - |  | Default: pads 1-2 bridged = 3V3 via R1/R2. For 5V: cut the 1-2 bridge, bridge 2-3 (via R3/R4) | （User が調査） |
| D1,D2 | 2 | NSSW157T | `head-sensor-board:LED_Nichia_NSSW157T` | NSSW157T（Nichia） | IF 150 mA max; VF 2.8-3.4 V @80 mA; 3.0x1.4x0.52 mm |  | Akizuki 116884. White chip LED, height 0.52 mm | （User が調査） |
| Q1,Q2 | 2 | AO3400A | `Package_TO_SOT_SMD:SOT-23` | AO3400A (alt. Si2302CDS)（Alpha & Omega (alt. Vishay)） | 30 V 5.7 A VGS(th) 0.65-1.45 V RDS(on)<48 mohm @2.5 V (alt. Si2302CDS 20 V 2.6 A 0.40-0.85 V <75 mohm) |  | SOT-23 pin 1=G 2=S 3=D. Gate driven by 3.3 V logic | （User が調査） |
| R1,R2 | 2 | 20 | `Resistor_SMD:R_0603_1608Metric` | chip resistor 20 ohm | 0.1 W (0603) |  | LED current limit @3V3 (20 ohm: 8.5/23.6/38.8 mA min/nom/max) | （User が調査） |
| R3,R4 | 2 | 33 | `Resistor_SMD:R_2010_5025Metric` | chip resistor 33 ohm | 0.5 W (2010) |  | LED current limit @5V (33 ohm 2010: 45/59/73 mA min/nom/max). Fitted, used only when SJ is set to 5V | （User が調査） |
| R5,R6 | 2 | 220 | `Resistor_SMD:R_0603_1608Metric` | chip resistor 220 ohm | 0.1 W (0603) |  | Gate series resistor (limits the gate charge peak to 15 mA) | （User が調査） |
| R7,R8 | 2 | 100k | `Resistor_SMD:R_0603_1608Metric` | chip resistor 100k ohm | 0.1 W (0603) |  | Gate pull-down: LED off during reset/boot (GPIO3 is a strapping pin) | （User が調査） |
| R9,R10 | 2 | 1 | `Resistor_SMD:R_0603_1608Metric` | chip resistor 1 ohm | 0.1 W (0603) 1 % |  | Current sense: TP ILED voltage = 1 mV per mA (1 %) | （User が調査） |
| R11, R12 | 2 | 10k | `Resistor_SMD:R_0603_1608Metric` | chip resistor 10k ohm | 0.1 W (0603) |  | XSHUT pull-up (ST DS12385 2.4: XSHUT must always be driven; 10k recommended) / XSHUT pull-up (ST DS12385 2.4) | （User が調査） |
| R13, R14 | 2 | 3.3k | `Resistor_SMD:R_0603_1608Metric` | chip resistor 3.3k ohm | 0.1 W (0603) | **DNP** | I2C pull-up. DNP: fit only if the module has none (ST Table 4: 3.6k for CL<=90 pF) / I2C pull-up. DNP: fit only if the module has none | （User が調査） |
| R15,R16 | 2 | 0 | `Resistor_SMD:R_0603_1608Metric` | chip resistor 0 ohm | 0 ohm jumper | **DNP** | GPIO1 link to XIAO D8/D9 (shares the Sense microSD SPI pins). Default: not fitted | （User が調査） |
| C1 | 1 | 10u | `Capacitor_SMD:C_0805_2012Metric` | ceramic capacitor 10uF | 10 V X5R 0805 |  | 3V3 bulk: LED PWM + ToF peaks (2 x 40 mA) | （User が調査） |
| C2, C3 | 2 | 100n | `Capacitor_SMD:C_0603_1608Metric` | ceramic capacitor 100nF | 16 V X7R 0603 |  | Bypass near ToF header J1 / Bypass near ToF header J2 | （User が調査） |

回路図に出るが部品ではないもの: **TP1〜TP8**（テストポイントのパッド φ1.5 mm、`TestPoint:TestPoint_Pad_D1.5mm`）、**H1, H2**（M2 取付穴 φ2.2、`MountingHole:MountingHole_2.2mm_M2`）、**SJ1, SJ2**（半田ジャンパーのパッド。部品なし）。

## 2. 基板の外の部品（組み立てに必要）

| 用途 | 数量 | 品名 | パッケージ・寸法 | 定格・メモ | DNP | 備考 |
|---|---|---|---|---|---|---|
| U1 用 | 2 | ピンソケット 1×7（メス） | 2.54 mm ピッチ、スルーホール | 高さ 8.5 mm と仮定（購入品で確認） | — | XIAO を載せる。ピンヘッダ（オス）に替えてもよい（同じパッド） |
| XIAO 側 | 2 | ピンヘッダ 1×7（オス） | 2.54 mm ピッチ | Seeed の 7 pin ヘッダ SKU 320020159 は全長 10.34 / 上 6.00 / 下 1.80 mm | — | XIAO に同梱かは**未確認**。無ければ購入 |
| J1, J2 用 | 12 | ジャンパー線（ToF 小基板との接続） | ToF 小基板のピンの種類による（メス–メス / メス–オス） | — | — | ToF のピン配置・コネクタは**未確認**。候補: 秋月 100288「ブレッドボード・ジャンパーワイヤ 14 種類×10 本」（`秋月_購入リスト_20260930.md` に記載。**xlsx の購入リストには無い**） |
| H1, H2 用 | 2 | M2 ねじ（+ スペーサ） | M2、取付穴 φ2.2 | — | — | 頭への取り付け方法が未定のため**未決**（任意） |

## 3. 仕様の根拠（主なもの）

- **NSSW157T**: Nichia STS-DA1-1913（秋月配布）— IF max 150 mA、VF 2.8〜3.4 V @80 mA、3.0×1.4×0.52 mm。
- **AO3400A**: Alpha & Omega Rev 3.1（2023-07）— 30 V / 5.7 A、VGS(th) 0.65〜1.45 V、RDS(on) < 48 mΩ @VGS=2.5 V、VGS 最大 ±12 V、SOT-23。**Si2302CDS**（Vishay S12-2336 Rev D）— 20 V / 2.6 A、VGS(th) 0.40〜0.85 V、RDS(on) < 75 mΩ @2.5 V、VGS 最大 ±8 V、SOT-23（1=G, 2=S, 3=D）。どちらも 3.3 V ロジックで駆動できる（ESP32-S3 の VOH 最小 2.64 V でも VGS(th) 最大の 1.8 倍以上）。
- **R3/R4（5V 用 33 Ω 2010）**: 最悪時 176 mW = 0.5 W の 35 %（`tools/led_budget.py`）。0603/0805 では足りない（1206 でも 70 % で 50 % 基準を超える）。
- **R1/R2（3V3 用 20 Ω 0603）**: 最悪時 30 mW = 0.1 W の 30 %。
- **C1（10 µF）**: 3V3 電源だめ。X5R の 10 µF は DC バイアスで容量が下がるので、10 V 以上を選ぶ。
