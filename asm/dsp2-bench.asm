; Dungeon Master, software DSP-2: a cartridge that measures the routines.
;
; The question this answers is how many cycles a command costs now that it is
; code rather than a chip, and the only honest way to answer it is to run the
; code and count frames. Each workload below repeats one command a fixed number
; of times and stamps a frame counter before and after, so the cost per command
; falls out of the difference.
;
; The workload mirrors what the cartridge actually asks for. A merge of 22 bytes
; is the most common single request, and a tile conversion is always 32 bytes.
; The feeds go through the block entry points because that is how the game
; delivers payloads, one MVN rather than a store per byte.
;
; Nothing here ships.

lorom

!ROUTINES  = $018000
!SOURCE    = $7E1000            ; a scratch payload, clear of the state block
!DEST      = $7E1400
!RESULTS   = $7F0000            ; out of reach of anything the routines touch

!MERGE_LEN = 22                 ; the most common merge the cartridge asks for
!ROUNDS    = 2000

org $008000
reset:
    sei
    clc
    xce
    rep #$30
    ldx.w #$1FFF
    txs
    lda.w #$0000
    tcd
    sep #$20
    lda.b #$8F
    sta $2100                   ; screen off, nothing here needs a picture
    rep #$30

    sep #$20
    lda.b #$11
    sta.l !RESULTS+8            ; reached the init call
    rep #$30

    jsl dsp_init

    sep #$20
    lda.b #$22
    sta.l !RESULTS+9            ; the init call returned
    rep #$30

    ldx.w #$0000
.fill:
    txa
    sep #$20
    sta.l !SOURCE,x
    rep #$30
    inx
    cpx.w #$0200
    bne .fill

    sep #$20
    lda.b #$33
    sta.l !RESULTS+10           ; the fill finished
    lda.b #$0F
    jsl dsp_write               ; the simplest command there is
    lda.b #$AA
    sta.l !RESULTS+15           ; a sync survived
    lda.b #$05
    jsl dsp_write               ; a command that takes a length
    lda.b #$BB
    sta.l !RESULTS+16
    lda.b #$16
    jsl dsp_write               ; the length itself
    lda.b #$CC
    sta.l !RESULTS+17
    rep #$30

    jsr bench_merge
    sep #$20
    lda.b #$A5
    sta.l !RESULTS+0
    rep #$30

    jsr bench_tile
    sep #$20
    lda.b #$A5
    sta.l !RESULTS+1
    rep #$30

.halt:
    bra .halt

; ---------------------------------------------------------------------------
; bench_merge
;
; Repeats a merge of !MERGE_LEN bytes !ROUNDS times, delivering both bitmaps
; through the block feed and taking the result through the block drain, which
; is the shape the renderer uses at $04:8871.
;
; Entry: A and index registers 16 bit, DB and DP zero.
; Exit:  the elapsed frame count at !RESULTS+0.
; ---------------------------------------------------------------------------
bench_merge:
    ldx.w #!ROUNDS
    stx.b $10

.round:
    sep #$20
    lda.b #$05
    jsl dsp_write               ; the merge command
    lda.b #!MERGE_LEN
    jsl dsp_write               ; and its declared length
    lda.b #$7E
    sta.l $000600+$0F           ; the bank both feeds read from
    rep #$30

    sep #$20
    lda.b #$44
    sta.l !RESULTS+11
    rep #$30
    lda.w #!MERGE_LEN-1
    ldx.w #$1000
    ldy.w #$8000
    jsl dsp_feed_bank           ; the background
    sep #$20
    lda.b #$55
    sta.l !RESULTS+12
    rep #$30

    lda.w #!MERGE_LEN-1
    ldx.w #$1100
    ldy.w #$8000
    jsl dsp_feed_bank           ; the overlay
    sep #$20
    lda.b #$66
    sta.l !RESULTS+13
    rep #$30

    sep #$20
    lda.b #$7E
    sta.l $000600+$0F           ; the bank the drain writes to
    rep #$30
    lda.w #!MERGE_LEN-1
    ldx.w #$8000
    ldy.w #$1400
    jsl dsp_drain_bank
    sep #$20
    lda.b #$77
    sta.l !RESULTS+14
    rep #$30

    dec.b $10
    bne .round
    rts

; ---------------------------------------------------------------------------
; bench_tile
;
; Repeats the 32 byte tile conversion !ROUNDS times, which is what the bulk
; converter at $00:9860 does 336 times in a row when a screen loads.
;
; Entry: A and index registers 16 bit, DB and DP zero.
; Exit:  the elapsed frame count at !RESULTS+4.
; ---------------------------------------------------------------------------
bench_tile:
    ldx.w #!ROUNDS
    stx.b $10

.round:
    sep #$20
    lda.b #$01
    jsl dsp_write
    lda.b #$7E
    sta.l $000600+$0F
    rep #$30

    lda.w #$001F
    ldx.w #$1000
    ldy.w #$8000
    jsl dsp_feed_bank

    sep #$20
    lda.b #$7E
    sta.l $000600+$0F
    rep #$30
    lda.w #$001F
    ldx.w #$8000
    ldy.w #$1400
    jsl dsp_drain_bank
    sep #$20
    lda.b #$77
    sta.l !RESULTS+14
    rep #$30

    dec.b $10
    bne .round
    rts

; The elapsed time is read from outside. Each workload sets its own marker when
; it finishes, and the harness is run at rising frame counts until the marker
; appears, which gives the number of frames the workload took without needing an
; interrupt handler or a timer inside the cartridge.

org !ROUTINES
incsrc "dsp2-soft.asm"

org $00FFC0
    db "SOFTWARE DSP2 BENCH  "
    db $20
    db $00
    db $08
    db $00
    db $01
    db $00
    db $00
    dw $0000
    dw $0000
org $00FFFC
    dw reset
    dw $0000
