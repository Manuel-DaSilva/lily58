#!/usr/bin/env python3
"""Generate the right-half nice!view artwork and its LVGL C source."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


PORTRAIT_WIDTH = 68
PORTRAIT_HEIGHT = 140
FRAMEBUFFER_WIDTH = PORTRAIT_HEIGHT
FRAMEBUFFER_HEIGHT = PORTRAIT_WIDTH
ROW_BYTES = (FRAMEBUFFER_WIDTH + 7) // 8
PALETTE_BYTES = 8


def parse_pbm(path: Path) -> bytes:
    data = path.read_bytes()
    index = 0
    tokens: list[bytes] = []

    while len(tokens) < 3:
        while index < len(data) and data[index] in b" \t\r\n":
            index += 1
        if index < len(data) and data[index] == ord("#"):
            index = data.index(b"\n", index) + 1
            continue

        start = index
        while index < len(data) and data[index] not in b" \t\r\n":
            index += 1
        tokens.append(data[start:index])

    if tokens != [
        b"P4",
        str(FRAMEBUFFER_WIDTH).encode(),
        str(FRAMEBUFFER_HEIGHT).encode(),
    ]:
        raise ValueError(f"unexpected PBM header: {tokens!r}")

    # A single whitespace character separates the header from the binary pixels.
    index += 1
    bitmap = data[index : index + ROW_BYTES * FRAMEBUFFER_HEIGHT]
    if len(bitmap) != ROW_BYTES * FRAMEBUFFER_HEIGHT:
        raise ValueError(f"unexpected PBM data size: {len(bitmap)}")

    # PBM uses 1 for black; the LVGL palette below uses index 0 for black.
    return bytes(byte ^ 0xFF for byte in bitmap)


def render_c(bitmap: bytes, source: Path) -> str:
    rows = []
    for offset in range(0, len(bitmap), ROW_BYTES):
        row = bitmap[offset : offset + ROW_BYTES]
        rows.append("        " + ", ".join(f"0x{byte:02x}" for byte in row) + ",")

    data_size = PALETTE_BYTES + len(bitmap)
    return f"""/* Generated from {source.name} as a 68x140 portrait in the 140x68 nice!view framebuffer. */
#include <lvgl.h>

#ifndef LV_ATTRIBUTE_MEM_ALIGN
#define LV_ATTRIBUTE_MEM_ALIGN
#endif
#ifndef LV_ATTRIBUTE_IMG_ICHIRO
#define LV_ATTRIBUTE_IMG_ICHIRO
#endif

const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST LV_ATTRIBUTE_IMG_ICHIRO uint8_t ichiro_map[] = {{
#if CONFIG_NICE_VIEW_WIDGET_INVERTED
        0xff, 0xff, 0xff, 0xff, /* Color of index 0 */
        0x00, 0x00, 0x00, 0xff, /* Color of index 1 */
#else
        0x00, 0x00, 0x00, 0xff, /* Color of index 0 */
        0xff, 0xff, 0xff, 0xff, /* Color of index 1 */
#endif
{chr(10).join(rows)}
}};

const lv_img_dsc_t ichiro = {{
    .header.cf = LV_IMG_CF_INDEXED_1BIT,
    .header.always_zero = 0,
    .header.reserved = 0,
    .header.w = {FRAMEBUFFER_WIDTH},
    .header.h = {FRAMEBUFFER_HEIGHT},
    .data_size = {data_size},
    .data = ichiro_map,
}};
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="source portrait")
    parser.add_argument("output", type=Path, help="generated LVGL C file")
    parser.add_argument(
        "--preview", type=Path, help="write the final 68x140 portrait-orientation one-bit PNG"
    )
    args = parser.parse_args()

    if shutil.which("magick") is None:
        raise SystemExit("ImageMagick's `magick` command is required")

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory)
        portrait = temporary_path / "portrait.png"
        framebuffer = temporary_path / "framebuffer.png"
        pbm = temporary_path / "framebuffer.pbm"

        subprocess.run(
            [
                "magick",
                str(args.source),
                "-gravity",
                "south",
                "-resize",
                f"{PORTRAIT_WIDTH}x{PORTRAIT_HEIGHT}^",
                "-extent",
                f"{PORTRAIT_WIDTH}x{PORTRAIT_HEIGHT}",
                "-colorspace",
                "Gray",
                "-threshold",
                "55%",
                "-type",
                "bilevel",
                str(portrait),
            ],
            check=True,
        )
        # The nice!view driver exposes a 140x68 landscape framebuffer even though
        # the panel is mounted as a 68x160 portrait. Match the widget's existing
        # clockwise rotation so the portrait is upright on the physical panel.
        subprocess.run(
            ["magick", str(portrait), "-rotate", "90", str(framebuffer)], check=True
        )
        subprocess.run(["magick", str(framebuffer), f"pbm:{pbm}"], check=True)

        args.output.write_text(render_c(parse_pbm(pbm), args.source))
        if args.preview:
            shutil.copyfile(portrait, args.preview)


if __name__ == "__main__":
    main()
