"""Local configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NaverCredentials:
    user_id: str | None
    password: str | None

    @property
    def is_complete(self) -> bool:
        return bool(self.user_id and self.password)

    @property
    def masked_user_id(self) -> str:
        if not self.user_id:
            return "(not set)"
        if len(self.user_id) <= 3:
            return self.user_id[0] + "**"
        return self.user_id[:3] + "***"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        values[key] = value
    return values


def load_naver_credentials(env_path: Path | None = None) -> NaverCredentials:
    env_values = parse_env_file(env_path or project_root() / ".env")
    user_id = os.environ.get("NAVER_ID") or env_values.get("NAVER_ID")
    password = os.environ.get("NAVER_PASSWORD") or env_values.get("NAVER_PASSWORD")
    return NaverCredentials(user_id=user_id, password=password)
