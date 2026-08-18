; Dungeon Master, software DSP-2: the state block.
;
; The chip is replaced by code, so the command and parameter state machine it
; kept internally has to live somewhere the CPU can reach. This block holds it.
;
; Placement is measured rather than guessed. Three seeded tours of 30,000 frames
; each recorded every read and every write of work RAM, and the intersection of
; the three leaves 37,245 bytes that none of them touched in either direction.
; The largest such run starts at $7E:05ED and is 6,060 bytes. What follows uses
; $7E:0600 to $7E:0AFF, which is nineteen bytes into that run and ends 4,761
; bytes short of its end, so there is margin on both sides.
;
; $7E:0000 to $7E:1FFF is mirrored into banks $00 to $3F and $80 to $BF, so with
; DB = $00 every field here is reachable by absolute addressing, and with
; DP = $0600 the scalars are reachable by direct page addressing, which is one
; byte shorter and one cycle cheaper per access.

!STATE          = $000600       ; base of the block, kept 256 byte aligned so the
                                ;   direct page register can point straight at it

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
!S_XFER_LEFT    = $13           ; bytes still to move, 16 bit
!S_XFER_TOTAL   = $15           ; bytes the transfer was asked for, 16 bit
!S_SAVE_A       = $17           ; the caller's registers, kept here rather than
!S_SAVE_X       = $19           ;   on the stack so the transfer can add the
!S_SAVE_Y       = $1B           ;   count to them before they go back
!S_SCRATCH      = $20           ; working room for the operations, $0620 to $06FF

; Buffers, reached through DB = $00 by absolute addressing.
!P_BUFFER       = $000800       ; parameters, 512 bytes. A merge of the longest
                                ;   declared length, 255, takes 2 x 255 = 510
!O_BUFFER       = $000A00       ; output, 256 bytes. No command produces more
                                ;   than 255, and the tile conversion takes 32
!STATE_END      = $000B00

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
