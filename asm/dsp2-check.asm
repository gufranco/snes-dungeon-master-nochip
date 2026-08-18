; Assembles the software DSP-2 on its own, so the code can be checked and
; measured without a cartridge present. It places the routines where the build
; will place them and prints nothing into the image beyond them.
;
; The address below is the largest run of filler that no tour ever read: 7,747
; bytes at $1C:E1BF, measured across three seeded tours of 30,000 frames with
; every cartridge read recorded.

lorom

!ROUTINES = $1CE1BF

org !ROUTINES
incsrc "dsp2-soft.asm"

dsp2_end:
print "software DSP-2 occupies ", dec(dsp2_end-!ROUTINES), " bytes"
