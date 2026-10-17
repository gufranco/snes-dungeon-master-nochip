# 不用 DSP-2 的 Dungeon Master

构建一个 Dungeon Master 卡带镜像，其中的 DSP-2 协处理器由 65816 例程取代，这些例程逐字节对照芯片自身的微码以及零售版卡带录制下来的端口通信。

[English](README.md) | [日本語](README.ja.md) | 简体中文 | [繁體中文（香港）](README.zh-HK.md)

[![CI](https://github.com/gufranco/snes-dungeon-master-nochip/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/snes-dungeon-master-nochip/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/gufranco/snes-dungeon-master-nochip)](https://github.com/gufranco/snes-dungeon-master-nochip/releases)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

来自 **4** 次各 30,000 帧运行的 **98,333,301** 个录制端口字节经例程重放，**0** 个错误；**17,241,846** 个返回字节由芯片的微码重现，**0** 个错误；**6** 条命令中的 6 条在选定输入上与芯片一致；**924** 个测试；**100%** 语句与分支覆盖率；仅使用标准库

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

该示例在一个 64 KB 镜像中放入卡带的五处端口访问，并按汇编器写出的格式的符号表将它们重定向。每处替换与被替换的指令等宽，因此镜像中没有任何内容移动。对 `$3F:8000` 的长存储变为对 `dsp_write` 的 `jsl`，但第一处除外，它调用启动入口 `b00_first`。长读取变为对 `dsp_read` 的 `jsl`，状态轮询变为 `lda #$00` 加两个 `nop`，而向端口的块传送变为对 bank `$00` 中 feed 桩的 `jsr`。`patch.residue` 统计仍然到达芯片的访问：之前五处，之后没有，且镜像长度不变。

## 安装

| 要求 | 版本 | 用途 |
|:--|:--|:--|
| Python | 3.12 或更新 | 所有模块和命令 |
| git | 任意 | 以子模块形式获取六个固定版本的模型 |
| Docker | 任意当前版本 | 汇编，以及所有驱动模拟器的命令 |
| 你拥有的 Dungeon Master 转储 | 1,048,576 字节，摘要见[转储](#the-dump) | 构建卡带 |
| 你拥有的 DSP-2 微码 | `snes-dsp-python` 接受的镜像 | 向芯片询问答案的命令 |

```bash
git clone --recurse-submodules https://github.com/gufranco/snes-dungeon-master-nochip.git
cd snes-dungeon-master-nochip
python3 doctor.py
```

不从任何软件包索引安装任何东西。通过下载 zip 链接得到的源码归档不含子模块，无法运行。若克隆时未使用 `--recurse-submodules`，请运行 `git submodule update --init --recursive`。

转储放在 `roms/dungeon-master-usa.sfc`。微码放在 `firmware/`，或放在 `UPD7725_FIRMWARE_DIR` 指定的目录。Git 忽略这两个目录，本项目不会下载其中任何一个文件。

诊断脚本会打印机器、Python、每个模型的版本、芯片的微码能否运行、它找到的每个转储的 SHA-256、三份录制跟踪中有多少位于 `build/`，以及每个模型自身的报告，列在该模型名下。抛出异常的检查会报告它抛出的内容。任一检查失败时以 1 退出。在全新的检出上，它以这一行结束：

```
  4 of 75 checks did not pass
```

这四项是：缺失的转储，本项目和 `snes-dsp-python` 各自报告的缺失微码，以及空的 `snes-mapper-python/cartridges` 目录。提交缺陷报告时请粘贴完整输出。

发布遵循[语义化版本](https://semver.org/)，由 semantic-release 根据提交标题生成。每个发布都会打标签，并列在[发布页面](https://github.com/gufranco/snes-dungeon-master-nochip/releases)上。发布不包含任何镜像：卡带在你的机器上由你的转储构建。

## 接口

每条命令都是一个文件，在仓库根目录用 `python3` 运行。退出码 0 表示成功。退出码 2 表示命令调用方式错误或没有可处理的内容，它打印的那一行会说明是哪种情况。

### 构建卡带

| 命令 | 参数 | 退出码 |
|:--|:--|:--|
| `cartridge.py <dump> <output>` | 零售版转储，以及成品卡带的写入位置 | 0 已写出。1 仍有访问到达芯片，或某个头部镜像仍声明协处理器，此时不写出任何文件。2 用法错误，或 `<dump>` 处没有文件。其他任何退出码来自汇编器 |
| `build.py <patch.asm> <dump> <output-name>` | 一个汇编文件、转储，以及结果的文件名 | 0 已汇编。1 工具链镜像未能构建。2 用法错误。其他任何退出码来自 asar |
| `build.py --image` | 无 | `docker build` 的退出码 |
| [`assembled.py`](assembled.py) | 无 | 0 `asm/dm-sym.sfc` 及其符号比所有 `asm/*.asm` 都新，或已重新构建。2 `roms/dungeon-master-usa.sfc` 处没有转储 |
| `similarity.py <dump> <cartridge>` | 零售版转储和一个成品卡带 | 0 每个改动的字节都位于已声明的区域内。1 至少有一个不在。2 用法错误，或 `asm/dm-sym.sfc` 缺失或比其源文件旧 |

```bash
python3 cartridge.py roms/dungeon-master-usa.sfc "build/Dungeon Master (USA) (nochip).sfc"
```

[`cartridge.py`](cartridge.py) 将转储复制到 `asm/<output-name>`，在固定版本、无网络的 asar 1.81 容器中把 [`asm/nochip.asm`](asm/nochip.asm) 汇编到其上，读取 asar 在旁边写出的符号表，就地重定向每处端口访问，并重写头部使其不声明任何协处理器。随后它统计剩余的问题：仍然通往芯片的访问，或仍然声明协处理器的头部镜像。任意一种都会让它在写出文件之前停止。一个放置了例程但未重定向访问的镜像也能启动并游玩，因为模拟器读取头部并提供一个 DSP-2，所以这项统计是区分两者的唯一手段。

[`build.py`](build.py) 每次运行都会重新构建 `snes-dungeon-master-nochip/asar:1.81` 镜像，并拒绝把结果放到它所接收的转储之上。[`assembled.py`](assembled.py) 为读取测量镜像 `asm/dm-sym.sfc` 的命令保持该镜像为最新。

[`similarity.py`](similarity.py) 列出卡带与转储不同的每个字节，并把每个字节归入认领它的区域：例程、bank `$00` 的桩、bank `$04` 的桩、被重定向的位置，或重写所触及的头部字段。它最多打印 8 个没有区域认领的字节，附带其偏移、地址和两边的值。

### 检查转储

| 命令 | 参数 | 退出码 |
|:--|:--|:--|
| `tools/identify.py [file name...]` | 可选的、来自 [`artifacts.manifest.json`](artifacts.manifest.json) 的文件名，默认全部 | 0 至少一个转储存在且正确，且没有错误的。1 某个转储大小错误、内容错误或带有另一条目的摘要，或没有可用的转储。2 清单中没有该名称的条目 |

```bash
python3 tools/identify.py
```

在全新的检出上，它打印：

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

第二行带有你机器上的绝对路径。在计算任何摘要之前，会先去掉 512 字节的拷贝机头部。不匹配的文件会打印其大小、CRC32 和 SHA-256、一条原因，以及在 macOS、Linux 和 Windows 上计算摘要的命令。

<a id="asking-the-part"></a>

### 询问芯片

这些命令让例程对照 DSP-2 自身微码返回的结果，微码由 `snes-dsp-python` 运行。例程在 snes9x 中的主机处理器上运行，由一个用 [`asm/dsp2-replay.asm`](asm/dsp2-replay.asm) 构建的脚本卡带驱动，因此这里除 `verify_trace.py` 外的每条命令都需要 Docker 和模拟器镜像。

| 命令 | 参数 | 退出码 |
|:--|:--|:--|
| `tools/verify_trace.py [limit] [trace...]` | 每份跟踪的字节上限，以及跟踪文件，默认 `build/trace-s1.bin` 到 `trace-s3.bin` | 0 芯片重现了每个返回字节，或未找到跟踪。1 未能重现。2 没有微码 |
| `tools/fuzz.py [seed] [count] [command...]` | 种子 1，20,000 次生成的交换，以及用于限定范围的命令字节，例如 `0x05` | 0 无错误。1 有字节错误或某批未完成。2 没有微码、没有用于校准的录制，或没有剩余可生成的命令 |
| `tools/replay.py <trace> [limit]` | 一份录制的跟踪，以及记录上限 | 0 无错误，或 `<trace>` 处没有文件。1 有字节错误或某批未运行。2 用法错误 |
| `tools/verify_merge.py [per-length]` | 每种长度 3 次合并，长度从 1 到 80，颜色取自 16 种 | 0 无错误。1 有字节错误、成文规则与芯片不再一致，或没有微码 |
| `tools/verify_multiply.py [extra]` | 17 组边界对加 120 组带种子的随机对 | 0 无错误。1 有字节错误、成文规则与芯片不再一致，或没有微码 |
| `tools/verify_commands.py [each]` | 每种形态 2 个：tile、从 1 到 80 每种长度的 mirror，以及卡带发送的两种 scale 形态 | 0 无错误。1 有字节错误，或没有微码 |
| `tools/verify_cpu.py [seed] [count]` | 种子 0，400 个单指令用例 | 0 `mos65xx` 65816 与 snes9x 在每个用例上的 A、X、Y 和 P 一致。1 不一致，或卡带未运行完毕 |

`verify_trace.py` 把每次录制的交换写入芯片，并将读回的内容与卡带读到的内容比较。`replay.py` 则把同一份录制送入在主机处理器上运行的例程，分成能放进 4 MB 脚本卡带的批次，每批打印一行。`fuzz.py` 先用一份录制检查每条命令：模型答案与卡带不一致、或导致下一次交换无法应答的命令会被排除并列出名称。`verify_cpu.py` 用运行例程的模拟器来检查为例程计算开销的处理器模型。

<a id="measuring-cost-play-and-placement"></a>

### 测量开销、游玩和放置

| 命令 | 参数 | 退出码 |
|:--|:--|:--|
| `tools/cost.py [image] [symbols] [trace] [samples]` | `asm/dm-sym.sfc`、其旁边的 `.sym`、`build/trace-s1.bin`，每条命令 60 次交换 | 0 每个采样答案都匹配。1 有一个不匹配。2 镜像或其符号缺失，或符号较旧 |
| `tools/frame_cost.py [image] [trace ...]` | `asm/dm-sym.sfc` 以及 `build/trace-s1.bin` 至 `trace-s3.bin` | 0 已计价。1 第 600 帧之后没有完整的交换。2 镜像、其符号或某个跟踪文件缺失 |
| `tools/pace.py <dump> <cartridge> [frames]` | 两个卡带，4,000 帧 | 0 比较已运行。1 模拟器失败。2 用法错误，或缺少文件 |
| `tools/boot.py [cartridge] [frames]` | `build/Dungeon Master (USA) (nochip).sfc`，8,000 帧 | 0 未声明协处理器、无芯片请求、每帧都已输出、屏幕点亮。1 其中任一项失败。2 没有卡带 |
| `tools/placement.py [dump] [frames] [seed]` | `roms/dungeon-master-usa.sfc`，19,000 帧，除非给出种子，否则走固定路线 | 0 游戏从未触及状态块的工作 RAM。1 触及了，或运行未留下映射。2 没有转储 |
| `tools/tour.py [--frames N] [--seed S] [--steady] [--out PATH]` | 24,000 帧，种子 0，输出到标准输出 | 0 已写出。2 用法错误 |

`cost.py` 在统计每个总线周期的 `mos65xx` 65816 模型上运行每条命令，从第 600 帧起向其输入录制的通信，检查每个答案，并按零售路径为同一次交换付出的代价计价：每次长存储 5 个周期，每个搬运的字节 7 个周期。它为每条命令打印一行，包括调用次数、直接调用的周期、经由块传送分派器的周期、零售周期、比值，以及正确答案的数量。零售路径等待时轮询状态寄存器所花的时间，双方都不计入。`frame_cost.py` 统计每个跟踪文件中从第 600 帧起的每次完整交换，区分经由工作 RAM 中四个块传送例程到达的调用与直接来自卡带调用点的调用；我方按 `cost.py` 对该命令和路径的平均值计价，零售路径则精确计价，并为每条命令打印一行，以及双方每帧的开销。

`pace.py` 在固定路线上驱动两个卡带，对每个完成的帧计算摘要，报告转换版绘制相同的帧数、绘制较晚的帧数、最大延迟和中位数，然后以 8 个点给出延迟曲线。`boot.py` 在以下四种情况中任一出现时失败：头部仍声明协处理器、向芯片发出了请求、运行提前停止，或屏幕从未点亮。`placement.py` 从 [`asm/dsp2-state.asm`](asm/dsp2-state.asm) 读取状态块的地址范围，并报告游戏从未触及的最长一段工作 RAM。`tour.py` 写出这些工具所用的输入脚本：带种子的随机行走，或由上、上、上、左、上、上、上、右构成的固定路线。

模拟器镜像只需构建一次，在仓库根目录执行：

```bash
docker build --tag snes-dungeon-master-nochip/emu:dev emu
```

### 运行所有门禁检查

| 命令 | 参数 | 退出码 |
|:--|:--|:--|
| `check.py [--quick]` | `--quick` 跳过所有需要已汇编镜像的门禁检查 | 0 所有门禁检查通过。1 至少一项失败，列出其名称和最后 6 行。2 用法错误 |
| [`doctor.py`](doctor.py) | 无 | 0 所有检查通过。1 至少一项未通过 |

[`check.py`](check.py) 在测量镜像缺失或过期时先汇编它，然后运行 lint、格式、类型、覆盖率下的测试、JSON 和 YAML 格式、工作流以及 shell 脚本，每项都使用流水线固定的版本。有镜像时，它还运行 [`tools/cost.py`](tools/cost.py)、三个 `*.retail.test.py` 检查，以及三个 `verify_*.py` 命令。它运行所有门禁检查，而不是在第一次失败时停止。

### 模块

| 调用 | 返回 |
|:--|:--|
| `sites.find(image, kinds=None)` | 每处端口访问，以 `Site(kind, offset, address, bank)` 表示，按偏移排序。`kind` 为 `write`、`read`、`status`、`feed` 或 `drain` |
| `sites.census(found)` | 每种类型的计数 |
| `sites.verify(found, region="USA")` | 普查结果；与 `EXPECTED[region]` 不同时为 `UnexpectedImage` |
| `sites.find_trampoline_calls(image, bank=0x04)` | bank `$04` 中每个调用位于 `$0080`、`$0084`、`$0088` 和 `$008C` 的四个块搬运器的 `jsr` |
| `sites.verify_trampoline_calls(calls)` | 每个搬运器的计数；与 `EXPECTED_TRAMPOLINE_CALLS` 不同时为 `UnexpectedImage` |
| `sites.address_of(offset)`, `sites.offset_of(bank, address)` | 文件偏移对应的 LoROM bank 和地址，以及反向换算 |
| `patch.read_symbols(text)` | 从 asar 符号文件得到的 `{name: (bank, address)}` |
| `patch.resolve(symbols)` | `REQUIRED` 列出的九个条目；缺失时为列出缺失项的 `MissingSymbol` |
| `patch.apply(image, symbols, boot_write_offset=None)` | 重定向后的镜像，类型为 `bytes`，长度相同。除非给出偏移，第一处存储即为启动写入 |
| `patch.residue(image)` | 仍到达芯片的访问的 `{kind: count}`，没有时为空 |
| `patch.regions(image)` | 重定向所改写的每个偏移，包括访问位置和搬运器调用 |
| `cartridge.finish(image, symbols_text)` | 已重定向且头部已重写为不声明协处理器的镜像 |
| `cartridge.unfinished(image)` | 每项仍通往芯片的内容一行，完成时为空 |
| `stateblock.fields(text)` | 状态块汇编中 `$100` 以下每个 `!S_` 字段的 `{name: (offset, width)}` |
| `stateblock.overlaps(declared)` | 每对共享字节的字段，以 `(name, other, first shared offset)` 表示 |
| `dsptrace.records(path)` | 录制跟踪中的每条 28 字节记录，以 `Record` 表示。末尾不完整时抛出 `TruncatedTrace` |
| `dsptrace.transactions(records)` | 按命令把记录分组为 `Transaction`，带有 `command`、`name`、`lengths`、`parameters`、`output`、`source` 和 `complete` |
| `dsptrace.summarise(transactions)`, `dsptrace.report(summary)` | 按命令、按发出位置和按源 bank 的计数，以及其打印形式 |
| `protocol.Shape()` | 仅凭字节跟踪一条命令还需要多少字节、还欠多少字节。`wrote(byte)`、`was_read()`、`expecting_input`、`produced`、`at_boundary` |
| `hardware.install()`, `hardware.load(package)` | 把 `mos65xx`、`snesdsp`、`mapper` 和 `romimage` 加入导入路径，并在 `UPD7725_FIRMWARE_DIR` 中指定 `firmware/`。`load` 导入其中一个 |
| `version.stamped(name, release=None)` | 发布时给镜像的文件名 |

`dsptrace` 和 `protocol` 只统计字节，从不计算答案：每个值都来自录制或芯片。

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

零售版 USA 镜像含有 78 处端口访问和 12 次对四个块搬运器的调用。计数不同的转储会被拒绝，而不是被打补丁。

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

状态块中的每个字段在其注释中写明宽度，而汇编器无法发现同一字节有两个名字。[`asm/dsp2-state.asm`](asm/dsp2-state.asm) 中的 25 个字段互不共享字节。最后一行显示：一个位于 `$10` 的双字节字段与一个位于 `$11` 的字段，在偏移 17 处被报告。

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

九条记录构成一次 multiply：命令字节、写入的四个操作数字节、读取的四个答案字节。[`emu/`](emu/) 中的测试框架写出跟踪，每次端口访问一条 28 字节记录。

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

长度为 2 的 merge 接收四个负载字节，欠两个字节。路线中的一行是一个帧号及从该帧起按住的按键，没有按键的行会松开它们。前 3,000 帧每 40 帧按一次 start，以通过标题画面。

### 错误

| 错误 | 抛出时机 |
|:--|:--|
| `sites.UnexpectedImage` | 访问或搬运器的计数与已测量的 USA 镜像不同，或该地区没有测量数据 |
| `patch.MissingSymbol` | 符号表缺少 `patch.REQUIRED` 中的某个名称 |
| `patch.UnknownSite` | 某个位置的类型不在重写覆盖范围内 |
| `hardware.UnknownPackage` | 模型名称不是四个 `hardware.PACKAGES` 之一 |
| `similarity.NoRegion` | 汇编或符号表未声明某个区域、某个区域的结束早于开始，或两个镜像长度不同 |
| `dsptrace.TruncatedTrace` | 跟踪在某条记录中间结束 |
| `dsptrace.UnknownLength` | 一个不接受长度的命令收到了长度字节 |
| `replay.ScriptTooLong` | 重放脚本超出脚本卡带剩余的空间 |
| `replay.EmulatorFailed` | 模拟器以非零值退出，或在 5 秒内未写出工作 RAM 转储 |
| `cost.Ran` | 例程触及开销测试框架未建模的地址，或在 4,000,000 步内未返回 |

## 芯片做了什么

Dungeon Master 是唯一带有 DSP-2 的 SNES 卡带。该芯片有六条命令：把 Atari ST 位图转换为主机的图块格式、设置透明色、以该透明色合并两幅位图、镜像、乘法和缩放。没有它，游戏无法绘制画面。

卡带要求它转换的是按玩家所在位置合成的地牢视图，因此不存在一组可以预先计算并存储的固定答案。在零售版转储中搜索卡带发送的确切字节，能找到 mirror 命令的全部输入、merge 命令的 1.2%，以及 tile 命令的 0.3%。因此这六条命令用 65816 重新实现，并让卡带自身的指令指向它们。

## 状态

| 部分 | 状态 |
|:--|:--|
| 转储识别 | 拒绝非已测量 USA 版本的转储 |
| 用 65816 实现的六条命令 | 在处理器上应答每个录制字节 |
| 成品卡带 | 一条命令即可从转储构建，且在无协处理器的情况下启动 |
| 速度 | 每帧 68,616 个周期，芯片路径为 15,009，一帧共 59,561 |

按卡带发送每条命令的频率加权，例程每帧花费 68,616 个周期，而端口通信的开销是 15,009。零售数字未计入游戏轮询状态寄存器等待答案的时间，这里没有任何手段能测量它，因此该比值是一个上界。59,561 周期的一帧是处理器拥有的全部时间。

沿固定路线驱动两个卡带运行 30,000 帧，即八分钟的行走和转向，有 29,941 帧绘制相同。转换版晚 56 帧到达标题画面，此后再未落后一帧。直接对 139 次地牢重绘计时，两个卡带都在 26 帧内稳定下来，转换版没有一次更慢。[OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) 记载了这两项测量以及各自无法说明的内容。

<a id="the-dump"></a>

## 转储

按 No-Intro 的命名方式命名。每个摘要都针对不含拷贝机头部的整个文件。以 SHA-256 为准；其余摘要用于与以它们为键的数据库交叉核对。

| 文件 | 读取路径 | 大小 |
|:--|:--|:--|
| Dungeon Master, USA | `roms/dungeon-master-usa.sfc` | 1,048,576 |

| 摘要 | 值 |
|:--|:--|
| SHA-256 | `2dfc2e037679a62a960dab9682bca6d1b2737f603edd336c8b2fdf05db10cc07` |
| SHA-1 | `e65ae62ec9a1c48a3512db66f929c7b0055ae2c3` |
| MD5 | `3d1b171d7486438af2d9ec3d98b155cd` |
| CRC32 | `0DFD9CEB` |

日版和欧版带有相同的芯片。[`artifacts.manifest.json`](artifacts.manifest.json) 列出了这两者但没有摘要，在测量出摘要之前，构建会拒绝它们。

## 底层的模型

关于芯片行为的每项论断都由本系列的另一个成员给出，它们以子模块形式按各自名称固定在本仓库根目录下。

| 模型 | 在此的用途 | 对照基准 |
|:--|:--|:--|
| [`mos65xx-python`](https://github.com/gufranco/mos65xx-python) | 在 [`tools/cost.py`](tools/cost.py) 中运行例程并计算开销，以及 [`tools/verify_cpu.py`](tools/verify_cpu.py) | 65816 逐操作码测试套件，5,120,000 个用例 |
| [`snes-dsp-python`](https://github.com/gufranco/snes-dsp-python) | 通过运行芯片自身的微码给出每个预期答案 | 微码本身 |
| [`snes-rom-image-python`](https://github.com/gufranco/snes-rom-image-python) | 摘要、拷贝机头部和头部重写 | 一个由真实卡带构成的库 |
| [`snes-mapper-python`](https://github.com/gufranco/snes-mapper-python) | 由 [`hardware.py`](hardware.py) 加入导入路径 | 该库中的每种头部组合 |
| [`snes-graphics-python`](https://github.com/gufranco/snes-graphics-python) | 已固定，这里没有模块导入它 | 主机的位平面布局 |
| [`snes-driver-python`](https://github.com/gufranco/snes-driver-python) | 已固定，这里没有模块导入它 | 卡带代码在何处访问其协处理器 |

这些模型以脏状态启动：内存和寄存器中是可重现的乱序值而不是零，因此读取从未写入过的内容会表现为错误答案。

## 仓库指南

| 路径 | 内容 |
|:--|:--|
| [`asm/`](asm/) | 65816 例程、状态块、桩、重放和自测卡带，以及 asar 1.81 容器 |
| [`emu/`](emu/) | 每次模拟器运行都要经过的 snes9x 测试框架，以固定到某个 snes9x 提交的容器形式提供 |
| [`snes9x/`](snes9x/) | 成品镜像所需的映射改动，以针对该提交的补丁形式提供 |
| [`tools/`](tools/) | [询问芯片](#asking-the-part)和[测量开销、游玩和放置](#measuring-cost-play-and-placement)下的命令 |
| [`conformance/divergences.json`](conformance/divergences.json) | 以程序可读形式记录的每个未决问题，由一个测试与 [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) 保持一致 |
| `*.retail.test.py` | 需要转储的检查，不纳入覆盖率门禁检查，没有转储时报告为已跳过 |

## 它正确吗

正确性从三个方面检查，每个方面都能说明其他方面说明不了的事情。

在模拟器上录制了四次各 30,000 帧的运行，包含进出端口的每个字节：三次带种子的随机行走和一次固定路线。[`tools/replay.py`](tools/replay.py) 把这些数据流送入在主机处理器上运行的例程，检查了 98,333,301 个字节，共执行 8,722,303 次。没有一个错误。

这份录制保存的是模拟器给出的答案，而模拟器用 C 计算芯片的结果。[`tools/verify_trace.py`](tools/verify_trace.py) 将一整份录制对照芯片自身的微码重放，重现了卡带返回的全部 17,241,846 个字节，没有一个错误，因此模拟器与芯片在所有录制内容上一致。

录制无法说明它未包含的输入：每次录制到的 multiply 第一个操作数都为零，而固定路线中没有 mirror 也没有 scale。因此这六条命令还通过 [`tools/verify_merge.py`](tools/verify_merge.py)、[`tools/verify_multiply.py`](tools/verify_multiply.py) 和 [`tools/verify_commands.py`](tools/verify_commands.py) 在选定输入上对照芯片。例程中的两个缺陷就是这样发现的，而重放通信无法发现其中任何一个。

仍未解决的问题，以及能解决每个问题的测量，记载于 [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) 和 [`conformance/divergences.json`](conformance/divergences.json)。

## 参与开发

| 需求 | 位置 |
|:--|:--|
| 所有门禁检查及其运行顺序 | [CONTRIBUTING.md](CONTRIBUTING.md) |
| 面向编码代理的同一份内容 | [AGENTS.md](AGENTS.md) |
| 本仓库与本系列其他仓库共享的标准 | [FAMILY.md](FAMILY.md) |
| 缺陷报告 | [GitHub Issues](https://github.com/gufranco/snes-dungeon-master-nochip/issues) |
| 安全报告 | [SECURITY.md](SECURITY.md) |

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
uvx --python 3.12 mypy==1.14.1 .
python3 -m coverage erase
for module in *.test.py tools/*.test.py conformance/*.test.py; do python3 -m coverage run -a "$module"; done
python3 -m coverage report
```

每个模块旁边都有一个 `<module>.test.py`，且每个都能单独运行。覆盖率是一道硬性门禁检查，要求 100% 的语句和分支，并且在既没有转储也没有微码的机器上达成。`python3 check.py` 一次运行所有门禁检查。

切勿在 issue 中附加卡带或微码镜像，也切勿链接到可以下载它们的地方。摘要能识别文件而不携带文件。

## 参考资料

- snes9x，提交 `2971061cf07fdc6fc7d18883edf4e648eb16a6d2` 中的 `dsp2.cpp`，https://github.com/snes9xgit/snes9x ，每次运行和录制都经过的模拟器。
- asar 1.81，https://github.com/RPGHacker/asar ，汇编器，固定在 [`asm/Dockerfile`](asm/Dockerfile) 中。
- neviksti 的 Star Ocean 无芯片转换，它是超出地址空间的镜像所用寻址规则的来源。
- Zeldix 社区，本项目所依赖的许多 SNES 改版知识都记录在那里。
- FTL Games 和 Software Heaven 制作了这款游戏及其移植版。

## 引用本项目

[CITATION.cff](CITATION.cff) 在每次发布时由为 [`version.py`](version.py) 加盖版本号的脚本更新。

## 许可证

MIT。见 [LICENSE](LICENSE)。该许可证涵盖工具、汇编代码和本文档。它不授予游戏的任何权利，本项目也不分发任何 ROM 数据。
