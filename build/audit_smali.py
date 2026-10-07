#!/usr/bin/env python3
"""Audit our smali for invoke opcodes that do not match the callee's visibility.

Why this exists
---------------
`invoke-virtual` on a `private` method is not an assembler error -- smali assembles it
happily -- but Dalvik requires `invoke-direct`, so it fails at RUNTIME with
IllegalAccessError. Version 0.1 shipped exactly that: ConfigureActivity called its own
private probeIntent() with invoke-virtual, so the activity died on entry, never wrote the
state file, and the WebUI showed an empty candidate list with no error anywhere. Nothing
short of a device flash would have surfaced it.

So the rule is checked here: for every call to a method declared in our own sources, the
opcode must be `invoke-direct` when the method is private and `invoke-virtual` when it is
not. Calls into framework classes cannot be checked (their flags are not in the sources)
and are skipped -- which is fine, because we only ever emit those correctly by hand.

Usage: audit_smali.py [smali-root]   (default: shim/smali)
"""
import glob
import os
import re
import sys

DECL_RE = re.compile(r'^\.method\s+([^\n]*?)\s*(\w+)\(([^)]*)\)(\S+)\s*$', re.M)
CLASS_RE = re.compile(r'^\.class[^\n]*\s(L[^\s;]+;)', re.M)
CALL_RE = re.compile(r'invoke-(\w+)\s+\{([^}]*)\},\s*(L[^\s;]+;)->(\w+)\(')


def visibility(flags):
    if 'private' in flags:
        return 'private'
    if 'protected' in flags:
        return 'protected'
    return 'public'


def collect(root):
    """(class, method) -> visibility, for every method we declare ourselves."""
    decl = {}
    for path in sorted(glob.glob(os.path.join(root, '**', '*.smali'), recursive=True)):
        src = open(path, encoding='utf-8').read()
        m = CLASS_RE.search(src)
        if not m:
            continue
        cls = m.group(1)
        for d in DECL_RE.finditer(src):
            flags, name = d.group(1), d.group(2)
            decl[(cls, name)] = visibility(flags)
    return decl


def main(argv):
    root = argv[0] if argv else 'shim/smali'
    if not os.path.isdir(root):
        sys.exit(f'no such smali root: {root}')

    decl = collect(root)
    if not decl:
        sys.exit(f'found no method declarations under {root}')

    problems = []
    calls = 0
    for path in sorted(glob.glob(os.path.join(root, '**', '*.smali'), recursive=True)):
        for lineno, line in enumerate(open(path, encoding='utf-8'), 1):
            m = CALL_RE.search(line)
            if not m:
                continue
            op, _args, cls, name = m.groups()
            key = (cls, name)
            if key not in decl:
                continue  # framework or foreign class: not checkable here
            calls += 1
            vis = decl[key]
            want = 'direct' if vis == 'private' else 'virtual'
            if op != want:
                problems.append((path, lineno, op, name, vis, want))

    print(f'smali invoke audit: {calls} self-call(s) checked across '
          f'{len(decl)} declared method(s)')
    if problems:
        for path, lineno, op, name, vis, want in problems:
            print(f'  {path}:{lineno}: invoke-{op} -> {name}() but it is {vis} '
                  f'(needs invoke-{want})', file=sys.stderr)
        sys.exit(f'{len(problems)} visibility mismatch(es)')
    print('OK: every self-call uses the opcode its visibility requires')


if __name__ == '__main__':
    main(sys.argv[1:])
