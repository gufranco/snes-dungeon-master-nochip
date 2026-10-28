# DSP-2を使わないDungeon Master

DSP-2コプロセッサを65816ルーチンで置き換えたDungeon Masterのカートリッジイメージをビルドします。ルーチンは、このチップ自身のマイクロコードと、市販カートリッジで記録したポート通信に1バイト単位で一致することを確認しています。

[English](README.md) | 日本語 | [简体中文](README.zh-Hans.md) | [繁體中文（香港）](README.zh-HK.md)

[![CI](https://github.com/gufranco/snes-dungeon-master-nochip/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/snes-dungeon-master-nochip/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/gufranco/snes-dungeon-master-nochip)](https://github.com/gufranco/snes-dungeon-master-nochip/releases)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

スケールを含まない記録の返却バイト**17,241,846**をチップのマイクロコードで再現して誤り**0**、選んだ入力でチップと一致を確認したコマンド6個中**6**個、テスト**924**件、ステートメントとブランチのカバレッジ**100%**、標準ライブラリのみ

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

この例は、カートリッジのポートアクセスのうち5つを64KBのイメージに置き、アセンブラが書き出す形式のシンボルテーブルに従ってリダイレクトします。置き換えは元の命令と同じ幅なので、イメージ内の何も移動しません。`$3F:8000`へのロングストアは`dsp_write`への`jsl`になります。ただし最初の1つは、ブートエントリ`b00_first`を呼び出します。ロングロードは`dsp_read`への`jsl`に、ステータスのポーリングは`lda #$00`と2つの`nop`に、ポートへのブロック転送はバンク`$00`のフィードスタブへの`jsr`になります。`patch.residue`は、まだチップに届くアクセスを数えます。前は5つ、後は0で、イメージの長さは変わりません。

## インストール

| 要件 | バージョン | 用途 |
|:--|:--|:--|
| Python | 3.12以降 | すべてのモジュールとコマンド |
| git | 任意 | 固定した6つのモデルをサブモジュールとして取得する |
| Docker | 現行の任意のバージョン | アセンブルと、エミュレータを動かすすべてのコマンド |
| 自分で所有するDungeon Masterのダンプ | 1,048,576バイト、ダイジェストは[ダンプ](#the-dump)を参照 | カートリッジのビルド |
| 自分で所有するDSP-2マイクロコード | `snes-dsp-python`が受け付けるイメージ | チップに答えを求めるコマンド |

```bash
git clone --recurse-submodules https://github.com/gufranco/snes-dungeon-master-nochip.git
cd snes-dungeon-master-nochip
python3 doctor.py
```

パッケージインデックスからは何もインストールしません。ZIPダウンロードのリンクから得たソースアーカイブにはサブモジュールが含まれず、実行できません。`--recurse-submodules`なしで作ったクローンでは、`git submodule update --init --recursive`を実行してください。

ダンプは`external/roms/dungeon-master-usa.sfc`に置きます。マイクロコードは`external/firmware/`、または`UPD7725_FIRMWARE_DIR`で指定したディレクトリに置きます。Gitは両方のディレクトリを無視し、ここにあるものはどちらのファイルもダウンロードしません。

ドクターは、マシン、Python、各モデルのバージョン、チップのマイクロコードが動くかどうか、見つけた各ダンプのSHA-256、記録した3つのトレースのうち`build/`にあるものの数、そして各モデル自身のレポートをそのモデル名の下に表示します。例外を投げたチェックは、投げた内容として報告します。いずれかのチェックが失敗すると終了コード1で終わります。新しいチェックアウトでは、次の行で終わります。

```
  4 of 75 checks did not pass
```

4つとは、ダンプがないこと、マイクロコードがないことをこのプロジェクトと`snes-dsp-python`がそれぞれ報告するもの、そして空の`snes-mapper-python/cartridges`ディレクトリです。バグ報告には出力全体を貼り付けてください。

リリースは[Semantic Versioning](https://semver.org/)に従い、コミットの件名からsemantic-releaseが作成します。すべてのリリースはタグ付けされ、[リリースページ](https://github.com/gufranco/snes-dungeon-master-nochip/releases)に掲載されます。リリースはイメージを公開しません。カートリッジは、あなたのマシンであなたのダンプからビルドします。

## インターフェース

各コマンドは、リポジトリのルートから`python3`で実行するファイルです。終了コード0は成功です。終了コード2は、コマンドの呼び出し方が誤っていたか、処理する対象がなかったことを意味し、表示される行がどちらかを示します。

### カートリッジのビルド

| コマンド | 引数 | 終了コード |
|:--|:--|:--|
| `cartridge.py <dump> [<destination>]` | 市販版のダンプと書き出し先のフォルダー。デフォルトは`dist` | 0は書き出し完了。1はアクセスがまだチップに届くか、ヘッダのミラーがまだコプロセッサを宣言しており、何も書き出しません。2は使い方の誤り、または`<dump>`にファイルがない。それ以外のコードはアセンブラのものです |
| `build.py <patch.asm> <dump> <output-name>` | アセンブリファイル、ダンプ、結果のファイル名 | 0はアセンブル完了。1はツールチェーンのイメージがビルドできなかった。2は使い方の誤り。それ以外のコードはasarのもの |
| `build.py --image` | なし | `docker build`の終了コード |
| [`assembled.py`](assembled.py) | なし | 0は`asm/dm-sym.sfc`とそのシンボルがすべての`asm/*.asm`より新しいか、再ビルドが済んだ。2は`external/roms/dungeon-master-usa.sfc`にダンプがない |
| `similarity.py <dump> <cartridge>` | 市販版のダンプと完成したカートリッジ | 0は変更されたすべてのバイトが宣言された領域内にある。1は少なくとも1つがそうでない。2は使い方の誤り、または`asm/dm-sym.sfc`がないかソースより古い |

```bash
python3 cartridge.py external/roms/dungeon-master-usa.sfc
```

[`cartridge.py`](cartridge.py)は、ダンプを`asm/<output-name>`にコピーし、ネットワークなしの固定版asar 1.81コンテナで[`asm/nochip.asm`](asm/nochip.asm)をその上にアセンブルし、asarが隣に書き出すシンボルテーブルを読み、すべてのポートアクセスをその場でリダイレクトし、コプロセッサを宣言しないようにヘッダを書き換えます。その後、残っているものを数えます。まだチップに向かうアクセスか、まだコプロセッサを宣言しているヘッダのミラーです。どちらか一方でもあれば、ファイルを書き出す前に止まります。ルーチンを配置してアクセスをリダイレクトしていないイメージも起動してプレイできます。エミュレータがヘッダを読んでDSP-2を用意するためです。そのため、この2つを区別できるのはこのカウントだけです。

完成したカートリッジは、機器ごとに1回ずつ`<destination>/v<version>/`へ書き出します。`emulator`、`supereverdrive`、`sd2snes`、`fxpak`には、ダンプ名とバージョンを付けたイメージをそのまま置き、`gamedoctor`には、512バイトのGame Doctorヘッダーを前に付けた`.smc`を置きます。このヘッダーは、ucon64の表と同じように8 Mbitのイメージと32 KBのセーブメモリーをマップします。ヘッダーは[snes-rom-image-python](https://github.com/gufranco/snes-rom-image-python)の`copier`モジュールが書き出します。カートリッジが宣言するヘッダーはバッテリーバックアップのセーブメモリーを残し、チップセットは`0x02`です。そのため、宣言されたバッテリーがあるときだけセーブRAMを保存するエミュレーターもセーブを保存します。

[`build.py`](build.py)は、実行のたびに`snes-dungeon-master-nochip/asar:1.81`イメージを再ビルドし、渡されたダンプの上に結果を置くことを拒否します。[`assembled.py`](assembled.py)は、計測用イメージ`asm/dm-sym.sfc`を、それを読むコマンドのために最新に保ちます。

[`similarity.py`](similarity.py)は、カートリッジがダンプと共有しないすべてのバイトを列挙し、それぞれをそのバイトを含む領域に分類します。領域は、ルーチン、バンク`$00`のスタブ、バンク`$04`のスタブ、リダイレクトした箇所、書き換えが触れるヘッダフィールドです。どの領域にも属さないバイトを最大8個、オフセット、アドレス、両方の値とともに表示します。

### ダンプの確認

| コマンド | 引数 | 終了コード |
|:--|:--|:--|
| `tools/identify.py [file name...]` | [`artifacts.manifest.json`](artifacts.manifest.json)にある任意のファイル名。デフォルトはすべて | 0は少なくとも1つのダンプが存在して正しく、誤ったものがない。1はダンプのサイズや内容が誤っているか、別のエントリのダイジェストを持つか、使えるダンプがない。2はその名前のマニフェストエントリがない |

```bash
python3 tools/identify.py
```

新しいチェックアウトでは、次のように表示します。

```
  dungeon-master-usa.sfc: missing  [Dungeon Master, USA]
      external/roms/dungeon-master-usa.sfc is not there
      macOS and Linux: shasum -a 256 external/roms/dungeon-master-usa.sfc
      Linux, coreutils: sha256sum external/roms/dungeon-master-usa.sfc
      Windows PowerShell: Get-FileHash -Algorithm SHA256 external\roms\dungeon-master-usa.sfc
  dungeon-master-jp.sfc: no digest published  [Dungeon Master, Japan]
      no dump measured yet
  dungeon-master-eur.sfc: no digest published  [Dungeon Master, UK and Europe]
      no dump measured yet

  0 of 3 declared dumps present and correct
```

2行目には、あなたのマシン上の絶対パスが入ります。512バイトのコピー機ヘッダは、ダイジェストを取る前に取り除きます。一致しないファイルについては、サイズ、CRC32、SHA-256、理由、そしてmacOS、Linux、Windowsでダイジェストを計算するコマンドを表示します。

<a id="asking-the-part"></a>

### チップに問い合わせる

これらのコマンドは、`snes-dsp-python`で実行したDSP-2自身のマイクロコードが返す値とルーチンが一致することを確認します。ルーチンはsnes9x内のコンソールのプロセッサで動き、[`asm/dsp2-replay.asm`](asm/dsp2-replay.asm)からビルドしたスクリプトカートリッジで駆動します。そのため、`verify_trace.py`を除くここのすべてのコマンドには、Dockerとエミュレータのイメージが必要です。

| コマンド | 引数 | 終了コード |
|:--|:--|:--|
| `tools/verify_trace.py [limit] [trace...]` | トレースごとのバイト数の上限とトレース。デフォルトは`build/trace-s1.bin`から`trace-s3.bin` | 0はチップがすべての返却バイトを再現したか、トレースが見つからなかった。1は再現しなかった。2はマイクロコードがない |
| `tools/fuzz.py [seed] [count] [command...]` | シード1、生成するやり取り20,000件、絞り込み用の`0x05`などのコマンドバイト | 0は誤りなし。1はバイトの誤りか、未完了のバッチがある。2はマイクロコードがない、較正に使う記録がない、または生成するコマンドが残っていない |
| `tools/replay.py <trace> [limit]` | 記録したトレースと、レコード数の上限 | 0は誤りなし、または`<trace>`にファイルがない。1はバイトの誤りか、実行されなかったバッチがある。2は使い方の誤り |
| `tools/verify_merge.py [per-length]` | 長さごとに3回のマージ、1から80までのすべての長さ、16色から選んだ色 | 0は誤りなし。1はバイトの誤り、記述したルールがもうチップと一致しない、またはマイクロコードがない |
| `tools/verify_multiply.py [extra]` | 境界値の組17個と、シード付きの組120個 | 0は誤りなし。1はバイトの誤り、記述したルールがもうチップと一致しない、またはマイクロコードがない |
| `tools/verify_commands.py [each]` | 形ごとに2回。タイル、1から80までのすべての長さのミラー、カートリッジが送る2種類のスケールの形 | 0は誤りなし。1はバイトの誤り、またはマイクロコードがない |
| `tools/verify_cpu.py [seed] [count]` | シード0、単一命令のケース400件 | 0は`mos65xx`の65816とsnes9xがすべてのケースでA、X、Y、Pについて一致する。1は一致しないか、カートリッジが完了しなかった |

`verify_trace.py`は、記録したすべてのやり取りをチップに書き込み、読み戻した値をカートリッジが読んだ値と比較します。`replay.py`は、同じ記録を代わりにコンソールのプロセッサ上のルーチンに送ります。4MBのスクリプトカートリッジに収まるバッチに分け、バッチごとに1行表示します。`fuzz.py`は、まず各コマンドを記録と照合します。モデルの答えがカートリッジと食い違うコマンドや、次のやり取りに答えられなくするコマンドは除外し、名前を表示します。`verify_cpu.py`は、ルーチンのコストを見積もるプロセッサモデルを、ルーチンを実行するエミュレータと照合します。

<a id="measuring-cost-play-and-placement"></a>

### コスト、プレイ、配置の計測

| コマンド | 引数 | 終了コード |
|:--|:--|:--|
| `tools/cost.py [image] [symbols] [trace] [samples]` | `asm/dm-sym.sfc`、その隣の`.sym`、`build/trace-s1.bin`、コマンドごとに60件のやり取り | 0はサンプルしたすべての答えがチップ自身の答えと一致した。1は一致しないものがあった。2はイメージかそのシンボルがない、シンボルの方が古い、またはチップが実行するマイクロコードがない |
| `tools/frame_cost.py [image] [trace ...]` | `asm/dm-sym.sfc`と`build/trace-s1.bin`から`trace-s3.bin`まで | 0は計算した。1はフレーム600以降に完了したやり取りがない。2はイメージ、そのシンボル、またはトレースがない |
| `tools/pace.py <dump> <cartridge> [frames]` | 両方のカートリッジ、4,000フレーム | 0は比較を実行した。1はエミュレータが失敗した。2は使い方の誤り、またはファイルがない |
| `tools/boot.py [cartridge] [frames]` | `dist/v<version>/emulator/dungeon-master-usa-nochip-v<version>.sfc`、8,000フレーム | 0はコプロセッサの宣言なし、チップへの要求なし、すべてのフレームが出力され、画面が点灯した。1はそのいずれかが失敗した。2はカートリッジがない |
| `tools/placement.py [dump] [frames] [seed]` | `external/roms/dungeon-master-usa.sfc`、19,000フレーム、シードを指定しない限り定常ルート | 0はゲームがステートブロックのワークRAMに一度も触れなかった。1は触れたか、実行がマップを残さなかった。2はダンプがない |
| `tools/tour.py [--frames N] [--seed S] [--steady] [--out PATH]` | 24,000フレーム、シード0、標準出力に表示 | 0は書き出し完了。2は使い方の誤り |

`cost.py`は、すべてのバスサイクルを数える`mos65xx`の65816モデルで各コマンドを実行し、フレーム600以降の記録した通信を与え、同じ通信に対してチップ自身のマイクロコードが返す答えと各答えを照合し、同じやり取りに市販版の経路が払ったコストを見積もります。ロングストア1回につき5サイクル、転送1バイトにつき7サイクルです。コマンドごとに1行、呼び出し回数、直接呼び出しのサイクル数、ブロック転送ディスパッチャ経由のサイクル数、市販版のサイクル数、比率、正しかった答えの数を表示します。市販版の経路がステータスレジスタのポーリングで待った時間は、どちらの側にも数えません。`frame_cost.py`は、各トレースのフレーム600以降の完了したやり取りをすべて数え、ワークRAMにある4つのブロック転送ルーチンを経由した呼び出しと、カートリッジ上の呼び出し箇所から直接来た呼び出しを区別します。こちらの側はコマンドと経路ごとの`cost.py`の平均で、市販版の経路は正確に計算し、コマンドごとに1行と、両側の1フレームあたりのコストを表示します。

`pace.py`は、両方のカートリッジを定常ルートで動かし、完成した各フレームのダイジェストを取り、変換版が同じに描画したフレーム数、遅れて描画したフレーム数、最大の遅れと中央値、そして8点の遅れ曲線を報告します。`boot.py`は、4つのうちいずれかで失敗します。ヘッダがまだコプロセッサを宣言している、チップに何かが要求された、実行が早く止まった、画面が一度も点灯しなかった、の4つです。`placement.py`は、ステートブロックのアドレス範囲を[`asm/dsp2-state.asm`](asm/dsp2-state.asm)から読み、ゲームが一度も触れなかったワークRAMの最長の連続範囲を報告します。`tour.py`は、これらが駆動に使う入力スクリプトを書き出します。シード付きのランダムウォークか、上、上、上、左、上、上、上、右の定常ルートです。

エミュレータのイメージは、リポジトリのルートから一度だけビルドします。

```bash
docker build --tag snes-dungeon-master-nochip/emu:dev emu
```

`build/`の3つのトレースはこのイメージで記録します。ダンプのコピーを`build/dungeon-master-usa.sfc`に置きます。それぞれシード付きの30,000フレームの巡回で、約1.7 GBになります。

```bash
for seed in 1 2 3; do
  python3 tools/tour.py --frames 30000 --seed "$seed" --out "build/tour-s$seed.script"
  docker run --rm --network=none --env "DMTRACE=trace-s$seed.bin" \
    --env "DMSCRIPT=tour-s$seed.script" --volume "$PWD/build:/work" \
    snes-dungeon-master-nochip/emu:dev dungeon-master-usa.sfc 30000
done
```

### すべてのゲートの実行

| コマンド | 引数 | 終了コード |
|:--|:--|:--|
| `check.py [--quick]` | `--quick`はアセンブル済みイメージが必要なゲートをすべて飛ばす | 0はすべてのゲートが通った。1は少なくとも1つが失敗し、最後の6行とともに名前を表示する。2は使い方の誤り |
| [`doctor.py`](doctor.py) | なし | 0はすべてのチェックが通った。1は少なくとも1つが通らなかった |

[`check.py`](check.py)は、計測用イメージがないか古い場合はまずアセンブルし、その後、lint、フォーマット、型、カバレッジ計測下のテスト、JSONとYAMLのフォーマット、ワークフロー、シェルスクリプトを、それぞれパイプラインが固定したバージョンで実行します。イメージがあれば、[`tools/cost.py`](tools/cost.py)、3つの`*.retail.test.py`チェック、3つの`verify_*.py`コマンドも実行します。最初の失敗で止まらず、すべてのゲートを実行します。

### モジュール

| 呼び出し | 戻り値 |
|:--|:--|
| `sites.find(image, kinds=None)` | すべてのポートアクセスを`Site(kind, offset, address, bank)`として、オフセット順に返す。`kind`は`write`、`read`、`status`、`feed`、`drain`のいずれか |
| `sites.census(found)` | 種類ごとの数 |
| `sites.verify(found, region="USA")` | 全数調査の結果。`EXPECTED[region]`と異なる場合は`UnexpectedImage` |
| `sites.find_trampoline_calls(image, bank=0x04)` | バンク`$04`にある、`$0080`、`$0084`、`$0088`、`$008C`の4つのブロック転送ルーチンへのすべての`jsr` |
| `sites.verify_trampoline_calls(calls)` | 転送ルーチンごとの数。`EXPECTED_TRAMPOLINE_CALLS`と異なる場合は`UnexpectedImage` |
| `sites.address_of(offset)`, `sites.offset_of(bank, address)` | ファイルオフセットに対応するLoROMのバンクとアドレス、およびその逆 |
| `patch.read_symbols(text)` | asarのシンボルファイルから得た`{name: (bank, address)}` |
| `patch.resolve(symbols)` | `REQUIRED`が挙げる9つのエントリ。欠けている場合は、それらを列挙する`MissingSymbol` |
| `patch.apply(image, symbols, boot_write_offset=None)` | リダイレクトしたイメージを同じ長さの`bytes`で返す。オフセットを指定しない限り、最初のストアがブート時の書き込みになる |
| `patch.residue(image)` | まだチップに届くアクセスの`{kind: count}`。ない場合は空 |
| `patch.regions(image)` | リダイレクトが書き換えるすべてのオフセット。アクセス箇所と転送ルーチンの呼び出しを合わせたもの |
| `cartridge.finish(image, symbols_text)` | リダイレクトし、コプロセッサを宣言しないようにヘッダを書き換えたイメージ |
| `cartridge.unfinished(image)` | まだチップに向かうものを1行ずつ。完成していれば空 |
| `stateblock.fields(text)` | ステートブロックのアセンブリにある、`$100`未満のすべての`!S_`フィールドの`{name: (offset, width)}` |
| `stateblock.overlaps(declared)` | バイトを共有するフィールドのすべての組を`(name, other, first shared offset)`として返す |
| `dsptrace.records(path)` | 記録したトレースの28バイトのレコードをそれぞれ`Record`として返す。末尾が短いと`TruncatedTrace`を送出する |
| `dsptrace.transactions(records)` | レコードをコマンドごとに1つの`Transaction`にまとめたもの。`command`、`name`、`lengths`、`parameters`、`output`、`source`、`complete`を持つ |
| `dsptrace.summarise(transactions)`, `dsptrace.report(summary)` | コマンドごと、発行箇所ごと、転送元バンクごとの数と、その表示形式 |
| `protocol.Shape()` | コマンドがあと何バイトを必要とし、何バイトを返す義務があるかを、バイト列だけから追跡する。`wrote(byte)`、`was_read()`、`expecting_input`、`produced`、`at_boundary` |
| `hardware.install()`, `hardware.load(package)` | `mos65xx`、`snesdsp`、`mapper`、`romimage`をインポートパスに置き、`UPD7725_FIRMWARE_DIR`に`external/firmware/`を設定する。`load`はそのうち1つをインポートする |
| `version.stamped(name, release=None)` | リリースがイメージに付けるファイル名 |

`dsptrace`と`protocol`はバイトを数えるだけで、答えを計算することはありません。すべての値は記録かチップから得ます。

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

市販のUSAイメージには、78個のポートアクセスと、4つのブロック転送ルーチンへの12個の呼び出しがあります。数が異なるダンプは、パッチを当てずに拒否します。

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

ステートブロックの各フィールドは、コメントで自分の幅を示しています。アセンブラは、1つのバイトに2つの名前があることを検出できません。[`asm/dsp2-state.asm`](asm/dsp2-state.asm)の25個のフィールドは、どれもバイトを共有していません。最後の行は、`$10`にある2バイトのフィールドと`$11`にあるフィールドが、オフセット17で報告される様子を示しています。

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

9つのレコードで1回の乗算になります。コマンドバイト、書き込む4つのオペランドバイト、読み出す4つの答えのバイトです。トレースは[`emu/`](emu/)のハーネスが書き出し、ポートアクセス1回につき28バイトのレコード1つです。

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

長さ2のマージは4バイトのペイロードを受け取り、2バイトを返す義務を負います。ルートの1行は、フレーム番号とそのフレームから押し続けるボタンで、ボタンのない行はボタンを離します。最初の3,000フレームでは、タイトルを抜けるために40フレームごとにスタートを押します。

### エラー

| エラー | 送出される条件 |
|:--|:--|
| `sites.UnexpectedImage` | アクセスまたは転送ルーチンの数が計測したUSAイメージと異なる、またはその地域に計測結果がない |
| `patch.MissingSymbol` | シンボルテーブルに`patch.REQUIRED`の名前が欠けている |
| `patch.UnknownSite` | 書き換えが扱わない種類のアクセス箇所がある |
| `hardware.UnknownPackage` | モデル名が4つの`hardware.PACKAGES`のいずれでもない |
| `similarity.NoRegion` | アセンブリまたはシンボルテーブルが領域を宣言していない、領域が始まる前に終わっている、または2つのイメージの長さが異なる |
| `dsptrace.TruncatedTrace` | トレースがレコードの途中で終わっている |
| `dsptrace.UnknownLength` | 長さを取らないコマンドに長さのバイトが届いた |
| `replay.ScriptTooLong` | 再生スクリプトがスクリプトカートリッジの残り容量を超える |
| `replay.EmulatorFailed` | エミュレータが0以外で終了するか、5秒以内にワークRAMのダンプを書き出さない |
| `cost.Ran` | ルーチンがコストハーネスのモデル化していないアドレスに触れる、または4,000,000ステップ以内に戻らない |

## チップがしていたこと

Dungeon Masterは、DSP-2を搭載した唯一のSNESカートリッジです。このチップには6つのコマンドがあります。Atari STのビットマップをコンソールのタイル形式に変換する、透明色を設定する、その色に対して2つのビットマップをマージする、ミラー、乗算、スケールです。チップがないと、ゲームは描画しません。

カートリッジが変換を求めるのは、プレイヤーの立ち位置に合わせて合成したダンジョンの視界です。そのため、前もって計算して保存しておける決まった答えの集合はありません。カートリッジが送る正確なバイト列を市販版のダンプから探すと、ミラーコマンドの入力はすべて、マージコマンドの入力は1.2%、タイルコマンドの入力は0.3%が見つかります。そこで6つのコマンドを65816で再実装し、カートリッジ自身の命令をそれらに向けています。

## 状況

| 部分 | 状態 |
|:--|:--|
| ダンプの識別 | 計測したUSA版でないダンプを拒否する |
| 65816による6つのコマンド | プロセッサ上で、記録したすべてのバイトに答える |
| 完成したカートリッジ | ダンプから1つのコマンドでビルドでき、コプロセッサなしで起動する |
| 速度 | 1フレームあたり68,616サイクル。チップ経由の経路は15,009サイクルで、1フレームは59,561サイクル |

カートリッジが各コマンドを送る頻度で重み付けすると、ポート通信が15,009サイクルかかっていたところで、ルーチンは1フレームあたり68,616サイクルを使います。市販版の数値には、ゲームが答えを待ってステータスレジスタをポーリングしていた時間が含まれていません。これはここでは計測できないため、この比率は上限です。59,561サイクルのフレームは、プロセッサが使える時間です。

両方のカートリッジを定常ルートで30,000フレーム、つまり歩いて向きを変える8分間動かすと、29,941フレームが同じに描画されます。変換版は56フレーム遅れてタイトル画面に到達し、その後は1フレームも遅れません。ダンジョンの再描画139回を直接計測すると、両方のカートリッジとも26フレームで落ち着き、変換版が遅かった回はありませんでした。[OPEN-QUESTIONS.md](OPEN-QUESTIONS.md)には、両方の計測と、それぞれが示せないことを記載しています。

<a id="the-dump"></a>

## ダンプ

名前はNo-Introの命名に従います。すべてのダイジェストは、コピー機ヘッダを除いたファイル全体に対するものです。判定にはSHA-256を使い、その他は、それらをキーにするデータベースとの照合に使います。

| ファイル | 読み込み先 | サイズ |
|:--|:--|:--|
| Dungeon Master, USA | `external/roms/dungeon-master-usa.sfc` | 1,048,576 |

| ダイジェスト | 値 |
|:--|:--|
| SHA-256 | `2dfc2e037679a62a960dab9682bca6d1b2737f603edd336c8b2fdf05db10cc07` |
| SHA-1 | `e65ae62ec9a1c48a3512db66f929c7b0055ae2c3` |
| MD5 | `3d1b171d7486438af2d9ec3d98b155cd` |
| CRC32 | `0DFD9CEB` |

日本版とヨーロッパ版も同じチップを搭載しています。[`artifacts.manifest.json`](artifacts.manifest.json)は両方をダイジェストなしで記載しており、ビルドは計測されるまでそれらを拒否します。

## 土台となるモデル

チップの動作に関する主張はすべて、ファミリーの別のメンバーが行います。各メンバーは、このリポジトリのルートに自身の名前でサブモジュールとして固定しています。

| モデル | ここでの用途 | 照合先 |
|:--|:--|:--|
| [`mos65xx-python`](https://github.com/gufranco/mos65xx-python) | [`tools/cost.py`](tools/cost.py)でのルーチンの実行とコスト見積もり、および[`tools/verify_cpu.py`](tools/verify_cpu.py) | 65816のオペコード別テストスイート、5,120,000ケース |
| [`snes-dsp-python`](https://github.com/gufranco/snes-dsp-python) | チップ自身のマイクロコードを実行して得る、すべての期待される答え | マイクロコードそのもの |
| [`snes-rom-image-python`](https://github.com/gufranco/snes-rom-image-python) | ダイジェスト、コピー機ヘッダ、ヘッダの書き換え | 実在するカートリッジのライブラリ |
| [`snes-mapper-python`](https://github.com/gufranco/snes-mapper-python) | [`hardware.py`](hardware.py)がインポートパスに置く | そのライブラリにあるすべてのヘッダの組み合わせ |
| [`snes-graphics-python`](https://github.com/gufranco/snes-graphics-python) | 固定しているが、ここのどのモジュールもインポートしない | コンソールのビットプレーン配置 |
| [`snes-driver-python`](https://github.com/gufranco/snes-driver-python) | 固定しているが、ここのどのモジュールもインポートしない | カートリッジのコードがコプロセッサにアクセスする箇所 |

モデルは汚れた状態で始まります。メモリとレジスタは0ではなく再現可能なランダムな値を持つため、一度も書き込んでいないものを読むと、誤った答えとして現れます。

## リポジトリガイド

| パス | 内容 |
|:--|:--|
| [`asm/`](asm/) | 65816ルーチン、ステートブロック、スタブ、再生用とセルフテスト用のカートリッジ、asar 1.81のコンテナ |
| [`emu/`](emu/) | すべてのエミュレータ実行が通るsnes9xのハーネス。1つのsnes9xコミットに固定したコンテナ |
| [`snes9x/`](snes9x/) | 完成したイメージに必要なマッピングの変更。そのコミットに対するパッチ |
| [`tools/`](tools/) | [チップに問い合わせる](#asking-the-part)と[コスト、プレイ、配置の計測](#measuring-cost-play-and-placement)にあるコマンド |
| [`conformance/divergences.json`](conformance/divergences.json) | すべての未解決の問題をプログラムが読める形にしたもの。テストで[OPEN-QUESTIONS.md](OPEN-QUESTIONS.md)と一致させている |
| `*.retail.test.py` | ダンプを必要とするチェック。カバレッジのゲートからは除外し、ダンプがなければスキップとして報告する |

## 正しいか

正しさは3つの方法で確認しており、それぞれが他の方法では示せないことを示します。

30,000フレームの実行4回を、ポートに出入りするすべてのバイトとともにエミュレータで記録しました。シード付きのランダムウォーク3回と、定常ルートです。[`tools/replay.py`](tools/replay.py)は、これらのストリームをコンソールのプロセッサ上のルーチンに通し、8,722,303回の実行をたどって98,333,301バイトを確認し、スケールのルーチンをチップに合わせて修正する前は誤りがありませんでした。ウォークには各スケールに対してsnes9xが答えた値が記録されており、チップはその値を返しません。そのため現在は、最初のウォークの先頭2,014,446バイトで598バイトが誤りになります。

この記録に含まれるのはエミュレータが答えた値で、エミュレータはチップの結果をCで計算しています。[`tools/verify_trace.py`](tools/verify_trace.py)は、記録をチップ自身のマイクロコードに対して再生します。スケールを含まない`build/trace-t1.bin`では、カートリッジが受け取った17,241,846バイトをすべて誤りなく再現します。3回のウォークでは、10,422回、1,068回、17,777回のスケールに対して10,416件、1,050件、17,302件のやり取りが一致しません。snes9xはスケールの刻みを`(out << 1) + 1`で割り、マイクロコードは`(out << 1) + 2`で割るからです。最初のウォークの先頭12,000,000バイトをコマンド別に数えると、不一致はすべてスケールです。したがって、エミュレータとチップは、記録されたコマンドのうちスケール以外のすべてで一致しています。

記録は、含まれていない入力については何も示しません。記録されたすべての乗算は第1オペランドが0で、定常ルートにはミラーもスケールもありません。そこで6つのコマンドすべてを、[`tools/verify_merge.py`](tools/verify_merge.py)、[`tools/verify_multiply.py`](tools/verify_multiply.py)、[`tools/verify_commands.py`](tools/verify_commands.py)を使い、選んだ入力でもチップと照合しています。この方法でルーチンの欠陥が2つ見つかりました。通信の再生では、どちらも見つけられませんでした。

未解決の点と、それぞれを決着させる計測は、[OPEN-QUESTIONS.md](OPEN-QUESTIONS.md)と[`conformance/divergences.json`](conformance/divergences.json)にあります。

## 開発に参加する

| 必要なもの | 場所 |
|:--|:--|
| すべてのゲートと実行順序 | [CONTRIBUTING.md](CONTRIBUTING.md) |
| コーディングエージェント向けの同じ内容 | [AGENTS.md](AGENTS.md) |
| このリポジトリがファミリーの他のリポジトリと共有する基準 | [FAMILY.md](FAMILY.md) |
| バグ報告 | [GitHub Issues](https://github.com/gufranco/snes-dungeon-master-nochip/issues) |
| セキュリティ報告 | [SECURITY.md](SECURITY.md) |

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
uvx --python 3.12 mypy==1.14.1 .
python3 -m coverage erase
for module in *.test.py tools/*.test.py conformance/*.test.py; do python3 -m coverage run -a "$module"; done
python3 -m coverage report
```

各モジュールの隣には`<module>.test.py`があり、それぞれ単独で実行できます。カバレッジはステートメントとブランチの100%を必須とするゲートで、ダンプもマイクロコードも持たないマシンで満たしています。`python3 check.py`は、すべてのゲートを1回で実行します。

イシューにカートリッジやマイクロコードのイメージを添付しないでください。また、どちらかをダウンロードできる場所へのリンクも貼らないでください。ダイジェストは、ファイルそのものを含めずにファイルを識別します。

## 参考資料

- snes9x、コミット`2971061cf07fdc6fc7d18883edf4e648eb16a6d2`の`dsp2.cpp`、https://github.com/snes9xgit/snes9x 。すべての実行と記録が通るエミュレータです。
- asar 1.81、https://github.com/RPGHacker/asar 。アセンブラで、[`asm/Dockerfile`](asm/Dockerfile)で固定しています。
- nevikstiによるStar Oceanのチップなし変換。アドレス空間に収まらない大きさのイメージに対するアドレッシング規則の出典です。
- Zeldixコミュニティ。このプロジェクトが依拠するSNESのROMハックの知識の多くが書き残されている場所です。
- ゲームと移植版は、FTL GamesとSoftware Heavenが制作しました。

## 引用

[CITATION.cff](CITATION.cff)は、[`version.py`](version.py)に刻印するスクリプトによってリリースごとに更新されます。

## ライセンス

MITです。[LICENSE](LICENSE)を参照してください。このライセンスは、ツール、アセンブリ、この文書を対象とします。ゲームに関する権利は一切付与せず、ここではROMデータを配布していません。
