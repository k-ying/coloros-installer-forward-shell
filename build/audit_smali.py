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
In ConfigureActivity.writeStateFile() the two filter branches jump PAST the emit when
their predicate is true, and `if-nez` branches when the value is non-zero -- so BOTH must
use if-nez, because both predicates return 1 exactly when the emit has to be skipped:
    String.equals(pkg, ours)     -> 1 means "that is us"
    ArrayList.contains(seen,pkg) -> 1 means "already emitted"
Version 0.3 (and 0.1, 0.2) had the contains branch as if-eqz, which inverts it: it skipped
every package that had NOT been seen yet. `seen` stayed empty, no candidate was ever
emitted, and the WebUI listed no installers -- while the state file was still written with
a valid "selected=" line, so it looked like a package-visibility or permission problem
rather than an inverted branch. Only dumping the built APK's dex made it visible, because
the smali source "looks" right until you trace the polarity.

This area has now been misread twice: the first attempt at the repair flipped the equals
branch as well, which is the OPPOSITE bug (it emits us and silently drops every real
candidate). That was caught by simulating the loop over the device's actual resolve list,
not by reading it. Hence both opcodes are pinned here, so the next edit gets checked
instead of eyeballed.

A later edit added a third rule of the same kind: pickTarget() skips a saved entry when
String.length() == 0, which has to be if-eqz. That was ALSO first written as if-nez, which
would have skipped every useful entry and returned only the blanks.

All three are therefore pinned in the POLARITY table below, each scoped to its own method.
If any of this is restructured, update the table deliberately instead of deleting it.

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

# Branch-polarity rules: (file, method, anchor call, opcode the following branch must use,
# why). Each is a "jump past the work when the predicate says so" branch, so the opcode has
# to match the polarity of the value the call returns. Three have now been written
# backwards in this project, so they are pinned here instead of being eyeballed.
#
# Scoped per method on purpose: `contains` is context dependent. In the OLD pickTarget()
# `pkgs.contains(pkg) == 1` meant "this is a real candidate", so if-eqz was correct there,
# and flagging it would have taught us to ignore this check.
POLARITY = [
    ('ConfigureActivity.smali', 'writeStateFile',
     'Ljava/lang/String;->equals(Ljava/lang/Object;)Z', 'if-nez',
     'equals() == 1 means "we are looking at ourselves", which must skip the emit'),
    ('ConfigureActivity.smali', 'writeStateFile',
     'Ljava/util/ArrayList;->contains(Ljava/lang/Object;)Z', 'if-nez',
     'contains() == 1 means "already emitted", which must skip the emit'),
    ('ForwardActivity.smali', 'pickTarget',
     'Ljava/lang/String;->length()I', 'if-eqz',
     'length() == 0 means the saved entry is blank, so it must be skipped'),
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
    """Verify every call site listed in POLARITY has the branch polarity it needs."""
    problems = []
    cache = {}
    for fname, method, anchor, want, why in POLARITY:
        path = os.path.join(root, 'com', 'android', 'packageinstaller', fname)
        if path not in cache:
            cache[path] = open(path, encoding='utf-8').read() if os.path.isfile(path) else None
        src = cache[path]
        if src is None:
            problems.append(f'{path}: missing, cannot verify its polarity rules')
            continue

        m = re.search(r'^\.method[^\n]*\b' + re.escape(method) + r'[^\n]*$.*?^\.end method$',
                      src, re.M | re.S)
        if not m:
            problems.append(f'{path}: {method}() not found, cannot verify its polarity rules')
            continue
        offset = src[:m.start()].count('\n')  # 0-based line of the method header
        lines = m.group(0).splitlines()
        callee = anchor.split('->')[1].split('(')[0]

        hits = 0
        for i, line in enumerate(lines):
            if anchor not in line:
                continue
            hits += 1
            # The branch that consumes the result follows the call, but blank lines,
            # comments and the move-result/check-cast in between must not hide it.
            branch = None
            for follow in lines[i + 1:i + 16]:
                t = follow.strip()
                if t == '' or t.startswith('#'):
                    continue
                b = BRANCH_RE.match(follow)
                if b:
                    branch = b.group(1)
                    break
                if t.startswith('move-result') or t.startswith('check-cast'):
                    continue
                break
            lineno = offset + i + 1
            if branch is None:
                problems.append(f'{path}:{lineno}: {callee}() result is not consumed by a '
                                f'branch -- {why}')
            elif branch != want:
                problems.append(f'{path}:{lineno}: {callee}() is guarded by {branch}, '
                                f'needs {want} -- {why}')
        if hits == 0:
            problems.append(f'{path}: no {callee}() call found in {method}() -- if the code '
                            f'was restructured, update the POLARITY table in this script')
    print(f'  check 2: {len(POLARITY)} pinned branch(es) checked')
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
