import platform
import subprocess

from platform_utils import detect_gpu_profile, get_creationflags


def detect_gpu():
    """Detect GPU and return encoder metadata for the frame composer."""
    info = {
        "type": "cpu",
        "name": "Только Процессор (CPU)",
        "encoder": "libx264",
        "available": False,
    }

    platform_profile = detect_gpu_profile()
    if platform_profile.get("available"):
        return {
            "type": platform_profile.get("type", "cpu"),
            "name": platform_profile.get("name", info["name"]),
            "encoder": platform_profile.get("encoder", "libx264"),
            "available": True,
        }

    if platform.system() != "Windows":
        return info

    try:
        cmd = 'powershell "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"'
        output = subprocess.check_output(
            cmd,
            shell=True,
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=get_creationflags(),
        ).strip()

        lines = [line.strip() for line in output.split("\n") if line.strip()]

        for name in lines:
            lowered = name.lower()
            if "nvidia" in lowered or "geforce" in lowered or "rtx" in lowered or "gtx" in lowered:
                info.update({"name": name, "encoder": "h264_nvenc", "type": "nvidia", "available": True})
                return info

        for name in lines:
            lowered = name.lower()
            if "amd" in lowered or "radeon" in lowered or "rx " in lowered:
                info.update({"name": name, "encoder": "h264_amf", "type": "amd", "available": True})
                return info

        for name in lines:
            lowered = name.lower()
            if "intel" in lowered or "uhd" in lowered or "hd graphics" in lowered or "iris" in lowered or "arc" in lowered:
                info.update({"name": name, "encoder": "h264_qsv", "type": "intel", "available": True})
                return info

        if lines:
            info["name"] = lines[0]
    except Exception as e:
        print(f"[Frame Composer] GPU detect error: {e}")

    return info
