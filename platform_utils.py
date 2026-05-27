import os
import platform
import shutil
import subprocess


_FFMPEG_ENCODER_CACHE = {}
_FFMPEG_ENCODER_RUNTIME_CACHE = {}


def get_system_name():
    return platform.system()


def is_windows():
    return get_system_name() == "Windows"


def is_macos():
    return get_system_name() == "Darwin"


def get_creationflags():
    if is_windows() and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0


def run_detached(command, **kwargs):
    kwargs.setdefault("creationflags", get_creationflags())
    return subprocess.run(command, **kwargs)


def popen_detached(command, **kwargs):
    kwargs.setdefault("creationflags", get_creationflags())
    return subprocess.Popen(command, **kwargs)


def open_path(path):
    if is_windows():
        os.startfile(path)
        return
    command = ["open", path] if is_macos() else ["xdg-open", path]
    run_detached(command, check=False)


def reveal_in_file_manager(path):
    normalized = os.path.normpath(path)
    if is_windows():
        if os.path.isfile(normalized):
            run_detached(["explorer", "/select,", normalized], check=False)
        else:
            open_path(normalized)
        return
    if is_macos():
        command = ["open", "-R", normalized] if os.path.isfile(normalized) else ["open", normalized]
        run_detached(command, check=False)
        return
    open_path(os.path.dirname(normalized) if os.path.isfile(normalized) else normalized)


def get_system_font_dirs():
    if is_windows():
        return [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
        ]
    if is_macos():
        return [
            "/Library/Fonts",
            "/System/Library/Fonts",
            os.path.expanduser("~/Library/Fonts"),
        ]
    return [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
    ]


def list_system_fonts():
    fonts = set()
    for font_dir in get_system_font_dirs():
        if not os.path.isdir(font_dir):
            continue
        try:
            for entry in os.listdir(font_dir):
                if entry.lower().endswith((".ttf", ".otf", ".ttc", ".woff", ".woff2")):
                    fonts.add(entry)
        except OSError:
            continue
    return sorted(fonts)


def find_font_file(font_filename):
    target = font_filename.lower()
    for font_dir in get_system_font_dirs():
        if not os.path.isdir(font_dir):
            continue
        direct_match = os.path.join(font_dir, font_filename)
        if os.path.exists(direct_match):
            return direct_match
        try:
            for entry in os.listdir(font_dir):
                if entry.lower() == target:
                    return os.path.join(font_dir, entry)
        except OSError:
            continue
    return None


def command_exists(command_name):
    return shutil.which(command_name) is not None


def ffmpeg_supports_encoder(encoder_name):
    if encoder_name in _FFMPEG_ENCODER_CACHE:
        return _FFMPEG_ENCODER_CACHE[encoder_name]

    if not command_exists("ffmpeg"):
        _FFMPEG_ENCODER_CACHE[encoder_name] = False
        return False

    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            creationflags=get_creationflags(),
            timeout=15,
        )
        output = (result.stdout or "") + (result.stderr or "")
        supported = encoder_name in output
    except Exception:
        supported = False

    _FFMPEG_ENCODER_CACHE[encoder_name] = supported
    return supported


def ffmpeg_encoder_runtime_works(encoder_name):
    if encoder_name in _FFMPEG_ENCODER_RUNTIME_CACHE:
        return _FFMPEG_ENCODER_RUNTIME_CACHE[encoder_name]

    if not ffmpeg_supports_encoder(encoder_name):
        _FFMPEG_ENCODER_RUNTIME_CACHE[encoder_name] = False
        return False

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-y",
                "-f", "lavfi", "-i", "color=c=black:s=16x16:d=0.1",
                "-frames:v", "1",
                "-c:v", encoder_name,
                "-f", "null", "-"
            ],
            capture_output=True,
            text=True,
            creationflags=get_creationflags(),
            timeout=20,
        )
        works = result.returncode == 0
    except Exception:
        works = False

    _FFMPEG_ENCODER_RUNTIME_CACHE[encoder_name] = works
    return works


def detect_gpu_profile():
    info = {
        "name": "Only CPU",
        "encoder": "libx264",
        "hwaccel": None,
        "type": "cpu",
        "available": False,
    }

    if is_macos():
        machine = platform.machine().lower()
        if ffmpeg_encoder_runtime_works("h264_videotoolbox"):
            info.update({
                "name": "Apple Silicon" if machine in {"arm64", "aarch64"} else "Apple GPU",
                "encoder": "h264_videotoolbox",
                "hwaccel": "videotoolbox",
                "type": "apple",
                "available": True,
            })
        else:
            info.update({
                "name": "Apple Silicon (CPU fallback)" if machine in {"arm64", "aarch64"} else "Apple CPU fallback",
                "encoder": "libx264",
                "hwaccel": None,
                "type": "cpu",
                "available": False,
            })

    return info
