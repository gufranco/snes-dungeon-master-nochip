; Dungeon Master, software DSP-2: the work RAM trampoline dispatchers.
;
; The boot code at $00:805A installs four block movers in low work RAM, at
; $0080, $0084, $0088 and $008C. Each is three bytes of MVN and one of RTS, and
; a caller writes the two bank operands before invoking it. They are reached as
; JSR from ten different banks and most of that traffic has nothing to do with
; the chip, so the trampolines themselves are left exactly as they are.
;
; Measurement decides which calls matter. Across a 30,000 frame tour, 24 of the
; 40 million port transactions arrive through these four addresses, so they are
; not a rare path: they carry sixty per cent of the traffic. Every one of them
; runs with the program bank at $04, and a scan of the whole image finds that
; bank $04 is also the only place that ever writes $3F into a trampoline
; operand, at eight stores in four routines. So the thirteen call sites in bank
; $04 are the complete set that can reach the chip this way, and the calls from
; banks $01, $03, $05, $08, $12, $1A, $1B, $1C and $1D are left alone.
;
; A dispatcher stands in for one trampoline. It reads that trampoline's own bank
; operands, which the caller has already written, and decides from them what the
; block move was going to be. Pointed at the chip in either direction it becomes
; the matching software transfer; pointed anywhere else it calls the real
; trampoline, which still works. Nothing here has to know which of the thirteen
; sites is which, because the operands say.
;
; Low work RAM is mirrored into banks $00 to $3F, so JSR $0084 reaches the same
; four bytes from bank $1C as it does from bank $04.

; ---------------------------------------------------------------------------
; trampoline
;
; Entry: A 16 bit holding the count less one, X the source offset, Y the
;        destination offset, exactly as the block move wanted them. Reached by
;        JSL from a five byte stub in the calling bank, because JSR cannot leave
;        its bank and the instruction being replaced is only three bytes.
; Exit:  as the block move would have left them.
;
; <destination> and <source> are the addresses of that trampoline's two operand
; bytes. <mover> is the trampoline itself.
; ---------------------------------------------------------------------------
macro trampoline(destination, source, mover)
    php
    rep #$30
    pha
    sep #$20

    lda.l <destination>
    cmp.b #!DSP_PORT_BANK
    beq ?feeding
    lda.l <source>
    cmp.b #!DSP_PORT_BANK
    beq ?draining

    rep #$30                    ; neither operand names the chip, so this is one
    pla                         ;   of the moves that has nothing to do with it
    plp
    jsr <mover>
    rtl

?feeding:
    lda.l <source>              ; the chip is the destination, so the bank the
    sta.l !STATE+!S_XFER_BANK   ;   payload comes from is the other operand
    rep #$30
    pla
    plp
    jml dsp_feed_bank           ; its RTL returns to the caller of this one

?draining:
    lda.l <destination>         ; the chip is the source, so the bank the result
    sta.l !STATE+!S_XFER_BANK   ;   lands in is the other operand
    rep #$30
    pla
    plp
    jml dsp_drain_bank
endmacro

tramp_0080:
    %trampoline($000081, $000082, $0080)

tramp_0084:
    %trampoline($000085, $000086, $0084)

tramp_0088:
    %trampoline($000089, $00008A, $0088)

tramp_008C:
    %trampoline($00008D, $00008E, $008C)
