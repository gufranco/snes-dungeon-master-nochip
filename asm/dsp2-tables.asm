; Dungeon Master, software DSP-2: the tables the hot operations read instead of
; computing.
;
; Two operations account for ninety two per cent of everything the cartridge
; asked the chip, measured across three recorded tours: 2,022,485 merges and
; 1,031,195 tile conversions against 96,112 of everything else. Both were written
; a bit at a time, which is the clearest way to write them and the slowest way to
; run them, and both turn into table lookups without changing what they answer.
;
; The tables are built here, by the assembler, out of the same expressions the
; bit serial code applied. Nothing generates them outside the build and nothing
; is checked in: a table computed where it is used cannot disagree with the code
; that uses it, and one that is pasted in can.
;
; ---------------------------------------------------------------------------
; The tile conversion's tables.
;
; A tile conversion takes eight rows of four bytes and produces four bitplanes.
; Each input byte carries two pixels, the high nibble first, and each pixel
; contributes one bit to each of the four planes. Byte j of a row therefore
; contributes to bit 7-2j and bit 6-2j of every plane, and which bits it sets
; depends only on the byte and on j.
;
; So there is one table per byte position, and each entry holds the contribution
; to two planes at once: planes 0 and 1 in tile_lo, planes 2 and 3 in tile_hi,
; the lower numbered plane in the low half of the word. That is the order the
; output wants them in, so one sixteen bit store puts both planes where they go
; without taking the word apart.
;
; Four positions of 256 words each, twice, is 4,096 bytes. The bit serial version
; spent about sixty eight cycles a byte; this spends about forty four, and spends
; it without a subroutine call per byte.
; ---------------------------------------------------------------------------

; Bytes from one byte position's table to the next.
!TILE_STRIDE = 512

tile_lo:
!j = 0
while !j < 4
    !high #= 7-(!j*2)
    !low #= 6-(!j*2)
    !b = 0
    while !b < 256
        !p0 #= (((!b>>4)&1)<<!high)+((!b&1)<<!low)
        !p1 #= (((!b>>5)&1)<<!high)+(((!b>>1)&1)<<!low)
        dw !p0+(!p1*256)
        !b #= !b+1
    endif
    !j #= !j+1
endif

tile_hi:
!j = 0
while !j < 4
    !high #= 7-(!j*2)
    !low #= 6-(!j*2)
    !b = 0
    while !b < 256
        !p2 #= (((!b>>6)&1)<<!high)+(((!b>>2)&1)<<!low)
        !p3 #= (((!b>>7)&1)<<!high)+(((!b>>3)&1)<<!low)
        dw !p2+(!p3*256)
        !b #= !b+1
    endif
    !j #= !j+1
endif
