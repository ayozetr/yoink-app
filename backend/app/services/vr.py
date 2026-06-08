"""VR (180°/360°) detection + spatial-media tagging.

Sources don't expose a "this is VR" flag through yt-dlp, so detection is a
heuristic over the metadata (known immersive studios, textual markers like
``180``/``360``/``SBS``). The user can always confirm or override it from the
preview card — see the toggle wired through :class:`DownloadRequest`.

When a download is marked VR, two independent things make a player
(Quest/DeoVR/Heresphere/Pigasus) treat it as immersive:

1. a **projection suffix** in the file name (e.g. ``…_180x180_3dh.mp4``), which
   the major VR players parse by convention. It is 180-aware, needs no
   dependencies, and is the robust primary mechanism; and
2. **Spherical Video V2** box metadata (``st3d`` + ``sv3d``) injected into the
   MP4 container, for players that read the boxes instead of the name.

The box injection is best-effort and atomic: the already-complete download is
rewritten to a temp file and swapped in only on success, so a failure can never
damage the user's video — it just keeps the (already working) name suffix.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

# Stereo + projection layouts we recognise. The default for an unqualified VR
# hit is 180° side-by-side, by far the most common immersive layout.
VRLayout = Literal[
    "180_sbs",
    "180_tb",
    "180_mono",
    "360_sbs",
    "360_tb",
    "360_mono",
    "fisheye190",
    "fisheye200",
    "mkx200",
    "mkx220",
    "rf52",
]

DEFAULT_LAYOUT: VRLayout = "180_sbs"

# Stereo modes per the Spherical Video V2 st3d box (0=mono, 1=TB, 2=LR).
_STEREO_MONO, _STEREO_TB, _STEREO_LR = 0, 1, 2

# Per-layout: the file-name suffix understood by DeoVR/Heresphere/Quest, the
# st3d stereo mode, and whether it maps to an equirectangular sv3d box. Fisheye
# variants (incl. MKX/RF52) are not equirectangular — the players detect them by
# the name suffix — so they carry the suffix + stereo (st3d) only.
_LAYOUTS: dict[str, dict[str, object]] = {
    "180_sbs": {"suffix": "_180x180_3dh", "stereo": _STEREO_LR, "equirect": True, "deg": 180},
    "180_tb": {"suffix": "_180x180_3dv", "stereo": _STEREO_TB, "equirect": True, "deg": 180},
    "180_mono": {"suffix": "_180x180", "stereo": _STEREO_MONO, "equirect": True, "deg": 180},
    "360_sbs": {"suffix": "_360_3dh", "stereo": _STEREO_LR, "equirect": True, "deg": 360},
    "360_tb": {"suffix": "_360_3dv", "stereo": _STEREO_TB, "equirect": True, "deg": 360},
    "360_mono": {"suffix": "_360", "stereo": _STEREO_MONO, "equirect": True, "deg": 360},
    "fisheye190": {"suffix": "_FISHEYE190", "stereo": _STEREO_LR, "equirect": False, "deg": 190},
    "fisheye200": {"suffix": "_FISHEYE200", "stereo": _STEREO_LR, "equirect": False, "deg": 200},
    "mkx200": {"suffix": "_MKX200", "stereo": _STEREO_LR, "equirect": False, "deg": 200},
    "mkx220": {"suffix": "_MKX220", "stereo": _STEREO_LR, "equirect": False, "deg": 220},
    "rf52": {"suffix": "_RF52", "stereo": _STEREO_LR, "equirect": False, "deg": 190},
}


def normalize_layout(layout: str | None) -> VRLayout:
    """Coerce an arbitrary value to a known layout (defaults to 180° SBS)."""
    return layout if layout in _LAYOUTS else DEFAULT_LAYOUT  # type: ignore[return-value]


def filename_suffix(layout: str | None) -> str:
    """Projection suffix to append to the file stem (before the extension)."""
    return str(_LAYOUTS[normalize_layout(layout)]["suffix"])


# ── Detection ──────────────────────────────────────────────────────────────

# Immersive studios whose uploads are VR. Matched as a substring against the
# uploader / uploader_id / channel fields (case-insensitive). Not exhaustive —
# anything missed just falls back to the manual toggle in the UI.
_VR_STUDIOS: tuple[str, ...] = (
    "virtualtaboo",
    "czechvr",
    "vrbangers",
    "vrbtrans",
    "wankzvr",
    "badoinkvr",
    "naughtyamericavr",
    "sexbabesvr",
    "realjamvr",
    "vrhush",
    "vrconk",
    "swallowbay",
    "tmwvrnet",
    "virtualrealporn",
    "stasyqvr",
    "18vr",
    "vrcosplayx",
    "kinkvr",
    "milfvr",
    "herpovr",
    "wetvr",
    "vrlatina",
    "sinsvr",
    "groobyvr",
    "pervrt",
    "vrintimacy",
    "vrporn",
    "slroriginals",
    "sexlikereal",
    "povr",
)

# Textual markers that, alone, signal immersive content. Word-bounded so "180"
# inside a longer number doesn't match, plus a few multi-word phrases. Bare "tb"
# is intentionally excluded here (too generic) — it only informs layout below.
_VR_MARKER = re.compile(
    r"\b(vr180|vr|180|360|sbs|mkx\d*|mkz\d*|rf52|fisheye\d*|domeplus)\b"
    r"|virtual reality|side[ -]by[ -]side|top[ -]bottom|over[ -]under",
    re.IGNORECASE,
)
_DEG360 = re.compile(r"\b360\b", re.IGNORECASE)
_DEG180 = re.compile(r"\b(180|vr180)\b", re.IGNORECASE)
_STEREO_TB_MARK = re.compile(r"\btb\b|top[ -]bottom|over[ -]under|3dv", re.IGNORECASE)
_FISHEYE_MARK = re.compile(r"fisheye|\bmkx\d*\b|\bmkz\d*\b|\brf52\b|domeplus", re.IGNORECASE)
_MONO_MARK = re.compile(r"\bmono\b|monoscopic", re.IGNORECASE)
# Specific fisheye camera/projection markers, most-specific first.
_MKX220_MARK = re.compile(r"mkx\s*220", re.IGNORECASE)
_MKX200_MARK = re.compile(r"mkx\s*200", re.IGNORECASE)
_RF52_MARK = re.compile(r"\brf\s?52\b|rf5\.2|canon\s+dual", re.IGNORECASE)
_FISHEYE200_MARK = re.compile(r"fisheye\s*200|\b200°", re.IGNORECASE)


def _fisheye_layout(blob: str) -> VRLayout:
    """Distinguish the fisheye family (MKX/RF52/fisheye200) from default 190."""
    if _MKX220_MARK.search(blob):
        return "mkx220"
    if _MKX200_MARK.search(blob):
        return "mkx200"
    if _RF52_MARK.search(blob):
        return "rf52"
    if _FISHEYE200_MARK.search(blob):
        return "fisheye200"
    return "fisheye190"


def _studio_hit(info: dict) -> bool:
    """True if the uploader/channel matches a known immersive studio."""
    for key in ("uploader_id", "uploader", "channel", "channel_id"):
        value = info.get(key)
        if isinstance(value, str):
            low = value.lower()
            if any(studio in low for studio in _VR_STUDIOS):
                return True
    return False


def _text_blob(info: dict) -> str:
    """Join the human-readable metadata fields into one lowercase haystack."""
    parts: list[str] = []
    for key in ("title", "description", "uploader", "uploader_id"):
        value = info.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("tags", "categories"):
        value = info.get(key)
        if isinstance(value, list):
            parts.extend(str(v) for v in value if isinstance(v, str))
    return " ".join(parts).lower()


def _best_video_aspect(info: dict) -> float | None:
    """Width/height of the highest-resolution video format, or None.

    Many extractors omit ``width`` (it came back None for the case that
    motivated this), so this is best-effort and absent for those sources.
    """
    formats = info.get("formats")
    if not isinstance(formats, list):
        return None
    best_height = 0
    best_aspect: float | None = None
    for fmt in formats:
        if not isinstance(fmt, dict):
            continue
        width, height = fmt.get("width"), fmt.get("height")
        if (
            isinstance(width, (int, float))
            and isinstance(height, (int, float))
            and width > 0
            and height > 0
            and height > best_height
        ):
            best_height, best_aspect = height, width / height
    return best_aspect


def _infer_layout(blob: str, aspect: float | None = None) -> VRLayout:
    """Pick the most likely layout from text markers, refined by aspect ratio.

    Text wins when explicit (fisheye / 360 / top-bottom). When the text is
    silent about the stereo split, the frame aspect disambiguates: a ~4:1 frame
    is two equirects side-by-side (360 SBS), and a ~1:1 frame is stacked
    (top-bottom). A ~2:1 frame is left as the 180 SBS / 360 default since both
    share it. Aspect is often unavailable (no width) — then it's pure text.
    """
    tb = bool(_STEREO_TB_MARK.search(blob))
    if _FISHEYE_MARK.search(blob):
        return _fisheye_layout(blob)
    deg360 = bool(_DEG360.search(blob)) and not bool(_DEG180.search(blob))
    if _MONO_MARK.search(blob):
        return "360_mono" if deg360 else "180_mono"
    if aspect is not None:
        if aspect >= 3.0:  # ~4:1 → two equirects side by side
            return "360_sbs"
        if aspect <= 1.3:  # ~1:1 → stacked (top-bottom)
            tb = True
        elif deg360 and not tb:  # ~2:1 single equirect under a 360 tag → mono
            return "360_mono"
    if deg360:
        return "360_tb" if tb else "360_sbs"
    # Default to 180° (the overwhelmingly common immersive layout).
    return "180_tb" if tb else "180_sbs"


def detect_vr(info: dict) -> tuple[bool, VRLayout]:
    """Heuristically decide whether a media item is VR and guess its layout.

    Returns ``(is_vr, layout)``. ``layout`` is always a valid suggestion (used
    to seed the preview card) even when ``is_vr`` is False, so the manual toggle
    has a sensible default. Detection leans on studio + textual signals (not
    resolution, which would false-positive on plain 4K); the frame aspect ratio
    only refines the *layout* guess, never the is-VR decision.
    """
    blob = _text_blob(info)
    is_vr = _studio_hit(info) or bool(_VR_MARKER.search(blob))
    return is_vr, _infer_layout(blob, _best_video_aspect(info))


# ── Spherical Video V2 box construction ────────────────────────────────────

# 180° crops the front hemisphere out of a full equirect projection: drop 25%
# off the left and right edges (keep the middle 180°), full vertical. As a
# 0.32 fixed-point fraction, 0.25 == 0x40000000.
_BOUND_QUARTER = 0x40000000


def _box(box_type: bytes, payload: bytes) -> bytes:
    """Assemble a 32-bit ISO-BMFF box: size + type + payload."""
    return (8 + len(payload)).to_bytes(4, "big") + box_type + payload


def _spherical_boxes(layout: str) -> bytes:
    """Build the ``st3d`` (+ ``sv3d`` for equirect) boxes for a layout."""
    spec = _LAYOUTS[normalize_layout(layout)]
    stereo = int(spec["stereo"])  # type: ignore[arg-type]

    # st3d: FullBox(version=0,flags=0) + stereo_mode (1 byte).
    st3d = _box(b"st3d", b"\x00\x00\x00\x00" + bytes([stereo]))

    if not spec["equirect"]:
        # Fisheye isn't equirectangular; the name suffix carries it. Stereo
        # alone (st3d) still helps players that read it.
        return st3d

    half = spec["deg"] == 180
    bound = _BOUND_QUARTER if half else 0
    # equi: FullBox + bounds top/bottom/left/right as 0.32 fixed-point uint32.
    equi_payload = b"\x00\x00\x00\x00" + b"".join(
        v.to_bytes(4, "big") for v in (0, 0, bound, bound)
    )
    equi = _box(b"equi", equi_payload)
    # prhd: FullBox + pose yaw/pitch/roll (16.16 fixed int32), all zero.
    prhd = _box(b"prhd", b"\x00\x00\x00\x00" + b"\x00" * 12)
    proj = _box(b"proj", prhd + equi)
    # svhd: FullBox + null-terminated metadata source string.
    svhd = _box(b"svhd", b"\x00\x00\x00\x00" + b"Yoink\x00")
    sv3d = _box(b"sv3d", svhd + proj)
    return st3d + sv3d


# ── MP4 box walking + injection ────────────────────────────────────────────

_U32_MAX = 0xFFFFFFFF


class _SphericalInjectError(Exception):
    """Raised internally when the MP4 can't be safely tagged (caller swallows)."""


def _read_header(buf: bytes, pos: int) -> tuple[str, int, int]:
    """Return (type, total_size, header_size) for the box starting at ``pos``."""
    if pos + 8 > len(buf):
        raise _SphericalInjectError("truncated box header")
    size = int.from_bytes(buf[pos : pos + 4], "big")
    box_type = buf[pos + 4 : pos + 8].decode("latin1")
    header = 8
    if size == 1:
        size = int.from_bytes(buf[pos + 8 : pos + 16], "big")
        header = 16
    elif size == 0:
        size = len(buf) - pos
    if size < header or pos + size > len(buf):
        raise _SphericalInjectError("box size out of range")
    return box_type, size, header


def _iter_children(
    buf: bytes, start: int, end: int, skip: int
) -> list[tuple[str, int, int, int]]:
    """List child boxes in ``[start+skip, end)`` as (type, offset, size, hsize)."""
    out: list[tuple[str, int, int, int]] = []
    pos = start + skip
    while pos + 8 <= end:
        box_type, size, header = _read_header(buf, pos)
        out.append((box_type, pos, size, header))
        pos += size
    return out


def _find(
    buf: bytes, start: int, end: int, want: str, skip: int
) -> tuple[str, int, int, int] | None:
    """First direct child of the given type, or None."""
    for child in _iter_children(buf, start, end, skip):
        if child[0] == want:
            return child
    return None


def _locate_video_sample_entry(
    buf: bytes,
) -> tuple[int, list[tuple[int, int, int]], list[tuple[int, int, int]]]:
    """Find the injection point and the boxes whose sizes must grow.

    Returns ``(insert_offset, ancestors, chunk_offset_boxes)`` where:
      * ``insert_offset`` is the byte position right after the video sample
        entry's existing children (where st3d/sv3d get appended);
      * ``ancestors`` is a list of ``(offset, size, header_size)`` for every box
        that fully contains the insertion point (sample entry → moov);
      * ``chunk_offset_boxes`` lists every ``stco``/``co64`` box across all
        traks, as ``(offset, size, header_size)``, for offset repair.

    Raises :class:`_SphericalInjectError` if the structure isn't what we expect.
    """
    moov = _find(buf, 0, len(buf), "moov", 0)
    if moov is None:
        raise _SphericalInjectError("no moov")
    _, moov_off, moov_size, moov_hdr = moov
    moov_end = moov_off + moov_size

    # Fragmented MP4 (moof/mvex): media lives in fragments whose chunk offsets
    # sit in tfhd/trun (often absolute base_data_offsets) that we don't repair —
    # growing the moov would shift the fragments and corrupt the file. `mvex`
    # inside moov is mandatory for fragmented files, so bail safely (the file
    # keeps only the projection name suffix, which is fine).
    if _find(buf, moov_off, moov_end, "mvex", moov_hdr) is not None:
        raise _SphericalInjectError("fragmented mp4 (mvex)")

    insert: int | None = None
    ancestors: list[tuple[int, int, int]] = []
    chunk_boxes: list[tuple[int, int, int]] = []

    for typ, trak_off, trak_size, trak_hdr in _iter_children(
        buf, moov_off, moov_end, moov_hdr
    ):
        if typ != "trak":
            continue
        trak_end = trak_off + trak_size
        mdia = _find(buf, trak_off, trak_end, "mdia", trak_hdr)
        if mdia is None:
            continue
        _, mdia_off, mdia_size, mdia_hdr = mdia
        mdia_end = mdia_off + mdia_size
        minf = _find(buf, mdia_off, mdia_end, "minf", mdia_hdr)
        if minf is None:
            continue
        _, minf_off, minf_size, minf_hdr = minf
        minf_end = minf_off + minf_size
        stbl = _find(buf, minf_off, minf_end, "stbl", minf_hdr)
        if stbl is None:
            continue
        _, stbl_off, stbl_size, stbl_hdr = stbl
        stbl_end = stbl_off + stbl_size

        # Every trak's chunk-offset table needs repairing if the moov shifts.
        for name in ("stco", "co64"):
            box = _find(buf, stbl_off, stbl_end, name, stbl_hdr)
            if box is not None:
                chunk_boxes.append((box[1], box[2], box[3]))

        # Only the video trak gets the spherical boxes.
        hdlr = _find(buf, mdia_off, mdia_end, "hdlr", mdia_hdr)
        if hdlr is None:
            continue
        h_off, h_hdr = hdlr[1], hdlr[3]
        # hdlr payload: version/flags(4) + pre_defined(4) + handler_type(4) + …
        handler = buf[h_off + h_hdr + 8 : h_off + h_hdr + 12]
        if handler != b"vide" or insert is not None:
            continue

        stsd = _find(buf, stbl_off, stbl_end, "stsd", stbl_hdr)
        if stsd is None:
            raise _SphericalInjectError("no stsd")
        _, stsd_off, _, stsd_hdr = stsd
        # stsd is a FullBox (4) + entry_count (4); the first sample entry follows.
        entry_count = int.from_bytes(
            buf[stsd_off + stsd_hdr + 4 : stsd_off + stsd_hdr + 8], "big"
        )
        if entry_count != 1:
            # Spherical V2 assumes a single video sample entry. With more than
            # one, our insertion point lands *between* entries (not inside the
            # entry's child boxes), which would corrupt stsd — skip safely.
            raise _SphericalInjectError("stsd has multiple sample entries")
        se_off = stsd_off + stsd_hdr + 8
        _, se_size, se_hdr = _read_header(buf, se_off)
        insert = se_off + se_size
        ancestors = [
            (se_off, se_size, se_hdr),
            (stsd_off, stsd[2], stsd_hdr),
            (stbl_off, stbl_size, stbl_hdr),
            (minf_off, minf_size, minf_hdr),
            (mdia_off, mdia_size, mdia_hdr),
            (trak_off, trak_size, trak_hdr),
            (moov_off, moov_size, moov_hdr),
        ]

    if insert is None:
        raise _SphericalInjectError("no video sample entry")
    return insert, ancestors, chunk_boxes


def _already_spherical(buf: bytes, ancestors: list[tuple[int, int, int]]) -> bool:
    """True if the video sample entry already carries an sv3d/st3d box."""
    se_off, se_size, _ = ancestors[0]
    return b"sv3d" in buf[se_off : se_off + se_size] or (
        b"st3d" in buf[se_off : se_off + se_size]
    )


def _patch_size(buf: bytearray, off: int, size: int, hsize: int, delta: int) -> None:
    """Grow a box's size field in place by ``delta`` (32- or 64-bit)."""
    new = size + delta
    if hsize == 16:
        buf[off + 8 : off + 16] = new.to_bytes(8, "big")
    elif new > _U32_MAX:
        raise _SphericalInjectError("box would exceed 32-bit size")
    else:
        buf[off : off + 4] = new.to_bytes(4, "big")


def _patch_chunk_offsets(
    buf: bytearray, box: tuple[int, int, int], threshold: int, delta: int
) -> None:
    """Shift chunk offsets at/after ``threshold`` by ``delta`` (stco/co64).

    ``box`` is located by its position within ``buf`` (the moov buffer), but the
    stored offset *values* are absolute file offsets, so they're compared
    against the absolute ``threshold`` (where bytes are being inserted).
    """
    off, size, hsize = box
    box_type = bytes(buf[off + 4 : off + 8])
    entry_size = 8 if box_type == b"co64" else 4
    count = int.from_bytes(buf[off + hsize + 4 : off + hsize + 8], "big")
    pos = off + hsize + 8
    end = off + size
    for _ in range(count):
        if pos + entry_size > end:
            break
        value = int.from_bytes(buf[pos : pos + entry_size], "big")
        if value >= threshold:
            value += delta
            if entry_size == 4 and value > _U32_MAX:
                raise _SphericalInjectError("chunk offset would exceed 32 bits")
            buf[pos : pos + entry_size] = value.to_bytes(entry_size, "big")
        pos += entry_size


# Cap the moov we'll read into RAM. Real moov boxes are metadata (KBs–low MBs);
# anything larger is pathological and we'd rather skip tagging than load it.
_MAX_MOOV = 256 * 1024 * 1024
_COPY_CHUNK = 1024 * 1024


def _read_moov(f, filesize: int) -> tuple[int, bytes]:
    """Locate the top-level moov by seeking headers; return (offset, bytes)."""
    pos = 0
    while pos + 8 <= filesize:
        f.seek(pos)
        head = f.read(16)
        if len(head) < 8:
            break
        size = int.from_bytes(head[:4], "big")
        box_type = head[4:8]
        header = 8
        if size == 1:
            if len(head) < 16:
                raise _SphericalInjectError("truncated largesize header")
            size = int.from_bytes(head[8:16], "big")
            header = 16
        elif size == 0:
            size = filesize - pos
        if size < header or pos + size > filesize:
            raise _SphericalInjectError("top-level box out of range")
        if box_type == b"moov":
            if size > _MAX_MOOV:
                raise _SphericalInjectError("moov too large")
            f.seek(pos)
            return pos, f.read(size)
        pos += size
    raise _SphericalInjectError("no moov")


def _copy_range(src, dst, start: int, end: int) -> None:
    """Stream-copy ``src[start:end]`` to ``dst`` in bounded-size chunks.

    Raises :class:`_SphericalInjectError` on a short read (the source shrank or
    a partial I/O occurred) so the caller never installs a truncated file.
    """
    src.seek(start)
    remaining = end - start
    while remaining > 0:
        chunk = src.read(min(_COPY_CHUNK, remaining))
        if not chunk:
            raise _SphericalInjectError("short read while copying")
        dst.write(chunk)
        remaining -= len(chunk)


def inject_spherical_metadata(path: Path, layout: str) -> bool:
    """Inject Spherical Video V2 (st3d/sv3d) boxes into an MP4, atomically.

    Streams the file (only the moov is held in memory) so multi-GB VR captures
    don't blow up RAM. Returns True if tagged, False if already tagged or the
    container can't be tagged safely. Never partially writes ``path``: the work
    goes to a sibling temp file swapped in via ``os.replace`` only on success,
    so any failure leaves the already-valid download untouched.
    """
    filesize = path.stat().st_size
    with path.open("rb") as f:
        try:
            moov_off, moov = _read_moov(f, filesize)
            insert, ancestors, chunk_boxes = _locate_video_sample_entry(moov)
            if _already_spherical(moov, ancestors):
                return False
            new_boxes = _spherical_boxes(layout)
            delta = len(new_boxes)

            buf = bytearray(moov)
            for off, size, hsize in ancestors:
                _patch_size(buf, off, size, hsize, delta)
            threshold = moov_off + insert  # absolute insertion point in the file
            for box in chunk_boxes:
                _patch_chunk_offsets(buf, box, threshold, delta)
            new_moov = bytes(buf[:insert]) + new_boxes + bytes(buf[insert:])
        except _SphericalInjectError:
            return False

        tmp = path.with_name(path.name + ".vrtmp")
        expected = filesize + delta
        try:
            with tmp.open("wb") as out:
                _copy_range(f, out, 0, moov_off)
                out.write(new_moov)
                _copy_range(f, out, moov_off + len(moov), filesize)
                # Flush to disk before the swap so a crash can't leave the
                # renamed file pointing at unwritten data.
                out.flush()
                os.fsync(out.fileno())
            # Final guard: the temp must be exactly the original plus the boxes,
            # or we never swap it in (keeps the valid download intact).
            if tmp.stat().st_size != expected:
                raise _SphericalInjectError("output size mismatch")
        except (OSError, _SphericalInjectError):
            tmp.unlink(missing_ok=True)
            return False
    os.replace(tmp, path)
    return True


def apply_vr(path: Path, layout: str) -> Path:
    """Tag a finished video as VR: add the projection suffix + spherical boxes.

    The name suffix is the robust, 180-aware signal every major VR player reads;
    the box injection is an extra for box-reading players and is best-effort. If
    a file with the target name already exists it is left as-is (no clobber).
    Returns the (possibly renamed) path.
    """
    layout = normalize_layout(layout)
    suffix = filename_suffix(layout)

    final = path
    if suffix and suffix not in path.stem:
        target = path.with_name(path.stem + suffix + path.suffix)
        if not target.exists():
            try:
                path.rename(target)
                final = target
            except OSError:
                final = path

    # Box metadata is ISO-BMFF (MP4/MOV share the structure); MKV keeps only the
    # suffix (no st3d/sv3d there). The injector bails safely on anything it can't
    # parse, so this is best-effort even for .mov.
    if final.suffix.lower() in (".mp4", ".m4v", ".mov"):
        try:
            inject_spherical_metadata(final, layout)
        except Exception:  # noqa: BLE001 — never let tagging break a good file.
            pass
    return final
