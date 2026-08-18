; Dungeon Master, software DSP-2: the six operations.
;
; Every routine here runs with DB = $00 and DP = !STATE, set by its caller in
; dsp2-soft.asm, and may use A, X and Y freely because that caller saved them.
; Each reads parameters from !P_BUFFER and leaves its result in !O_BUFFER with
; the length in !S_OUT_LEN.
;
; The behaviour reproduced here was read from snes9x dsp2.cpp at master 2971061
; and checked a second way: a Python model of the same six operations replayed
; 71,970,987 bytes that the retail cartridge's chip returned across three
; recorded tours and reproduced every one. Where this file and that model
; disagree, this file is wrong.
;
; Every routine is entered with A 8 bit and index registers 16 bit, and leaves
; them that way.

; ---------------------------------------------------------------------------
; op_tile
;
; Command $01. 32 bytes in, 32 bytes out, and the size never varies.
;
; The input is a linear 4bpp bitmap: eight groups of four bytes, each group one
; row of eight pixels, two pixels to a byte. The output is one SNES 4bpp tile,
; which interleaves bitplanes 0 and 1 in its first sixteen bytes and planes 2
; and 3 in its last sixteen.
;
; A bitplane byte gathers one bit from each of the row's eight pixels, so the
; conversion is a bit transpose. Shifting the input byte left eight times walks
; its bits from 7 down to 0, and each falls out into the carry in exactly the
; order the four planes want them:
;
;   bit 7 -> plane 3      bit 3 -> plane 3
;   bit 6 -> plane 2      bit 2 -> plane 2
;   bit 5 -> plane 1      bit 1 -> plane 1
;   bit 4 -> plane 0      bit 0 -> plane 0
;
; because a pixel's bit for plane n sits at 4+n in its high nibble and at n in
; its low one. Rotating each carry into its plane accumulator therefore builds
; all four planes in one pass with no masks and no table, and the first bit
; rotated in ends up in bit 7, which is the order the reference produces.
;
; Entry: DB = $00, DP = !STATE, !P_BUFFER holds 32 bytes.
; Exit:  !O_BUFFER holds 32 bytes, !S_OUT_LEN = 32.
; ---------------------------------------------------------------------------
op_tile:
    ldy.w #$0000                  ; Y walks the input, four bytes to a group
    ldx.w #$0000                  ; X walks the output, two bytes to a group

.group:
    stz !S_SCRATCH+0            ; the four plane accumulators for this row
    stz !S_SCRATCH+1
    stz !S_SCRATCH+2
    stz !S_SCRATCH+3

    lda.w !P_BUFFER+0,y
    jsr tile_row_byte
    lda.w !P_BUFFER+1,y
    jsr tile_row_byte
    lda.w !P_BUFFER+2,y
    jsr tile_row_byte
    lda.w !P_BUFFER+3,y
    jsr tile_row_byte

    lda !S_SCRATCH+0            ; planes 0 and 1 go to the first half
    sta.w !O_BUFFER+0,x
    lda !S_SCRATCH+1
    sta.w !O_BUFFER+1,x
    lda !S_SCRATCH+2            ; planes 2 and 3 to the second
    sta.w !O_BUFFER+16,x
    lda !S_SCRATCH+3
    sta.w !O_BUFFER+17,x

    inx
    inx
    iny
    iny
    iny
    iny
    cpy.w #!TILE_BYTES
    bne .group

    rep #$20
    lda.w #!TILE_BYTES
    sta !S_OUT_LEN
    sep #$20
    rts

; Shifts one pixel pair into the four plane accumulators.
;
; Entry: A 8 bit, holding the input byte. DP = !STATE.
; Exit:  A clobbered, the accumulators at !S_SCRATCH+0 to +3 advanced by two
;        bits each. X and Y preserved.
tile_row_byte:
    asl                         ; bit 7
    rol !S_SCRATCH+3
    asl                         ; bit 6
    rol !S_SCRATCH+2
    asl                         ; bit 5
    rol !S_SCRATCH+1
    asl                         ; bit 4
    rol !S_SCRATCH+0
    asl                         ; bit 3
    rol !S_SCRATCH+3
    asl                         ; bit 2
    rol !S_SCRATCH+2
    asl                         ; bit 1
    rol !S_SCRATCH+1
    asl                         ; bit 0
    rol !S_SCRATCH+0
    rts

; ---------------------------------------------------------------------------
; op_transparent
;
; Command $03. One byte in, nothing out. The chip keeps only the low nibble and
; every later merge compares against it, so the value has to outlive this call.
;
; Entry: DB = $00, DP = !STATE, !P_BUFFER+0 holds the colour.
; Exit:  !S_TRANSPARENT holds the low nibble. !S_OUT_LEN is left alone,
;        because this command produces nothing and so spends nothing.
; ---------------------------------------------------------------------------
op_transparent:
    lda.w !P_BUFFER
    and.b #$0F
    sta !S_TRANSPARENT
    asl                         ; the same colour in the high nibble, so a merge
    asl                         ;   can compare a whole byte at a time without
    asl                         ;   shifting the overlay down first
    asl
    sta !S_SCRATCH+16           ; the count is deliberately left alone: setting
    rep #$20                    ;   the transparent colour produces nothing and
    sep #$20                    ;   does not spend a result already waiting
    rts

; ---------------------------------------------------------------------------
; op_merge
;
; Command $05. Two bitmaps of !S_LEN1 bytes each in, one of !S_LEN1 bytes out.
;
; The overlay wins wherever it is not the transparent colour, and the decision
; is per pixel rather than per byte, so one output byte can take its high pixel
; from the overlay and its low pixel from the background.
;
; This is the command the cartridge issues most, twenty three times a frame, and
; it is the one that gets cheaper by losing the chip: the retail path pushed
; three bytes through the port for every byte it produced and this touches each
; byte once.
;
; Entry: DB = $00, DP = !STATE, !P_BUFFER holds the background then the overlay.
; Exit:  !O_BUFFER holds the result, !S_OUT_LEN = !S_LEN1.
; ---------------------------------------------------------------------------
op_merge:
    lda !S_LEN1
    beq .empty

    rep #$20
    and.w #$00FF
    sta !S_OUT_LEN
    tay                         ; Y indexes the overlay, which starts at !S_LEN1
    ldx.w #$0000                  ; X indexes the background and the output
    sep #$20

.byte:
    lda.w !P_BUFFER,y           ; the overlay's high pixel
    and.b #$F0
    cmp !S_SCRATCH+16
    bne .keep_high
    lda.w !P_BUFFER,x           ; transparent, so the background shows through
    and.b #$F0
.keep_high:
    sta !S_SCRATCH+17

    lda.w !P_BUFFER,y           ; and its low pixel
    and.b #$0F
    cmp !S_TRANSPARENT
    bne .keep_low
    lda.w !P_BUFFER,x
    and.b #$0F
.keep_low:
    ora !S_SCRATCH+17
    sta.w !O_BUFFER,x

    iny
    inx
    cpx !S_OUT_LEN
    bne .byte
    rts

.empty:
    rep #$20
    stz !S_OUT_LEN
    sep #$20
    rts

; ---------------------------------------------------------------------------
; op_mirror
;
; Command $06. !S_LEN1 bytes in and the same count out, reversed end for end
; with the two pixels inside each byte swapped as well, which is what makes it a
; mirror of the picture rather than of the storage.
;
; Entry: DB = $00, DP = !STATE, !P_BUFFER holds the bitmap.
; Exit:  !O_BUFFER holds the result, !S_OUT_LEN = !S_LEN1.
; ---------------------------------------------------------------------------
op_mirror:
    lda !S_LEN1
    beq .empty

    rep #$20
    and.w #$00FF
    sta !S_OUT_LEN
    dec a
    tax                         ; X walks the output back from its last byte
    ldy.w #$0000                  ; Y walks the input forward
    sep #$20

.byte:
    lda.w !P_BUFFER,y
    asl
    asl
    asl
    asl                         ; the low pixel becomes the high one
    sta !S_SCRATCH+17
    lda.w !P_BUFFER,y
    lsr
    lsr
    lsr
    lsr                         ; and the high pixel becomes the low one
    ora !S_SCRATCH+17
    sta.w !O_BUFFER,x

    iny
    dex
    cpy !S_OUT_LEN
    bne .byte
    rts

.empty:
    rep #$20
    stz !S_OUT_LEN
    sep #$20
    rts

; ---------------------------------------------------------------------------
; op_multiply
;
; Command $09. Two 16 bit operands in, one 32 bit product out, little endian.
;
; The CPU has an 8 by 8 unsigned multiplier: write the multiplicand to $4202 and
; the multiplier to $4203, and the 16 bit product is at $4216 eight cycles
; later. The routine at $04:83D8 in this game already uses it and waits with
; four NOPs, so composing a 16 by 16 product from four passes is the game's own
; idiom rather than an emulation of anything.
;
;   (ah:al) * (bh:bl) = al*bl + ((ah*bl + al*bh) << 8) + ((ah*bh) << 16)
;
; Entry: DB = $00, DP = !STATE, !P_BUFFER holds al, ah, bl, bh.
; Exit:  !O_BUFFER holds the product, !S_OUT_LEN = 4.
; ---------------------------------------------------------------------------
op_multiply:
    rep #$20
    stz !S_SCRATCH+18           ; the running total, low word
    stz !S_SCRATCH+20           ; and high word
    sep #$20

    lda.w !P_BUFFER+0           ; al * bl, weighted by one
    ldx.w !P_BUFFER+2
    jsr multiply_pass
    rep #$20
    sta !S_SCRATCH+18
    sep #$20

    lda.w !P_BUFFER+1           ; ah * bl, weighted by 256
    ldx.w !P_BUFFER+2
    jsr multiply_pass
    jsr multiply_add_shifted

    lda.w !P_BUFFER+0           ; al * bh, weighted by 256
    ldx.w !P_BUFFER+3
    jsr multiply_pass
    jsr multiply_add_shifted

    lda.w !P_BUFFER+1           ; ah * bh, weighted by 65536
    ldx.w !P_BUFFER+3
    jsr multiply_pass
    rep #$20
    clc
    adc !S_SCRATCH+20
    sta !S_SCRATCH+20

    lda !S_SCRATCH+18
    sta.w !O_BUFFER+0
    lda !S_SCRATCH+20
    sta.w !O_BUFFER+2
    lda.w #!MULTIPLY_BYTES
    sta !S_OUT_LEN
    sep #$20
    rts

; Runs one 8 by 8 multiply through the CPU's own multiplier.
;
; Entry: A 8 bit holding one operand, X 16 bit holding the other in its low
;        byte. DB = $00.
; Exit:  A 16 bit holding the product. X and Y preserved, A width left at 16.
multiply_pass:
    sta $4202
    txa
    sta $4203
    nop                         ; the product needs eight cycles to settle and
    nop                         ;   these four NOPs plus the following read
    nop                         ;   cover them, which is what $04:83D8 does
    nop
    rep #$20
    lda $4216
    rts

; Adds a 16 bit partial product weighted by 256 into the 32 bit running total.
;
; Entry: A 16 bit holding the partial. DP = !STATE.
; Exit:  the total at !S_SCRATCH+18 and +20 is updated. A 8 bit on exit,
;        X and Y preserved.
multiply_add_shifted:
    pha
    and.w #$00FF
    xba                         ; the partial's low byte, moved up eight places
    clc
    adc !S_SCRATCH+18
    sta !S_SCRATCH+18
    lda.w #$0000
    adc.w #$0000                  ; carry out of the low word
    sta !S_SCRATCH+22
    pla
    xba
    and.w #$00FF                  ; the partial's high byte, moved down eight
    clc
    adc !S_SCRATCH+22
    adc !S_SCRATCH+20
    sta !S_SCRATCH+20
    sep #$20
    rts

; ---------------------------------------------------------------------------
; op_scale
;
; Command $0D. !S_LEN1 nibbles in, !S_LEN2 bytes out, resampled horizontally.
;
; The cursor steps in fixed point with sixteen fractional bits. When the input
; is no longer than the output the step is exactly one and the nibbles copy
; across in order; otherwise it is (in << 17) / ((out << 1) + 1). That
; expression is the reference implementation's and is reproduced rather than
; corrected, including the doubling and the plus one, because matching the chip
; matters more than resampling well.
;
; The cartridge only ever asks for four length pairs, $48 to $26, $48 to $32,
; $78 to $3A and $78 to $50, and only 561 times in 30,000 frames, so the divide
; below costs nothing that can be measured.
;
; Entry: DB = $00, DP = !STATE, !P_BUFFER holds ceil(!S_LEN1 / 2) bytes.
; Exit:  !O_BUFFER holds !S_LEN2 bytes, !S_OUT_LEN = !S_LEN2.
; ---------------------------------------------------------------------------
op_scale:
    rep #$20
    lda !S_LEN2
    and.w #$00FF
    sta !S_OUT_LEN
    beq .done

    lda !S_LEN1
    and.w #$00FF
    sta !S_SCRATCH+24           ; the input length, in nibbles
    lda !S_OUT_LEN
    cmp !S_SCRATCH+24
    bcc .shrink                 ; input longer than output, so derive the step

    stz !S_SCRATCH+26           ; a step of exactly one, as 16.16 fixed point
    lda.w #$0001
    sta !S_SCRATCH+28
    bra .walk

.shrink:
    jsr scale_step

.walk:
    stz !S_SCRATCH+30           ; the cursor, fractional half
    stz !S_SCRATCH+32           ; and whole half, which is a nibble index
    ldx.w #$0000                  ; X counts output bytes

.byte:
    jsr scale_nibble            ; the high pixel of this output byte
    asl
    asl
    asl
    asl
    sta !S_SCRATCH+34
    jsr scale_nibble            ; and the low one
    ora !S_SCRATCH+34
    sep #$20
    sta.w !O_BUFFER,x
    rep #$20
    inx
    cpx !S_OUT_LEN
    bne .byte

.done:
    sep #$20
    rts

; Reads the nibble the cursor points at, then advances the cursor by one step.
;
; Entry: A and index registers 16 bit, DP = !STATE, DB = $00.
; Exit:  A 16 bit with the nibble in its low four bits. Y clobbered, X kept.
scale_nibble:
    lda !S_SCRATCH+32           ; the whole part is a nibble index, so halving
    lsr                         ;   it reaches the byte that holds the nibble
    tay
    sep #$20
    lda.w !P_BUFFER,y
    rep #$20
    and.w #$00FF
    sta !S_SCRATCH+36

    lda !S_SCRATCH+32
    and.w #$0001
    bne .low
    lda !S_SCRATCH+36           ; an even index means the high nibble
    lsr
    lsr
    lsr
    lsr
    bra .advance
.low:
    lda !S_SCRATCH+36
    and.w #$000F

.advance:
    pha
    lda !S_SCRATCH+30
    clc
    adc !S_SCRATCH+26
    sta !S_SCRATCH+30
    lda !S_SCRATCH+32
    adc !S_SCRATCH+28
    sta !S_SCRATCH+32
    pla
    rts

; Computes (in << 17) / ((out << 1) + 1) by restoring long division and leaves
; the quotient as the fixed point step in !S_SCRATCH+26, low word, and +28,
; high word. The dividend needs 25 bits for the lengths the cartridge asks for,
; so a 16 bit divide will not reach.
;
; Entry: A and index registers 16 bit. !S_SCRATCH+24 holds the input length.
; Exit:  the step is in place. A, Y clobbered, X preserved.
scale_step:
    lda !S_OUT_LEN
    asl
    inc a
    sta !S_SCRATCH+38           ; the divisor, (out << 1) + 1

    lda !S_SCRATCH+24
    asl                         ; the dividend is the length shifted by 17, and
    sta !S_SCRATCH+42           ;   17 is one shift here plus the sixteen the
    stz !S_SCRATCH+40           ;   word boundary already supplies
    stz !S_SCRATCH+26
    stz !S_SCRATCH+28
    stz !S_SCRATCH+44           ; the remainder, low word
    stz !S_SCRATCH+46           ; and high word

    ldy.w #$0020                  ; thirty two quotient bits, most significant first
.bit:
    asl !S_SCRATCH+40           ; shift the dividend up into the remainder
    rol !S_SCRATCH+42
    rol !S_SCRATCH+44
    rol !S_SCRATCH+46

    asl !S_SCRATCH+26           ; and make room for this quotient bit
    rol !S_SCRATCH+28

    sec                         ; does the divisor come out of the remainder
    lda !S_SCRATCH+44
    sbc !S_SCRATCH+38
    pha
    lda !S_SCRATCH+46
    sbc.w #$0000
    bcc .keep                   ; no, so the quotient bit stays clear

    sta !S_SCRATCH+46
    pla
    sta !S_SCRATCH+44
    inc !S_SCRATCH+26           ; yes, so set it
    bra .next

.keep:
    pla

.next:
    dey
    bne .bit
    rts
