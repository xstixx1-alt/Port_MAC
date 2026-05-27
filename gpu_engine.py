import platform
import subprocess

from platform_utils import detect_gpu_profile, ffmpeg_encoder_runtime_works, get_creationflags


def detect_gpu():
    """Detect GPU and choose the safest FFmpeg encoder for the current OS."""
    gpu_info = {
        "name": "Only CPU",
        "encoder": "libx264",
        "hwaccel": None,
        "type": "cpu",
    }

    platform_profile = detect_gpu_profile()
    if platform_profile.get("available"):
        return platform_profile

    if platform.system() != "Windows":
        return gpu_info

    try:
        output = subprocess.check_output(
            'powershell "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"',
            shell=True,
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=get_creationflags(),
        ).lower()

        if "nvidia" in output:
            gpu_info["name"] = [line.strip() for line in output.split("\n") if "nvidia" in line][0].upper()
            if ffmpeg_encoder_runtime_works("h264_nvenc"):
                gpu_info["encoder"] = "h264_nvenc"
                gpu_info["hwaccel"] = "cuda"
                gpu_info["type"] = "nvidia"
            else:
                gpu_info["encoder"] = "libx264"
                gpu_info["hwaccel"] = None
                gpu_info["type"] = "cpu"
        elif "amd" in output or "radeon" in output:
            candidates = [line.strip() for line in output.split("\n") if "amd" in line or "radeon" in line]
            gpu_info["name"] = candidates[0].upper() if candidates else "AMD GPU"
            if ffmpeg_encoder_runtime_works("h264_amf"):
                gpu_info["encoder"] = "h264_amf"
                gpu_info["hwaccel"] = "d3d11va"
                gpu_info["type"] = "amd"
            else:
                gpu_info["encoder"] = "libx264"
                gpu_info["hwaccel"] = None
                gpu_info["type"] = "cpu"
        elif "intel" in output or "hd graphics" in output or "uhd" in output:
            candidates = [line.strip() for line in output.split("\n") if "intel" in line]
            gpu_info["name"] = candidates[0].upper() if candidates else "INTEL GPU"
            if ffmpeg_encoder_runtime_works("h264_qsv"):
                gpu_info["encoder"] = "h264_qsv"
                gpu_info["hwaccel"] = "qsv"
                gpu_info["type"] = "intel"
            else:
                gpu_info["encoder"] = "libx264"
                gpu_info["hwaccel"] = None
                gpu_info["type"] = "cpu"
    except Exception as e:
        print(f"GPU detection error: {e}")

    return gpu_info


_cached_gpu_info = None


def get_gpu_info():
    global _cached_gpu_info
    if _cached_gpu_info is None:
        _cached_gpu_info = detect_gpu()
    return _cached_gpu_info
