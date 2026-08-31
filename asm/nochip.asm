; Dungeon Master without the DSP-2: where everything the conversion adds lands.
;
; Three regions, all of them filler that no tour ever read, measured across
; three seeded runs of 30,000 frames with every cartridge read recorded:
;
;   $1C:E1BF   7,747 bytes   the routines and the trampoline dispatchers
;   $00:FBED     979 bytes   the stubs bank $00 reaches by JSR
;   $04:AA1B     257 bytes   the stubs bank $04 reaches by JSR
;
; The routines are placed through bank $9C rather than $1C. The two are the same
; bytes, because banks $80 to $BF mirror $00 to $3F, but the fast mirror answers
; an instruction fetch in six master clocks where the slow one takes eight, and
; the boot code has already enabled that by writing $01 to $00:420D at $00:8004.
; The data the routines touch is in work RAM either way, which is always eight,
; so this speeds the fetching and not the working.
;
; A stub exists because JSR cannot leave its bank while JSL can, and the
; instructions being replaced are three bytes where a JSL is four. So a site
; three bytes wide becomes a JSR to a stub in its own bank, and the stub is free
; to be as long as it likes and to JSL anywhere.

lorom

!ROUTINES = $9CE1BF
!BANK00   = $00FBED
!BANK04   = $04AA1B

org !ROUTINES
incsrc "dsp2-tables.asm"
incsrc "dsp2-soft.asm"
incsrc "dsp2-tramp.asm"
routines_end:

; ---------------------------------------------------------------------------
; The stubs bank $00 reaches.
;
; b00_first stands in for the first of the six sync commands the boot code
; writes at $00:801E. Sync produces nothing, so putting the state block in
; order before passing the byte on costs the game nothing, and it is the
; earliest point in the run where the processor is in native mode with the data
; bank and the direct page already set.
;
; b00_feed and b00_drain stand in for the eighteen block moves in this bank,
; sixteen feeding the port from work RAM and two draining it back. Both name
; their banks in the instruction, so neither needs a bank supplied.
; ---------------------------------------------------------------------------
org !BANK00
b00_first:
    jsl dsp_init
    jml dsp_write               ; its RTL returns to the boot code

b00_feed:
    jsl dsp_feed_wram
    rts

b00_drain:
    jsl dsp_drain_wram
    rts
bank00_end:

; ---------------------------------------------------------------------------
; The stubs bank $04 reaches.
;
; Thirteen sites in this bank call one of the four work RAM trampolines, and
; bank $04 is the only place in the image that ever points one of them at the
; chip. Each site becomes a JSR to the stub for the trampoline it named, and the
; dispatcher behind that stub reads the trampoline's own operands to decide
; whether this particular call was going to the chip or somewhere ordinary.
; ---------------------------------------------------------------------------
org !BANK04
b04_0080:
    jsl tramp_0080
    rts

b04_0084:
    jsl tramp_0084
    rts

b04_0088:
    jsl tramp_0088
    rts

b04_008C:
    jsl tramp_008C
    rts
bank04_end:

print "routines      ", dec(routines_end-!ROUTINES), " bytes of 7747"
print "bank 00 stubs ", dec(bank00_end-!BANK00), " bytes of 979"
print "bank 04 stubs ", dec(bank04_end-!BANK04), " bytes of 257"
