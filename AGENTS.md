# Working in this repository

Read [`FAMILY.md`](FAMILY.md) first. It is the standard every member is built to
and it is identical in all twenty of them. This file is the part that is only
true here.

## What this project is, in one paragraph

Dungeon Master is the one SNES cartridge carrying a DSP-2, and without that part
the game does not draw. This replaces the part with 65816 code and points the
cartridge's own instructions at it. Every access is redirected in place and every
replacement is the same width as the instruction it replaces, so nothing in the
image moves and no address the game computes for itself changes meaning.

## The part is a renderer, not an unpacker

This is the fact the shape of everything here follows from, and it is the first
thing a reader assumes wrongly.

The DSP-2 has six commands: convert a bitmap to the console's tile format, set a
transparent colour, merge two bitmaps against it, mirror, multiply, and scale.
None of them decompresses anything. What the cartridge asks it to convert is the
dungeon view as composed for where the player is standing, so the set of inputs
is not fixed and cannot be computed ahead of time and stored.

That was measured rather than argued. Searching the retail dump for the exact
bytes the cartridge sends finds every one of the mirror command's inputs, 1.2% of
the merge command's, and 0.3% of the tile command's. Mirror only ever mirrors
fixed assets. The two that matter do not.

A second measurement closes the other half of it. Comparing two recorded runs,
99.3% of tile calls and 99.2% of merge calls use an input the other run had
already seen, so a table of answers would cover almost everything. But no cheap
key exists to find them by: a sixteen byte prefix still fails to tell 154 of
1,767 tile inputs apart, and a sixty four entry cache of recent inputs hits 2.7%,
because the repeats are spread across a whole run rather than clustered.

## Speed is a measured number, not a claim

A chip worked while the program feeding it carried on. Moving that work onto the
processor cannot be free, so every statement about it here is a cycle count.

[`tools/cost.py`](tools/cost.py) runs each command on the 65816 model, which
drives a bus cycle by cycle, feeds it the cartridge's own recorded traffic, checks
every answer against what the recording holds, and prices the exchange against what
it cost when a chip answered it. Both figures print per command. A single total
would hide which one regressed, which is the whole reason for the tool.

Three things follow for anybody changing the assembly:

- **Run the cost tool before and after.** A change that makes an operation
  clearer and slower is a change this project cannot take without saying so.
- **The scaffolding is the cost, not the arithmetic.** A merge computes four
  bytes for about 180 cycles and the whole exchange takes 1,207, or 1,292 when
  it arrives through a dispatcher, which most of the traffic does. The rest is
  standing in for one instruction: saving what the caller had, pointing the data
  bank and the direct page at the state block, and putting it back. There are
  about 120 of those interceptions in a frame.
- **Know the ceiling before optimising.** The routines add 53,607 cycles to a
  frame that holds 59,561, and the two commands that matter are already within a
  few hundred cycles of what this shape can do.
  [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) carries the measurements, including
  the two ideas that look obvious and do not work: caching answers, and indexing
  a table by two input bytes at once.

## The six models, and why there are six

Every claim about what a part does is made by a member on the import path, never
here. [`hardware.py`](hardware.py) is the only way any of them is reached.

| model | what it answers for |
|---|---|
| `snes-dsp` | what the DSP-2 returns, by running the part's own microcode |
| `mos65xx` | the processor the replacement runs on, and the instrument it is measured with |
| `snes-mapper` | the cartridge map |
| `snes-rom-image` | the forms the image is stored in |
| `snes-graphics` | the tile format the conversion produces |
| `snes-driver` | where in the cartridge's own code it reaches the part |

The models start dirty. Memory and registers hold arbitrary but reproducible
values rather than zeroes, because hardware does, so anything wanting a cleared
machine has to ask for one.

## The table is the design and the fallback is what keeps it honest

The family standard carries this rule; what follows is what it means here.

The table holds what the game asks for, never what the part accepts. Sizing
against the part's input domain concludes that nothing can be stored, because the
domain is the exponent of the argument count. Sizing against the game concludes
that almost all of it can. Any figure here says which of the two it measured.

What the game asks for is a property of the whole game. A recording is a floor,
and a recording of the attract demo with the controls untouched is the lowest
floor there is. A figure taken from one states the frames it covers and what the
run was doing.

Two questions come apart and are answered separately. Which calculations the game
can ask for is answered by reading the whole image, and that closes. Which values
it asks for them with is answered by running the game, and that does not: the
values are computed from state the image does not hold.

Every command has a fallback in 65816, and it is never optional. A lookup with no
row has no answer, so a replacement that meets one either hangs or reads whatever
was in memory. The intent is that the fallback never runs; the requirement is that
it always could. A slower answer beats a stopped machine.

A fallback nobody measured is a fallback nobody has. Its cost is stated in cycles
and a build reports how often it fired, rather than asserting it did not.

## Assembly is source, is commented line by line, and is fast

Three rules bind every `.asm` file in this repository, and a file that breaks any
of them is incomplete rather than merely untidy.

**Everything ships as source.** The `.asm` files are the deliverable. Nothing
assembled is checked in: no patched image, no object file, no symbol file, no
table pasted in as a block of numbers. A build produces those into an ignored
directory and a clone reproduces them from source. Where a table can be computed,
it is computed by the assembler at build time from the same expression that
describes it, because a table worked out where it is used cannot drift away from
the code that uses it and a table pasted in as numbers can.

**Every file is commented line by line, for a reader who does not know
assembly.** This is not the comment policy that governs the rest of the
repository, and the difference is deliberate. In a high level language a name
carries the meaning, so a comment restating it is noise that goes stale. In
assembly there are no names: there are registers, raw addresses and opcodes, and
nothing in `lda $2140` says what `$2140` is or why it is being read. So each file
opens with what it does and what a reader needs to know to follow it, each block
says what it is for, and each line that is not self-evident carries a short note
of what it does and why. A number that came from a measurement says which one.

**Performance is an absolute priority.** This code runs in place of a coprocessor
on a 3.58 MHz processor, inside a frame budget the game already spends. Every
routine is written for speed first:

- Count cycles, not instructions, and state the count where it matters.
- Prefer the shortest addressing mode that reaches: direct page over absolute,
  absolute over long. Direct page is one byte and one cycle cheaper per access.
- Keep the direct page pointed at the working set so the cheap mode is reachable.
- Stay in sixteen bit mode for anything that moves words; `rep`/`sep` pairs
  around a byte operation usually cost more than they save.
- Unroll the inner loop of anything that runs per scanline or per pixel. The
  branch and the counter are pure overhead there.
- Prefer a table lookup to arithmetic when the table fits, and arithmetic to a
  lookup when the arithmetic is a shift.
- Do not call a subroutine from an inner loop when it can be inlined; `jsr` plus
  `rts` is twelve cycles that compute nothing.
- Reach ROM through the fast mirror at banks `$80`-`$BF` when the cartridge is
  configured for it, which answers a fetch in six master clocks against eight.

A routine that is correct and slow is not finished. Where a faster form was
rejected, the reason is written down beside the slower one, because the next
reader will otherwise assume nobody thought of it.

## What must never enter this repository

No cartridge, no microcode, no patched output, no intermediate derived from any
of them. Not as a fixture, not as a test resource, not in a commit that is later
reverted. Digests identify a file without carrying it, and
[`artifacts.manifest.json`](artifacts.manifest.json) is where they live.

This is why parts of the suite skip rather than fail without a dump, and why the
checks that need one live in `*.retail.test.py` files kept out of the coverage
measurement: a machine with the dump runs one set of paths and a machine without
it runs the other, so no single run can exercise both.

## Gates

Everything below must pass before a change is done. There is no partial credit,
and one command runs all of it:

```bash
python3 check.py            # every gate, including the ones that need the dump
python3 check.py --quick    # only the ones that do not shell into a container
```

It assembles the measurement image first when it is missing or older than any
assembly source, names each gate as it passes or fails, and runs the rest rather
than stopping at the first. Every tool it runs is pinned to the version the
runner installs, because reporting coverage with a newer build than the one that
recorded it named four lines uncovered that were not.

The gates it runs, for reference:

| gate | command |
|---|---|
| tests | `for t in *.test.py tools/*.test.py conformance/*.test.py; do python3 "$t" \|\| break; done` |
| coverage, which fails below 100% | `python3 -m coverage erase && for t in *.test.py tools/*.test.py conformance/*.test.py; do python3 -m coverage run -a "$t"; done && python3 -m coverage report` |
| types | `mypy .` |
| lint | `ruff check .` |
| format | `ruff format --check .` |
| yaml | `uvx yamllint==1.38.0 --strict .` |
| workflows | `actionlint` |
| this machine | `python3 doctor.py` |
| the cartridge | `python3 cartridge.py roms/<dump>.sfc build/<name>.sfc` |
| how far behind it runs | `python3 tools/pace.py roms/<dump>.sfc build/<name>.sfc` |
| that the block's work RAM is still free | `python3 tools/placement.py` |
| that nothing outside a declared region moved | `python3 similarity.py roms/<dump>.sfc build/<name>.sfc` |

A change to the assembly adds two more: rebuild, then run
[`tools/cost.py`](tools/cost.py) and read both columns, and run
[`tools/boot.py`](tools/boot.py), which drives the finished cartridge and fails
if the header still declares a coprocessor, if anything asked one for something,
if the run stopped early, or if the screen never lit. The last of those is not
padding: the first wrong placement of the state block passed every other check
and booted to black.

## Conventions that are only true here

- **Comments are required in the assembly and only there.** Entry and exit state,
  register widths, and where each recovered address came from. Python carries
  none, docstrings included.
- **The assembler is asar 1.81, pinned in a container.** It has two traps worth
  knowing: `label+0*N` silently assembles to `$FFFFFF` rather than to `label`, and
  a define written as `!NAME = 512  ; a comment` captures the comment, so any
  expression using it fails to resolve. Both cost a debugging session; write the
  offsets out.
- **An eight bit immediate inside a sixteen bit region desynchronises the
  instruction stream** and the symptom is a stack that runs away, not an
  assembler error. Check the width the code is in before adding a `lda.b`.
- **The state block's layout is checked against itself.** Every field in
  [`dsp2-state.asm`](asm/dsp2-state.asm) states its width, and
  [`stateblock.py`](stateblock.py) reads those statements and refuses two fields
  that share a byte. The assembler cannot: an offset is a number, and two names
  for one number assemble without complaint. Two did share, and one of them was
  the bank a split transfer reads from. Adding a field means stating its width.
- **An image with the routines placed is not a converted cartridge.** Assembling
  puts the replacement in the image; nothing calls it until
  [`patch.py`](patch.py) redirects the accesses and the header stops declaring a
  coprocessor. The half-done image boots and plays, because the emulator reads
  that header and provides the chip. What tells you is the emulator's own line:
  `dsp=2` with millions of chip events on a run that should have none. Build
  through [`cartridge.py`](cartridge.py), which does both steps and refuses to
  write the file if either check finds anything left.
- **Placement in work RAM is measured, never guessed.** The state block sits in a
  run of 4,078 bytes that three thirty thousand frame tours never touched, found
  by comparing the whole of work RAM against the previous frame after every
  frame. An earlier instrument watched byte accesses only, missed everything this
  game moves by DMA, and put the block on top of a live table. Moving the block,
  or wanting to trust it under a new input, means running
  [`tools/placement.py`](tools/placement.py), which reads the addresses out of
  the assembly rather than repeating them.

## Bound the domain before building a table, never after

A table keyed on values taken from a recording covers the recording and nothing
else. That is not a small caveat, it is the whole behaviour of the thing: a
recorded-set table answers the run it was built from perfectly and answers a run
it has not seen almost never. Measure it and the gap is not subtle. Splitting one
recording in half and asking the second half what the first half learned, this
project's table answered 7.2% of calls. Asking it a different recording of the
same demo it answered 91.4%, and that number is worse than useless without the
first one beside it: the recordings are the same attract sequence, so the 91.4%
measures repetition and not coverage.

So the domain comes first, and it comes from the code.

**Do this in order, per calculation, before a single row is written.**

1. **Read the part's own program for what bounds each input.** A table lookup
   with a fixed size bounds its index. A mask bounds a word. A shift bounds a
   magnitude. A clamp bounds both ends. These are true bounds, independent of
   any recording, and they are the only kind that is.

2. **Read the calling code for what it can compose.** An argument built from a
   fixed table, a constant, or a quantised angle has a domain the caller decides
   and the image holds. This closes for the same reason the command census
   closes: it is a property of the image, not of a run.

3. **Size an exhaustive table over that domain.** Both the span of each word and
   the set of distinct values it can take, because they give very different
   answers when an input is quantised. This project has an argument whose span is
   32,769 and whose value set is seven, and the two sizings differ by four orders
   of magnitude.

4. **Choose per calculation, and record which case it is.**

   | case | what to build |
   |---|---|
   | the exhaustive table fits | build it. No miss is possible, and the fallback behind it becomes unreachable rather than merely unlikely |
   | it does not fit, but the arithmetic is readable | read the arithmetic. A routine covers the whole domain and costs no space |
   | neither | a recorded-set table, and say plainly that it covers the recording and what the holdout rate is |

5. **Publish the holdout for every calculation in the third case.** Build the
   table from part of the recordings and ask it the rest. A coverage figure with
   no holdout beside it is a claim about the data it was built from.

**A recorded-set table is the last resort, never the first move.** Reaching for
one before steps 1 to 3 have been done produces a table that looks finished,
measures well against its own inputs, and fails on a player. The failure is
silent, because a fallback answers and nothing reports that it did.

**Weight the effort by traffic, not by command count.** Three commands here are
77% of all calls. Making a rare command exhaustive while a heavy one is guessing
from its nearest neighbour is work in the wrong place.

**A miss is not the same as a wrong answer, and both get measured.** When a
fallback takes the nearest row, how near it is varies by orders of magnitude
between calculations: measured on real misses here, one command's nearest row is
never more than 26 out and another's is 23,154 out. The first is a near miss and
the second is noise. Which is which decides whether a recorded-set table is
tolerable for that calculation at all.

## Where the open questions are

[`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md). Anything not yet settled by measurement
belongs there, with the measurement that would settle it.
