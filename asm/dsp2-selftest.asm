; Dungeon Master, software DSP-2: a cartridge that runs the routines and
; nothing else.
;
; The routines have to be shown to behave like the chip, and the honest way to
; run 65816 is on a 65816. This assembles a small complete cartridge that boots,
; walks a script of writes and reads compiled into it, feeds each through the
; same entry points the patched game will call, records every byte read back,
; and then stops. The harness runs it and dumps work RAM, and the comparison
; against the Python model happens outside.
;
; Nothing here ships. It exists so the routines are checked on a real processor
; rather than against an interpreter written for the occasion, which would only
; move the question of correctness somewhere else.
;
; The script is a byte stream, assembled at !SCRIPT:
;
;   $01 lo hi <n bytes>   feed these n bytes to the chip
;   $02 lo hi             read n bytes back and record them
;   $00                   the script is finished
;
; Results land at !RESULTS, preceded by a 16 bit count, and !DONE is set to
; $A5 once the script has run so the reader can tell a finished run from a
; hung one.

lorom

!ROUTINES   = $018000           ; the software chip, in its own bank
!SCRIPT     = $028000           ; the script, in the next one
; Results live in bank $7E rather than in the low mirror. The mirror reaches
; only $0000 to $1FFF, and the stack grows down from $1FFF, so results written
; upward from $1000 ran into it after about two hundred and fifty requests and
; took the return addresses with them.
!RESULTS    = $7E4000
!RESULT_LEN = $7E3FFC
!DONE       = $7E3FFE

; The cartridge's own working variables. They live in work RAM because a store
; to ROM does nothing: an earlier version declared them as words in the code
; bank, so the script cursor never advanced and the run read the first byte of
; the script forever.
script_cursor = $000FF0
script_temp   = $000FF2
feed_left     = $000FF4
drain_left    = $000FF6

org $008000
reset:
    sei
    clc
    xce                         ; native mode
    rep #$38                    ; A and index 16 bit, decimal clear
    ldx.w #$1FFF
    txs
    lda.w #$0000
    tcd

    sep #$20
    lda.b #$8F
    sta $2100                   ; screen off, the run needs no picture
    rep #$20

    lda.w #$0000                ; STZ has no long addressing mode
    sta.l !RESULT_LEN
    sep #$20
    lda.b #$00
    sta.l !DONE
    rep #$20

    jsl dsp_init                ; work RAM holds nothing in particular at power
                                ;   on, so the state block is put in order before
                                ;   the first byte reaches it
    rep #$30

    jsr run_script

    sep #$20
    lda.b #$A5
    sta.l !DONE
    rep #$20

.halt:
    bra .halt

; ---------------------------------------------------------------------------
; run_script
;
; Walks the script and drives the chip through the same entry points the
; patched game uses. Feeds go one byte at a time through dsp_write, which is
; what the game's own store sites do, and reads come back through dsp_read.
;
; Entry: A and index registers 16 bit, DB and DP zero.
; Exit:  every result recorded at !RESULTS with the count at !RESULT_LEN.
; ---------------------------------------------------------------------------
run_script:
    rep #$30
    lda.w #$0000
    sta.l script_cursor

.next:
    jsr script_byte
    cmp.w #$0001
    beq .feed
    cmp.w #$0002
    beq .drain
    rts

.feed:
    jsr script_word
    sta.l feed_left
.feed_byte:
    lda.l feed_left
    beq .next
    dec a
    sta.l feed_left
    jsr script_byte
    sep #$20
    jsl dsp_write
    rep #$20
    bra .feed_byte

.drain:
    jsr script_word
    sta.l drain_left
.drain_byte:
    lda.l drain_left
    beq .next
    dec a
    sta.l drain_left

    sep #$20
    jsl dsp_read
    rep #$30
    and.w #$00FF
    pha
    lda.l !RESULT_LEN
    tax
    pla
    sep #$20
    sta.l !RESULTS,x
    rep #$20
    lda.l !RESULT_LEN
    inc a
    sta.l !RESULT_LEN
    bra .drain_byte

; Reads one script byte and advances the cursor.
;
; Entry: A and index registers 16 bit.
; Exit:  A 16 bit holding the byte in its low half. X clobbered.
script_byte:
    lda.l script_cursor
    tax
    inc a
    sta.l script_cursor
    sep #$20
    lda.l !SCRIPT,x
    rep #$20
    and.w #$00FF
    rts

; Reads one little endian script word and advances the cursor by two.
;
; Entry: A and index registers 16 bit.
; Exit:  A 16 bit holding the word. X clobbered.
script_word:
    jsr script_byte
    sta.l script_temp
    jsr script_byte
    xba
    ora.l script_temp
    rts


org !ROUTINES
incsrc "dsp2-soft.asm"

org $00FFC0
    db "SOFTWARE DSP2 SELFTEST"
    db $20                      ; LoROM, slow
    db $00                      ; no coprocessor
    db $08                      ; 256 KB
    db $00                      ; no save RAM
    db $01                      ; country, so the harness picks 60 Hz
    db $00
    db $00
    dw $0000
    dw $0000

org $00FFE0
    dw $0000, $0000, $0000, $0000, $0000, $0000, $0000, $0000
org $00FFFC
    dw reset
    dw $0000
