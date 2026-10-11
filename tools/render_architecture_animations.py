"""Render documentation GIFs from source-verified architecture storyboards.

Run from the repository root with the repository virtual environment. Pillow is
already pinned in requirements-dev.txt. No application configuration is loaded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import GifImagePlugin, Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "architecture" / "assets"
STORYBOARDS = ASSETS / "architecture-storyboards.json"
WIDTH, HEIGHT, SCALE = 1280, 940, 2
TICKS, TICK_MS = 24, 250
INK, MUTED = "#142D45", "#50677C"
TEAL, PALE, LINE = "#087F8C", "#E6F5F5", "#B8C8D6"
AMBER, AMBER_BG = "#925507", "#FFF2DB"
STATES = {
    "normal": ("#FFFFFF", "#D5DFE8", INK),
    "active": (PALE, TEAL, TEAL),
    "done": ("#EAF5ED", "#42825B", "#286641"),
    "warning": (AMBER_BG, "#CE9B4D", AMBER),
    "failed": ("#FBECEC", "#C46666", "#9B3737"),
}


@lru_cache(maxsize=24)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a readable font, preferring the Windows documentation typeface."""
    candidates = [
        Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu")
        / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size * SCALE)
    raise FileNotFoundError("Install Segoe UI or DejaVu Sans to render diagrams.")


def label(draw: ImageDraw.ImageDraw, x: float, y: float, text: str,
          size: int = 23, color: str = INK, bold: bool = False) -> None:
    draw.text((round(x * SCALE), round(y * SCALE)), text,
              font=font(size, bold), fill=color)


def wrapped(draw: ImageDraw.ImageDraw, x: float, y: float, text: str,
            width: float, size: int, max_lines: int, color: str = MUTED,
            bold: bool = False) -> None:
    """Wrap by rendered width and reject overflowing text instead of clipping."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        if draw.textlength(word, font=font(size, bold)) > width * SCALE:
            raise ValueError(f"Word exceeds available width: {word}")
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font(size, bold)) > width * SCALE:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        raise ValueError(f"Text needs {len(lines)} lines, limit {max_lines}: {text}")
    for index, text_line in enumerate(lines):
        label(draw, x, y + index * (size + 8), text_line, size, color, bold)


def box(draw: ImageDraw.ImageDraw, bounds: tuple[float, ...], fill: str,
        outline: str | None = None, width: int = 1, radius: int = 16) -> None:
    draw.rounded_rectangle(tuple(round(value * SCALE) for value in bounds),
                           radius=radius * SCALE, fill=fill, outline=outline,
                           width=width * SCALE)


def edge_points(nodes: dict[str, dict[str, Any]], edge: list[str],
                paths: dict[str, list[list[float]]] | None = None) -> list[tuple[float, float]]:
    """Connect facing card edges, keeping paths outside card interiors."""
    custom = (paths or {}).get("->".join(edge))
    if custom:
        return [(x, y) for x, y in custom]
    a, b = (nodes[key] for key in edge)
    ax, ay, aw, ah = a["box"]
    bx, by, bw, bh = b["box"]
    ac, bc = (ax + aw / 2, ay + ah / 2), (bx + bw / 2, by + bh / 2)
    if abs(ac[0] - bc[0]) < 30:
        return [(ac[0], ay + ah if bc[1] > ac[1] else ay),
                (bc[0], by if bc[1] > ac[1] else by + bh)]
    right = bc[0] > ac[0]
    start = (ax + aw if right else ax, ac[1])
    end = (bx if right else bx + bw, bc[1])
    mid_x = (start[0] + end[0]) / 2
    return [start, (mid_x, start[1]), (mid_x, end[1]), end]


def stroke(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]],
           color: str, width: int = 3) -> None:
    draw.line([(round(x * SCALE), round(y * SCALE)) for x, y in points],
              fill=color, width=width * SCALE, joint="curve")


def validate_storyboard(board: dict[str, Any]) -> None:
    """Reject dangling references and invalid canvas geometry before rendering."""
    nodes = board["nodes"]
    if not board["stages"]:
        raise ValueError("An animation needs at least one stage.")
    for node in nodes.values():
        x, y, width, height = node["box"]
        if not (40 <= x and 180 <= y and width > 0 and height > 0
                and x + width <= 1240 and y + height <= 600):
            raise ValueError(f"Node outside diagram bounds: {node}")
    edges = {tuple(edge) for edge in board["edges"]}
    for a, b in edges:
        if a not in nodes or b not in nodes:
            raise ValueError(f"Unknown edge endpoint: {a}, {b}")
    for stage in board["stages"]:
        if set(stage.get("nodes", {})) - nodes.keys():
            raise ValueError("Stage refers to an unknown node.")
        if any(tuple(edge) not in edges for edge in stage.get("edges", [])):
            raise ValueError("Stage refers to an unknown edge.")
        if not 0 <= stage["source"] < len(board["sources"]):
            raise ValueError("Stage refers to an unknown source.")
    for source in board["sources"]:
        path = ROOT / source["path"]
        if not path.is_file():
            raise ValueError(f"Missing source: {source['path']}")
        if source["symbol"] not in path.read_text(encoding="utf-8-sig"):
            raise ValueError(f"Missing source symbol: {source}")


def render_stage(board: dict[str, Any], index: int, revision: str,
                 verified_on: str) -> Image.Image:
    """Draw one complete, readable scene before adding motion."""
    stage = board["stages"][index]
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), "#F1F5F9")
    draw = ImageDraw.Draw(image)
    box(draw, (0, 0, WIDTH, 148), INK, radius=0)
    wrapped(draw, 55, 24, board["title"], 1000, 38, 1, "#FFFFFF", True)
    label(draw, 57, 88, board["subtitle"], 23, "#BDD0DF")
    box(draw, (1100, 35, 1225, 96), "#27465E")
    label(draw, 1122, 50, f"{index + 1} / {len(board['stages'])}", 26, "#FFFFFF", True)
    label(draw, 55, 162, board["legend"], 18, MUTED)

    active_edges = {tuple(edge) for edge in stage.get("edges", [])}
    for edge in board["edges"]:
        points = edge_points(board["nodes"], edge, board.get("paths"))
        color = TEAL if tuple(edge) in active_edges else LINE
        stroke(draw, points, color, 4 if tuple(edge) in active_edges else 2)
        previous, end = points[-2:]
        angle = math.atan2(end[1] - previous[1], end[0] - previous[0])
        arms = [(end[0] - 10 * math.cos(angle + offset),
                 end[1] - 10 * math.sin(angle + offset)) for offset in (-0.55, 0.55)]
        stroke(draw, [arms[0], end, arms[1]], color)

    for key, original in board["nodes"].items():
        node = {**original, **stage.get("nodes", {}).get(key, {})}
        x, y, width, height = node["box"]
        fill, outline, text_color = STATES[node.get("state", "normal")]
        box(draw, (x + 2, y + 4, x + width + 2, y + height + 4), "#E1E8EF")
        box(draw, (x, y, x + width, y + height), fill, outline,
            3 if node.get("state", "normal") != "normal" else 1)
        wrapped(draw, x + 18, y + 12, node["title"], width - 36, 24, 1, text_color, True)
        wrapped(draw, x + 18, y + 49, node["detail"], width - 36, 20,
                max(1, int((height - 53) // 28)), INK)

    box(draw, (55, 622, 1225, 849), "#FFFFFF", "#D5DFE8")
    box(draw, (55, 622, 65, 849), TEAL, radius=0)
    wrapped(draw, 85, 637, f"{index + 1:02d}  {stage['title']}", 1090, 31, 1, INK, True)
    wrapped(draw, 85, 690, stage["text"], 790, 24, 4)
    box(draw, (910, 688, 1205, 830), AMBER_BG, radius=14)
    wrapped(draw, 928, 700, stage["badge"], 257, 16, 1, AMBER, True)
    wrapped(draw, 928, 731, stage["note"], 257, 20, 3, AMBER)
    source = board["sources"][stage["source"]]
    label(draw, 55, 895, f"SOURCE  {source['path']} : {source['symbol']}", 16)
    label(draw, 55, 921,
          f"Code review: {verified_on} / {revision[:7]}  |  "
          f"Loop: {len(board['stages']) * 6}s  |  "
          "Synthetic examples; no live deployment check",
          15, MUTED)
    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def point_on_path(points: list[tuple[float, float]], progress: float) -> tuple[float, float]:
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    target = sum(lengths) * progress
    for a, b, length in zip(points, points[1:], lengths):
        if target <= length and length:
            fraction = target / length
            return a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction
        target -= length
    return points[-1]


def animate(board: dict[str, Any], revision: str, verified_on: str,
            output: Path, preview_dir: Path | None) -> dict[str, Any]:
    """Encode a looping GIF and validate the decoded timing and motion."""
    validate_storyboard(board)
    scenes = [render_stage(board, i, revision, verified_on)
              for i in range(len(board["stages"]))]
    montage = Image.new("RGB", (WIDTH, HEIGHT * len(scenes)))
    for i, scene in enumerate(scenes):
        montage.paste(scene, (0, i * HEIGHT))
    palette = montage.quantize(colors=128)
    frames = []
    for i, scene in enumerate(scenes):
        paths = [edge_points(board["nodes"], edge, board.get("paths"))
                 for edge in board["stages"][i].get("edges", [])]
        for tick in range(TICKS):
            frame = scene.copy()
            draw = ImageDraw.Draw(frame)
            progress = tick / (TICKS - 1)
            for points in paths:
                x, y = point_on_path(points, progress)
                draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=TEAL, outline="white", width=2)
            count = len(scenes)
            step_width = 1170 / count
            for step in range(count):
                x = 55 + step * step_width
                draw.rounded_rectangle(
                    (x, 870, x + step_width - 10, 878), radius=4,
                    fill="#D0DDE6",
                )
                amount = 1 if step < i else progress if step == i else 0
                if amount:
                    draw.rounded_rectangle(
                        (x, 870, x + max(6, (step_width - 10) * amount), 878),
                        radius=4, fill=TEAL,
                    )
            frames.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
    target = output / f"{board['id']}.gif"
    target.parent.mkdir(parents=True, exist_ok=True)
    provenance = json.dumps({
        "storyboard_sha256": hashlib.sha256(
            json.dumps(board, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "verified_revision": revision,
        "verified_on": verified_on,
    }, sort_keys=True).encode("utf-8")
    frames[0].save(target, save_all=True, append_images=frames[1:],
                   duration=TICK_MS, loop=0, optimize=True, disposal=1,
                   comment=provenance)
    total_ms = 0
    with Image.open(target) as decoded:
        if not isinstance(decoded, GifImagePlugin.GifImageFile):
            raise ValueError(f"Expected a GIF animation: {target}")
        encoded_frames = decoded.n_frames
        if encoded_frames < len(scenes) * 2 or decoded.info.get("loop") != 0:
            raise ValueError(f"Missing animation or infinite loop: {target}")
        for index in range(decoded.n_frames):
            decoded.seek(index)
            decoded.load()
            total_ms += decoded.info["duration"]
    if total_ms != len(scenes) * TICKS * TICK_MS:
        raise ValueError(f"Incorrect GIF timing: {target}")
    if preview_dir is not None:
        preview_dir.mkdir(parents=True, exist_ok=True)
        contact = Image.new(
            "RGB", (WIDTH, math.ceil(len(scenes) / 2) * HEIGHT // 2), "#F1F5F9"
        )
        for i, scene in enumerate(scenes):
            contact.paste(scene.resize((WIDTH // 2, HEIGHT // 2)),
                          ((i % 2) * WIDTH // 2, (i // 2) * HEIGHT // 2))
        contact.save(preview_dir / f"{board['id']}-contact.png")
        scenes[min(2, len(scenes) - 1)].save(preview_dir / f"{board['id']}-preview.png")
    return {"file": target.name, "frames": encoded_frames, "duration_ms": total_ms,
            "bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--only", help="Render only one storyboard ID.")
    args = parser.parse_args()
    data = json.loads(STORYBOARDS.read_text(encoding="utf-8"))
    boards = [board for board in data["animations"]
              if args.only is None or board["id"] == args.only]
    if not boards:
        parser.error("Unknown storyboard ID.")
    for board in boards:
        result = animate(board, data["verified_revision"], data["verified_on"],
                         ASSETS, args.preview_dir)
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
