# Contributing

## The short version

Evidence over assertion. A change that claims something is correct carries the run that shows it,
and a claim that cannot be checked is not ready.

## Before you open a pull request

Run every gate, and read the output rather than the exit code:

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
pnpm install --frozen-lockfile && pnpm run format:check
python3 -m coverage erase
for module in *.test.py tools/*.test.py; do python3 -m coverage run -a "$module"; done
python3 -m coverage report
python3 doctor.py
```

Every model this project measures itself against lives in its own repository and is pinned here as
a submodule at the root. `python3 doctor.py` reports the whole chain, including each model's own
report and the digest of every file it loaded, and it is the first thing to paste into an issue.

Coverage is a hard gate at 100% of statements and branches, and it is met on a machine holding
neither the cartridge nor the microcode. A check that needs either is a script rather than a test, or
lives in a `*.retail.test.py` file kept out of the measurement, and reports as skipped.

## What the parts are checked against

The retail cartridge is the only oracle for what the game asks. The part's own microcode is the only
oracle for what the answer is. Nothing here computes a DSP-2 result, and nothing here should start:
a value that did not come from the part is a value nobody can act on.

The microcode is not carried in this repository and never will be. A copy you already own goes in
`firmware/`, which is ignored, or anywhere `UPD7725_FIRMWARE_DIR` names. Without one the checks that
drive the part report that they had nothing to run rather than passing.

## Tests

A test file sits beside the module it covers and is named after it. Test bodies carry no comments:
arrange, act and assert are separated by one blank line each, and the test name says what behaviour
is being pinned.

A test never needs microcode or a cartridge. Where a check needs either, the part is passed in, the
tests pass a stand-in, and the run against the real thing is a script rather than a test. That is
what keeps the suite meaningful on a machine that holds neither.

## Commits

Conventional Commits, subject under fifty characters, imperative mood. The body explains what
changed and why, wrapped at seventy two columns. Releases are cut by semantic-release from those
subjects, so the type is what decides the version.

## What will be sent back

- A file nobody can legally redistribute: a cartridge, a microcode image, or any bytes from either.
- A number in a document that no run produced.
- A behaviour changed without the recorded traffic or the pinned digests moving with it.
- A test that asserts what the code does rather than what the hardware does.
- An answer computed here that should have come from the part.

## Conduct

The [Code of Conduct](CODE_OF_CONDUCT.md) applies wherever this project is discussed. One line of it
is specific to this repository and worth reading twice: never post a copyrighted image, a game, or a
link to somewhere either can be downloaded. A digest identifies a file without carrying it, and a
digest is all anybody needs.

## What is welcome without asking

Measurements. A run against a region this has not been run against, a disagreement between the
converted cartridge and the retail one, or a trace from hardware nobody here has. A recording of
what really happened is worth more than an argument about what should.
