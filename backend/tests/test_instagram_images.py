"""Tests for the Instagram photo shim + still-image classification."""

from __future__ import annotations

from app.services import ytdlp_service
from app.services.instagram_image_extractor import _promote_image


def test_promote_image_adds_best_candidate_as_format():
    # candidates are largest-first; the first usable one wins, as a jpg format.
    product = {
        "image_versions2": {
            "candidates": [
                {"url": "https://ig/large.jpg", "width": 1080, "height": 1350},
                {"url": "https://ig/small.jpg", "width": 320, "height": 400},
            ]
        }
    }
    info = _promote_image({"id": "1", "formats": []}, product)
    assert info["formats"] == [
        {
            "url": "https://ig/large.jpg",
            "format_id": "image",
            "ext": "jpg",
            "width": 1080,
            "height": 1350,
            "vcodec": "none",
            "acodec": "none",
        }
    ]


def test_promote_image_leaves_videos_untouched():
    info = {"id": "1", "formats": [{"url": "https://ig/v.mp4", "vcodec": "h264"}]}
    out = _promote_image(info, {"image_versions2": {"candidates": [{"url": "x"}]}})
    assert out["formats"] == [{"url": "https://ig/v.mp4", "vcodec": "h264"}]


def test_promote_image_noop_without_candidates():
    info = {"id": "1", "formats": []}
    assert _promote_image(info, {"image_versions2": {"candidates": []}}) == info


def test_is_image_item_true_for_image_only():
    assert ytdlp_service._is_image_item(
        [{"url": "u", "ext": "jpg", "vcodec": "none", "acodec": "none"}]
    )


def test_is_image_item_false_for_video_audio_or_empty():
    assert not ytdlp_service._is_image_item([])
    assert not ytdlp_service._is_image_item(None)
    assert not ytdlp_service._is_image_item(
        [{"url": "u", "ext": "mp4", "vcodec": "h264", "acodec": "aac"}]
    )
    # A url-less candidate doesn't count.
    assert not ytdlp_service._is_image_item([{"ext": "jpg"}])


def test_build_video_sets_is_image_flag():
    info = {
        "id": "x",
        "title": "A photo",
        "formats": [
            {"url": "https://ig/p.jpg", "ext": "jpg", "vcodec": "none", "acodec": "none"}
        ],
    }
    assert ytdlp_service._build_video(info).is_image is True
