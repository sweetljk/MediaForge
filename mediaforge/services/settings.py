from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("MEDIAFORGE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return root / "MediaForge"


@dataclass
class Settings:
    ffmpeg: str = ""
    ffprobe: str = ""
    libreoffice: str = ""
    imagemagick: str = ""
    output_dir: str = field(default_factory=lambda: str(Path.home() / "MediaForge Output"))
    temp_dir: str = field(default_factory=lambda: str(data_dir() / "temp"))
    log_dir: str = field(default_factory=lambda: str(data_dir() / "logs"))
    theme: str = "dark"
    concurrency: int = 1
    overwrite: str = "rename"
    default_params: dict = field(default_factory=dict)
    timeout: int = 7200

    @classmethod
    def load(cls) -> Settings:
        path = data_dir() / "settings.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            allowed = {f.name for f in fields(cls)}
            value = cls(**{k: v for k, v in raw.items() if k in allowed})
            if not isinstance(value.default_params, dict):
                value.default_params = {}
            value.default_params = {key: params for key, params in value.default_params.items()
                                    if key in {"video", "audio", "image", "document", "pdf"} and isinstance(params, dict)}
            value.concurrency = max(1, min(3, int(value.concurrency)))
            value.timeout = max(30, int(value.timeout))
            if value.overwrite not in {"rename", "skip", "overwrite"}:
                value.overwrite = "rename"
            if value.theme not in {"light", "dark"}:
                value.theme = "dark"
            for name in ("ffmpeg", "ffprobe", "libreoffice", "imagemagick", "output_dir", "temp_dir", "log_dir"):
                if not isinstance(getattr(value, name), str):
                    raise ValueError("Invalid settings path")
            return value
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

    def save(self) -> None:
        root = data_dir()
        root.mkdir(parents=True, exist_ok=True)
        temporary = root / "settings.json.tmp"
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(root / "settings.json")
