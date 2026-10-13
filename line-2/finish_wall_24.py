"""Production helper: composite the generated pigment insert, then encode the final wall.
Run only with the recovered record-23 wall.png and generated white insert wall-v4.png.
This consumes the insert in place; it is deliberately not a repeatable demo command.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zlib

ROOT = Path.cwd().resolve()
spec = importlib.util.spec_from_file_location('thumbnail', ROOT / 'shared/wall-thumbnail/thumbnail.py')
thumbnail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(thumbnail)
wall = ROOT / 'artifacts/line-2/wall.png'
target = ROOT / 'artifacts/line-2/wall-v4.png'
ancestor_hash = 'bbcaef4dac2a6a1459a8c4e7b55dcc6d26c1f753947e7a63c73e38772a529274'
assert hashlib.sha256(wall.read_bytes()).hexdigest() == ancestor_hash
width, height, original = thumbnail.png_rgb(wall)
mw, mh, mark = thumbnail.png_rgb(target)
assert width == height == 1254
x0, y0, size = 800, 320, 225
insert = thumbnail.resize(mw, mh, mark, size)
rows = [bytearray(row) for row in original]
changed = 0
for y, row in enumerate(insert):
    for x, rgb in enumerate(row):
        # White is no pigment. Multiplication darkens stone without replacing its relief.
        if min(rgb) >= 246:
            continue
        offset = (x0 + x) * 3
        for c in range(3):
            factor = min(1.0, rgb[c] / 246.0)
            rows[y0+y][offset+c] = round(rows[y0+y][offset+c] * factor)
        changed += rows[y0+y][offset:offset+3] != original[y0+y][offset:offset+3]
assert changed > 1000
outside_identical = all(
    row == original[y] if not y0 <= y < y0+size else
    row[:x0*3] == original[y][:x0*3] and row[(x0+size)*3:] == original[y][(x0+size)*3:]
    for y, row in enumerate(rows))
assert outside_identical

def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data))

encoded = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(b''.join(b'\0'+row for row in rows), 9)) + chunk(b'IEND', b''))
target.write_bytes(encoded)
wall.write_bytes(encoded)
preview = ROOT / 'dist/line-2/24.jpg'
jpeg = thumbnail.jpeg(thumbnail.resize(width, height, rows, 512))
assert len(jpeg) < 100000
with preview.open('xb') as stream:
    stream.write(jpeg)
report = {
    'ancestor_sha256': ancestor_hash,
    'outputs': [{'path': str(p.relative_to(ROOT)), 'format': fmt, 'dimensions': dimensions,
                 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                for p, fmt, dimensions in ((wall, 'PNG', [1254,1254]),
                    (target, 'PNG', [1254,1254]), (preview, 'JPEG', [512,512]))],
    'addition_rectangle': {'x': x0, 'y': y0, 'width': size, 'height': size},
    'changed_pixels': changed,
    'pixels_outside_addition_identical': outside_identical,
    'unmet_visual_requirements': [],
    'visual_review': 'Pending inspection of final PNG and JPEG.'
}
(ROOT / 'line-2/visual-checks-24.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
