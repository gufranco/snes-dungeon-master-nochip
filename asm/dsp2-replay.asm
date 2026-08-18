; Dungeon Master, software DSP-2: a cartridge that replays recorded traffic.
;
; The routines have to answer every request the cartridge ever made with the
; byte its chip answered, and the only way to know that is to make the requests
; and compare. This assembles a cartridge that carries a recorded stream, feeds
; it to the routines through the entry points the patched game calls, and checks
; each returned byte against the one the chip returned at that point in the run.
;
; An earlier form stored every returned byte in work RAM for a reader outside to
; compare. That capped a run at what work RAM holds, about twenty six thousand
; bytes of script, and a full trace is sixty three million records, so the run
; would have taken hours of container starts. Here the expected bytes travel in
; the script and the comparison happens on the processor, so a run reports six
; counters and the script may be as large as the cartridge.
;
; The script is a byte stream:
;
;   $01 lo hi <n bytes>   feed these n bytes to the chip
;   $02 lo hi <n bytes>   read n bytes back and check them against these
;   $00                   the script is finished
;
; It is read through a 24 bit pointer rather than an index, so it may span banks.
; LoROM exposes only $8000 to $FFFF of each, so the pointer steps from $XX:FFFF
; to $XX+1:8000 rather than to $XX+1:0000.
;
; Nothing here ships.

lorom

!ROUTINES   = $018000           ; the software chip, in its own bank
!SCRIPT     = $028000           ; where the script starts, and it may run on
                                ;   through every bank above this one

!R_STATE    = $000D00           ; this cartridge's own variables, clear of the
                                ;   software chip's block at $0900 to $0CFF
!R_PTR      = $00               ; 24 bit cursor into the script
!R_BYTE     = $04               ; the script byte just read
!R_COUNT    = $06               ; bytes left in the run being fed or checked
!R_GOT      = $08               ; the byte the routines just returned
!R_TRANS    = $0A               ; runs walked, 32 bit
!R_CMP      = $0E               ; bytes checked, 32 bit
!R_BAD      = $12               ; bytes that did not match, 32 bit
!R_FIRST    = $16               ; index of the first that did not, 32 bit
!R_FEXP     = $1A               ; what the chip returned there
!R_FGOT     = $1B               ; what the routines returned there
!R_DONE     = $1C               ; $A5 once the script has run out
!R_WORD     = $1E               ; working room for the two byte reader
!R_EXP      = $20               ; and for the byte being compared

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
    rep #$30

    pea $0000                   ; data bank zero, so the direct page below is
    plb                         ;   reached through the low work RAM mirror
    plb
    lda.w #!R_STATE
    tcd

    jsr clear_counters

    jsl dsp_init                ; work RAM holds nothing in particular at power
    rep #$30                    ;   on, so the state block is put in order first

    lda.w #!SCRIPT&$FFFF
    sta !R_PTR
    sep #$20
    lda.b #!SCRIPT>>16
    sta !R_PTR+2
    rep #$30

    jsr run_script

    sep #$20
    lda.b #$A5
    sta !R_DONE
    rep #$30

.halt:
    bra .halt

; ---------------------------------------------------------------------------
; clear_counters
;
; Work RAM is not guaranteed to hold anything at power on, so every counter is
; written before it is read.
;
; Entry: A and index registers 16 bit, DB = $00, DP = !R_STATE.
; Exit:  every counter zero. A clobbered. Widths unchanged.
; ---------------------------------------------------------------------------
clear_counters:
    stz !R_TRANS
    stz !R_TRANS+2
    stz !R_CMP
    stz !R_CMP+2
    stz !R_BAD
    stz !R_BAD+2
    stz !R_FIRST
    stz !R_FIRST+2
    stz !R_COUNT
    sep #$20
    stz !R_FEXP
    stz !R_FGOT
    stz !R_DONE
    rep #$20
    rts

; ---------------------------------------------------------------------------
; run_script
;
; Walks the script until it runs out.
;
; Entry: A and index registers 16 bit, DB = $00, DP = !R_STATE.
; Exit:  the counters hold the result. A, X, Y clobbered.
; ---------------------------------------------------------------------------
run_script:
.next:
    jsr script_byte
    cmp.w #$0001
    beq .feed
    cmp.w #$0002
    beq .check
    rts                         ; anything else, including zero, ends the run

.feed:
    jsr script_word
    sta !R_COUNT
    jsr bump_transactions
.feed_byte:
    lda !R_COUNT
    beq .next
    jsr script_byte
    sep #$20
    jsl dsp_write               ; the byte is in A eight bits wide, which is
    rep #$30                    ;   what the cartridge's own store sites pass
    dec !R_COUNT
    bra .feed_byte

.check:
    jsr script_word
    sta !R_COUNT
    jsr bump_transactions
.check_byte:
    lda !R_COUNT
    beq .next
    sep #$20
    jsl dsp_read                ; returns the byte in A with N and Z set from
    sta !R_GOT                  ;   it, which is what the port did
    rep #$30
    jsr script_byte             ; and the byte the cartridge's own chip returned
    sep #$20
    sta !R_EXP
    lda !R_GOT
    cmp !R_EXP
    beq .matched
    jsr note_mismatch
.matched:
    rep #$30
    jsr bump_compared
    dec !R_COUNT
    bra .check_byte

; ---------------------------------------------------------------------------
; note_mismatch
;
; Counts a byte the routines got wrong, and keeps the first one seen so a reader
; has somewhere to start rather than only a total.
;
; Entry: A 8 bit, DB = $00, DP = !R_STATE, !R_EXP and !R_GOT set.
; Exit:  A clobbered. Widths left at A 8 bit and index 16 bit.
; ---------------------------------------------------------------------------
note_mismatch:
    rep #$30
    lda !R_BAD
    ora !R_BAD+2
    bne .already                ; only the first one is kept

    lda !R_CMP
    sta !R_FIRST
    lda !R_CMP+2
    sta !R_FIRST+2
    sep #$20
    lda !R_EXP
    sta !R_FEXP
    lda !R_GOT
    sta !R_FGOT
    rep #$30

.already:
    lda !R_BAD
    inc a
    sta !R_BAD
    bne .done
    lda !R_BAD+2
    inc a
    sta !R_BAD+2
.done:
    sep #$20
    rts

; ---------------------------------------------------------------------------
; bump_compared
;
; A 32 bit counter, carried by hand because the accumulator is sixteen bits.
;
; Entry: A and index registers 16 bit, DP = !R_STATE.
; Exit:  A clobbered.
; ---------------------------------------------------------------------------
bump_compared:
    lda !R_CMP
    inc a
    sta !R_CMP
    bne +
    lda !R_CMP+2
    inc a
    sta !R_CMP+2
+   rts

; ---------------------------------------------------------------------------
; bump_transactions
;
; The same, for the runs the script declares, and it keeps the accumulator so
; the caller's count survives.
;
; Entry: A and index registers 16 bit, DP = !R_STATE.
; Exit:  A unchanged.
; ---------------------------------------------------------------------------
bump_transactions:
    pha
    lda !R_TRANS
    inc a
    sta !R_TRANS
    bne +
    lda !R_TRANS+2
    inc a
    sta !R_TRANS+2
+   pla
    rts

; ---------------------------------------------------------------------------
; script_byte
;
; Reads the next byte of the script and advances the cursor. LoROM exposes only
; the upper half of each bank, so the cursor steps from $XX:FFFF to $XX+1:8000.
;
; Entry: A and index registers 16 bit, DP = !R_STATE.
; Exit:  A 16 bit with the byte in its low half. Y clobbered.
; ---------------------------------------------------------------------------
script_byte:
    ldy.w #$0000
    sep #$20
    lda [!R_PTR],y
    sta !R_BYTE
    rep #$30

    lda !R_PTR
    inc a
    sta !R_PTR
    bne .same_bank
    lda.w #$8000                ; the low half of a bank is not cartridge
    sta !R_PTR
    sep #$20
    lda !R_PTR+2
    inc a
    sta !R_PTR+2
    rep #$30

.same_bank:
    sep #$20
    lda !R_BYTE
    rep #$30
    and.w #$00FF
    rts

; ---------------------------------------------------------------------------
; script_word
;
; Reads the next little endian pair and advances the cursor by two.
;
; Entry: A and index registers 16 bit, DP = !R_STATE.
; Exit:  A 16 bit holding the word. Y clobbered.
; ---------------------------------------------------------------------------
script_word:
    jsr script_byte
    sta !R_WORD
    jsr script_byte
    xba
    ora !R_WORD
    rts

org !ROUTINES
incsrc "dsp2-soft.asm"

org $00FFC0
    db "SOFTWARE DSP2 REPLAY  "
    db $20
    db $00
    db $0C
    db $00
    db $01
    db $00
    db $00
    dw $0000
    dw $0000
org $00FFFC
    dw reset
    dw $0000
