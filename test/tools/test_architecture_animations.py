"""Check documentation animation readability, provenance and playback."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest
from PIL import GifImagePlugin, Image

from tools.render_architecture_animations import (
    ASSETS,
    HEIGHT,
    STORYBOARDS,
    TICK_MS,
    TICKS,
    WIDTH,
    render_stage,
    validate_storyboard,
)

DATA = json.loads(STORYBOARDS.read_text(encoding="utf-8"))
BOARDS = DATA["animations"]


@pytest.mark.parametrize("board", BOARDS, ids=lambda board: board["id"])
def test_architecture_scenes_fit_and_reference_existing_sources(
    board: dict[str, Any],
) -> None:
    """Catch clipped text, invalid geometry and dangling source references."""
    validate_storyboard(board)
    for index in range(len(board["stages"])):
        scene = render_stage(
            board, index, DATA["verified_revision"], DATA["verified_on"]
        )
        assert scene.size == (WIDTH, HEIGHT)


@pytest.mark.parametrize("board", BOARDS, ids=lambda board: board["id"])
def test_published_gif_matches_storyboard_and_plays_all_scenes(
    board: dict[str, Any],
) -> None:
    """Detect stale exports, static substitutes and truncated playback."""
    target = ASSETS / f"{board['id']}.gif"
    expected_digest = hashlib.sha256(
        json.dumps(board, sort_keys=True).encode("utf-8")
    ).hexdigest()
    with Image.open(target) as animation:
        assert isinstance(animation, GifImagePlugin.GifImageFile)
        assert animation.size == (WIDTH, HEIGHT)
        assert animation.info["loop"] == 0
        provenance = json.loads(animation.info["comment"])
        assert provenance["storyboard_sha256"] == expected_digest
        assert provenance["verified_revision"] == DATA["verified_revision"]
        assert provenance["verified_on"] == DATA["verified_on"]
        assert animation.n_frames >= len(board["stages"]) * 2
        duration = 0
        for index in range(animation.n_frames):
            animation.seek(index)
            animation.load()
            duration += animation.info["duration"]
        assert duration == len(board["stages"]) * TICKS * TICK_MS


@pytest.mark.parametrize("invalid_reference", ["edge", "node"])
def test_invalid_storyboard_references_fail_before_rendering(
    invalid_reference: str,
) -> None:
    board = copy.deepcopy(BOARDS[0])
    if invalid_reference == "edge":
        board["stages"][0]["edges"] = [["missing", "intake"]]
    else:
        board["stages"][0]["nodes"] = {"missing": {"state": "active"}}
    with pytest.raises(ValueError, match="unknown"):
        validate_storyboard(board)
