#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "libretro.h"
#include "snes9x.h"
#include "memmap.h"
#include "65c816.h"
#include "ppu.h"

#include "windowed_lorom.h"

static const unsigned TRACE_RECORD_BYTES = 28;

static const unsigned TRAMPOLINE_OPERANDS[8] = {
    0x0081, 0x0082, 0x0085, 0x0086, 0x0089, 0x008A, 0x008D, 0x008E,
};

static FILE *trace_out = NULL;
static unsigned long trace_events = 0;
static unsigned long frames_seen = 0;

static unsigned long sram_reads[256];
static unsigned long sram_writes[256];
static unsigned long sram_low_reads[256];
static unsigned long sram_low_writes[256];
static bool watch_sram = false;

static std::vector<uint16_t> frame;
static unsigned frame_width = 0;
static unsigned frame_height = 0;
static unsigned frame_pitch = 0;
static unsigned long frames_delivered = 0;

static uint16_t pad_state = 0;

static void put_u32(unsigned char *at, unsigned long value)
{
    at[0] = (unsigned char)(value & 0xFF);
    at[1] = (unsigned char)((value >> 8) & 0xFF);
    at[2] = (unsigned char)((value >> 16) & 0xFF);
    at[3] = (unsigned char)((value >> 24) & 0xFF);
}

static void put_u16(unsigned char *at, unsigned value)
{
    at[0] = (unsigned char)(value & 0xFF);
    at[1] = (unsigned char)((value >> 8) & 0xFF);
}

extern "C" void dm_note_dsp(int is_read, unsigned char byte, unsigned short address)
{
    (void)address;
    trace_events++;
    if (!trace_out) {
        return;
    }

    unsigned char record[TRACE_RECORD_BYTES];
    memset(record, 0, sizeof(record));
    put_u32(record + 0, frames_seen);
    put_u32(record + 4, (unsigned long)Registers.PBPC);
    put_u16(record + 8, Registers.X.W);
    put_u16(record + 10, Registers.Y.W);
    record[12] = (unsigned char)(is_read ? 1 : 0);
    record[13] = byte;
    for (unsigned i = 0; i < 8; i++) {
        record[14 + i] = Memory.RAM[TRAMPOLINE_OPERANDS[i] & 0x1FFFF];
    }
    record[22] = (unsigned char)Registers.DB;
    record[23] = (unsigned char)(Registers.P.W & 0xFF);

    const uint32 pc = (uint32)Registers.PBPC;
    const uint32 bank = pc & 0xFF0000;
    record[24] = S9xGetByte(bank | ((pc - 3) & 0xFFFF));
    record[25] = S9xGetByte(bank | ((pc - 2) & 0xFFFF));
    record[26] = S9xGetByte(bank | ((pc - 1) & 0xFFFF));
    record[27] = S9xGetByte(bank | (pc & 0xFFFF));

    fwrite(record, 1, sizeof(record), trace_out);
}

static inline bool is_lorom_sram_bank(unsigned bank)
{
    return (bank >= 0x70 && bank <= 0x7D) || bank >= 0xF0;
}

static const unsigned long WRAM_BYTES = 0x20000;
static unsigned char *wram_touched = NULL;
static unsigned char *wram_shadow = NULL;
static const unsigned char WRAM_READ = 1;
static const unsigned char WRAM_WRITE = 2;

static unsigned long watch_address = 0xFFFFFFFF;
static unsigned long watch_hits = 0;

static void note_wram_changes(void)
{
    if (!wram_touched || !wram_shadow) {
        return;
    }
    for (unsigned long at = 0; at < WRAM_BYTES; at++) {
        if (Memory.RAM[at] != wram_shadow[at]) {
            wram_touched[at] |= WRAM_WRITE;
            wram_shadow[at] = Memory.RAM[at];
        }
    }
}

static unsigned long rom_bytes = 0;
static unsigned char *rom_touched = NULL;

static inline long rom_offset(unsigned long address)
{
    if (rom_bytes == 0) {
        return -1;
    }
    const unsigned bank = (address >> 16) & 0xFF;
    const unsigned offset = address & 0xFFFF;
    if (bank == 0x7E || bank == 0x7F) {
        return -1;
    }
    if (offset < 0x8000) {
        return -1;
    }
    const unsigned long linear = (unsigned long)(bank & 0x7F) * 0x8000 + (offset - 0x8000);
    return (long)(linear % rom_bytes);
}

static inline long wram_offset(unsigned long address)
{
    const unsigned bank = (address >> 16) & 0xFF;
    const unsigned offset = address & 0xFFFF;
    if (bank == 0x7E) {
        return (long)offset;
    }
    if (bank == 0x7F) {
        return (long)(0x10000 + offset);
    }
    if (bank < 0x40 || (bank >= 0x80 && bank < 0xC0)) {
        if (offset < 0x2000) {
            return (long)offset;
        }
    }
    return -1;
}

extern "C" void dm_note_read(unsigned long address)
{
    if (rom_touched) {
        const long at = rom_offset(address);
        if (at >= 0) {
            rom_touched[at] = 1;
        }
    }
    if (wram_touched) {
        const long at = wram_offset(address);
        if (at >= 0) {
            wram_touched[at] |= WRAM_READ;
        }
    }
    if (!watch_sram) {
        return;
    }
    const unsigned bank = (address >> 16) & 0xFF;
    if (!is_lorom_sram_bank(bank)) {
        return;
    }
    sram_reads[bank]++;
    if ((address & 0xFFFF) < 0x8000) {
        sram_low_reads[bank]++;
    }
}

extern "C" void dm_note_write(unsigned long address)
{
    if (watch_address != 0xFFFFFFFF && (address & 0xFFFFFF) == watch_address && watch_hits < 40) {
        watch_hits++;
        printf("WATCH write $%06lX from $%06lX frame %lu\n",
               (unsigned long)(address & 0xFFFFFF),
               (unsigned long)Registers.PBPC, frames_seen);
    }
    if (wram_touched) {
        const long at = wram_offset(address);
        if (at >= 0) {
            wram_touched[at] |= WRAM_WRITE;
        }
    }
    if (!watch_sram) {
        return;
    }
    const unsigned bank = (address >> 16) & 0xFF;
    if (!is_lorom_sram_bank(bank)) {
        return;
    }
    sram_writes[bank]++;
    if ((address & 0xFFFF) < 0x8000) {
        sram_low_writes[bank]++;
    }
}

static void cb_video(const void *data, unsigned width, unsigned height, size_t pitch)
{
    frames_delivered++;
    if (!data) {
        return;
    }
    frame_width = width;
    frame_height = height;
    frame_pitch = (unsigned)(pitch / sizeof(uint16_t));
    frame.assign((const uint16_t *)data, (const uint16_t *)data + frame_pitch * height);
}

static void cb_audio(int16_t, int16_t) {}

static size_t cb_audio_batch(const int16_t *, size_t frames_count)
{
    return frames_count;
}

static void cb_input_poll(void) {}

static int16_t cb_input_state(unsigned port, unsigned, unsigned, unsigned id)
{
    if (port != 0 || id > 15) {
        return 0;
    }
    return (pad_state >> id) & 1;
}

static bool cb_environment(unsigned cmd, void *data)
{
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char **)data = ".";
        return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
    case RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_VARIABLES:
    case RETRO_ENVIRONMENT_SET_MEMORY_MAPS:
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
    case RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS:
        return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *(bool *)data = false;
        return true;
    default:
        return false;
    }
}

static unsigned long long frame_hash(void)
{
    unsigned long long hash = 1469598103934665603ULL;
    for (unsigned y = 0; y < frame_height; y++) {
        for (unsigned x = 0; x < frame_width; x++) {
            hash ^= (unsigned long long)frame[y * frame_pitch + x];
            hash *= 1099511628211ULL;
        }
    }
    return hash;
}

static double frame_brightness(void)
{
    if (frame.empty() || frame_width == 0) {
        return -1.0;
    }
    double total = 0.0;
    for (unsigned y = 0; y < frame_height; y++) {
        for (unsigned x = 0; x < frame_width; x++) {
            const uint16_t pixel = frame[y * frame_pitch + x];
            total += ((pixel >> 11) & 0x1F) * 8 + ((pixel >> 5) & 0x3F) * 4 + (pixel & 0x1F) * 8;
        }
    }
    return total / (double)(frame_width * frame_height * 3);
}

static void write_ppm(const char *path)
{
    if (frame.empty() || frame_width == 0) {
        return;
    }
    FILE *out = fopen(path, "wb");
    if (!out) {
        return;
    }
    fprintf(out, "P6\n%u %u\n255\n", frame_width, frame_height);
    for (unsigned y = 0; y < frame_height; y++) {
        for (unsigned x = 0; x < frame_width; x++) {
            const uint16_t pixel = frame[y * frame_pitch + x];
            const unsigned char rgb[3] = {
                (unsigned char)(((pixel >> 11) & 0x1F) << 3),
                (unsigned char)(((pixel >> 5) & 0x3F) << 2),
                (unsigned char)((pixel & 0x1F) << 3),
            };
            fwrite(rgb, 1, 3, out);
        }
    }
    fclose(out);
}

struct ScriptStep {
    unsigned long frame;
    uint16_t buttons;
};

static std::vector<ScriptStep> script;

static int button_id(const std::string &name)
{
    if (name == "up") return RETRO_DEVICE_ID_JOYPAD_UP;
    if (name == "down") return RETRO_DEVICE_ID_JOYPAD_DOWN;
    if (name == "left") return RETRO_DEVICE_ID_JOYPAD_LEFT;
    if (name == "right") return RETRO_DEVICE_ID_JOYPAD_RIGHT;
    if (name == "a") return RETRO_DEVICE_ID_JOYPAD_A;
    if (name == "b") return RETRO_DEVICE_ID_JOYPAD_B;
    if (name == "x") return RETRO_DEVICE_ID_JOYPAD_X;
    if (name == "y") return RETRO_DEVICE_ID_JOYPAD_Y;
    if (name == "l") return RETRO_DEVICE_ID_JOYPAD_L;
    if (name == "r") return RETRO_DEVICE_ID_JOYPAD_R;
    if (name == "start") return RETRO_DEVICE_ID_JOYPAD_START;
    if (name == "select") return RETRO_DEVICE_ID_JOYPAD_SELECT;
    return -1;
}

static bool load_script(const char *path)
{
    FILE *in = fopen(path, "r");
    if (!in) {
        return false;
    }
    char line[512];
    while (fgets(line, sizeof(line), in)) {
        char *hash = strchr(line, '#');
        if (hash) {
            *hash = '\0';
        }
        char *cursor = line;
        while (*cursor == ' ' || *cursor == '\t') {
            cursor++;
        }
        if (*cursor == '\0' || *cursor == '\n') {
            continue;
        }
        ScriptStep step;
        step.buttons = 0;
        char *token = strtok(cursor, " \t\r\n");
        if (!token) {
            continue;
        }
        step.frame = strtoul(token, NULL, 10);
        while ((token = strtok(NULL, " \t\r\n")) != NULL) {
            const int id = button_id(token);
            if (id >= 0) {
                step.buttons |= (uint16_t)(1u << id);
            }
        }
        script.push_back(step);
    }
    fclose(in);
    return true;
}

static void apply_script(unsigned long at_frame)
{
    for (size_t i = 0; i < script.size(); i++) {
        if (script[i].frame == at_frame) {
            pad_state = script[i].buttons;
            return;
        }
    }
}

static bool read_file(const char *path, std::vector<unsigned char> &out)
{
    FILE *file = fopen(path, "rb");
    if (!file) {
        return false;
    }
    fseek(file, 0, SEEK_END);
    const long size = ftell(file);
    fseek(file, 0, SEEK_SET);
    out.resize((size_t)size);
    const bool complete = fread(out.data(), 1, (size_t)size, file) == (size_t)size;
    fclose(file);
    return complete;
}

static void report_wram(const char *path)
{
    FILE *out = fopen(path, "wb");
    if (!out) {
        return;
    }
    fwrite(wram_touched, 1, WRAM_BYTES, out);
    fclose(out);

    unsigned long untouched = 0;
    for (unsigned long i = 0; i < WRAM_BYTES; i++) {
        untouched += wram_touched[i] == 0;
    }
    printf("WRAM untouched=%lu of %lu\n", untouched, WRAM_BYTES);
}

static void dump_wram(const char *path)
{
    FILE *out = fopen(path, "wb");
    if (!out) {
        return;
    }
    fwrite(Memory.RAM, 1, 0x20000, out);
    fclose(out);
    printf("WRAM dumped to %s\n", path);
}

static void report_rom(const char *path)
{
    FILE *out = fopen(path, "wb");
    if (!out) {
        return;
    }
    fwrite(rom_touched, 1, rom_bytes, out);
    fclose(out);

    unsigned long untouched = 0;
    for (unsigned long i = 0; i < rom_bytes; i++) {
        untouched += rom_touched[i] == 0;
    }
    printf("ROM untouched=%lu of %lu\n", untouched, rom_bytes);
}

static void report_sram(void)
{
    for (unsigned bank = 0; bank < 256; bank++) {
        if (sram_reads[bank] == 0 && sram_writes[bank] == 0) {
            continue;
        }
        printf("SRAMBANK bank=%02X reads=%lu writes=%lu lowreads=%lu lowwrites=%lu\n",
               bank, sram_reads[bank], sram_writes[bank],
               sram_low_reads[bank], sram_low_writes[bank]);
    }
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: dmemu <rom> <frames>\n");
        fprintf(stderr, "  DMTRACE=<path>   binary DSP-2 transaction log\n");
        fprintf(stderr, "  DMSRAM=1         report which save RAM banks are touched\n");
        fprintf(stderr, "  DMWRAM=<path>    write a read and write map of work RAM\n");
        fprintf(stderr, "  DMROM=<path>     write a read map of the cartridge\n");
        fprintf(stderr, "  DMDUMP=<path>    dump work RAM when the run ends\n");
        fprintf(stderr, "  DMSCRIPT=<path>  input script, one 'frame button...' per line\n");
        fprintf(stderr, "  DMHASH=<path>    per-frame digests\n");
        fprintf(stderr, "  DMPPM=<prefix>   frame captures\n");
        fprintf(stderr, "  DMPPMAT=<list>   comma separated frames to capture\n");
        fprintf(stderr, "  DMWINDOW=<n>     install the windowed map with mirror shift n\n");
        return 2;
    }

    const unsigned long frames_to_run = strtoul(argv[2], NULL, 10);

    std::vector<unsigned char> rom;
    if (!read_file(argv[1], rom)) {
        fprintf(stderr, "cannot read %s\n", argv[1]);
        return 1;
    }

    const char *trace_path = getenv("DMTRACE");
    if (trace_path) {
        trace_out = fopen(trace_path, "wb");
        if (!trace_out) {
            fprintf(stderr, "cannot write %s\n", trace_path);
            return 1;
        }
    }
    watch_sram = getenv("DMSRAM") != NULL;

    const char *rom_path = getenv("DMROM");
    if (rom_path) {
        rom_bytes = (unsigned long)rom.size();
        rom_touched = (unsigned char *)calloc(rom_bytes, 1);
        if (!rom_touched) {
            fprintf(stderr, "cannot allocate the rom map\n");
            return 1;
        }
    }

    const char *watch = getenv("DMWATCH");
    if (watch) {
        watch_address = strtoul(watch, NULL, 16);
    }

    const char *wram_path = getenv("DMWRAM");
    if (wram_path) {
        wram_touched = (unsigned char *)calloc(WRAM_BYTES, 1);
        wram_shadow = (unsigned char *)malloc(WRAM_BYTES);
        if (wram_shadow) {
            memcpy(wram_shadow, Memory.RAM, WRAM_BYTES);
        }
        if (!wram_touched) {
            fprintf(stderr, "cannot allocate the work RAM map\n");
            return 1;
        }
    }

    const char *script_path = getenv("DMSCRIPT");
    if (script_path && !load_script(script_path)) {
        fprintf(stderr, "cannot read %s\n", script_path);
        return 1;
    }

    retro_set_environment(cb_environment);
    retro_set_video_refresh(cb_video);
    retro_set_audio_sample(cb_audio);
    retro_set_audio_sample_batch(cb_audio_batch);
    retro_set_input_poll(cb_input_poll);
    retro_set_input_state(cb_input_state);
    retro_init();

    retro_game_info info;
    memset(&info, 0, sizeof(info));
    info.path = argv[1];
    info.data = rom.data();
    info.size = rom.size();

    if (!retro_load_game(&info)) {
        printf("RESULT load=failed\n");
        return 1;
    }

    const char *window = getenv("DMWINDOW");
    if (window) {
        const int mirror_shift = atoi(window);
        if (Memory.ROM && Memory.MAX_ROM_SIZE >= rom.size()) {
            memcpy(Memory.ROM, rom.data(), rom.size());
        }
        Memory.CalculatedSize = (uint32)rom.size();
        install_windowed_lorom_map(mirror_shift);
        S9xReset();
        install_windowed_lorom_map(mirror_shift);
    }

    printf("ROM title='%s' map=%02X chipset=%02X size=%02X sram=%02X dsp=%d bytes=%u\n",
           Memory.ROMName, Memory.ROMSpeed, Memory.ROMType, Memory.ROMSize,
           Memory.SRAMSize, (int)Settings.DSP, (unsigned)Memory.CalculatedSize);

    FILE *hash_out = NULL;
    const char *hash_path = getenv("DMHASH");
    if (hash_path) {
        hash_out = fopen(hash_path, "w");
    }

    const char *ppm_prefix = getenv("DMPPM");
    const char *ppm_at = getenv("DMPPMAT");

    for (unsigned long i = 0; i < frames_to_run; i++) {
        frames_seen = i;
        apply_script(i);
        retro_run();
        note_wram_changes();

        if (hash_out) {
            fprintf(hash_out, "%lu %016llx %.4f\n", i, frame_hash(), frame_brightness());
        }
        if (ppm_prefix && ppm_at) {
            char wanted[32];
            snprintf(wanted, sizeof(wanted), "%lu", i);
            const char *found = strstr(ppm_at, wanted);
            const bool boundary_before = found && (found == ppm_at || found[-1] == ',');
            const size_t span = strlen(wanted);
            const bool boundary_after = found && (found[span] == '\0' || found[span] == ',');
            if (boundary_before && boundary_after) {
                char path[512];
                snprintf(path, sizeof(path), "%s%06lu.ppm", ppm_prefix, i);
                write_ppm(path);
            }
        }
    }

    if (hash_out) {
        fclose(hash_out);
    }
    if (trace_out) {
        fclose(trace_out);
        trace_out = NULL;
    }
    if (watch_sram) {
        report_sram();
    }
    if (wram_touched) {
        report_wram(getenv("DMWRAM"));
    }
    if (rom_touched) {
        report_rom(getenv("DMROM"));
    }
    if (getenv("DMDUMP")) {
        dump_wram(getenv("DMDUMP"));
    }

    printf("RESULT load=ok frames=%lu delivered=%lu dspevents=%lu brightness=%.4f\n",
           frames_to_run, frames_delivered, trace_events, frame_brightness());
    return 0;
}
