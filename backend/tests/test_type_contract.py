"""Guard: the hand-written TS domain types mirror the Pydantic models 1:1.

FastAPI's models (backend/app/models) and the frontend's hand-written types
(src/types/*.ts) must agree on field names. This catches the drift that creeps
in when a field is added to one side only — the gap that an OpenAPI-generated
client would otherwise close (openapi-typescript can't be a clean devDep yet: it
peers on TypeScript 5.x while the app is on 6.x).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.models import media, music

_TYPES_DIR = Path(__file__).resolve().parents[2] / "src" / "types"


def _ts_interface_fields(name: str, source: str) -> set[str]:
    match = re.search(rf"export interface {name} \{{(.*?)\n\}}", source, re.DOTALL)
    assert match, f"interface {name} not found"
    return set(
        re.findall(r"^\s*([a-z_][a-zA-Z0-9_]*)\??:", match.group(1), re.MULTILINE)
    )


# (Pydantic model, TS interface name, TS file) that must agree on field names.
_PAIRS: list[tuple[type[BaseModel], str, str]] = [
    (media.MediaFormat, "MediaFormat", "download.ts"),
    (media.VideoInfo, "VideoInfo", "download.ts"),
    (media.PlaylistEntry, "PlaylistEntry", "download.ts"),
    (media.PlaylistInfo, "PlaylistInfo", "download.ts"),
    (media.DownloadRequest, "DownloadRequest", "download.ts"),
    (media.HistoryEntry, "HistoryEntry", "download.ts"),
    (media.AppSettings, "AppSettings", "download.ts"),
    (media.HistoryStats, "DownloadStats", "download.ts"),  # TS interface renamed
    (media.VersionInfo, "VersionInfo", "download.ts"),
    (music.MusicTrack, "MusicTrack", "music.ts"),
    (music.MusicImportInfo, "MusicImportInfo", "music.ts"),
]


@pytest.mark.parametrize("model, ts_name, ts_file", _PAIRS)
def test_ts_type_matches_pydantic(model, ts_name, ts_file):
    source = (_TYPES_DIR / ts_file).read_text(encoding="utf-8")
    py_fields = set(model.model_fields.keys())
    ts_fields = _ts_interface_fields(ts_name, source)
    assert py_fields == ts_fields, (
        f"{ts_name} drift — only in Pydantic: {py_fields - ts_fields}; "
        f"only in TS: {ts_fields - py_fields}"
    )
