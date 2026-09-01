; Dungeon Master, software DSP-2: the state block.
;
; The chip is replaced by code, so the command and parameter state machine it
; kept internally has to live somewhere the CPU can reach. This block holds it.
;
; Placement is measured rather than guessed, and the first measurement was
; wrong. Three seeded tours recorded every read and every write of work RAM
; through the emulator's byte access path and reported 37,245 bytes that none of
; them touched. That path does not see a DMA transfer, and this game clears and
; fills work RAM by DMA, so whole regions the game uses constantly looked idle.
; The block was placed at $7E:0600 on the strength of it, on top of a live table,
; and the converted image drew a blank screen.
;
; The instrument now compares the whole of work RAM against the previous frame
; after every frame, which sees a write whatever path made it. Measured that way
; a 30,000 frame tour leaves 4,568 bytes untouched in 87 runs, and only one of
; them is usable: 4,078 bytes at $7E:083E.
;
; What follows uses $7E:0900 to $7E:0EFF, which is 194 bytes into that run and
; ends 2,348 bytes short of its end, so there is margin on both sides. The base
; is 256 byte aligned so the direct page register can point straight at it.
;
; Every field below states its width, and stateblock.py reads those statements
; and checks that no two of them share a byte. Two did. The assembler cannot
; catch it: an offset is a number, and two names for one number assemble without
; complaint.
;
!STATE          = $000900       ; base of the block

; Scalars, reached through DP.
!S_STAGE        = $00           ; 0 idle, 1 taking lengths, 2 taking parameters
!S_COMMAND      = $01           ; the command byte in flight
!S_LEN1         = $02           ; first declared length, merge and mirror and scale
!S_LEN2         = $03           ; second declared length, scale only
!S_WANT_LEN     = $04           ; declared lengths still to arrive
!S_WANT_PARAM   = $05           ; parameter bytes still to arrive, 16 bit
!S_PARAM_INDEX  = $07           ; write cursor into the parameter buffer, 16 bit
!S_OUT_LEN      = $09           ; bytes the finished operation produced, 16 bit
!S_OUT_INDEX    = $0B           ; read cursor into the output buffer, 16 bit
!S_TRANSPARENT  = $0D           ; transparent colour, low nibble only
!S_INBYTE       = $0E           ; the byte a caller just wrote, parked so the
                                ;   accumulator can be saved and restored
!S_XFER_BANK    = $0F           ; the bank a block transfer reads or writes,
                                ;   supplied by whichever entry point was called
!S_XFER_PTR     = $10           ; 24 bit pointer the transfer indexes through
!S_XFER_LEFT    = $13           ; bytes of a split run already moved, 16 bit
!S_XFER_TOTAL   = $15           ; bytes the transfer was asked for, 16 bit
!S_SAVE_A       = $17           ; the caller's accumulator, 16 bit
!S_SAVE_X       = $19           ; and both index registers, 16 bit, kept here
!S_SAVE_Y       = $1B           ;   rather than on the stack, 16 bit, so the
                                ;   transfer can add the count to them before
                                ;   they go back
!S_OVERLAY      = $1D           ; where the overlay half of a merge payload
                                ;   starts, 16 bit, so the loop can reach it
                                ;   through the direct page rather than carrying
                                ;   a second index it would have to save and
                                ;   restore. It was declared at $0E for a while,
                                ;   which is !S_INBYTE, and the sixteen bit store
                                ;   that sets it reached into !S_XFER_BANK as
                                ;   well. A transfer that splits re-reads that
                                ;   bank after the operation runs, so a merge
                                ;   would have taken its next chunk from whatever
                                ;   the pointer's high byte held. Nothing in any
                                ;   recording splits, so it never fired
!S_MVN          = $20           ; a four byte MVN stub, built by dsp_init and
                                ;   patched with its banks before each use. Code
                                ;   in ROM cannot modify itself, and a block move
                                ;   names its banks in the instruction rather than
                                ;   in a register, so the one instruction that can
                                ;   move a payload without a loop has to live in
                                ;   writable memory. The cartridge's own boot code
                                ;   reaches the same conclusion and installs four
                                ;   of these at $0080
!S_CHUNK        = $24           ; bytes the current block move covers, 16 bit,
                                ;   kept out of !S_SCRATCH because an operation
                                ;   runs in the middle of a transfer and owns that
!S_TABLE_FOR    = $26           ; the transparent colour the merge tables were
                                ;   built for, or $FF when they hold nothing. The
                                ;   cartridge sets the colour 8,852 times in a
                                ;   30,000 frame tour and changes it three times,
                                ;   so comparing costs almost nothing and
                                ;   rebuilding almost never happens. It sat eight
                                ;   bytes into !S_SCRATCH until the layout was
                                ;   checked against itself, which no operation
                                ;   happened to reach and any new one would have
!S_SCRATCH      = $28           ; working room for the operations, $0928 to $09EF
!S_SCRATCH_END  = $F0           ; where that room stops, read by stateblock.py so
                                ;   a field above it is not taken for a collision
!S_STEP_FOR     = $F0           ; 16 bit. The two declared lengths the resampling
                                ;   step below was worked out for, read as one
                                ;   word because they are adjacent. $FFFF means
                                ;   nothing is held: a scale only derives a step
                                ;   when its output is shorter than its input, so
                                ;   a pair of equal lengths never gets here
!S_STEP         = $F2           ; 32 bit. That step, in 16.16 fixed point. The
                                ;   division that produces it is a thirty two bit
                                ;   restoring divide, thirty two iterations of
                                ;   six shifts and a compare, and the cartridge
                                ;   asks for the same answer over and over: one
                                ;   30,000 frame tour makes 10,422 scale calls
                                ;   with two distinct length pairs between them,
                                ;   changing pair twice

; Buffers, reached through DB = $00 by absolute addressing.

!P_BUFFER       = $000A00       ; parameters, 512 bytes. A merge of the longest
                                ;   declared length, 255, takes 2 x 255 = 510
!O_BUFFER       = $000C00       ; output, 256 bytes. No command produces more
                                ;   than 255, and the tile conversion takes 32
!MERGE_KEEP     = $000D00       ; the overlay byte with its transparent nibbles
                                ;   cleared, for every byte value
!MERGE_MASK     = $000E00       ; where those nibbles were, as $F, so the
                                ;   background can be let through them
!STATE_END      = $000F00

!STAGE_IDLE     = $00
!STAGE_LENGTH   = $01
!STAGE_PARAM    = $02

!CMD_TILE       = $01
!CMD_TRANSPARENT = $03
!CMD_MERGE      = $05
!CMD_MIRROR     = $06
!CMD_MULTIPLY   = $09
!CMD_SCALE      = $0D

!TILE_BYTES     = $20           ; the tile conversion is always 32 bytes each way
!MULTIPLY_BYTES = $04

!IDLE_BYTE      = $FF           ; what the chip returns with nothing pending,
                                ;   taken from DSP2GetByte in snes9x dsp2.cpp

!DSP_PORT_BANK  = $3F           ; the bank the retail cartridge fed and drained,
                                ;   kept only so a block move can leave DB where
                                ;   the instruction it replaces would have left it
