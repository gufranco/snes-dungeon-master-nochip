; Dungeon Master, software DSP-2: the block transfer entry points.
;
; The cartridge moves payloads to and from the chip with MVN rather than a store
; per byte, either from a fixed instruction in bank $00 or through one of four
; self modifying MVN trampolines the boot code installs in low work RAM at
; $0080, $0084, $0088 and $008C. A trampoline is three bytes of instruction and
; one of RTS, and the caller writes its bank operands before each use.
;
; A block move is a loop inside one instruction, so it cannot become a JSL: that
; is four bytes against its three. Each site instead becomes a JSR to a stub in
; the caller's own bank, which is also three bytes, and the stub is free to be
; long. The stubs live in dsp2-sites.asm, in filler measured to be unread.
;
; Everything here reproduces what MVN left behind, because the callers depend on
; it. After MVN dst,src has moved n bytes:
;
;   X and Y have both advanced by n
;   the whole accumulator holds $FFFF
;   DB holds the destination bank
;
; The trampolines themselves are never patched. They carry traffic that has
; nothing to do with the chip, and only the sites that pointed one at bank $3F
; are changed.

; ---------------------------------------------------------------------------
; block_enter
;
; Saves the caller's registers into the state block, where the transfer can add
; the count to them before they go back, and points DB and DP at the block.
;
; Entry: A 16 bit holding the count less one, X and Y 16 bit.
; Exit:  DB = $00, DP = !STATE. !S_XFER_TOTAL and !S_XFER_LEFT hold the count.
;        A, X clobbered.
; ---------------------------------------------------------------------------
block_enter:
    sta.l !STATE+!S_SAVE_A
    phx                         ; only the accumulator has long addressing, so
    pla                         ;   the index registers go through it
    sta.l !STATE+!S_SAVE_X
    phy
    pla
    sta.l !STATE+!S_SAVE_Y

    pea $0000
    plb
    plb
    ldx.w #!STATE
    phx
    pld

    lda !S_SAVE_A
    inc a                       ; MVN takes the count less one
    sta !S_XFER_TOTAL
    sta !S_XFER_LEFT
    rts

; ---------------------------------------------------------------------------
; block_leave
;
; Puts the caller's registers back with X and Y advanced by the count and the
; accumulator holding $FFFF, which is what MVN would have left.
;
; Entry: DB = $00, DP = !STATE, A and index registers 16 bit.
; Exit:  X and Y advanced, A = $FFFF. DB and DP still the block's, and the
;        entry point restores those.
; ---------------------------------------------------------------------------
block_leave:
    lda !S_SAVE_X
    clc
    adc !S_XFER_TOTAL
    tax
    lda !S_SAVE_Y
    clc
    adc !S_XFER_TOTAL
    tay
    lda.w #$FFFF
    rts

; ---------------------------------------------------------------------------
; dsp_feed_wram
;
; Stands in for MVN $3F,$7E, the fixed form in bank $00 that feeds the chip from
; work RAM.
;
; Entry: A 16 bit holding the count less one, X the source offset, Y the
;        destination offset, which the port ignored. Widths 16 bit, as MVN needs.
; Exit:  as MVN would leave them.
; ---------------------------------------------------------------------------
dsp_feed_wram:
    php
    rep #$30
    phb
    phd
    jsr block_enter

    sep #$20
    lda.b #$7E
    sta !S_XFER_BANK
    rep #$20
    jsr feed
    jsr block_leave

    pld
    plb
    plp
    rtl

; ---------------------------------------------------------------------------
; dsp_drain_wram
;
; Stands in for MVN $7E,$3F, the fixed form in bank $00 that drains the chip
; into work RAM. Sixteen of the block moves in that bank feed from work RAM and
; two drain back into it, and both forms name their banks in the instruction, so
; neither needs the caller to supply one.
;
; Entry: A 16 bit holding the count less one, X the source offset, which the
;        port ignored, Y the destination offset. Widths 16 bit, as MVN needs.
; Exit:  as MVN would leave them.
; ---------------------------------------------------------------------------
dsp_drain_wram:
    php
    rep #$30
    phb
    phd
    jsr block_enter

    sep #$20
    lda.b #$7E
    sta !S_XFER_BANK
    rep #$20
    jsr drain
    jsr block_leave

    pld
    plb
    plp
    rtl

; ---------------------------------------------------------------------------
; dsp_feed_bank
;
; Stands in for a trampoline pointed at the chip, where the source bank is
; whatever the caller wrote into that trampoline's operand. The stub that calls
; this reads the operand and leaves it in !S_XFER_BANK.
;
; Entry: as above, plus !S_XFER_BANK already holding the source bank.
; Exit:  as MVN would leave them.
; ---------------------------------------------------------------------------
dsp_feed_bank:
    php
    rep #$30
    phb
    phd
    sta.l !STATE+!S_SAVE_A      ; keep the count before block_enter reloads it
    lda.l !STATE+!S_XFER_BANK   ; and the bank, which block_enter does not touch
    pha
    lda.l !STATE+!S_SAVE_A
    jsr block_enter
    pla
    sta !S_XFER_BANK

    jsr feed
    jsr block_leave

    pld
    plb
    plp
    rtl

; ---------------------------------------------------------------------------
; dsp_drain_bank
;
; Stands in for a trampoline pointed the other way, draining the chip's finished
; output into memory. The destination bank is in !S_XFER_BANK.
;
; Entry: A 16 bit holding the count less one, X the source offset, which the
;        port ignored, Y the destination offset.
; Exit:  as MVN would leave them.
; ---------------------------------------------------------------------------
dsp_drain_bank:
    php
    rep #$30
    phb
    phd
    sta.l !STATE+!S_SAVE_A
    lda.l !STATE+!S_XFER_BANK
    pha
    lda.l !STATE+!S_SAVE_A
    jsr block_enter
    pla
    sta !S_XFER_BANK

    jsr drain
    jsr block_leave

    pld
    plb
    plp
    rtl

; ---------------------------------------------------------------------------
; feed
;
; Runs the transfer's bytes through the write state machine, reading them from
; the caller's source through a long pointer so any bank can be the source.
;
; Entry: DB = $00, DP = !STATE, !S_XFER_BANK and !S_SAVE_X and !S_XFER_LEFT set.
; Exit:  A, X, Y clobbered. Widths left at A 16 bit, index 16 bit.
; ---------------------------------------------------------------------------
feed:
    lda !S_XFER_TOTAL
    beq .done

    lda !S_SAVE_X
    sta !S_XFER_PTR
    sep #$20
    lda !S_XFER_BANK
    sta !S_XFER_PTR+2
    rep #$20
    stz !S_XFER_LEFT            ; bytes of the run delivered so far

.chunk:
    lda !S_XFER_LEFT
    cmp !S_XFER_TOTAL
    beq .done

    sep #$20                    ; the machine only takes a shortcut while it is
    lda !S_STAGE                ;   collecting a payload, because that is the one
    cmp.b #!STAGE_PARAM         ;   stage where every byte does the same thing:
    rep #$20                    ;   store, advance, count down. A command byte or
    bne .one                    ;   a length byte decides something, so those keep
    lda !S_WANT_PARAM           ;   going through the state machine one at a time
    beq .one

    sta !S_CHUNK                ; the run may hold more than the payload wants,
    lda !S_XFER_TOTAL           ;   and the payload may want more than this run
    sec                         ;   carries, so the block covers the smaller
    sbc !S_XFER_LEFT
    cmp !S_CHUNK
    bcs .have_count
    sta !S_CHUNK
.have_count:

    sep #$20
    lda !S_XFER_BANK
    sta !S_MVN+2                ; the stub reads from the caller's bank
    stz !S_MVN+1                ;   and writes into the parameter buffer's
    rep #$20

    lda !S_SAVE_X
    clc
    adc !S_XFER_LEFT
    tax
    lda !S_PARAM_INDEX
    clc
    adc.w #(!P_BUFFER&$FFFF)
    tay
    lda !S_CHUNK
    dec a                       ; a block move takes the count less one
    jsl !STATE+!S_MVN           ; leaves DB holding the destination bank, $00,
                                ;   which is where it already was
    lda !S_CHUNK
    clc
    adc !S_PARAM_INDEX
    sta !S_PARAM_INDEX
    lda !S_CHUNK
    clc
    adc !S_XFER_LEFT
    sta !S_XFER_LEFT
    lda !S_WANT_PARAM
    sec
    sbc !S_CHUNK
    sta !S_WANT_PARAM
    bne .chunk
    jsr run                     ; the payload is complete, so the operation runs
    rep #$30                    ;   here exactly as write_byte would have run it
    bra .chunk

.one:
    lda !S_XFER_LEFT
    tay
    sep #$20
    lda [!S_XFER_PTR],y
    sta !S_INBYTE
    rep #$20
    jsr write_byte
    rep #$30
    inc !S_XFER_LEFT
    bra .chunk

.done:
    rts

; ---------------------------------------------------------------------------
; drain
;
; The mirror of the above: takes the transfer's bytes from the finished output
; and writes them through the caller's destination.
;
; Entry: DB = $00, DP = !STATE, !S_XFER_BANK and !S_SAVE_Y and !S_XFER_LEFT set.
; Exit:  A, X, Y clobbered. Widths left at A 16 bit, index 16 bit.
; ---------------------------------------------------------------------------
drain:
    lda !S_XFER_TOTAL
    beq .done

    lda !S_SAVE_Y
    sta !S_XFER_PTR
    sep #$20
    lda !S_XFER_BANK
    sta !S_XFER_PTR+2
    rep #$20
    stz !S_XFER_LEFT            ; bytes of the run taken so far

.chunk:
    lda !S_XFER_LEFT
    cmp !S_XFER_TOTAL
    beq .done

    lda !S_OUT_LEN              ; only the bytes the operation actually produced
    sec                         ;   can be moved in a block. Past the end the port
    sbc !S_OUT_INDEX            ;   returned an idle byte rather than memory, so
    beq .one                    ;   those go one at a time
    bcc .one
    sta !S_CHUNK
    lda !S_XFER_TOTAL
    sec
    sbc !S_XFER_LEFT
    cmp !S_CHUNK
    bcs .have_count
    sta !S_CHUNK
.have_count:

    sep #$20
    stz !S_MVN+2                ; from the output buffer's bank
    lda !S_XFER_BANK
    sta !S_MVN+1                ;   into the caller's
    rep #$20

    lda !S_OUT_INDEX
    clc
    adc.w #(!O_BUFFER&$FFFF)
    tax
    lda !S_SAVE_Y
    clc
    adc !S_XFER_LEFT
    tay
    lda !S_CHUNK
    dec a
    jsl !STATE+!S_MVN           ; leaves DB holding the caller's bank, so bank
    pea $0000                   ;   zero is put back before the next field is
    plb                         ;   read. This code runs from bank one, so the
    plb                         ;   program bank is not the one wanted here
    rep #$30

    lda !S_CHUNK
    clc
    adc !S_OUT_INDEX
    sta !S_OUT_INDEX
    lda !S_CHUNK
    clc
    adc !S_XFER_LEFT
    sta !S_XFER_LEFT
    bra .chunk

.one:
    jsr read_byte
    rep #$30
    ldy !S_XFER_LEFT
    sep #$20
    sta [!S_XFER_PTR],y
    rep #$20
    inc !S_XFER_LEFT
    bra .chunk

.done:
    rts
