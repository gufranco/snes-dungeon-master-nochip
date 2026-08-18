FROM debian:bookworm-slim AS build

ARG SNES9X_REF=2971061cf07fdc6fc7d18883edf4e648eb16a6d2

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git ca-certificates make perl \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none --no-checkout \
        https://github.com/snes9xgit/snes9x.git /src/snes9x \
    && git -C /src/snes9x checkout --quiet "${SNES9X_REF}" \
    && test "$(git -C /src/snes9x rev-parse HEAD)" = "${SNES9X_REF}"

RUN perl -0pi -e 's/(void DSP2SetByte \(uint8 byte, uint16 address\)\n\{)/extern "C" void dm_note_dsp(int, unsigned char, unsigned short);\n$1\n\tdm_note_dsp(0, byte, address);/' /src/snes9x/dsp2.cpp \
    && test "$(grep -c 'dm_note_dsp(0, byte, address)' /src/snes9x/dsp2.cpp)" = "1"

RUN perl -0pi -e 's/(\tt = 0x80;\n\n)(\treturn \(t\);)/$1\tdm_note_dsp(1, t, address);\n$2/' /src/snes9x/dsp2.cpp \
    && test "$(grep -c 'dm_note_dsp(1, t, address)' /src/snes9x/dsp2.cpp)" = "1"

RUN perl -0pi -e 's/(inline uint8 S9xGetByte \(uint32 Address\)\n\{)/extern "C" void dm_note_read(unsigned long);\n$1\n\tdm_note_read(Address);/' /src/snes9x/getset.h \
    && test "$(grep -c 'dm_note_read(Address)' /src/snes9x/getset.h)" = "1"

RUN perl -0pi -e 's/(inline void S9xSetByte \(uint8 Byte, uint32 Address\)\n\{)/extern "C" void dm_note_write(unsigned long);\n$1\n\tdm_note_write(Address);/' /src/snes9x/getset.h \
    && test "$(grep -c 'dm_note_write(Address)' /src/snes9x/getset.h)" = "1"

WORKDIR /src/snes9x/libretro
RUN make STATIC_LINKING=1 -j"$(nproc)" \
    && cp snes9x_libretro.so /src/snes9x/libretro/snes9x_libretro.a

COPY main.cpp /src/frontend/main.cpp
COPY windowed_lorom.cpp /src/frontend/windowed_lorom.cpp
COPY windowed_lorom.h /src/frontend/windowed_lorom.h

RUN g++ -O2 -std=c++11 -o /src/dmemu \
        /src/frontend/main.cpp /src/frontend/windowed_lorom.cpp \
        -I/src/frontend -I/src/snes9x -I/src/snes9x/libretro \
        -I/src/snes9x/libretro/libretro-common/include \
        -I/src/snes9x/apu -I/src/snes9x/apu/bapu \
        /src/snes9x/libretro/snes9x_libretro.a

FROM debian:bookworm-slim

COPY --from=build /src/dmemu /usr/local/bin/dmemu

RUN useradd --create-home --uid 1000 runner
USER runner
WORKDIR /work

ENTRYPOINT ["dmemu"]
