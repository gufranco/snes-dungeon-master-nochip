#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include <dlfcn.h>
#include <SDL.h>

#include "libretro.h"

static const int SCREEN_WIDTH = 256;
static const int SCREEN_HEIGHT = 224;
static const int DEFAULT_SCALE = 3;
static const int AUDIO_CHANNELS = 2;
static const int AUDIO_QUEUE_LIMIT = 8192;

static SDL_Window *window = NULL;
static SDL_Renderer *renderer = NULL;
static SDL_Texture *texture = NULL;
static SDL_AudioDeviceID audio_device = 0;

static unsigned texture_width = 0;
static unsigned texture_height = 0;
static enum retro_pixel_format pixel_format = RETRO_PIXEL_FORMAT_0RGB1555;

static const uint8_t *keyboard = NULL;

struct Binding {
    unsigned id;
    SDL_Scancode key;
};

static const Binding BINDINGS[] = {
    {RETRO_DEVICE_ID_JOYPAD_UP, SDL_SCANCODE_UP},
    {RETRO_DEVICE_ID_JOYPAD_DOWN, SDL_SCANCODE_DOWN},
    {RETRO_DEVICE_ID_JOYPAD_LEFT, SDL_SCANCODE_LEFT},
    {RETRO_DEVICE_ID_JOYPAD_RIGHT, SDL_SCANCODE_RIGHT},
    {RETRO_DEVICE_ID_JOYPAD_B, SDL_SCANCODE_Z},
    {RETRO_DEVICE_ID_JOYPAD_A, SDL_SCANCODE_X},
    {RETRO_DEVICE_ID_JOYPAD_Y, SDL_SCANCODE_A},
    {RETRO_DEVICE_ID_JOYPAD_X, SDL_SCANCODE_S},
    {RETRO_DEVICE_ID_JOYPAD_L, SDL_SCANCODE_Q},
    {RETRO_DEVICE_ID_JOYPAD_R, SDL_SCANCODE_W},
    {RETRO_DEVICE_ID_JOYPAD_START, SDL_SCANCODE_RETURN},
    {RETRO_DEVICE_ID_JOYPAD_SELECT, SDL_SCANCODE_RSHIFT},
};

static std::string save_directory;

static bool environment(unsigned command, void *data)
{
    switch (command) {
    case RETRO_ENVIRONMENT_GET_CAN_DUPE:
        *(bool *)data = true;
        return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        pixel_format = *(const enum retro_pixel_format *)data;
        return pixel_format == RETRO_PIXEL_FORMAT_RGB565 ||
               pixel_format == RETRO_PIXEL_FORMAT_0RGB1555 ||
               pixel_format == RETRO_PIXEL_FORMAT_XRGB8888;
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char **)data = save_directory.c_str();
        return true;
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
        return false;
    default:
        return false;
    }
}

static Uint32 sdl_format(void)
{
    switch (pixel_format) {
    case RETRO_PIXEL_FORMAT_RGB565:
        return SDL_PIXELFORMAT_RGB565;
    case RETRO_PIXEL_FORMAT_XRGB8888:
        return SDL_PIXELFORMAT_ARGB8888;
    default:
        return SDL_PIXELFORMAT_ARGB1555;
    }
}

static void ensure_texture(unsigned width, unsigned height)
{
    if (texture && width == texture_width && height == texture_height) {
        return;
    }
    if (texture) {
        SDL_DestroyTexture(texture);
    }
    texture = SDL_CreateTexture(renderer, sdl_format(), SDL_TEXTUREACCESS_STREAMING,
                                (int)width, (int)height);
    texture_width = width;
    texture_height = height;
}

static void video_refresh(const void *data, unsigned width, unsigned height, size_t pitch)
{
    if (!data) {
        return;
    }
    ensure_texture(width, height);
    if (!texture) {
        return;
    }
    SDL_UpdateTexture(texture, NULL, data, (int)pitch);
    SDL_RenderClear(renderer);
    SDL_RenderCopy(renderer, texture, NULL, NULL);
    SDL_RenderPresent(renderer);
}

static void audio_sample(int16_t left, int16_t right)
{
    const int16_t frame[2] = {left, right};
    if (audio_device) {
        SDL_QueueAudio(audio_device, frame, sizeof(frame));
    }
}

static size_t audio_sample_batch(const int16_t *data, size_t frames)
{
    if (audio_device && SDL_GetQueuedAudioSize(audio_device) < AUDIO_QUEUE_LIMIT * 4) {
        SDL_QueueAudio(audio_device, data, (Uint32)(frames * AUDIO_CHANNELS * sizeof(int16_t)));
    }
    return frames;
}

static void input_poll(void)
{
    keyboard = SDL_GetKeyboardState(NULL);
}

static int16_t input_state(unsigned port, unsigned device, unsigned index, unsigned id)
{
    (void)index;
    if (port != 0 || device != RETRO_DEVICE_JOYPAD || !keyboard) {
        return 0;
    }
    for (size_t at = 0; at < sizeof(BINDINGS) / sizeof(BINDINGS[0]); at++) {
        if (BINDINGS[at].id == id) {
            return keyboard[BINDINGS[at].key] ? 1 : 0;
        }
    }
    return 0;
}

template <typename T>
static T resolve(void *core, const char *name)
{
    T found = (T)dlsym(core, name);
    if (!found) {
        fprintf(stderr, "the core declares no %s\n", name);
        exit(1);
    }
    return found;
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

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: dmplay <image.sfc> [core.dylib] [scale]\n");
        return 1;
    }

    const char *rom_path = argv[1];
    const char *core_path = argc > 2 ? argv[2] : "build/native/snes9x/libretro/snes9x_libretro.dylib";
    const int scale = argc > 3 ? atoi(argv[3]) : DEFAULT_SCALE;

    std::string sram_path(rom_path);
    const size_t dot = sram_path.find_last_of('.');
    sram_path = (dot == std::string::npos ? sram_path : sram_path.substr(0, dot)) + ".srm";
    const size_t slash = sram_path.find_last_of('/');
    save_directory = slash == std::string::npos ? "." : sram_path.substr(0, slash);

    void *core = dlopen(core_path, RTLD_LAZY);
    if (!core) {
        fprintf(stderr, "cannot open %s: %s\n", core_path, dlerror());
        return 1;
    }

    typedef void (*set_environment_t)(retro_environment_t);
    typedef void (*set_video_t)(retro_video_refresh_t);
    typedef void (*set_audio_t)(retro_audio_sample_t);
    typedef void (*set_audio_batch_t)(retro_audio_sample_batch_t);
    typedef void (*set_input_poll_t)(retro_input_poll_t);
    typedef void (*set_input_state_t)(retro_input_state_t);
    typedef void (*void_call_t)(void);
    typedef bool (*load_game_t)(const struct retro_game_info *);
    typedef void (*av_info_t)(struct retro_system_av_info *);
    typedef void *(*memory_data_t)(unsigned);
    typedef size_t (*memory_size_t)(unsigned);

    resolve<set_environment_t>(core, "retro_set_environment")(environment);
    resolve<set_video_t>(core, "retro_set_video_refresh")(video_refresh);
    resolve<set_audio_t>(core, "retro_set_audio_sample")(audio_sample);
    resolve<set_audio_batch_t>(core, "retro_set_audio_sample_batch")(audio_sample_batch);
    resolve<set_input_poll_t>(core, "retro_set_input_poll")(input_poll);
    resolve<set_input_state_t>(core, "retro_set_input_state")(input_state);
    resolve<void_call_t>(core, "retro_init")();

    std::vector<unsigned char> image;
    if (!read_file(rom_path, image)) {
        fprintf(stderr, "cannot read %s\n", rom_path);
        return 1;
    }

    struct retro_game_info info;
    memset(&info, 0, sizeof(info));
    info.path = rom_path;
    info.data = image.data();
    info.size = image.size();

    if (!resolve<load_game_t>(core, "retro_load_game")(&info)) {
        fprintf(stderr, "the core refused %s\n", rom_path);
        return 1;
    }

    memory_data_t memory_data = resolve<memory_data_t>(core, "retro_get_memory_data");
    memory_size_t memory_size = resolve<memory_size_t>(core, "retro_get_memory_size");
    void *sram = memory_data(RETRO_MEMORY_SAVE_RAM);
    const size_t sram_bytes = memory_size(RETRO_MEMORY_SAVE_RAM);

    std::vector<unsigned char> saved;
    if (sram && sram_bytes && read_file(sram_path.c_str(), saved) && saved.size() == sram_bytes) {
        memcpy(sram, saved.data(), sram_bytes);
        printf("loaded %zu bytes of save RAM from %s\n", sram_bytes, sram_path.c_str());
    }

    struct retro_system_av_info av;
    memset(&av, 0, sizeof(av));
    resolve<av_info_t>(core, "retro_get_system_av_info")(&av);

    const unsigned width = av.geometry.base_width ? av.geometry.base_width : SCREEN_WIDTH;
    const unsigned height = av.geometry.base_height ? av.geometry.base_height : SCREEN_HEIGHT;
    const double fps = av.timing.fps > 1.0 ? av.timing.fps : 60.0;

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO) != 0) {
        fprintf(stderr, "SDL refused to start: %s\n", SDL_GetError());
        return 1;
    }

    window = SDL_CreateWindow("Dungeon Master, no chip", SDL_WINDOWPOS_CENTERED,
                              SDL_WINDOWPOS_CENTERED, (int)width * scale, (int)height * scale,
                              SDL_WINDOW_SHOWN | SDL_WINDOW_ALLOW_HIGHDPI);
    renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!window || !renderer) {
        fprintf(stderr, "cannot open a window: %s\n", SDL_GetError());
        return 1;
    }
    SDL_RenderSetLogicalSize(renderer, (int)width, (int)height);

    SDL_AudioSpec wanted;
    memset(&wanted, 0, sizeof(wanted));
    wanted.freq = (int)(av.timing.sample_rate > 1000.0 ? av.timing.sample_rate : 32040.0);
    wanted.format = AUDIO_S16SYS;
    wanted.channels = AUDIO_CHANNELS;
    wanted.samples = 512;
    audio_device = SDL_OpenAudioDevice(NULL, 0, &wanted, NULL, 0);
    if (audio_device) {
        SDL_PauseAudioDevice(audio_device, 0);
    }

    printf("running %s at %ux%u, %.2f fps\n", rom_path, width, height, fps);
    printf("arrows move, Z and X are B and A, A and S are Y and X, Q and W are L and R,\n");
    printf("return is start, right shift is select, escape quits and writes save RAM\n");

    void_call_t run = resolve<void_call_t>(core, "retro_run");
    bool running = true;
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) {
                running = false;
            } else if (event.type == SDL_KEYDOWN && event.key.keysym.sym == SDLK_ESCAPE) {
                running = false;
            }
        }
        run();
    }

    if (sram && sram_bytes) {
        FILE *out = fopen(sram_path.c_str(), "wb");
        if (out) {
            fwrite(sram, 1, sram_bytes, out);
            fclose(out);
            printf("wrote %zu bytes of save RAM to %s\n", sram_bytes, sram_path.c_str());
        }
    }

    resolve<void_call_t>(core, "retro_unload_game")();
    resolve<void_call_t>(core, "retro_deinit")();
    SDL_Quit();
    return 0;
}
