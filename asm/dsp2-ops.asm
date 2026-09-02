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
; The conversion is always eight rows and never any other number, so the rows
; are written out rather than looped. A loop over eight passes spent an index
; register on walking the input, a direct page word on the output cursor, and a
; compare and a branch per row, all of which are constants once the count cannot
; vary: 28 cycles a row, 224 for a conversion, for eight repetitions of one
; macro. The cartridge asks for a conversion 1,031,195 times across three
; recorded tours, which is where the exchange goes from cheap to worth unrolling.
; The four bytes of a row are gathered in the output itself rather than in a
; pair of scratch words that are copied there at the end. Planes 0 and 1 are
; adjacent in the output, so one sixteen bit access carries both, and planes 2
; and 3 sit sixteen bytes along. The first byte stores, so nothing has to be
; cleared beforehand, and the other three merge in place with TSB, which is one
; instruction where a load, an or and a store were three. That removes the two
; copies each row used to end with and two cycles from each of its six merges.
; A row's four bytes are read where the caller left them, through the same
; pointer a merge uses, so the payload does not have to be copied into the
; parameter buffer first. Reaching a byte costs four cycles more that way and
; the copy charged seven, so a conversion comes out ninety six cycles ahead.
;
; The reads are sixteen bit, which is what the tables and the accumulators want,
; and each takes the low half. That means every read but the last also touches
; the byte after it, and the last one would touch the byte after the payload.
; Inside the buffer that was harmless; in a caller's memory it is a read of a
; byte nobody offered, so the final one is taken eight bits wide.
macro tile_byte(output, table_offset, merge, narrow)
if <narrow> == 1
    sep #$20                    ; the payload's last byte, read without reaching
    lda [!S_PARAM_PTR],y        ;   past what the transfer delivered
    rep #$20
else
    lda [!S_PARAM_PTR],y
endif
    and.w #$00FF
    asl                         ; the tables hold words, so the index is doubled
    tax
    iny
    lda.l tile_lo+<table_offset>,x
if <merge> == 1
    tsb.w !O_BUFFER+<output>+0
else
    sta.w !O_BUFFER+<output>+0  ; planes 0 and 1, in the order the output wants
endif
    lda.l tile_hi+<table_offset>,x
if <merge> == 1
    tsb.w !O_BUFFER+<output>+16
else
    sta.w !O_BUFFER+<output>+16 ; planes 2 and 3
endif
endmacro

macro tile_row(output, last)
    %tile_byte(<output>, 0, 0, 0)
    %tile_byte(<output>, 512, 1, 0)
    %tile_byte(<output>, 1024, 1, 0)
    %tile_byte(<output>, 1536, 1, <last>)
endmacro

op_tile:
    rep #$20                    ; sixteen bit for the whole conversion: every
                                ;   table entry is a word and so is every
                                ;   accumulator, and switching per row cost more
                                ;   than the switching saved

    ldy.w #$0000                ; the payload is walked once, forward
    %tile_row(0, 0)
    %tile_row(2, 0)
    %tile_row(4, 0)
    %tile_row(6, 0)
    %tile_row(8, 0)
    %tile_row(10, 0)
    %tile_row(12, 0)
    %tile_row(14, 1)

    lda.w #!TILE_BYTES
    sta !S_OUT_LEN
    sep #$20
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
    cmp !S_TABLE_FOR            ; the cartridge sets this 8,852 times in a tour
    beq .unchanged              ;   and changes it three times, so the tables
    sta !S_TRANSPARENT          ;   almost always stand and this almost always
    asl                         ;   ends here
    asl
    asl
    asl
    sta !S_SCRATCH+16
    jsr build_merge
.unchanged:
    rts

; ---------------------------------------------------------------------------
; build_merge
;
; Fills the two tables a merge reads, for the colour now in !S_TRANSPARENT.
;
; A merge asks the same question of every byte: for each of its two nibbles,
; does the overlay hold the transparent colour, and if it does let the
; background through. The answer depends only on the overlay byte, so it can be
; worked out once for all 256 of them and read back rather than recomputed two
; million times a tour.
;
; keep holds what the overlay contributes, its transparent nibbles cleared.
; mask holds $F where a nibble was transparent, so the background passes through
; exactly there. A merged byte is then keep or background and mask, which is
; three reads and no branches.
;
; Entry: DB = $00, DP = !STATE, A 8 bit, index 16 bit, !S_SCRATCH+16 holding the
;        transparent colour moved into the high nibble.
; Exit:  both tables filled, !S_TABLE_FOR recording what they were built for.
;        A, X clobbered. Y preserved.
; ---------------------------------------------------------------------------
build_merge:
    lda !S_TRANSPARENT
    sta !S_TABLE_FOR
    ldx.w #$0000

.entry:
    txa                         ; the byte this entry answers for
    and.b #$F0
    cmp !S_SCRATCH+16
    bne .high_opaque
    stz !S_SCRATCH+20           ; transparent, so the overlay keeps nothing here
    lda.b #$F0                  ;   and the background comes through all of it
    bra .high_done
.high_opaque:
    sta !S_SCRATCH+20
    lda.b #$00
.high_done:
    sta !S_SCRATCH+21

    txa
    and.b #$0F
    cmp !S_TRANSPARENT
    bne .low_opaque
    lda !S_SCRATCH+21
    ora.b #$0F
    sta !S_SCRATCH+21
    bra .low_done
.low_opaque:
    ora !S_SCRATCH+20
    sta !S_SCRATCH+20
.low_done:

    lda !S_SCRATCH+20
    sta.w !MERGE_KEEP,x
    lda !S_SCRATCH+21
    sta.w !MERGE_MASK,x

    inx
    cpx.w #$0100
    bne .entry
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
macro merge_byte()
    lda [!S_OVERLAY_PTR],y      ; the overlay byte decides for both its nibbles
    tax
    lda.w !MERGE_MASK,x         ; where it was transparent, and only there
    and [!S_PARAM_PTR],y        ;   the background shows through
    ora.w !MERGE_KEEP,x         ; everywhere else the overlay stands
    sta.w !O_BUFFER,y
endmacro

op_merge:
    lda !S_LEN1
    beq .empty

    rep #$20
    and.w #$00FF
    sta !S_OUT_LEN
    clc                         ; the overlay follows the background, so its base
    adc !S_PARAM_PTR            ;   is one length along whatever the payload is
    sta !S_OVERLAY_PTR          ;   being read from
    sep #$20
    lda !S_PARAM_PTR+2          ; the carry out of that add belongs to the bank,
    adc.b #$00                  ;   because a caller's buffer can sit anywhere
    sta !S_OVERLAY_PTR+2
    rep #$20

    ldy !S_OUT_LEN              ; the walk runs down rather than up, so its end
    dey                         ;   is the sign bit of the index and no compare
    lda !S_OUT_LEN              ;   against the length is needed. Every byte is
    lsr                         ;   decided by its own two nibbles and nothing
                                ;   else, so the order they are visited in does
                                ;   not reach the result, and two of them can
                                ;   share one test of the index. The carry out of
                                ;   this shift is the length's low bit, which
                                ;   says whether the pairs start one byte in.
    lda.w #$0000                ; the high byte of the accumulator is cleared
    sep #$20                    ;   once so that every later transfer to X
                                ;   carries the overlay byte alone
    bcc .pair
    %merge_byte()               ; an odd length takes its first byte alone, so
    dey                         ;   what is left of it divides in two
    bmi .done

.pair:
    %merge_byte()
    dey
    %merge_byte()
    dey
    bpl .pair
.done:
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
    dex                         ; the output index runs down to its own sign
    bpl .byte                   ;   bit, which the input index reaching the
    rts                         ;   length would say no sooner and no cheaper

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

    lda.w !P_BUFFER+0           ; the four passes are unsigned, and the part
    bpl .a_positive             ;   multiplies signed, so each negative operand
    lda !S_SCRATCH+20           ;   costs the other one out of the high word
    sec
    sbc.w !P_BUFFER+2
    sta !S_SCRATCH+20
.a_positive:
    lda.w !P_BUFFER+2
    bpl .b_positive
    lda !S_SCRATCH+20
    sec
    sbc.w !P_BUFFER+0
    sta !S_SCRATCH+20
.b_positive:

    lda !S_SCRATCH+18           ; the part's multiplier leaves the product
    pha                         ;   doubled across two registers and the code
    and.w #$7FFF                ;   shifts each back arithmetically, so bit 14
    sta.w !O_BUFFER+0           ;   of the low word reappears as bit 15
    pla
    and.w #$4000
    asl a
    ora.w !O_BUFFER+0
    sta.w !O_BUFFER+0

    lda !S_SCRATCH+20           ; and the high word is masked before it is sent
    and.w #$7FFF
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
; Both declared lengths count nibbles, not bytes. That is measurable rather than
; assumed: a recorded scale writes 63 bytes and then reads 40, and the 63 are a
; command, two lengths and ceil(120 / 2) of payload, so the 40 read back are
; ceil(80 / 2). Reading the second length as a byte count produced twice as many
; bytes as the chip returns, and derived the resampling step from the wrong
; figure as well, so every scaled row was wrong past its first few pixels.
;
; Exit:  !O_BUFFER holds ceil(!S_LEN2 / 2) bytes, !S_OUT_LEN the same count.
; ---------------------------------------------------------------------------
op_scale:
    rep #$20
    lda !S_LEN2
    and.w #$00FF
    sta !S_SCRATCH+40           ; the output length in nibbles, which is what the
                                ;   resampling step is derived from
    inc a
    lsr
    sta !S_OUT_LEN              ; and in bytes, which is what the caller drains
    beq .done

    lda !S_LEN1
    and.w #$00FF
    sta !S_SCRATCH+24           ; the input length, in nibbles
    lda !S_SCRATCH+40
    cmp !S_SCRATCH+24
    bcc .shrink                 ; input longer than output, so derive the step

    stz !S_SCRATCH+26           ; a step of exactly one, as 16.16 fixed point
    lda.w #$0001
    sta !S_SCRATCH+28
    bra .walk

.shrink:
    lda !S_LEN1                 ; both declared lengths as one word, which is the
    cmp !S_STEP_FOR             ;   whole of what the step depends on
    bne .derive

    lda !S_STEP                 ; the same pair as last time, so the divide that
    sta !S_SCRATCH+26           ;   answers it has already been done
    lda !S_STEP+2
    sta !S_SCRATCH+28
    bra .walk

.derive:
    lda !S_LEN1
    sta !S_STEP_FOR
    jsr scale_step
    lda !S_SCRATCH+26
    sta !S_STEP
    lda !S_SCRATCH+28
    sta !S_STEP+2

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
    lda !S_SCRATCH+40           ; nibbles, because both declared lengths are
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
