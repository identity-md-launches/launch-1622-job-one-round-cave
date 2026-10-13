#!/usr/bin/env python3
"""Blend the reviewed round-four pigment motif into the prior gathering wall.

This is deliberately a small, standard-library compositing helper.  It retains
the source wall byte-for-byte outside the declared rectangle and mixes the
generated pigment with the source rock inside it.  It accepts absolute source
paths because the prior wall and generated draft are transient inputs; the
output must remain inside this workspace.
"""
import argparse
from pathlib import Path
import struct
import zlib


def rgb_png(path):
    raw = Path(path).read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    position, compressed = 8, bytearray()
    dimensions = None
    while position < len(raw):
        length = int.from_bytes(raw[position:position + 4], "big")
        kind = raw[position + 4:position + 8]
        data = raw[position + 8:position + 8 + length]
        if zlib.crc32(kind + data) != int.from_bytes(raw[position + 8 + length:position + 12 + length], "big"):
            raise ValueError("bad PNG chunk CRC")
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data)
            if (depth, color, compression, filtering, interlace) != (8, 2, 0, 0, 0):
                raise ValueError("need non-interlaced 8-bit RGB PNG")
            dimensions = width, height
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
        position += length + 12
    if dimensions is None:
        raise ValueError("missing PNG header")
    width, height = dimensions
    packed, stride = zlib.decompress(compressed), width * 3
    if len(packed) != (stride + 1) * height:
        raise ValueError("bad PNG raster length")
    previous, rows = bytearray(stride), []
    for y in range(height):
        offset = y * (stride + 1)
        mode, row = packed[offset], bytearray(packed[offset + 1:offset + 1 + stride])
        for x in range(stride):
            left = row[x - 3] if x >= 3 else 0
            above = previous[x]
            upper_left = previous[x - 3] if x >= 3 else 0
            if mode == 0:
                predicted = 0
            elif mode == 1:
                predicted = left
            elif mode == 2:
                predicted = above
            elif mode == 3:
                predicted = (left + above) // 2
            elif mode == 4:
                value = left + above - upper_left
                candidates = (abs(value - left), abs(value - above), abs(value - upper_left))
                predicted = (left, above, upper_left)[candidates.index(min(candidates))]
            else:
                raise ValueError("unknown PNG filter")
            row[x] = (row[x] + predicted) & 255
        rows.append(row)
        previous = row
    return width, height, rows


def png_bytes(width, height, rows):
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raster = b"".join(b"\0" + bytes(row) for row in rows)
    def chunk(kind, value):
        return (struct.pack(">I", len(value)) + kind + value +
                struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raster, 9)) + chunk(b"IEND", b"")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="reviewed previous gathering RGB PNG")
    parser.add_argument("draft", help="reviewed generated RGB PNG with the new motif")
    parser.add_argument("output", help="new workspace-local RGB PNG; must not exist")
    args = parser.parse_args()
    width, height, source = rgb_png(args.source)
    other_width, other_height, draft = rgb_png(args.draft)
    if (width, height) != (1254, 1254) or (other_width, other_height) != (width, height):
        raise ValueError("both walls must be 1254-square")
    target = Path(args.output).resolve()
    if not target.is_relative_to(Path.cwd().resolve()) or target.exists():
        raise ValueError("output must be a new path inside the workspace")
    # The frame is a bare lower-right rock patch below the prior stone strings.
    x0, y0, x1, y1 = 730, 890, 920, 1010
    for y in range(y0, y1):
        for x in range(x0, x1):
            at = 3 * x
            for channel in range(3):
                # Source rock remains visible beneath the worn pigment.
                source[y][at + channel] = (source[y][at + channel] * 45 + draft[y][at + channel] * 55 + 50) // 100
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png_bytes(width, height, source))
    print(f"{target.relative_to(Path.cwd())}: blended rectangle {x0},{y0}..{x1 - 1},{y1 - 1}")


if __name__ == "__main__":
    main()
