# Open questions

What this project does not know for certain, and what it would take to find out.

This member claims less about hardware than its size suggests. Every statement
about what the DSP-2 returns is made by `snes-dsp`, which runs the part's own
microcode, and every statement about the processor is made by `mos65xx`. What is
left here is a question about coverage, a question about placement, and a
question about speed, and the speed one is the one that matters.

Every entry below is also in
[`conformance/divergences.json`](conformance/divergences.json) with its status
and severity, so a program can read what a person reads here.

## The replacement costs about one extra frame of processor time per frame

Priced against the cartridge's own recorded traffic, the routines spend **63,168
cycles a frame** where the chip path spent **7,600**. A frame holds 59,561. So
the conversion adds very nearly a whole frame of work to every frame, averaged
over three tours that walk the dungeon continuously.

Two commands carry almost all of it:

| command | calls across three tours | cycles a frame, ours | cycles a frame, the chip path |
|:--|--:|--:|--:|
| tile | 1,031,195 | 30,031 | 5,190 |
| merge | 2,023,023 | 28,278 | 2,113 |
| scale | 29,267 | 3,552 | 233 |
| everything else | 253,288 | 1,307 | 64 |

The figure is a weighted one, because the cartridge reaches the chip two ways and
they do not cost the same. Eighteen sites in bank $00 name their banks in the
instruction and become a call straight to a transfer. The rest go through one of
four block movers the boot code installs in work RAM, whose bank operands the
caller writes first; those became dispatchers that read the operands back and
decide from them, and that costs 42 cycles a transfer. Sixty per cent of the
traffic arrives that way. Priced through the direct path alone the total is
61,387, which is the number to compare against when changing an operation and
the wrong one to quote as what the cartridge costs.

The merge row is the one that says where the cost actually is. A merge computes
four bytes, and the arithmetic for those four bytes is about 180 cycles of the
1,207 it takes. The rest is the price of standing in for one instruction: saving
what the caller had, pointing the data bank and the direct page at the state
block, and putting it all back. There are about 120 of those interceptions in a
frame. No arrangement of lookup tables removes them, because they are not
computation.

This is not a shortfall that closes with more optimisation of the same shape.
Since this was first measured the figure has come down from 95,258 cycles a
frame to 63,168, and every remaining idea that has been costed is worth low
thousands rather than tens of thousands. Reaching the chip's own figure is not
possible at all: the chip computed while the program that fed it carried on, so
its work was free to the program in a way software never is.

### What that costs in practice is much less than the sum suggests

The sum is not the question a player has, so
[`tools/pace.py`](tools/pace.py) asks the other one. Both cartridges are driven
with the same input, the emulator digests every finished frame, and the picture
the retail run showed at frame n is looked for in the converted run's stream. How
much later it turns up is how far behind the conversion is.

The lag does not grow. Over 30,000 frames of walking and turning, eight minutes
of play in which the cartridge sends the chip about 85 million bytes, it appears
once and clears:

| from frame | frames behind |
|--:|--:|
| 0 | 61 |
| 3,806 | 0 |
| 11,290 | 0 |
| 18,774 | 0 |
| 26,258 | 0 |

**29,936 of the 30,000 frames were drawn the same.** A conversion that is
steadily slower falls further behind every frame. This one loses one second on
the first dungeon draw and then does not lose another frame for the remaining
twenty six thousand.

The route is not a light one. Over 12,000 frames it provokes 33,994,917 chip
events; the random walk the recordings came from provokes 31,471,694 over the
same span. Pressing more often changes nothing, because the
game gates movement on its own step animation: at one press every 20 frames the
count is 33,994,910 and the lag profile is identical.

The most likely reason is the one thing the cycle comparison deliberately leaves
out. The retail path polls a status register in a loop until the chip answers,
and how long that takes is not something a table can price, so
[`tools/cost.py`](tools/cost.py) counts it for neither side. The replacement
answers that poll immediately. Whatever the retail cartridge spent spinning is
time the conversion gets back, and it does not appear in the 55,567.

Two limits, both of which cap what this can say:

- The emulator answers a chip command in no time at all, so the retail run here
  is faster than the cartridge ever was. The gap measured this way is an upper
  bound rather than the gap on hardware.
- The input fires at fixed frame numbers, so once the runs drift far enough the
  game receives its buttons at different points in its own logic and the two stop
  being the same playthrough. A random walk crosses that line early: driven by
  one, the comparison follows 3,403 frames of 9,000 and then says nothing. The
  steady route exists for this reason and survives the whole run.

**What would settle it:** real hardware, or an emulator whose coprocessor takes
the time the part took. Both are out of reach here, and what is measurable
without them has been measured.

## The recorded traffic is four recordings, not the whole game

Every claim of correctness here rests on 4,636,076 transactions recorded from
four runs: three seeded random walks of 30,000 frames each, and one steady route
of the same length. A command shape none of them produced has never been checked.

Replaying all four through the routines, on the processor, checks **98,333,301
bytes** against what the emulator the recording was made on answered. None are
wrong. That emulator computes the part's results in C rather than running its
microcode, so this is a statement about agreement with snes9x.

What the fourth recording shows is why this question stays open. It is a
different shape of workload, not merely more of the same: over 30,000 frames it
produces 848,987 merges and 372,624 tile conversions and **not one mirror or
scale**. The three walks produce both, and unevenly at that: scale appears 10,422
times in the first, 1,068 in the second and 17,777 in the third.

So no single input reaches all six commands, and the coverage argument rests on
the union of four. What bounds the risk is that the shapes are few and each
operation is a closed function of its payload.

What that argument has to carry has shrunk. Correctness no longer rests on the
recordings: five of the six commands are held to the part directly, over inputs
chosen rather than observed, with a part built fresh for each case.

| command | held to the part by | over |
|---|---|---|
| tile | [`tools/verify_commands.py`](tools/verify_commands.py) | random 32 byte payloads |
| transparent | [`tools/verify_merge.py`](tools/verify_merge.py) | every colour, through the merge |
| merge | [`tools/verify_merge.py`](tools/verify_merge.py) | every declared length to 80 |
| mirror | [`tools/verify_commands.py`](tools/verify_commands.py) | every declared length to 80 |
| multiply | [`tools/verify_multiply.py`](tools/verify_multiply.py) | the corners and 120 seeded pairs |
| scale | [`tools/verify_commands.py`](tools/verify_commands.py) | both shapes the cartridge sends |

The mirror shows what this buys. One recorded route of thirty thousand frames
contains **not a single mirror**, and the routines are checked against the part
on eighty of them regardless.

What the recordings still settle, and nothing else does, is which inputs the
cartridge actually sends. That is what the cost figures are weighted by, and it
is why this entry stays open rather than closing.

All six are now held to the part, so the correctness half of this entry is
closed. What is left is only which inputs occur, which the cost figures are
weighted by.

**What would settle it: nothing in reach.** No route proves it reached every
screen. More inputs narrow it and none closes it.

## The scale has never been compared against the part

Five of the six commands are now held to the part directly. The scale is the one
that is not, and it turns out never to have been.

[`scalestep.retail.test.py`](scalestep.retail.test.py) checks the routines
against themselves: that one length pair answers the same every time, and that
two pairs answer differently. It never asks the part what the answer should be.
So a command carrying 10,422 calls in one recorded tour has no check that its
arithmetic is right.

Driven the way the other five are driven, over the only two length pairs the
cartridge asks for, `(72, 38)` and `(120, 80)` counted in nibbles, the part and
the routines disagree on **146 of 236 bytes**.

That is not yet a finding. The tile disagreed on every byte until a one byte
preamble was understood, and the merge disagreed on almost every byte until its
length prefix was restored. A command nobody has driven before disagreeing means
the driving is unproven, not that the routines are wrong. It is left out of the
gate rather than shipped as a passing check that avoids the hard case.

**What would settle it:** establishing how the cartridge drives a scale, from its
own code or from a recording that contains one. No recording taken here contains
a scale at all, which is the same coverage hole the mirror had.

## The recordings and the part agree, and the verifier that says so now works

Both of these were open, and both are closed by the same measurement.

The comparison was framing, and two numbers were missing from it. **A tile is
preceded by one byte that is not part of its answer**, and **a sync leaves one
byte behind that the cartridge never reads.** Those two, with the length byte the
parser strips into its own field written back, are the whole of it.

With them, replaying a whole recording against the part's own program walks
45,313,954 records and reproduces **all 17,241,846 bytes the cartridge returned,
none wrong.** Without them it disagreed on more than nine tenths.

So the emulator's C and the part's microcode give the same answers for everything
the cartridge actually asks, and a figure quoted against a recording is a figure
against the part as well.

What a recording still cannot say is anything about inputs it does not contain,
and that is exactly where the routines were found wrong. Every recorded multiply
has a zero first operand. No recording taken here contains a scale or a mirror at
all. Both defects were found by asking the part directly, and neither could ever
have been found by replaying traffic.

[`tools/verify_trace.py`](tools/verify_trace.py) drives by transaction rather
than by byte, because only the protocol can say which write is a command, which
is a declared length, and which byte of the output was never going to be read.

## One command answers differently outside anything the cartridge asks for

Three places stood here where the routines and the part parted company. Two are
closed by reading the part's program rather than by running it, and what is left
is one.

**A merge longer than 80 bytes. The boundary is measured, and everything below
it is now held to the part.**

Asked directly, with a part built fresh for each case, the part and the rule the
routines follow agree on **every declared length from 1 to 80**, over 240 random
bitmaps and colours, and on **none from 81 to 199**. At 81 the part emits one
byte before the run and then drifts, which is the shape of a buffer running out
rather than of different arithmetic. snes9x's source says the same in a comment:
the hardware does strange things if the size is varied.

[`tools/verify_merge.py`](tools/verify_merge.py) now holds the routines to the
part over every length up to 80, on the processor, and is a gate. That is the
whole of what the cartridge can ask for: the largest merge in 60,000 recorded
exchanges declares 30, and only five distinct lengths appear at all.

What the part does above 80 is still not modelled. The routines hold a 512 byte
parameter buffer and so have an answer for every length the protocol can declare,
and whether the part has one is a question about the part.

**A multiply of anything but zero. Settled, and the routines were wrong.**

The routine at `$0478` loads `$7FFF` as a mask, hands both operands to the
multiplier, and shifts a result word right by one before masking it. Reading the
registers while it runs says why: the multiplier leaves the signed product
doubled across `M` and `N`, and `shr1` on this part is arithmetic. So the rule is

```
product = signed(a) * signed(b)
low     = (product & 0x7FFF) | ((product & 0x4000) << 1)
high    = (product >> 16) & 0x7FFF
```

which agrees with the part on 610 of 610 operand pairs, including zero on either
side, both signs, and the value whose product sets bit 14 next to the one just
below it.

The routines computed a plain unsigned product, which is wrong for 140 of 200
random pairs. They now compute this, and
[`tools/verify_multiply.py`](tools/verify_multiply.py) holds them to it over the
corners and 120 seeded pairs, on the processor, against the part. It was driven
to failure both ways before being trusted: with the rule broken it reports the
part no longer matching, and with the old routine restored it reports 59 of 228
bytes wrong.

Nothing recorded could ever have caught this. Every multiply in every recording
has a zero first operand, tens of thousands without exception, and the rule and
the plain product agree on zero.

## The state block sits where three tours never wrote

The block needs 1,536 bytes of work RAM the game does not use, and the game's own
use of work RAM is written down nowhere. It was found by comparing the whole of
work RAM against the previous frame after every frame of three 30,000 frame
tours. That leaves 4,568 bytes untouched across 87 runs, only one of which is
long enough to hold the block, and the block sits 194 bytes into that run and
2,860 bytes short of its end.

It is listed because the first attempt was wrong in a way that looked right. An
earlier instrument watched byte accesses only. This game moves work RAM by DMA,
which that path does not see, so it reported 37,245 bytes free and the block went
on top of a live table. The converted image drew a blank screen.

A fourth input has since been tried, and the claim held.
[`tools/placement.py`](tools/placement.py) drives the retail cartridge along the
steady route for 19,000 frames, during which it sends the chip 55,805,743 bytes,
and reports what work RAM it touched. Not one byte of $00900 to $00EFF, and the
longest free stretch is the same $0083E for 4,078 bytes the tours found. The
addresses come out of the assembly rather than being repeated in the tool, so a
block that moves cannot leave this checking where it used to be.

Three more inputs have since been tried and the claim held under all of them.
[`tools/placement.py`](tools/placement.py) now takes a seed, so a random walk can
be asked for instead of the steady route, and three walks of 19,000 frames each
report what the tours and the steady route did: **not one byte of `$00900` to
`$00EFF` touched**, and the same longest free stretch of 4,078 bytes at `$0083E`.
That is seven distinct inputs.

Whether reading the code could settle it instead was tried, and it cannot.
Scanning the whole dump for instruction-shaped writes landing in that range
returns 965 hits against a random-noise expectation of roughly 844 for a scan of
that shape over a megabyte, so the reading is noise rather than evidence.
Following the code instead would need every entry point found, and even then an
indexed write and a computed DMA destination cannot be bounded without running
them.

**What would settle it: nothing in reach.** A run reaching every screen would,
and no route proves it reached every screen. A disassembly would, and the writes
that matter are indexed or computed. What exists instead is a check any new input
can be tried against in one command, and seven inputs that agree.

## What is closed, and why it is worth saying

**Scale declared its lengths in nibbles, and the parser shared the mistake.** The
chip reads the scale command's two declared lengths as counts of nibbles. Both
the routine and the tool that parses recorded traffic read them as byte counts,
and because they shared the mistake, scale was not merely wrong: it was
unverifiable. The harness fed it a payload of the wrong length and compared the
answer against an expectation of the wrong length, and the two agreed with each
other. It was found by reading the raw shape of a scale exchange, 63 writes then
40 reads, against what the parser claimed. Both were corrected. Scale now answers
every recorded byte and its cost fell from 44,521 cycles to 13,490.

**The replay harness reported numbers it had not measured.** Its counters live in
work RAM at an address nothing else reached until the merge lookup tables were
placed there. The tables overwrote the counters, and the byte the finish flag is
read from happened to hold the value that means finished, so a run reported the
same 353,637,138 wrong bytes for any script and reported them as a completed run.
Two more ways the same harness could report a result it had not measured turned
up beside it: the emulator's exit code was discarded, and the memory dump was
read whether or not that run had written it. All three are fixed and guarded.

**Two fields of the state block shared a byte.** The block is laid out by hand
as a list of offsets, and nothing checked that list against itself: an offset is
a number, and two names for one number assemble without complaint. `!S_OVERLAY`
was declared at `$0E`, which is `!S_INBYTE`, and the sixteen bit store that sets
it reached into `$0F`, which is the bank a block transfer reads from. A transfer
that overruns one command's payload carries on into the next and re-reads that
bank, so a merge would have taken its continuation from wherever the overlay
pointer's high byte pointed. Nothing in 4.6 million recorded transactions
overruns, which is why it never fired and why it needed a check rather than a
reading. [`stateblock.py`](stateblock.py) now refuses any two fields that share a
byte, and [`splitfeed.retail.test.py`](splitfeed.retail.test.py) drives the
overrun: against the old layout it reads bank `$0A` and stops, against the new
one it answers what a single move answers.

**The part is a renderer, not an unpacker.** If it expanded stored graphics the
conversion would be a build step: expand everything once into the image and the
cartridge would never need an answer computed. Searching the retail dump for the
exact bytes the cartridge sends settles it. Every one of the mirror command's
inputs is a run found in the dump. Of the tile command's, 0.3% are, and of the
merge command's, 1.2%. The two commands that matter are handed a view composed in
work RAM for wherever the player is standing, which exists nowhere in the image.

**A cache of recent answers does not pay.** Across two tours, 99.3% of tile calls
and 99.2% of merge calls use an input the other tour had already seen, so the
idea is worth testing rather than dismissing. It fails on the key. A sixteen byte
prefix still fails to tell 154 of 1,767 distinct tile inputs apart, and the
repeats are spread across a whole run rather than clustered: a sixty four entry
cache of recent inputs hits 2.7% on tile and 5.0% on merge.

**A sixteen bit table index cannot be reached under this mapping.** The obvious
way to halve the tile conversion is to look up two input bytes at once, which
needs a table indexed by a sixteen bit value, and no amount of image growth
provides one. Long indexed addressing adds a sixteen bit index to a twenty four
bit base, and 32 kilobytes past any base the address leaves the mapped half of
the bank and lands in the system area rather than in the rest of the table. A
single lookup is capped at a fifteen bit index here, and lifting that would mean
remapping the cartridge, which moves every address the game computes for itself.

## Boundaries, so nobody mistakes them for gaps

**Nothing here models hardware.** The six members on the import path do. The one
thing this measures directly is how many cycles its own routines spend, and it
measures that by running them on a processor model that drives a bus cycle by
cycle rather than by counting from a table.

**Neither the cartridge nor the microcode is here.** Nor is any image built from
either. Everything published is a digest, which is why parts of the suite skip
rather than fail on a machine holding neither, and why the checks that need one
live in files kept out of the coverage measurement.
