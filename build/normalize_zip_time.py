#!/usr/bin/env python3
"""Normalise the zip timestamps of a built APK, in place, so builds are reproducible.

Why
---
Everything else about this build is deterministic -- identical entry contents, CRCs,
compression, offsets, padding and a signing block that comes out byte-identical -- except
the DOS date/time stamped into every local header and central-directory entry, which is
simply when the build ran. The effect is that two builds of the same source produce two
different APKs, which makes any hash published in the docs unverifiable and makes a diff
between two builds meaningless.

Why patching rather than rewriting
----------------------------------
Rewriting the archive with zipfile would drop the zipalign padding and therefore break
entry alignment -- harmless today (the shell has no native libraries) and a silent trap the
moment it does. Patching the four timestamp bytes in place leaves sizes, offsets and
padding bit-identical, so the only thing that changes is the thing we mean to change.

Usage:
    normalize_zip_time.py <apk> [more.apk ...]
Reports how many headers it touched and refuses to continue if anything else moved.
"""
import struct
import sys
import zipfile

# 2026-10-07 00:00:00 in MS-DOS format: year-1980 << 9 | month << 5 | day
FIXED_DATE = ((2026 - 1980) << 9) | (10 << 5) | 7
FIXED_TIME = 0

LOCAL_SIG = b'PK\x03\x04'
CENTRAL_SIG = b'PK\x01\x02'
EOCD_SIG = b'PK\x05\x06'


def normalize(path):
    before = open(path, 'rb').read()
    d = bytearray(before)
    touched = []

    with zipfile.ZipFile(path) as z:
        local_offsets = [i.header_offset for i in z.infolist()]

    for h in local_offsets:
        if d[h:h + 4] != LOCAL_SIG:
            sys.exit(f'{path}: no local header at {h}')
        d[h + 10:h + 14] = struct.pack('<HH', FIXED_TIME, FIXED_DATE)
        touched.append(('local', h))

    eocd = d.rfind(EOCD_SIG)
    if eocd < 0:
        sys.exit(f'{path}: no EOCD')
    cd_size, cd_off = struct.unpack_from('<II', d, eocd + 12)

    p, end = cd_off, cd_off + cd_size
    while p < end:
        if d[p:p + 4] != CENTRAL_SIG:
            sys.exit(f'{path}: expected a central directory entry at {p}')
        d[p + 12:p + 16] = struct.pack('<HH', FIXED_TIME, FIXED_DATE)
        touched.append(('central', p))
        fn, ex, cm = struct.unpack_from('<HHH', d, p + 28)
        p += 46 + fn + ex + cm
    if p != end:
        sys.exit(f'{path}: central directory walk overran ({p} != {end})')

    # --- verification -------------------------------------------------------
    if len(d) != len(before):
        sys.exit(f'{path}: length changed')
    changed = [i for i in range(len(before)) if before[i] != d[i]]
    allowed = set()
    for kind, off in touched:
        base = off + 10 if kind == 'local' else off + 12
        allowed.update(range(base, base + 4))
    stray = [i for i in changed if i not in allowed]
    if stray:
        sys.exit(f'{path}: bytes changed outside the timestamp fields: {stray[:8]}')

    open(path, 'wb').write(bytes(d))
    print(f'{path}: normalised {len(touched)} timestamps '
          f'({len(changed)} bytes touched, no offsets moved)')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        normalize(arg)
