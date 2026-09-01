; Dungeon Master, software DSP-2: the command and parameter state machine, and
; the entry points that stand in for the ways the cartridge reached the chip.
;
; The retail cartridge talks to the DSP-2 four ways, and every one is replaced
; here by something the same size or smaller, so nothing moves:
;
;   STA $3F8000     four bytes   becomes JSL dsp_write   four bytes
;   LDA $3F8000     four bytes   becomes JSL dsp_read    four bytes
;   LDA $3FC000     four bytes   becomes LDA #$00 : NOP : NOP
;   MVN $3F,$7E     three bytes  becomes JSR to a stub in the same bank
;   JSR $0084       three bytes  becomes JSR to a stub in the same bank
;
; The last two matter because a block move is a loop inside one instruction and
; cannot become a JSL, which is four bytes against its three. A JSR to a stub in
; the caller's own bank is three bytes, and the stub is free to be long.
;
; Every entry point restores A, X, Y, DB, DP and the processor status exactly as
; the instruction it replaced would have left them, because the call sites were
; written against a memory mapped port and assume nothing else changed.

incsrc "dsp2-state.asm"

; ---------------------------------------------------------------------------
; dsp_init
;
; Puts the state block into a known condition.
;
; Work RAM is not guaranteed to hold any particular value at power on, so every
; field the state machine reads has to be written before it is read. Without
; this the first byte the game sends could arrive with the stage byte holding
; whatever was in that address, be taken for a parameter rather than a command,
; and leave the chip out of step for the rest of the run.
;
; The boot code writes the sync command six times at $00:801E. Sync produces
; nothing, so the first of the six becomes this call and the other five stay as
; writes. A JSL is four bytes and so is the store it replaces, so nothing moves.
;
; Entry: any state.
; Exit:  everything restored. The state block is idle with no output pending.
; ---------------------------------------------------------------------------
dsp_init:
    php
    rep #$30
    phb
    phd
    pha
    phx
    phy

    jsr enter
    sep #$20
    stz !S_STAGE
    stz !S_COMMAND
    stz !S_LEN1
    stz !S_LEN2
    stz !S_WANT_LEN
    stz !S_TRANSPARENT
    lda.b #$FF                  ; no colour, so the first transparent command
    sta !S_TABLE_FOR            ;   builds the merge tables rather than trusting
                                ;   whatever those two pages happen to hold. A
                                ;   nibble is never $FF, so nothing matches this
    stz !S_INBYTE
    stz !S_XFER_BANK
    rep #$20
    stz !S_WANT_PARAM
    stz !S_PARAM_INDEX
    stz !S_OUT_LEN
    stz !S_OUT_INDEX
    stz !S_XFER_LEFT
    stz !S_XFER_TOTAL
    stz !S_SCRATCH+16           ; the transparent colour in its high nibble form,
                                ;   which the table builder compares against

    lda.w #$FFFF                ; no resampling step held yet. A pair of equal
    sta !S_STEP_FOR             ;   lengths never reaches the code that reads
                                ;   this, so it cannot be mistaken for one

    ldx.w #$0000                ; the parameter buffer is cleared as well. A
.clear:                         ;   scale reads past the payload it was handed,
    stz.w !P_BUFFER,x           ;   by design, and takes whatever the last
    inx                         ;   command left there, so what it finds has to
    inx                         ;   be decided rather than inherited from work
    cpx.w #$0200                ;   RAM. The chip's own parameter RAM is equally
    bne .clear                  ;   undefined at power on; this makes ours not.

    rep #$30                    ; the widths are put back before the pulls. The
                                ;   pushes were made with both sixteen bit, and
                                ;   an operation leaves the accumulator eight, so
                                ;   without this the pull takes one byte where
                                ;   two went on and every later pull is displaced
    ply
    plx
    pla
    pld
    plb
    plp
    rtl

; ---------------------------------------------------------------------------
; with_context
;
; Runs a routine that may reach a buffer or finish an operation, with the data
; bank pointed at bank zero and both index registers put back afterwards.
;
; The widths are set back to sixteen before the pulls. The pushes were made with
; both sixteen bit, and an operation leaves the accumulator eight, so without it
; the pull takes one byte where two went on and every later pull is displaced.
; ---------------------------------------------------------------------------
macro with_context(routine)
    rep #$30
    phb
    phx
    phy
    pea $0000
    plb
    plb
    jsr <routine>
    rep #$30
    ply
    plx
    plb
endmacro

; ---------------------------------------------------------------------------
; dsp_write
;
; Stands in for a single byte written to the data port.
;
; A command byte is the majority of what arrives here: 3,336,773 of the
; 5,433,289 single byte writes across three recorded tours, because a payload
; travels by block move and only the command and its declared lengths come one
; at a time. A command byte decides fields in the state block and nothing else.
; It reaches no buffer, so it needs neither the data bank pointed at bank zero
; nor the index registers saved, and it can never finish a payload, so it can
; never run an operation. That path therefore takes none of it.
;
; Entry: A 8 bit holding the byte. Every register and flag as the caller had it.
; Exit:  everything restored, including the M and X widths and the carry.
; ---------------------------------------------------------------------------
dsp_write:
    php
    sep #$20
    sta.l !STATE+!S_INBYTE      ; park the byte before the accumulator is saved
    rep #$30
    phd
    pha
    lda.w #!STATE
    tcd

    sep #$20
    lda !S_STAGE
    cmp.b #!STAGE_IDLE
    beq .command
    cmp.b #!STAGE_LENGTH
    beq .length

    %with_context(write_byte)   ; a payload byte, which reaches a buffer and can
    bra .leave                  ;   finish an operation

.length:
    jsr length_byte             ; a declared length, which reaches nothing but
    bcc .leave                  ;   the block and so needs none of the above

    %with_context(run)          ; unless it declared nothing, which completes the
    bra .leave                  ;   payload before any of it arrives

.command:
    rep #$20
    jsr command_byte

.leave:
    rep #$30
    pla
    pld
    plp
    rtl

; ---------------------------------------------------------------------------
; dsp_read
;
; Stands in for a single byte read from the data port.
;
; A read from the retail port set N and Z from the byte it returned, and callers
; branch on that, so the flags are rebuilt from the byte rather than restored.
;
; Entry: every register and flag as the caller had it, A width 8 bit.
; Exit:  A 8 bit holding the byte, N and Z set from it, everything else restored.
; ---------------------------------------------------------------------------
dsp_read:
    php
    rep #$30
    phb
    phd
    phx
    phy

    jsr enter
    jsr read_byte               ; leaves the byte in the low byte of A
    sta.l !STATE+!S_INBYTE

    rep #$30                    ; as above: both widths back before the pulls
    ply
    plx
    pld
    plb
    plp
    sep #$20
    lda.l !STATE+!S_INBYTE      ; the load sets N and Z the way the port did
    rtl

; ---------------------------------------------------------------------------
; enter
;
; Points DB at bank $00 and DP at the state block, so the rest of this file can
; use absolute and direct page addressing instead of long addressing.
;
; Entry: A and index registers 16 bit.
; Exit:  DB = $00, DP = !STATE. A clobbered.
; ---------------------------------------------------------------------------
enter:
    pea $0000
    plb
    plb
    lda.w #!STATE
    tcd
    rts

; ---------------------------------------------------------------------------
; write_byte
;
; One step of the chip's command and parameter state machine, taking the byte
; from !S_INBYTE. This mirrors DSP2SetByte in snes9x dsp2.cpp: the first byte of
; a transaction is the command, three commands then take one or two declared
; lengths, and the payload follows.
;
; Entry: DB = $00, DP = !STATE, A and index registers 16 bit.
; Exit:  A, X, Y clobbered. Widths left at A 16 bit, index 16 bit.
; ---------------------------------------------------------------------------
write_byte:
    sep #$20                    ; A 8 bit for every comparison in this routine,
    rep #$10                    ;   and the index registers 16 bit for the buffer
    lda !S_STAGE
    cmp.b #!STAGE_LENGTH
    beq .length
    cmp.b #!STAGE_PARAM
    beq .parameter
    rep #$20                    ; idle, or a stage byte holding anything else,
    jmp command_byte            ;   which is not a state this machine ever wrote
                                ;   and is treated as idle rather than trusted

.parameter:
    ldx !S_PARAM_INDEX
    lda !S_INBYTE
    sta.w !P_BUFFER,x
    inx
    stx !S_PARAM_INDEX
    rep #$20
    lda !S_WANT_PARAM
    dec a
    sta !S_WANT_PARAM
    bne .waiting
    jmp run
.waiting:
    rts

.length:
    jsr length_byte             ; one implementation, whichever way the byte
    bcc +                       ;   arrived: a single store or a block move that
    jmp run                     ;   split across the boundary
+   rts

; ---------------------------------------------------------------------------
; length_byte
;
; A declared length, which says how much payload has to arrive before the
; command can run.
;
; Its own routine for the reason command_byte is: it reads no buffer and writes
; none, so the data bank can be anything and neither index register is touched,
; and a caller is free to save less. The one case that does need the full
; context is a length of zero, where the payload is complete before any of it
; arrives and the operation runs at once. That is reported through the carry
; rather than run here, so the saving stays off the path that never needs it.
;
; Entry: DP = !STATE, A 8 bit, index registers 16 bit.
; Exit:  carry set when the operation still has to run. A clobbered, X and Y
;        untouched. Widths left at A 16 bit, index 16 bit.
; ---------------------------------------------------------------------------
length_byte:
    lda !S_WANT_LEN
    cmp.b #$02
    bne .second
    lda !S_INBYTE               ; the scale command declares its input length
    sta !S_LEN1                 ;   first and its output length second
    lda.b #$01
    sta !S_WANT_LEN
    rep #$20
    clc
    rts

.second:
    lda !S_INBYTE
    sta !S_SCRATCH              ; park the byte, because the command has to be
    lda !S_COMMAND              ;   read into the same accumulator to test it
    cmp.b #!CMD_SCALE
    beq .scale
    cmp.b #!CMD_MIRROR          ; how much payload the length implies is decided
    beq .mirror                 ;   here, where the command has just been read,
                                ;   rather than in a routine that reads it again
                                ;   and asks the same two questions over
    lda !S_SCRATCH              ; a merge, which takes two bitmaps
    sta !S_LEN1
    stz !S_WANT_LEN
    rep #$20
    and.w #$00FF
    asl
    bra .sized

.mirror:
    lda !S_SCRATCH
    sta !S_LEN1
    stz !S_WANT_LEN
    rep #$20
    and.w #$00FF
    bra .sized

.scale:
    lda !S_SCRATCH              ; the second declared length is the output's, and
    sta !S_LEN2                 ;   the payload is sized from the first
    stz !S_WANT_LEN
    lda !S_LEN1
    rep #$20
    and.w #$00FF
    inc a
    lsr

.sized:
    sta !S_WANT_PARAM
    ora.w #$0000
    beq .empty
    sep #$20
    lda.b #!STAGE_PARAM
    sta !S_STAGE
    rep #$20
    clc
    rts
.empty:
    sec
    rts

; ---------------------------------------------------------------------------
; command_byte
;
; The first byte of a transaction, which names the operation and says what has
; to arrive before it can run.
;
; This is its own routine rather than a branch inside the state machine because
; it is the one step that touches nothing but the state block. It reads no
; buffer, so the data bank can be anything, and it can never complete a payload,
; so it can never run an operation. Its caller is free to save less.
;
; Entry: DP = !STATE, A and index registers 16 bit.
; Exit:  A clobbered. Widths left at A 16 bit, index 16 bit.
; ---------------------------------------------------------------------------
command_byte:
    sep #$20
    lda !S_INBYTE
    sta !S_COMMAND
    rep #$20
    stz !S_PARAM_INDEX          ; the output is not touched here. A command byte
    lda.w #(!P_BUFFER&$FFFF)    ;   arriving does not spend the previous result,
    sta !S_PARAM_PTR            ;   and reads between the command and its last
    sep #$20                    ;   parameter still drain what was already
    stz !S_PARAM_PTR+2          ;   waiting. The cursor rewinds when the command
                                ;   runs, which is where the chip rewinds it.
                                ; The payload is read out of the buffer it is
                                ;   collected in unless a transfer says the whole
                                ;   of it arrived somewhere else at once.

    lda !S_COMMAND              ; tested in the order the cartridge sends them,
    cmp.b #!CMD_MERGE           ;   measured over three thousand frames of play:
    beq .takes_one_length       ;   a merge 23 times a frame, a conversion 10,
    cmp.b #!CMD_TILE            ;   a sync under two, and the remaining four
    beq .tile                   ;   under one between them. A mirror never
    cmp.b #!CMD_MIRROR          ;   appears at all in that span
    beq .takes_one_length
    cmp.b #!CMD_MULTIPLY
    beq .multiply
    cmp.b #!CMD_TRANSPARENT
    beq .transparent
    cmp.b #!CMD_SCALE
    beq .takes_two_lengths

    rep #$20                    ; a sync, or a command this chip does not know
    stz !S_WANT_PARAM
    bra .nothing_to_collect

.tile:                          ; the three whose payload never varies. Each is
    lda.b #!TILE_BYTES          ;   its own branch rather than a second pass over
    bra .collect                ;   the command byte in a routine of its own
.multiply:
    lda.b #!MULTIPLY_BYTES
    bra .collect
.transparent:
    lda.b #$01

.collect:
    rep #$20
    and.w #$00FF
    sta !S_WANT_PARAM
    sep #$20
    lda.b #!STAGE_PARAM
    sta !S_STAGE
    rep #$20
    rts

.nothing_to_collect:
    sep #$20
    stz !S_STAGE
    rep #$20
    stz !S_OUT_INDEX            ; which still rewinds the read cursor, so a
                                ;   result read only in part can be read again
    rts

.takes_one_length:
    lda.b #$01
    sta !S_WANT_LEN
    lda.b #!STAGE_LENGTH
    sta !S_STAGE
    rep #$20
    rts

.takes_two_lengths:
    lda.b #$02
    sta !S_WANT_LEN
    lda.b #!STAGE_LENGTH
    sta !S_STAGE
    rep #$20
    rts

; ---------------------------------------------------------------------------
; run
;
; Dispatches a finished transaction, then returns the chip to idle with the
; output cursor at the start of whatever it produced.
;
; Entry: DB = $00, DP = !STATE.
; Exit:  A, X, Y clobbered. Widths left at A 8 bit, index 16 bit.
; ---------------------------------------------------------------------------
run:
    sep #$20                    ; the index registers are already sixteen bit at
    stz !S_STAGE                ;   all five places this is reached from, so
                                ;   widening them again bought nothing
    rep #$20
    stz !S_OUT_INDEX            ; the read cursor rewinds for every command, but
                                ;   the count does not clear. A command that
                                ;   produces nothing leaves the previous result
                                ;   readable again from its start, which is what
                                ;   the chip does. Only the five commands that
                                ;   produce something set the count, each at its
                                ;   own end.
    sep #$20

    lda !S_COMMAND              ; in the same order as the one that decides what
    cmp.b #!CMD_MERGE           ;   a command collects, and for the same reason:
    bne +                       ;   every test a merge walks past is paid twenty
    jmp op_merge                ;   three times a frame and a conversion's ten
+   cmp.b #!CMD_TILE
    bne +
    jmp op_tile
+   cmp.b #!CMD_MULTIPLY
    bne +
    jmp op_multiply
+   cmp.b #!CMD_TRANSPARENT
    bne +
    jmp op_transparent
+   cmp.b #!CMD_SCALE
    bne +
    jmp op_scale
+   cmp.b #!CMD_MIRROR
    bne +
    jmp op_mirror
+   rts                         ; a command this chip does not know produces
                                ;   nothing, as the reference does

; ---------------------------------------------------------------------------
; read_byte
;
; Hands back the next byte of the finished output, or the idle byte once the
; output is spent, which is what the port did.
;
; Entry: DB = $00, DP = !STATE, A and index registers 16 bit.
; Exit:  A 16 bit with the byte in its low half. X clobbered.
; ---------------------------------------------------------------------------
read_byte:
    lda !S_OUT_INDEX
    cmp !S_OUT_LEN
    bcc .have_one
    lda.w #!IDLE_BYTE
    rts

.have_one:
    tax
    inc a
    sta !S_OUT_INDEX
    sep #$20
    lda.w !O_BUFFER,x
    rep #$20
    and #$00FF
    rts

incsrc "dsp2-ops.asm"
incsrc "dsp2-block.asm"

; The tables the operations read are included here rather than by each cartridge
; that assembles this file. Four of the five harnesses had been assembling
; without them since the tables were added, and every one failed at link time
; with a missing label rather than producing something wrong, which is the good
; failure. Including them beside the code that reads them makes the pair
; impossible to separate.
incsrc "dsp2-tables.asm"
