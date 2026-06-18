"""Tests for VR detection + Spherical Video V2 tagging.

The injection tests build synthetic-but-structurally-valid MP4s (ftyp + mdat +
moov in both orders), inject, and re-parse to confirm st3d/sv3d landed in the
video sample entry, every ancestor box grew by exactly the inserted size, chunk
offsets were repaired correctly, and the box tree still fills exactly (no size
drift). They never touch a real file.
"""

from __future__ import annotations

from pathlib import Path

from app.services import vr


# ── Detection ──────────────────────────────────────────────────────────────


def test_detect_vr_known_studio():
    is_vr, layout = vr.detect_vr({"uploader_id": "virtualtaboo", "title": "Some clip"})
    assert is_vr is True
    assert layout == "180_sbs"


def test_detect_vr_title_360():
    # A 360 degree marker only counts as VR alongside a stereo/VR cue.
    is_vr, layout = vr.detect_vr({"title": "Amazing 360 VR experience", "uploader": "x"})
    assert is_vr is True
    assert layout == "360_sbs"


def test_detect_vr_bare_degree_is_not_vr():
    # A lone "180"/"360" with no VR cue is far too common to mean VR.
    for title in ("Xbox 360 retrospective", "Top 180 Workout Songs", "Nikon Z6 360 review"):
        is_vr, _ = vr.detect_vr({"title": title, "uploader": "x"})
        assert is_vr is False, title


def test_detect_vr_top_bottom_360():
    is_vr, layout = vr.detect_vr({"title": "trip 360 top-bottom", "description": ""})
    assert is_vr is True
    assert layout == "360_tb"


def test_detect_vr_fisheye():
    is_vr, layout = vr.detect_vr({"title": "scene MKX200 fisheye", "tags": []})
    assert is_vr is True
    assert layout == "mkx200"  # MKX200 is recognised specifically


def test_detect_vr_tags_marker():
    is_vr, layout = vr.detect_vr({"title": "clip", "tags": ["VR", "180"]})
    assert is_vr is True
    assert layout == "180_sbs"


def test_detect_vr_negative():
    is_vr, layout = vr.detect_vr({"title": "Funny cats compilation", "uploader": "lol"})
    assert is_vr is False
    # Layout is still a sensible default for the manual toggle.
    assert layout == "180_sbs"


def test_infer_layout_aspect_square_is_top_bottom():
    # ~1:1 frame with no stereo marker in the text → inferred as top-bottom.
    info = {"uploader": "czechvr", "title": "clip", "formats": [{"width": 4096, "height": 4096}]}
    is_vr, layout = vr.detect_vr(info)
    assert is_vr is True
    assert layout == "180_tb"


def test_infer_layout_aspect_wide_is_360_sbs():
    # ~4:1 frame → two equirects side by side → 360 SBS.
    info = {"uploader": "wankzvr", "title": "clip", "formats": [{"width": 8192, "height": 2048}]}
    _, layout = vr.detect_vr(info)
    assert layout == "360_sbs"


def test_infer_layout_360_mono_from_2to1_aspect():
    # A "360" title with a single-equirect ~2:1 frame is monoscopic, not SBS.
    info = {"title": "VR 360 roller coaster", "formats": [{"width": 3840, "height": 2048}]}
    is_vr, layout = vr.detect_vr(info)
    assert is_vr is True
    assert layout == "360_mono"


def test_infer_layout_text_beats_aspect():
    # Explicit fisheye marker wins regardless of a square aspect.
    info = {"title": "scene MKX200", "formats": [{"width": 4096, "height": 4096}]}
    _, layout = vr.detect_vr(info)
    assert layout == "mkx200"


def test_infer_layout_no_width_falls_back_to_text():
    # width missing (the real-world case) → aspect is None → pure text default.
    info = {"uploader": "virtualtaboo", "formats": [{"height": 1920}]}
    _, layout = vr.detect_vr(info)
    assert layout == "180_sbs"


def test_build_playlist_detects_vr():
    from app.services.ytdlp_service import _build_playlist

    info = {
        "id": "PL1",
        "title": "Best VR 360 experiences",
        "entries": [{"id": "a", "url": "http://x/a", "title": "clip"}],
    }
    pl = _build_playlist(info)
    assert pl.is_vr is True
    assert pl.vr_layout == "360_sbs"


def test_build_playlist_non_vr():
    from app.services.ytdlp_service import _build_playlist

    pl = _build_playlist({"id": "PL2", "title": "Cooking recipes", "entries": []})
    assert pl.is_vr is False


def test_infer_layout_180_mono():
    info = {"title": "VR 180 monoscopic clip", "uploader": "x"}
    is_vr, layout = vr.detect_vr(info)
    assert is_vr is True
    assert layout == "180_mono"


def test_infer_layout_fisheye_variants():
    assert vr.detect_vr({"title": "scene MKX220 fisheye"})[1] == "mkx220"
    assert vr.detect_vr({"title": "scene MKX200"})[1] == "mkx200"
    assert vr.detect_vr({"title": "Canon RF52 dual fisheye"})[1] == "rf52"
    assert vr.detect_vr({"title": "fisheye 200 clip"})[1] == "fisheye200"
    assert vr.detect_vr({"title": "plain fisheye video"})[1] == "fisheye190"


def test_filename_suffix_mapping():
    assert vr.filename_suffix("180_sbs") == "_180x180_3dh"
    assert vr.filename_suffix("180_mono") == "_180x180"
    assert vr.filename_suffix("360_mono") == "_360"
    assert vr.filename_suffix("mkx200") == "_MKX200"
    assert vr.filename_suffix("rf52") == "_RF52"
    assert vr.filename_suffix("bogus") == "_180x180_3dh"  # falls back to default


def test_fisheye_variants_suffix_only_no_sv3d():
    # MKX/fisheye are not equirectangular: st3d (stereo) but no sv3d projection.
    boxes = vr._spherical_boxes("mkx200")
    assert b"st3d" in boxes and b"sv3d" not in boxes


# ── Synthetic MP4 builders ─────────────────────────────────────────────────


def _box(box_type: bytes, payload: bytes) -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + box_type + payload


def _box_large(box_type: bytes, payload: bytes) -> bytes:
    """A box with a 64-bit largesize header (size==1 + 8-byte size)."""
    total = 16 + len(payload)
    return (1).to_bytes(4, "big") + box_type + total.to_bytes(8, "big") + payload


def _ftyp() -> bytes:
    return _box(b"ftyp", b"isom" + (0).to_bytes(4, "big") + b"isommp42")


def _sample_entry() -> bytes:
    header = b"\x00" * 6 + (1).to_bytes(2, "big")  # reserved + data_ref_index
    header += b"\x00" * 16  # pre_defined + reserved + pre_defined[3]
    header += (1920).to_bytes(2, "big") + (1080).to_bytes(2, "big")
    header += (0x00480000).to_bytes(4, "big") * 2  # horiz/vert resolution
    header += b"\x00" * 4  # reserved
    header += (1).to_bytes(2, "big")  # frame_count
    header += b"\x00" * 32  # compressorname
    header += (24).to_bytes(2, "big") + (0xFFFF).to_bytes(2, "big")  # depth + pre_defined
    assert len(header) == 78
    avcc = _box(b"avcC", b"\x01\x64\x00\x28")
    return _box(b"avc1", header + avcc)


def _hdlr(handler: bytes) -> bytes:
    payload = b"\x00\x00\x00\x00" + b"\x00" * 4 + handler + b"\x00" * 12 + b"\x00"
    return _box(b"hdlr", payload)


def _stco(offsets: list[int]) -> bytes:
    payload = b"\x00\x00\x00\x00" + len(offsets).to_bytes(4, "big")
    payload += b"".join(o.to_bytes(4, "big") for o in offsets)
    return _box(b"stco", payload)


def _stsd(sample_entry: bytes) -> bytes:
    return _box(b"stsd", b"\x00\x00\x00\x00" + (1).to_bytes(4, "big") + sample_entry)


def _co64(offsets: list[int]) -> bytes:
    payload = b"\x00\x00\x00\x00" + len(offsets).to_bytes(4, "big")
    payload += b"".join(o.to_bytes(8, "big") for o in offsets)
    return _box(b"co64", payload)


def _trak(handler: bytes, offsets: list[int]) -> bytes:
    stbl = _box(b"stbl", _stsd(_sample_entry()) + _stco(offsets))
    minf = _box(b"minf", stbl)
    mdia = _box(b"mdia", _hdlr(handler) + minf)
    return _box(b"trak", mdia)


def _trak_co64(handler: bytes, offsets: list[int]) -> bytes:
    """Like _trak but with a 64-bit chunk-offset table (co64)."""
    stbl = _box(b"stbl", _stsd(_sample_entry()) + _co64(offsets))
    minf = _box(b"minf", stbl)
    mdia = _box(b"mdia", _hdlr(handler) + minf)
    return _box(b"trak", mdia)


def _trak_multi_entry() -> bytes:
    """A video trak whose stsd declares TWO sample entries (entry_count=2)."""
    entries = _sample_entry() + _sample_entry()
    stsd = _box(b"stsd", b"\x00\x00\x00\x00" + (2).to_bytes(4, "big") + entries)
    stbl = _box(b"stbl", stsd + _stco([100]))
    minf = _box(b"minf", stbl)
    mdia = _box(b"mdia", _hdlr(b"vide") + minf)
    return _box(b"trak", mdia)


def _build_mp4(moov_first: bool) -> tuple[bytes, int]:
    """Build ftyp + mdat + moov (or moov before mdat). Returns (bytes, stco_off).

    ``stco_off`` is the chunk offset written into the video trak (pointing at the
    mdat payload), so tests can assert whether it was repaired.
    """
    mdat_payload = b"\x00" * 64
    ftyp = _ftyp()

    if moov_first:
        # We need the mdat offset, which depends on moov size, which depends on
        # the stco value — so build moov with a placeholder, measure, rebuild.
        guess = _box(b"moov", _trak(b"vide", [0]) + _trak(b"soun", [0]))
        mdat_payload_off = len(ftyp) + len(guess) + 8
        moov = _box(
            b"moov",
            _trak(b"vide", [mdat_payload_off]) + _trak(b"soun", [mdat_payload_off + 8]),
        )
        assert len(moov) == len(guess)  # offset width is fixed, sizes match
        data = ftyp + moov + _box(b"mdat", mdat_payload)
    else:
        mdat_payload_off = len(ftyp) + 8
        moov = _box(
            b"moov",
            _trak(b"vide", [mdat_payload_off]) + _trak(b"soun", [mdat_payload_off + 8]),
        )
        data = ftyp + _box(b"mdat", mdat_payload) + moov

    return data, mdat_payload_off


# ── Box-tree validation ────────────────────────────────────────────────────

# Bytes from a box's start to its first child, per type (None = leaf box).
_CONTAINER_SKIP = {
    **{t: 8 for t in ("moov", "trak", "mdia", "minf", "stbl", "sv3d", "proj")},
    "stsd": 16,
    **{t: 86 for t in ("avc1", "avc3", "hvc1", "hev1", "mp4v", "av01", "vp09")},
}


def _assert_tree_fills(buf: bytes, start: int, end: int, skip: int) -> None:
    """Recursively assert every container's children exactly fill it."""
    pos = start + skip
    while pos < end:
        box_type, size, _ = vr._read_header(buf, pos)
        assert pos + size <= end, f"{box_type} overruns its parent"
        child_skip = _CONTAINER_SKIP.get(box_type)
        if child_skip is not None:
            _assert_tree_fills(buf, pos, pos + size, child_skip)
        pos += size
    assert pos == end, "children do not exactly fill the container (size drift)"


def _video_sample_entry_bytes(buf: bytes) -> bytes:
    insert, ancestors, _ = vr._locate_video_sample_entry(_moov_bytes(buf))
    se_off, se_size, _ = ancestors[0]
    moov = _moov_bytes(buf)
    return moov[se_off : se_off + se_size]


def _moov_bytes(buf: bytes) -> bytes:
    box = vr._find(buf, 0, len(buf), "moov", 0)
    assert box is not None
    _, off, size, _ = box
    return buf[off : off + size]


def _read_video_stco(buf: bytes) -> int:
    """Read the first chunk offset of the video trak (for repair assertions)."""
    moov = vr._find(buf, 0, len(buf), "moov", 0)
    assert moov is not None
    _, moff, msize, mhdr = moov
    for typ, toff, tsize, thdr in vr._iter_children(buf, moff, moff + msize, mhdr):
        if typ != "trak":
            continue
        mdia = vr._find(buf, toff, toff + tsize, "mdia", thdr)
        assert mdia is not None
        _, doff, dsize, dhdr = mdia
        hdlr = vr._find(buf, doff, doff + dsize, "hdlr", dhdr)
        assert hdlr is not None
        ho, hh = hdlr[1], hdlr[3]
        if buf[ho + hh + 8 : ho + hh + 12] != b"vide":
            continue
        minf = vr._find(buf, doff, doff + dsize, "minf", dhdr)
        assert minf is not None
        _, mio, mis, mih = minf
        stbl = vr._find(buf, mio, mio + mis, "stbl", mih)
        assert stbl is not None
        _, so, ss, sh = stbl
        stco = vr._find(buf, so, so + ss, "stco", sh)
        assert stco is not None
        co, _, ch = stco[1], stco[2], stco[3]
        return int.from_bytes(buf[co + ch + 8 : co + ch + 12], "big")
    raise AssertionError("no video stco")


# ── Injection ──────────────────────────────────────────────────────────────


def _ancestor_sizes(buf: bytes) -> list[int]:
    _, ancestors, _ = vr._locate_video_sample_entry(_moov_bytes(buf))
    return [size for _, size, _ in ancestors]


def test_inject_moov_at_end(tmp_path: Path):
    data, stco_off = _build_mp4(moov_first=False)
    path = tmp_path / "clip.mp4"
    path.write_bytes(data)

    before = _ancestor_sizes(data)
    delta = len(vr._spherical_boxes("180_sbs"))

    assert vr.inject_spherical_metadata(path, "180_sbs") is True
    out = path.read_bytes()

    # The whole file grew by exactly the inserted boxes.
    assert len(out) == len(data) + delta
    # Every ancestor (sample entry → moov) grew by exactly delta.
    after = _ancestor_sizes(out)
    assert after == [s + delta for s in before]
    # The spherical boxes are inside the video sample entry.
    se = _video_sample_entry_bytes(out)
    assert b"st3d" in se and b"sv3d" in se and b"equi" in se
    # moov is after mdat, so the chunk offset must be unchanged.
    assert _read_video_stco(out) == stco_off
    # Box tree still fills exactly at every level.
    _assert_tree_fills(out, 0, len(out), 0)
    # Idempotent: a second pass is a no-op.
    assert vr.inject_spherical_metadata(path, "180_sbs") is False


def test_inject_moov_first_repairs_offsets(tmp_path: Path):
    data, stco_off = _build_mp4(moov_first=True)
    path = tmp_path / "clip.mp4"
    path.write_bytes(data)

    delta = len(vr._spherical_boxes("360_mono"))
    assert vr.inject_spherical_metadata(path, "360_mono") is True
    out = path.read_bytes()

    assert len(out) == len(data) + delta
    # moov precedes mdat, so the mdat shifted by delta — the chunk offset must
    # have been repaired to match.
    assert _read_video_stco(out) == stco_off + delta
    se = _video_sample_entry_bytes(out)
    assert b"st3d" in se
    # 360 mono is full equirect: bounds are zero but the sv3d/equi boxes exist.
    assert b"sv3d" in se and b"equi" in se
    _assert_tree_fills(out, 0, len(out), 0)


def test_inject_skips_non_mp4(tmp_path: Path):
    # A bogus/non-MP4 file must be left untouched (no crash, returns False).
    path = tmp_path / "not.mp4"
    path.write_bytes(b"this is not an mp4 at all")
    assert vr.inject_spherical_metadata(path, "180_sbs") is False
    assert path.read_bytes() == b"this is not an mp4 at all"


def test_apply_vr_renames_and_tags(tmp_path: Path):
    data, _ = _build_mp4(moov_first=False)
    path = tmp_path / "movie.mp4"
    path.write_bytes(data)

    result = vr.apply_vr(path, "180_sbs")
    assert result.name == "movie_180x180_3dh.mp4"
    assert result.exists()
    assert not path.exists()  # original was renamed
    se = _video_sample_entry_bytes(result.read_bytes())
    assert b"sv3d" in se


def test_inject_rejects_multiple_sample_entries(tmp_path: Path):
    # entry_count>1 would put the insertion point *between* sample entries and
    # corrupt stsd — the injector must refuse and leave the file untouched.
    moov = _box(b"moov", _trak_multi_entry())
    data = _ftyp() + _box(b"mdat", b"\x00" * 64) + moov
    path = tmp_path / "multi.mp4"
    path.write_bytes(data)
    assert vr.inject_spherical_metadata(path, "180_sbs") is False
    assert path.read_bytes() == data  # byte-for-byte untouched


def test_copy_range_raises_on_short_read():
    import io
    import pytest

    class _ShortSource:
        def seek(self, _pos):
            pass

        def read(self, _n):
            return b""  # source unexpectedly yields nothing

    with pytest.raises(vr._SphericalInjectError):
        vr._copy_range(_ShortSource(), io.BytesIO(), 0, 10)


def test_inject_co64_repairs_offsets(tmp_path: Path):
    # moov-first with a 64-bit chunk-offset table; the offset must be repaired.
    guess = _box(b"moov", _trak_co64(b"vide", [0]))
    mdat_off = len(_ftyp()) + len(guess) + 8
    moov = _box(b"moov", _trak_co64(b"vide", [mdat_off]))
    assert len(moov) == len(guess)
    data = _ftyp() + moov + _box(b"mdat", b"\x00" * 64)
    path = tmp_path / "c.mp4"
    path.write_bytes(data)

    delta = len(vr._spherical_boxes("180_sbs"))
    assert vr.inject_spherical_metadata(path, "180_sbs") is True
    out = path.read_bytes()
    _assert_tree_fills(out, 0, len(out), 0)

    # Read back the (single) co64 entry of the video trak and check the repair.
    moov_box = vr._find(out, 0, len(out), "moov", 0)
    _, moff, msize, mhdr = moov_box
    trak = vr._find(out, moff, moff + msize, "trak", mhdr)
    _, toff, tsize, thdr = trak
    mdia = vr._find(out, toff, toff + tsize, "mdia", thdr)
    _, doff, dsize, dhdr = mdia
    minf = vr._find(out, doff, doff + dsize, "minf", dhdr)
    _, io_, is_, ih = minf
    stbl = vr._find(out, io_, io_ + is_, "stbl", ih)
    _, so, ss, sh = stbl
    co64 = vr._find(out, so, so + ss, "co64", sh)
    co, _, ch = co64[1], co64[2], co64[3]
    value = int.from_bytes(out[co + ch + 8 : co + ch + 16], "big")
    assert value == mdat_off + delta


def test_inject_rejects_fragmented_mp4(tmp_path: Path):
    # A fragmented MP4 (mvex in moov) has chunk offsets in moof fragments we
    # don't repair — injecting would corrupt it, so it must be refused untouched.
    moov = _box(b"moov", _trak(b"vide", [100]) + _box(b"mvex", b""))
    data = _ftyp() + _box(b"mdat", b"\x00" * 64) + moov
    path = tmp_path / "frag.mp4"
    path.write_bytes(data)
    assert vr.inject_spherical_metadata(path, "180_sbs") is False
    assert path.read_bytes() == data  # byte-for-byte untouched


def test_inject_largesize_moov(tmp_path: Path):
    # A moov with a 64-bit largesize header exercises _patch_size's 16-byte
    # branch (the path that matters for >4GB VR captures).
    ftyp = _ftyp()
    mdat_off = len(ftyp) + 8
    inner = _trak(b"vide", [mdat_off]) + _trak(b"soun", [mdat_off + 8])
    moov = _box_large(b"moov", inner)
    data = ftyp + _box(b"mdat", b"\x00" * 64) + moov
    path = tmp_path / "large.mp4"
    path.write_bytes(data)

    delta = len(vr._spherical_boxes("180_sbs"))
    assert vr.inject_spherical_metadata(path, "180_sbs") is True
    out = path.read_bytes()
    assert len(out) == len(data) + delta
    _assert_tree_fills(out, 0, len(out), 0)
    se = _video_sample_entry_bytes(out)
    assert b"st3d" in se and b"sv3d" in se
    # The largesize 64-bit field (bytes 8:16 of moov) carries the grown size.
    moov_box = vr._find(out, 0, len(out), "moov", 0)
    moff, msize = moov_box[1], moov_box[2]
    assert int.from_bytes(out[moff + 8 : moff + 16], "big") == msize


def test_apply_vr_fisheye_suffix_only(tmp_path: Path):
    # Fisheye isn't equirectangular: it gets the name suffix but no sv3d box.
    data, _ = _build_mp4(moov_first=False)
    path = tmp_path / "movie.mp4"
    path.write_bytes(data)

    result = vr.apply_vr(path, "fisheye190")
    assert result.name == "movie_FISHEYE190.mp4"
    se = _video_sample_entry_bytes(result.read_bytes())
    assert b"st3d" in se  # stereo still tagged
    assert b"sv3d" not in se  # but no spherical projection


# ── V1 / MKV / ffprobe-validation follow-ups ────────────────────────────────


def test_spherical_v1_xml_only_for_360_equirect():
    # V1 predates 180° VR — it must only be emitted for full 360° equirect.
    assert vr._spherical_v1_xml("180_sbs") is None
    assert vr._spherical_v1_xml("180_mono") is None
    assert vr._spherical_v1_xml("fisheye190") is None
    assert vr._spherical_v1_xml("mkx200") is None
    sbs = vr._spherical_v1_xml("360_sbs")
    assert sbs is not None and b"left-right" in sbs and b"equirectangular" in sbs
    assert b"top-bottom" in (vr._spherical_v1_xml("360_tb") or b"")
    assert b"mono" in (vr._spherical_v1_xml("360_mono") or b"")


def test_inject_v1_moov_first_repairs_offsets(tmp_path: Path):
    data, stco_off = _build_mp4(moov_first=True)
    path = tmp_path / "clip.mp4"
    path.write_bytes(data)
    before = _ancestor_sizes(data)  # [se, stsd, stbl, minf, mdia, trak, moov]

    assert vr.inject_spherical_v1(path, "360_mono") is True
    out = path.read_bytes()
    delta = len(out) - len(data)
    assert delta > 0

    # The legacy uuid box + RDF/XML landed.
    assert vr._SPHERICAL_V1_UUID in out and b"GSpherical:Spherical" in out
    # It's a trak-level box: only the trak and moov grew; deeper boxes didn't.
    after = _ancestor_sizes(out)
    assert after[:5] == before[:5]
    assert after[5] == before[5] + delta  # trak
    assert after[6] == before[6] + delta  # moov
    # moov precedes mdat here, so the chunk offset was repaired by delta.
    assert _read_video_stco(out) == stco_off + delta
    # Box tree still fills exactly, and a second pass is a no-op.
    _assert_tree_fills(out, 0, len(out), 0)
    assert vr.inject_spherical_v1(path, "360_mono") is False
    # Not applicable to a 180° layout.
    assert vr.inject_spherical_v1(path, "180_sbs") is False


def test_set_mkv_stereo_mode_mono_is_noop():
    # Mono has no StereoMode to signal, so it returns early without ffmpeg.
    assert vr.set_mkv_stereo_mode(Path("/nonexistent.mkv"), "360_mono") is False


def test_has_spherical_metadata_none_without_ffprobe(tmp_path: Path, monkeypatch):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"\x00" * 32)
    monkeypatch.setattr(vr, "ffprobe_path", lambda: "/nonexistent/ffprobe-xyz")
    assert vr.has_spherical_metadata(f) is None
