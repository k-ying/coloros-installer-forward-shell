#!/usr/bin/env python3
"""Audit our smali for the two failure modes that the device cannot warn us about.

Check 1 -- invoke opcode vs callee visibility
---------------------------------------------
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

Check 2 -- branch polarity of the candidate-enumeration loop
------------------------------------------------------------
In ConfigureActivity.writeStateFile() each filter branch jumps PAST the emit when its
answer is true, so the opcode has to match the polarity of the value:
    String.equals(pkg, ours)     -> 1 means "that is us"      -> if-eqz
    ArrayList.contains(seen,pkg) -> 1 means "already emitted" -> if-nez
Version 0.3 (and 0.1, 0.2) had these two swapped. Every candidate then failed the first
branch, `seen` stayed empty, and the WebUI listed no installers -- while the state file
was still written with a valid "selected=" line, so it looked like a package-visibility or
permission problem rather than a one-opcode inversion. Only dumping the built APK's dex
made it visible, because reading the smali source "looks" right until you trace it.

The polarity is therefore pinned here. If the enumeration is ever restructured, update
this check deliberately instead of deleting it.

Usage: audit_smali.py [smali-root]   (default: shim/smali)
"""
import glob
import os
import re
import sys

DECL_RE = re.compile(r'^\.method\s+([^\n]*?)\s*(\w+)\(([^)]*)\)(\S+)\s*$', re.M)
CLASS_RE = re.compile(r'^\.class[^\n]*\s(L[^\s;]+;)', re.M)
CALL_RE = re.compile(r'invoke-(\w+)\s+\{([^}]*)\},\s*(L[^\s;]+;)->(\w+)\(')
BRANCH_RE = re.compile(r'^\s*(if-(?:eqz|nez|eq|ne|lt|ge|gt|le))\b')

# (anchor that starts the sequence, opcode the following branch must use, what it means)
POLARITY = [
    ('Ljava/lang/String;->equals(Ljava/lang/Object;)Z', 'if-eqz',
     'equals() == 1 means "we are looking at ourselves", which must skip the emit'),
    ('Ljava/util/ArrayList;->contains(Ljava/lang/Object;)Z', 'if-nez',
     'contains() == 1 means "already emitted", which must skip the emit'),
]


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


def check_invoke_opcodes(root, decl):
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
                problems.append(f'{path}:{lineno}: invoke-{op} -> {name}() but it is '
                                f'{vis} (needs invoke-{want})')
    print(f'  check 1: {calls} self-call(s) checked across {len(decl)} declared method(s)')
    return problems


def check_branch_polarity(root):
    """Verify the candidate-enumeration branches inside writeStateFile().

    Scoped deliberately to that one method: `contains` is context dependent. In
    ForwardActivity.pickTarget() `pkgs.contains(pkg) == 1` means "this is a real
    candidate", so the branch there is if-eqz and is CORRECT. Flagging it would train
    us to ignore this check, which is worse than not having it.
    """
    problems = []
    path = os.path.join(root, 'com', 'android', 'packageinstaller', 'ConfigureActivity.smali')
    if not os.path.isfile(path):
        return [f'{path}: missing, cannot verify the enumeration branches']

    src = open(path, encoding='utf-8').read()
    m = re.search(r'^\.method[^\n]*writeStateFile[^\n]*$.*?^\.end method$', src, re.M | re.S)
    if not m:
        return [f'{path}: writeStateFile() not found, cannot verify the enumeration branches']
    body = m.group(0)
    offset = src[:m.start()].count('\n')  # 0-based line of the method header
    lines = body.splitlines()

    for anchor, want, why in POLARITY:
        hits = 0
        for i, line in enumerate(lines):
            if anchor not in line:
                continue
            hits += 1
            # the branch that consumes move-result follows the call immediately
            branch = None
            for follow in lines[i + 1:i + 5]:
                b = BRANCH_RE.match(follow)
                if b:
                    branch = b.group(1)
                    break
            lineno = offset + i + 1
            method = anchor.split('->')[1].split('(')[0]
            if branch is None:
                problems.append(f'{path}:{lineno}: {method}() result is not consumed by a '
                                f'branch -- {why}')
            elif branch != want:
                problems.append(f'{path}:{lineno}: {method}() is guarded by {branch}, '
                                f'needs {want} -- {why}')
        if hits == 0:
            problems.append(f'{path}: no {anchor.split("->")[1].split("(")[0]}() branch '
                            f'found in writeStateFile() -- if the loop was restructured, '
                            f'update the POLARITY table in this script')
    print(f'  check 2: enumeration branches in writeStateFile() checked')
    return problems


def main(argv):
    root = argv[0] if argv else 'shim/smali'
    if not os.path.isdir(root):
        sys.exit(f'no such smali root: {root}')

    decl = collect(root)
    if not decl:
        sys.exit(f'found no method declarations under {root}')

    print('smali audit:')
    problems = check_invoke_opcodes(root, decl) + check_branch_polarity(root)
    if problems:
        for p in problems:
            print(f'  {p}', file=sys.stderr)
        sys.exit(f'{len(problems)} problem(s)')
    print('OK: call opcodes match visibility, enumeration branches have the right polarity')


if __name__ == '__main__':
    main(sys.argv[1:])
