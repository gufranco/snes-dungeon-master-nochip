# 不用 DSP-2 的 Dungeon Master

本專案建立一個 Dungeon Master 卡帶映像檔，以 65816 例程取代其中的 DSP-2 協處理器。這些例程逐位元組對照該晶片本身的微碼，以及零售版卡帶錄得的埠通訊。

[English](README.md) &nbsp;|&nbsp; [日本語](README.ja.md) &nbsp;|&nbsp; [简体中文](README.zh-Hans.md) &nbsp;|&nbsp; 繁體中文（香港）

[![CI](https://github.com/gufranco/snes-dungeon-master-nochip/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/snes-dungeon-master-nochip/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/gufranco/snes-dungeon-master-nochip)](https://github.com/gufranco/snes-dungeon-master-nochip/releases)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

來自 **4** 次各 30,000 幀運行的 **98,333,301** 個錄得埠位元組經例程重播，錯誤 **0** 個；**17,241,846** 個返回位元組由晶片微碼重現，錯誤 **0** 個；**6** 個指令中 6 個在選定輸入上與晶片一致；**924** 個測試；**100%** 語句及分支覆蓋率；只用標準函式庫

```python
import patch
import sites

image = bytearray(0x10000)
image[0x0100:0x0104] = sites.STA_PORT
image[0x0200:0x0204] = sites.STA_PORT
image[0x0300:0x0304] = sites.LDA_PORT
image[0x0400:0x0404] = sites.LDA_STATUS
image[0x0500:0x0503] = sites.MVN_TO_PORT

symbols = patch.resolve(
    patch.read_symbols(
        """
        00:ff00 b00_first
        00:ff10 b00_feed
        00:ff20 b00_drain
        04:ff00 b04_0080
        04:ff04 b04_0084
        04:ff08 b04_0088
        04:ff0c b04_008C
        20:8000 dsp_write
        20:8040 dsp_read
        """
    )
)

finished = patch.apply(image, symbols)
for site in sites.find(image):
    width = patch.WIDTHS[site.kind]
    before = image[site.offset : site.offset + width].hex(" ")
    after = finished[site.offset : site.offset + width].hex(" ")
    print(f"{site.kind:<6} ${site.bank:02X}:{site.address:04X}  {before}  ->  {after}")
print(patch.residue(image))
print(patch.residue(finished), len(finished) == len(image))
```

```
write  $00:8100  8f 00 80 3f  ->  22 00 ff 00
write  $00:8200  8f 00 80 3f  ->  22 00 80 20
read   $00:8300  af 00 80 3f  ->  22 40 80 20
status $00:8400  af 00 c0 3f  ->  a9 00 ea ea
feed   $00:8500  54 3f 7e  ->  20 10 ff
{'write': 2, 'read': 1, 'status': 1, 'feed': 1}
{} True
```

這個示例在一個 64 KB 的映像檔中放入卡帶的五個埠存取，再按照組譯器寫出的格式的符號表把它們重新導向。每個替換的長度與被替換的指令相同，因此映像檔中沒有任何內容移位。對 `$3F:8000` 的長儲存變成跳往 `dsp_write` 的 `jsl`，但第一個除外，它呼叫開機入口 `b00_first`。長載入變成跳往 `dsp_read` 的 `jsl`，狀態輪詢變成 `lda #$00` 加兩個 `nop`，而寫入埠的區塊搬移則變成跳往 bank `$00` 中 feed 樁程式的 `jsr`。`patch.residue` 計算仍然到達晶片的存取：之前五個，之後一個也沒有，而映像檔長度不變。

## 安裝

| 需求 | 版本 | 用途 |
|:--|:--|:--|
| Python | 3.12 或更新 | 所有模組及指令 |
| git | 任何版本 | 以子模組形式取得六個固定版本的模型 |
| Docker | 任何現行版本 | 組譯，以及所有驅動模擬器的指令 |
| 你擁有的 Dungeon Master 傾印檔 | 1,048,576 位元組，摘要見[傾印檔](#the-dump) | 建立卡帶 |
| 你擁有的 DSP-2 微碼 | `snes-dsp-python` 接受的映像檔 | 向晶片要求答案的指令 |

```bash
git clone --recurse-submodules https://github.com/gufranco/snes-dungeon-master-nochip.git
cd snes-dungeon-master-nochip
python3 doctor.py
```

不會從任何套件索引安裝東西。經「下載 zip」連結取得的原始碼封存檔不含子模組，無法運行。若複製時沒有使用 `--recurse-submodules`，請執行 `git submodule update --init --recursive`。

傾印檔放在 `roms/dungeon-master-usa.sfc`。微碼放在 `firmware/`，或放在 `UPD7725_FIRMWARE_DIR` 指定的目錄。Git 會忽略這兩個目錄，本專案也不會下載其中任何一個檔案。

診斷腳本會列印機器、Python、每個模型的版本、晶片微碼能否運行、找到的每個傾印檔的 SHA-256、三個錄得追蹤檔中有多少個位於 `build/`，以及每個模型在其名稱下的自身報告。拋出例外的檢查會報告為它拋出的內容。任何檢查失敗時，它以 1 退出。在全新的 checkout 上，最後一行是：

```
  4 of 75 checks did not pass
```

這四項是：缺少傾印檔、缺少微碼（本專案與 `snes-dsp-python` 各自報告一次），以及空的 `snes-mapper-python/cartridges` 目錄。提交錯誤報告時，請貼上完整輸出。

發佈遵循 [Semantic Versioning](https://semver.org/)，由 semantic-release 根據提交標題產生。每個發佈都有標籤，並列於[發佈頁面](https://github.com/gufranco/snes-dungeon-master-nochip/releases)。發佈不附帶任何映像檔：卡帶在你的機器上從你的傾印檔建立。

## 介面

每個指令都是一個檔案，從儲存庫根目錄以 `python3` 執行。退出碼 0 代表成功。退出碼 2 代表指令呼叫方式錯誤或沒有可處理的內容，列印出的那一行會說明是哪一種。

### 建立卡帶

| 指令 | 參數 | 退出碼 |
|:--|:--|:--|
| `cartridge.py <dump> <output>` | 零售版傾印檔，以及完成的卡帶的寫入位置 | 0 已寫入。1 仍有存取到達晶片，或某個標頭鏡像仍宣告協處理器，此時不寫入任何檔案。2 用法錯誤，或 `<dump>` 處沒有檔案。其他退出碼來自組譯器 |
| `build.py <patch.asm> <dump> <output-name>` | 一個組合語言檔案、傾印檔，以及結果的檔案名稱 | 0 已組譯。1 工具鏈映像未能建立。2 用法錯誤。其他退出碼來自 asar |
| `build.py --image` | 無 | `docker build` 的退出碼 |
| [`assembled.py`](assembled.py) | 無 | 0 `asm/dm-sym.sfc` 及其符號比所有 `asm/*.asm` 都新，或已重新建立。2 `roms/dungeon-master-usa.sfc` 沒有傾印檔 |
| `similarity.py <dump> <cartridge>` | 零售版傾印檔及一個完成的卡帶 | 0 每個改動的位元組都位於已宣告的區域。1 至少一個不是。2 用法錯誤，或 `asm/dm-sym.sfc` 缺失或比其原始檔舊 |

```bash
python3 cartridge.py roms/dungeon-master-usa.sfc "build/Dungeon Master (USA) (nochip).sfc"
```

[`cartridge.py`](cartridge.py) 把傾印檔複製到 `asm/<output-name>`，在固定版本、無網絡的 asar 1.81 容器中把 [`asm/nochip.asm`](asm/nochip.asm) 組譯到它上面，讀取 asar 在旁邊寫出的符號表，原地重新導向每個埠存取，並改寫標頭，使其不宣告任何協處理器。然後它計算剩下的東西：仍然前往晶片的存取，或仍然宣告協處理器的標頭鏡像。任何一項都會令它在寫入檔案前停止。一個已放入例程但未重新導向存取的映像檔同樣能開機和遊玩，因為模擬器讀取標頭並提供 DSP-2，所以只有這個計數能分辨兩者。

[`build.py`](build.py) 每次運行都重新建立 `snes-dungeon-master-nochip/asar:1.81` 映像，並拒絕把結果放到給它的傾印檔上。[`assembled.py`](assembled.py) 為讀取量度映像檔 `asm/dm-sym.sfc` 的指令保持該檔案為最新。

[`similarity.py`](similarity.py) 列出卡帶與傾印檔不相同的每個位元組，並把每一個歸入認領它的區域：例程、bank `$00` 樁程式、bank `$04` 樁程式、重新導向的位置，或改寫觸及的標頭欄位。它最多列印 8 個沒有區域認領的位元組，附上偏移、位址及兩邊的數值。

### 檢查傾印檔

| 指令 | 參數 | 退出碼 |
|:--|:--|:--|
| `tools/identify.py [file name...]` | 可選的檔案名稱，取自 [`artifacts.manifest.json`](artifacts.manifest.json)，預設為全部 | 0 至少一個傾印檔存在且正確，並且沒有錯誤的。1 某個傾印檔大小錯誤、內容錯誤或帶有另一項目的摘要，或沒有可用的傾印檔。2 清單中沒有該名稱的項目 |

```bash
python3 tools/identify.py
```

在全新的 checkout 上，它會列印：

```
  dungeon-master-usa.sfc: missing  [Dungeon Master, USA]
      roms/dungeon-master-usa.sfc is not there
      macOS and Linux: shasum -a 256 roms/dungeon-master-usa.sfc
      Linux, coreutils: sha256sum roms/dungeon-master-usa.sfc
      Windows PowerShell: Get-FileHash -Algorithm SHA256 roms\dungeon-master-usa.sfc
  dungeon-master-jp.sfc: no digest published  [Dungeon Master, Japan]
      no dump measured yet
  dungeon-master-eur.sfc: no digest published  [Dungeon Master, UK and Europe]
      no dump measured yet

  0 of 3 declared dumps present and correct
```

第二行會顯示你機器上的絕對路徑。計算任何摘要前，會先去掉 512 位元組的燒錄器標頭。不符合的檔案會列印其大小、CRC32 及 SHA-256、原因，以及在 macOS、Linux 和 Windows 上計算摘要的指令。

<a id="asking-the-part"></a>

### 詢問晶片

這些指令以 DSP-2 本身微碼的返回結果檢驗例程，微碼由 `snes-dsp-python` 執行。例程在 snes9x 內的主機處理器上運行，由一個以 [`asm/dsp2-replay.asm`](asm/dsp2-replay.asm) 建立的腳本卡帶驅動，所以除了 `verify_trace.py` 之外，這裏的每個指令都需要 Docker 和模擬器映像。

| 指令 | 參數 | 退出碼 |
|:--|:--|:--|
| `tools/verify_trace.py [limit] [trace...]` | 每個追蹤檔的位元組上限，以及追蹤檔，預設為 `build/trace-s1.bin` 至 `trace-s3.bin` | 0 晶片重現了每個返回的位元組，或找不到追蹤檔。1 未能重現。2 沒有微碼 |
| `tools/fuzz.py [seed] [count] [command...]` | 種子 1、20,000 個產生的交換，以及用來限制範圍的指令位元組，例如 `0x05` | 0 沒有錯誤。1 有位元組錯誤或有批次未完成。2 沒有微碼、沒有可用來校準的錄音，或沒有剩下可產生的指令 |
| `tools/replay.py <trace> [limit]` | 一個錄得的追蹤檔，以及記錄上限 | 0 沒有錯誤，或 `<trace>` 處沒有檔案。1 有位元組錯誤或有批次沒有運行。2 用法錯誤 |
| `tools/verify_merge.py [per-length]` | 每個長度 3 次合併，長度由 1 至 80，顏色取自 16 種 | 0 沒有錯誤。1 有位元組錯誤、寫下的規則不再與晶片一致，或沒有微碼 |
| `tools/verify_multiply.py [extra]` | 17 對邊界組合加 120 對帶種子的組合 | 0 沒有錯誤。1 有位元組錯誤、寫下的規則不再與晶片一致，或沒有微碼 |
| `tools/verify_commands.py [each]` | 每種形態 2 個：tile、由 1 至 80 每個長度的 mirror，以及卡帶發送的兩種 scale 形態 | 0 沒有錯誤。1 有位元組錯誤，或沒有微碼 |
| `tools/verify_cpu.py [seed] [count]` | 種子 0，400 個單指令案例 | 0 `mos65xx` 65816 與 snes9x 在每個案例的 A、X、Y 和 P 上一致。1 不一致，或卡帶未完成 |

`verify_trace.py` 把每個錄得的交換寫入晶片，並把讀回的內容與卡帶當時讀到的內容比較。`replay.py` 則把同一份錄音送經主機處理器上的例程，以能放進 4 MB 腳本卡帶的批次進行，每個批次列印一行。`fuzz.py` 先用錄音檢查每個指令：若某指令的模型答案與卡帶不符，或令下一個交換無法回答，該指令會被排除並列出名稱。`verify_cpu.py` 以運行例程的模擬器檢驗為例程計算成本的處理器模型。

<a id="measuring-cost-play-and-placement"></a>

### 量度成本、遊玩及放置

| 指令 | 參數 | 退出碼 |
|:--|:--|:--|
| `tools/cost.py [image] [symbols] [trace] [samples]` | `asm/dm-sym.sfc`、旁邊的 `.sym`、`build/trace-s1.bin`，每個指令 60 個交換 | 0 每個抽樣答案都相符。1 有一個不符。2 映像檔或其符號缺失，或符號較舊 |
| `tools/frame_cost.py [image] [trace ...]` | `asm/dm-sym.sfc` 及 `build/trace-s1.bin` 至 `trace-s3.bin` | 0 已計價。1 第 600 幀之後沒有完整的交換。2 映像檔、其符號或某個追蹤檔缺失 |
| `tools/pace.py <dump> <cartridge> [frames]` | 兩個卡帶，4,000 幀 | 0 比較已運行。1 模擬器失敗。2 用法錯誤，或缺少檔案 |
| `tools/boot.py [cartridge] [frames]` | `build/Dungeon Master (USA) (nochip).sfc`，8,000 幀 | 0 沒有宣告協處理器、沒有晶片請求、每幀都已輸出、畫面已亮起。1 任何一項失敗。2 沒有卡帶 |
| `tools/placement.py [dump] [frames] [seed]` | `roms/dungeon-master-usa.sfc`，19,000 幀，除非給出種子，否則走固定路線 | 0 遊戲從未觸及狀態區塊的工作 RAM。1 觸及了，或運行沒有留下地圖。2 沒有傾印檔 |
| `tools/tour.py [--frames N] [--seed S] [--steady] [--out PATH]` | 24,000 幀，種子 0，輸出到標準輸出 | 0 已寫入。2 用法錯誤 |

`cost.py` 在 `mos65xx` 65816 模型上運行每個指令，該模型計算每個匯流排週期。它從第 600 幀起餵入錄得的通訊，檢查每個答案，並按零售路徑當時的成本為同一個交換計價：每個長儲存 5 個週期，每個搬移的位元組 7 個週期。它為每個指令列印一行，包括呼叫次數、直接呼叫的週期、經區塊搬移分派器的週期、零售週期、比率，以及有多少答案正確。零售路徑等待時輪詢狀態暫存器所花的時間，兩邊都不計算。`frame_cost.py` 統計每個追蹤檔中由第 600 幀起的每個完整交換，分辨經工作 RAM 內四個區塊搬移常式到達的呼叫與直接來自卡帶呼叫點的呼叫；我方按 `cost.py` 對該指令及路徑的平均值計價，零售路徑則精確計價，並為每個指令列印一行，以及兩邊每幀的成本。

`pace.py` 在固定路線上驅動兩個卡帶，為每個完成的幀計算摘要，並報告轉換版畫得相同的幀數、畫得較遲的幀數、最大延遲及中位數，然後以 8 個點列出延遲曲線。`boot.py` 在四種情況之一出現時失敗：標頭仍宣告協處理器、有東西向晶片提出請求、運行提早停止，或畫面從未亮起。`placement.py` 從 [`asm/dsp2-state.asm`](asm/dsp2-state.asm) 讀出狀態區塊的位址範圍，並報告遊戲從未觸及的最長一段工作 RAM。`tour.py` 寫出這些指令所用的輸入腳本：帶種子的隨機漫步，或由上、上、上、左、上、上、上、右組成的固定路線。

模擬器映像只需從儲存庫根目錄建立一次：

```bash
docker build --tag snes-dungeon-master-nochip/emu:dev emu
```

### 執行所有關卡檢查

| 指令 | 參數 | 退出碼 |
|:--|:--|:--|
| `check.py [--quick]` | `--quick` 跳過所有需要已組譯映像檔的關卡檢查 | 0 所有關卡檢查通過。1 至少一項失敗，並列出其名稱及最後 6 行。2 用法錯誤 |
| [`doctor.py`](doctor.py) | 無 | 0 所有檢查通過。1 至少一項未通過 |

[`check.py`](check.py) 在量度映像檔缺失或過時時先組譯它，然後運行 lint、格式、型別、在覆蓋率下的測試、JSON 和 YAML 格式、工作流程及 shell 腳本，每項都使用管線固定的版本。有映像檔時，它還會運行 [`tools/cost.py`](tools/cost.py)、三個 `*.retail.test.py` 檢查，以及三個 `verify_*.py` 指令。它會運行每一項關卡檢查，而不是在第一個失敗時停止。

### 模組

| 呼叫 | 返回 |
|:--|:--|
| `sites.find(image, kinds=None)` | 每個埠存取，形式為 `Site(kind, offset, address, bank)`，按偏移排序。`kind` 為 `write`、`read`、`status`、`feed` 或 `drain` |
| `sites.census(found)` | 每種類別的計數 |
| `sites.verify(found, region="USA")` | 普查結果；若與 `EXPECTED[region]` 不同則為 `UnexpectedImage` |
| `sites.find_trampoline_calls(image, bank=0x04)` | bank `$04` 中每個跳往位於 `$0080`、`$0084`、`$0088` 和 `$008C` 的四個區塊搬移程式的 `jsr` |
| `sites.verify_trampoline_calls(calls)` | 每個搬移程式的計數；若與 `EXPECTED_TRAMPOLINE_CALLS` 不同則為 `UnexpectedImage` |
| `sites.address_of(offset)`, `sites.offset_of(bank, address)` | 檔案偏移對應的 LoROM bank 及位址，以及反向轉換 |
| `patch.read_symbols(text)` | 從 asar 符號檔得出的 `{name: (bank, address)}` |
| `patch.resolve(symbols)` | `REQUIRED` 列出的九個項目，或列出缺失項目的 `MissingSymbol` |
| `patch.apply(image, symbols, boot_write_offset=None)` | 已重新導向的映像檔，型別為 `bytes`，長度不變。除非給出偏移，否則第一個儲存就是開機寫入 |
| `patch.residue(image)` | 仍到達晶片的存取的 `{kind: count}`，沒有時為空 |
| `patch.regions(image)` | 重新導向改寫的每個偏移，包括位置及搬移程式呼叫 |
| `cartridge.finish(image, symbols_text)` | 已重新導向、標頭已改寫為不宣告協處理器的映像檔 |
| `cartridge.unfinished(image)` | 每項仍前往晶片的東西一行，完成時為空 |
| `stateblock.fields(text)` | 狀態區塊組合語言中每個位於 `$100` 以下的 `!S_` 欄位的 `{name: (offset, width)}` |
| `stateblock.overlaps(declared)` | 每對共用一個位元組的欄位，形式為 `(name, other, first shared offset)` |
| `dsptrace.records(path)` | 錄得追蹤檔中每個 28 位元組記錄，形式為 `Record`。不完整的結尾會引發 `TruncatedTrace` |
| `dsptrace.transactions(records)` | 按指令把記錄歸組成一個 `Transaction`，含 `command`、`name`、`lengths`、`parameters`、`output`、`source` 和 `complete` |
| `dsptrace.summarise(transactions)`, `dsptrace.report(summary)` | 按指令、發出位置及來源 bank 的計數，以及其列印形式 |
| `protocol.Shape()` | 只憑位元組追蹤一個指令還需要多少位元組及還欠多少位元組。`wrote(byte)`、`was_read()`、`expecting_input`、`produced`、`at_boundary` |
| `hardware.install()`, `hardware.load(package)` | 把 `mos65xx`、`snesdsp`、`mapper` 和 `romimage` 放到匯入路徑上，並在 `UPD7725_FIRMWARE_DIR` 中指定 `firmware/`。`load` 匯入其中一個 |
| `version.stamped(name, release=None)` | 發佈給映像檔的檔案名稱 |

`dsptrace` 和 `protocol` 只計算位元組，從不計算答案：每個數值都來自錄音或晶片。

```python
import hardware
import patch
import sites

print(sites.EXPECTED["USA"])
print({f"${mover:04X}": calls for mover, calls in sites.EXPECTED_TRAMPOLINE_CALLS.items()})
bank, address = sites.address_of(0x012345)
print(f"${bank:02X}:{address:04X}", hex(sites.offset_of(0x82, 0xA345)))

try:
    sites.verify([], "Japan")
except sites.UnexpectedImage as refusal:
    print(refusal)

try:
    patch.resolve({"dsp_write": (0x20, 0x8000)})
except patch.MissingSymbol as refusal:
    print(refusal)

try:
    hardware.root_of("snesgfx")
except hardware.UnknownPackage as refusal:
    print(refusal)
```

```
{'write': 51, 'read': 4, 'status': 5, 'feed': 16, 'drain': 2}
{'$0080': 2, '$0084': 5, '$0088': 4, '$008C': 1}
$02:A345 0x12345
no measured site counts for region Japan; measured regions are ['USA']
the assembled image declares no b00_first, b00_feed, b00_drain, b04_0080, b04_0084, b04_0088, b04_008C, dsp_read
snesgfx is not vendored here; this project carries mapper, mos65xx, romimage, snesdsp
```

零售版 USA 映像檔有 78 個埠存取，以及 12 個對四個區塊搬移程式的呼叫。計數不同的傾印檔會被拒絕，而不會被修補。

```python
import stateblock

declared = stateblock.fields(stateblock.SOURCE.read_text())
widest = max(declared.items(), key=lambda one: one[1][1])
print(len(declared), "fields, widest", widest)
print(stateblock.overlaps(declared))
print(stateblock.overlaps({"!S_A": (0x10, 2), "!S_B": (0x11, 1)}))
```

```
25 fields, widest ('!S_SCRATCH', (40, 200))
[]
[('!S_A', '!S_B', 17)]
```

狀態區塊中每個欄位都在其註解中註明寬度，而組譯器看不出同一個位元組有兩個名稱。[`asm/dsp2-state.asm`](asm/dsp2-state.asm) 中的 25 個欄位沒有共用任何位元組。最後一行顯示位於 `$10` 的兩位元組欄位與位於 `$11` 的欄位，在偏移 17 處被報告。

```python
import tempfile
from pathlib import Path

import dsptrace

exchange = [(0, 0x09), (0, 0x03), (0, 0x00), (0, 0x04), (0, 0x00)]
exchange += [(1, 0x0C), (1, 0x00), (1, 0x00), (1, 0x00)]

with tempfile.TemporaryDirectory() as folder:
    trace = Path(folder) / "trace.bin"
    trace.write_bytes(
        b"".join(
            dsptrace.RECORD.pack(700, 0x04A123, 0, 0, kind, byte, bytes(8), 0x7E, 0x30, bytes(4))
            for kind, byte in exchange
        )
    )
    found = list(dsptrace.transactions(dsptrace.records(trace)))

print(found)
print(found[0].parameters.hex(" "), found[0].output.hex(" "), found[0].complete)
print(dsptrace.report(dsptrace.summarise(found)))
```

```
[<multiply frame=700 pc=$04A123 in=4 out=4>]
03 00 04 00 0c 00 00 00 True
  transactions 1, incomplete 0
    $09 multiply              1
  issuing sites 1
    $04A123           1
  source banks, by command
  distinct source addresses 0
  distinct length tuples 0
```

九個記錄組成一次 multiply：指令位元組、寫入的四個運算元位元組，以及讀取的四個答案位元組。[`emu/`](emu/) 中的測試工具寫出追蹤檔，每個埠存取一個 28 位元組記錄。

```python
from tools import protocol, tour

shape = protocol.Shape()
for byte in (0x05, 0x02, 0x11, 0x22, 0x33, 0x44):
    shape.wrote(byte)
print(shape, shape.produced)

route = tour.steady(3400).splitlines()
print(len(route), route[-4:])
```

```
<Shape between commands, 2 owed> 2
162 ['3260 up', '3266', '3308 up', '3314']
```

長度為 2 的 merge 接收四個資料位元組，並欠兩個。路線中的一行是一個幀號，以及從該幀起按住的按鈕；沒有按鈕的一行會放開它們。最初 3,000 幀每 40 幀按一次 start，以通過標題畫面。

### 錯誤

| 錯誤 | 引發時機 |
|:--|:--|
| `sites.UnexpectedImage` | 存取或搬移程式的計數與已量度的 USA 映像檔不同，或該地區沒有量度數據 |
| `patch.MissingSymbol` | 符號表缺少 `patch.REQUIRED` 中的某個名稱 |
| `patch.UnknownSite` | 某個位置的類別不在改寫涵蓋範圍內 |
| `hardware.UnknownPackage` | 模型名稱不是四個 `hardware.PACKAGES` 之一 |
| `similarity.NoRegion` | 組合語言或符號表沒有宣告某個區域、某區域的結束早於開始，或兩個映像檔長度不同 |
| `dsptrace.TruncatedTrace` | 追蹤檔在某個記錄中途結束 |
| `dsptrace.UnknownLength` | 不接收長度的指令收到長度位元組 |
| `replay.ScriptTooLong` | 重播腳本超出腳本卡帶的剩餘空間 |
| `replay.EmulatorFailed` | 模擬器以非零退出，或在 5 秒內沒有寫出工作 RAM 傾印 |
| `cost.Ran` | 例程觸及成本測試工具沒有模擬的位址，或在 4,000,000 步內沒有返回 |

## 晶片做了甚麼

Dungeon Master 是唯一載有 DSP-2 的 SNES 卡帶。該晶片有六個指令：把 Atari ST 點陣圖轉換為主機的圖塊格式、設定透明色、以該透明色合併兩個點陣圖、鏡像、乘法，以及縮放。沒有它，遊戲就不會繪畫。

卡帶要求它轉換的是按玩家所在位置組合的地下城畫面，所以沒有一組固定答案可以預先計算並儲存。在零售版傾印檔中搜尋卡帶發送的確切位元組，可以找到 mirror 指令的全部輸入、merge 指令的 1.2%，以及 tile 指令的 0.3%。因此這六個指令以 65816 重新實作，並把卡帶自身的指令指向它們。

## 狀態

| 部分 | 狀態 |
|:--|:--|
| 傾印檔識別 | 拒絕並非已量度 USA 版本的傾印檔 |
| 以 65816 實作的六個指令 | 在處理器上回答每個錄得的位元組 |
| 完成的卡帶 | 以一個指令從傾印檔建立，並在沒有協處理器的情況下開機 |
| 速度 | 每幀 68,616 個週期，晶片路徑為 15,009，一幀共有 59,561 |

按卡帶發送各指令的頻率加權，例程每幀花費 68,616 個週期，而埠通訊的成本是 15,009。零售數字不包括遊戲輪詢狀態暫存器等待答案的時間，這裏沒有任何方法能量度，所以這個比率是上限。59,561 週期的一幀是處理器所擁有的時間。

在固定路線上驅動兩個卡帶 30,000 幀，即八分鐘的行走和轉身，有 29,941 幀畫得相同。轉換版到達標題畫面遲 56 幀，此後再沒有落後一幀。直接計時 139 次地下城重繪，兩個卡帶都在 26 幀內穩定下來，而轉換版沒有一次較慢。[OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) 載有這兩項量度，以及各自無法說明的地方。

<a id="the-dump"></a>

## 傾印檔

按 No-Intro 的命名。每個摘要都是針對不含燒錄器標頭的整個檔案。以 SHA-256 為準；其他摘要用於與以它們為鍵的數據庫交叉核對。

| 檔案 | 讀取位置 | 大小 |
|:--|:--|:--|
| Dungeon Master, USA | `roms/dungeon-master-usa.sfc` | 1,048,576 |

| 摘要 | 數值 |
|:--|:--|
| SHA-256 | `2dfc2e037679a62a960dab9682bca6d1b2737f603edd336c8b2fdf05db10cc07` |
| SHA-1 | `e65ae62ec9a1c48a3512db66f929c7b0055ae2c3` |
| MD5 | `3d1b171d7486438af2d9ec3d98b155cd` |
| CRC32 | `0DFD9CEB` |

日本版和歐洲版載有同一晶片。[`artifacts.manifest.json`](artifacts.manifest.json) 列出兩者但沒有摘要，在其中一個被量度之前，建立過程會拒絕它們。

## 底層模型

關於晶片行為的每項說法，都由同一系列的另一個成員作出，該成員以其本身名稱作為子模組固定在本儲存庫根目錄。

| 模型 | 在此的用途 | 驗證依據 |
|:--|:--|:--|
| [`mos65xx-python`](https://github.com/gufranco/mos65xx-python) | 在 [`tools/cost.py`](tools/cost.py) 中運行例程並計算其成本，以及 [`tools/verify_cpu.py`](tools/verify_cpu.py) | 65816 逐操作碼測試套件，5,120,000 個案例 |
| [`snes-dsp-python`](https://github.com/gufranco/snes-dsp-python) | 透過運行晶片本身的微碼得出每個預期答案 | 微碼本身 |
| [`snes-rom-image-python`](https://github.com/gufranco/snes-rom-image-python) | 摘要、燒錄器標頭及標頭改寫 | 一個由真實卡帶組成的資料庫 |
| [`snes-mapper-python`](https://github.com/gufranco/snes-mapper-python) | 由 [`hardware.py`](hardware.py) 放到匯入路徑上 | 該資料庫中的每種標頭組合 |
| [`snes-graphics-python`](https://github.com/gufranco/snes-graphics-python) | 已固定版本，這裏沒有模組匯入 | 主機的位元平面佈局 |
| [`snes-driver-python`](https://github.com/gufranco/snes-driver-python) | 已固定版本，這裏沒有模組匯入 | 卡帶程式碼在何處存取其協處理器 |

模型以「髒」狀態啟動：記憶體和暫存器存有可重現的打亂數值，而不是零，所以讀取從未寫入的東西會表現為錯誤答案。

## 儲存庫指南

| 路徑 | 內容 |
|:--|:--|
| [`asm/`](asm/) | 65816 例程、狀態區塊、樁程式、重播及自我測試卡帶，以及 asar 1.81 容器 |
| [`emu/`](emu/) | 每次模擬器運行都經過的 snes9x 測試工具，以固定在一個 snes9x commit 的容器形式提供 |
| [`snes9x/`](snes9x/) | 完成的映像檔所需的映射改動，以針對該 commit 的修補檔形式提供 |
| [`tools/`](tools/) | [詢問晶片](#asking-the-part)及[量度成本、遊玩及放置](#measuring-cost-play-and-placement)下的指令 |
| [`conformance/divergences.json`](conformance/divergences.json) | 以程式可讀取的形式列出每個未解決問題，並由測試與 [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) 保持一致 |
| `*.retail.test.py` | 需要傾印檔的檢查，不計入覆蓋率關卡檢查，沒有傾印檔時報告為已跳過 |

## 是否正確

正確性以三種方式檢查，每種都說明了其他方式無法說明的事。

在模擬器上錄得四次各 30,000 幀的運行，包括進出埠的每個位元組：三次帶種子的隨機漫步，以及固定路線。[`tools/replay.py`](tools/replay.py) 把這些數據流送經主機處理器上的例程，檢查 98,333,301 個位元組，共執行 8,722,303 次運行。沒有任何錯誤。

該錄音保存的是模擬器的回答，而模擬器以 C 計算晶片的結果。[`tools/verify_trace.py`](tools/verify_trace.py) 把整份錄音以晶片本身的微碼重播，重現了卡帶返回的全部 17,241,846 個位元組，沒有錯誤，所以模擬器與晶片在所有錄得的內容上一致。

錄音無法說明它不包含的輸入：每個錄得的 multiply 的第一個運算元都是零，而固定路線不含 mirror 和 scale。所以六個指令也透過 [`tools/verify_merge.py`](tools/verify_merge.py)、[`tools/verify_multiply.py`](tools/verify_multiply.py) 和 [`tools/verify_commands.py`](tools/verify_commands.py)，在選定的輸入上與晶片對照。例程中的兩個缺陷就是這樣找到的，而重播通訊兩個都找不到。

仍未解決的問題，以及能解決每一個的量度方法，載於 [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) 和 [`conformance/divergences.json`](conformance/divergences.json)。

## 參與開發

| 需要 | 位置 |
|:--|:--|
| 每項關卡檢查及其運行次序 | [CONTRIBUTING.md](CONTRIBUTING.md) |
| 給程式編寫代理的相同資料 | [AGENTS.md](AGENTS.md) |
| 本儲存庫與同系列其他成員共用的標準 | [FAMILY.md](FAMILY.md) |
| 錯誤報告 | [GitHub Issues](https://github.com/gufranco/snes-dungeon-master-nochip/issues) |
| 安全報告 | [SECURITY.md](SECURITY.md) |

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
uvx --python 3.12 mypy==1.14.1 .
python3 -m coverage erase
for module in *.test.py tools/*.test.py conformance/*.test.py; do python3 -m coverage run -a "$module"; done
python3 -m coverage report
```

每個模組旁邊都有一個 `<module>.test.py`，每個都可以獨立運行。覆蓋率是硬性關卡檢查，要求語句及分支達 100%，並在既沒有傾印檔也沒有微碼的機器上達成。`python3 check.py` 一次過運行所有關卡檢查。

切勿把卡帶或微碼映像附加到 issue，也切勿連結到可下載其中任何一個的地方。摘要可以識別檔案而不攜帶檔案。

## 參考資料

- snes9x，commit `2971061cf07fdc6fc7d18883edf4e648eb16a6d2` 的 `dsp2.cpp`，https://github.com/snes9xgit/snes9x ，每次運行和錄音所經過的模擬器。
- asar 1.81，https://github.com/RPGHacker/asar ，組譯器，固定於 [`asm/Dockerfile`](asm/Dockerfile)。
- neviksti 的 Star Ocean 免晶片轉換，是對超出位址空間的映像檔所用定址規則的來源。
- Zeldix 社群，本專案所依賴的大量 SNES romhacking 知識記載於此。
- FTL Games 和 Software Heaven 製作了遊戲及其移植版。

## 引用本專案

[CITATION.cff](CITATION.cff) 在每次發佈時，由為 [`version.py`](version.py) 加上版本標記的腳本更新。

## 授權

MIT。見 [LICENSE](LICENSE)。授權涵蓋工具、組合語言程式碼及本文件。它不授予遊戲的任何權利，這裏也不分發任何 ROM 數據。
