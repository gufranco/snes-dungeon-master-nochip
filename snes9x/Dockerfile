FROM debian:bookworm-slim AS build

ARG SNES9X_REF=2971061cf07fdc6fc7d18883edf4e648eb16a6d2

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git ca-certificates make \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none --no-checkout \
        https://github.com/snes9xgit/snes9x.git /src/snes9x \
    && git -C /src/snes9x checkout --quiet "${SNES9X_REF}" \
    && test "$(git -C /src/snes9x rev-parse HEAD)" = "${SNES9X_REF}"

COPY windowed-lorom-map.patch /src/windowed-lorom-map.patch

RUN git -C /src/snes9x apply --check /src/windowed-lorom-map.patch \
    && git -C /src/snes9x apply /src/windowed-lorom-map.patch

RUN grep -q "Map_WindowedLoROMMap" /src/snes9x/memmap.h \
    && grep -q "DUNGEON MASTER" /src/snes9x/memmap.cpp \
    && grep -q "map_LoROMSRAM" /src/snes9x/memmap.cpp \
    && ! grep -q "SDD1Decompressed" /src/snes9x/memmap.cpp

WORKDIR /src/snes9x/libretro
RUN make STATIC_LINKING=1 -j"$(nproc)"

FROM debian:bookworm-slim

COPY --from=build /src/snes9x/libretro/snes9x_libretro.so /opt/snes9x/snes9x_libretro.so

RUN useradd --create-home --uid 1000 builder
USER builder
WORKDIR /work

ENTRYPOINT ["sha256sum", "/opt/snes9x/snes9x_libretro.so"]
