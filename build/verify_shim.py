#!/usr/bin/env python3
"""Assert the boot-critical invariants of a built COS-IFS shell APK.

Why this exists
---------------
`getRequiredInstallerLPr()` requires the system to expose EXACTLY ONE installer
component, and the uninstaller query must resolve to exactly one component too. Getting
that wrong means zero installers, which means the device does not boot -- a failure mode
the sibling project hit for real, once, and had to rescue through recovery.

Those counts are a property of the BUILT manifest, so they are asserted mechanically on
every build rather than eyeballed. The checks are:

  1. package / versionCode / versionName are the pinned values
  2. exactly one component matches the installer query
  3. exactly one component matches the uninstaller query
  4. the four caller-facing aliases exist, are exported, and have NO intent-filter
     (a filter on any of them would add a second match to check 2 or 3)
  5. the Configure alias and its target exist, are exported, and carry the CONFIGURE
     permission -- the alias needs its own, since an alias is a distinct component
  6. nothing requests a permission (the shell needs none, and a priv-app asking for an
     allowlisted privileged permission is its own boot hazard)

Usage:
    verify_shim.py <apk | AndroidManifest.xml> [--version-code N] [--version-name S]
Exits non-zero with a readable report on the first violated invariant.
"""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axml_manifest  # noqa: E402

DEFAULT_CAT = 'android.intent.category.DEFAULT'
INSTALL_ACTIONS = {'android.intent.action.INSTALL_PACKAGE'}
UNINSTALL_ACTIONS = {'android.intent.action.UNINSTALL_PACKAGE',
                     'android.intent.action.DELETE'}
APK_MIME = 'application/vnd.android.package-archive'
PKG = 'com.android.packageinstaller'
CONFIGURE_PERM = PKG + '.permission.CONFIGURE'

# Addressed by explicit cmp= from file managers and the like; must stay filterless.
CALLER_ALIASES = [PKG + '.InstallStart', PKG + '.UninstallerActivity',
                  PKG + '.UnarchiveActivity', PKG + '.UnarchiveErrorActivity']
FORWARDER = PKG + '.ForwardActivity'
UNINSTALLER = PKG + '.ForwardUninstallActivity'
CONFIGURE = PKG + '.ConfigureActivity'
CONFIGURE_ALIAS = PKG + '.Configure'

COMPONENT_KINDS = ('activity', 'activity-alias', 'receiver', 'service')


class Fail(Exception):
    pass


def load_manifest(path):
    """Accept either an APK or an already-extracted binary AndroidManifest.xml."""
    if path.lower().endswith('.apk'):
        with zipfile.ZipFile(path) as z:
            data = z.read('AndroidManifest.xml')
        fd, tmp = tempfile.mkstemp(suffix='.bin')
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
        try:
            return axml_manifest.parse(tmp)
        finally:
            os.unlink(tmp)
    return axml_manifest.parse(path)


def components(app):
    """Flatten to (kind, node) so aliases and activities are treated uniformly."""
    out = []
    for kind in COMPONENT_KINDS:
        for n in app.find(kind):
            out.append((kind, n))
    return out


def filters(node):
    return node.find('intent-filter')


def filter_names(f, tag):
    return {c.get('name') for c in f.find(tag) if c.get('name')}


def data_attrs(f):
    schemes, mimes, others = set(), set(), False
    for d in f.find('data'):
        for k, v in d.attrs.items():
            if k == 'scheme':
                schemes.add(v)
            elif k == 'mimeType':
                mimes.add(v)
            else:
                others = True
    return schemes, mimes, others


def matches(f, actions, scheme=None, mime=None):
    """Approximate IntentFilter matching: an omitted scheme/mimeType is a wildcard."""
    if not (filter_names(f, 'action') & actions):
        return False
    if DEFAULT_CAT not in filter_names(f, 'category'):
        return False
    schemes, mimes, _ = data_attrs(f)
    if scheme and schemes and scheme not in schemes:
        return False
    if scheme and not schemes:
        return False  # an intent carrying a URI needs the filter to accept it
    if mime and mimes and mime not in mimes:
        return False
    # a filter with no mimeType at all accepts any type
    return True


def query(app, actions, scheme, mime):
    hits = []
    for kind, n in components(app):
        if kind == 'receiver':
            continue
        for f in filters(n):
            if matches(f, actions, scheme, mime):
                hits.append(n.get('name') or '<unnamed>')
                break
    return hits


def exported(n):
    return n.get('exported') == 'true'


def main(argv):
    if not argv:
        sys.exit(__doc__)
    path = argv[0]
    expect_code = expect_name = None
    i = 1
    while i < len(argv):
        if argv[i] == '--version-code':
            i += 1
            expect_code = argv[i]
        elif argv[i] == '--version-name':
            i += 1
            expect_name = argv[i]
        else:
            sys.exit(f'unknown argument: {argv[i]}')
        i += 1

    root = load_manifest(path)
    app_list = root.find('application')
    if not app_list:
        raise Fail('no <application> element')
    app = app_list[0]

    print(f'verifying {path}')

    # 1. identity
    got_pkg = root.get('package')
    if got_pkg != PKG:
        raise Fail(f'package is {got_pkg!r}, expected {PKG!r}')
    code, name = root.get('versionCode'), root.get('versionName')
    if expect_code and str(code) != str(expect_code):
        raise Fail(f'versionCode is {code!r}, expected {expect_code!r}')
    if expect_name and str(name) != str(expect_name):
        raise Fail(f'versionName is {name!r}, expected {expect_name!r}')
    print(f'  package={got_pkg} versionCode={code} versionName={name}')

    # 2 & 3. the two self-check queries.
    # The installer query's scheme is ambiguous across AOSP versions -- it is built from
    # Uri.fromFile() (a "file" URI) in some releases and described as "content" elsewhere --
    # so require exactly one match on BOTH schemes and require them to be the same
    # component. Our filter declares both, so a stricter check costs nothing and covers
    # whichever the ROM actually uses.
    inst_file = query(app, INSTALL_ACTIONS, 'file', APK_MIME)
    inst_content = query(app, INSTALL_ACTIONS, 'content', APK_MIME)
    unin = query(app, UNINSTALL_ACTIONS, 'package', None)
    print(f'  installer query (file://)    -> {inst_file}')
    print(f'  installer query (content://) -> {inst_content}')
    print(f'  uninstaller query            -> {unin}')
    if len(inst_file) != 1 or len(inst_content) != 1:
        raise Fail('installer query must resolve to exactly 1 component under both the '
                   f'file:// and content:// forms; got {inst_file} and {inst_content}')
    if inst_file != inst_content:
        raise Fail(f'the two installer query forms disagree: {inst_file} vs {inst_content}')
    if inst_file[0] != FORWARDER:
        raise Fail(f'the sole installer component should be {FORWARDER}, got {inst_file[0]}')
    if len(unin) != 1:
        raise Fail(f'uninstaller query must resolve to exactly 1 component, got {len(unin)}: {unin}')
    if unin[0] != UNINSTALLER:
        raise Fail(f'the sole uninstaller component should be {UNINSTALLER}, got {unin[0]}')

    # 4. caller-facing aliases: present, exported, filterless
    by_name = {(n.get('name') or ''): (k, n) for k, n in components(app)}
    for a in CALLER_ALIASES:
        if a not in by_name:
            raise Fail(f'missing caller-facing alias {a}')
        kind, n = by_name[a]
        if kind != 'activity-alias':
            raise Fail(f'{a} should be an activity-alias, found <{kind}>')
        if not exported(n):
            raise Fail(f'{a} must be exported (callers use an explicit cmp=)')
        if filters(n):
            raise Fail(f'{a} must be filterless; a filter would add a second self-check match')
        if not n.get('targetActivity'):
            raise Fail(f'{a} has no targetActivity')
    print(f'  {len(CALLER_ALIASES)} caller aliases present, exported, filterless')

    # 5. configuration surface
    for label, want_alias in ((CONFIGURE_ALIAS, True), (CONFIGURE, False)):
        if label not in by_name:
            raise Fail(f'missing configuration component {label}')
        kind, n = by_name[label]
        if want_alias and kind != 'activity-alias':
            raise Fail(f'{label} should be an activity-alias, found <{kind}>')
        if not exported(n):
            raise Fail(f'{label} must be exported (the WebUI reaches it through am start)')
        if n.get('permission') != CONFIGURE_PERM:
            raise Fail(f'{label} must be gated by {CONFIGURE_PERM}, '
                       f'found {n.get("permission")!r}')
        if filters(n):
            raise Fail(f'{label} must be filterless')
    print(f'  {CONFIGURE_ALIAS} -> {CONFIGURE}, both gated by the signature permission')

    # 6. permissions: NONE requested, and exactly one declared.
    #
    # This assertion was briefly relaxed to allow QUERY_ALL_PACKAGES, and the very next
    # device boot looped. A priv-app requesting a permission it did not request before is
    # exactly the class of change that can stop a device from coming up -- it is why the
    # sibling project spent so long trimming its own request set -- so the rule is absolute
    # again: this shell requests nothing.
    #
    # If package visibility ever needs solving, solve it OUTSIDE the manifest. The WebUI
    # already runs as root and can resolve a component itself, and an intent carrying an
    # explicit ComponentName is not subject to visibility filtering at all.
    ups = {c.get('name') for c in root.kids if c.tag.startswith('uses-permission')}
    if ups:
        raise Fail(f'the shell must request NO permissions, found {sorted(ups)}; adding one '
                   f'to a priv-app is a boot hazard')
    declared = [c.get('name') for c in root.find('permission')]
    if declared != [CONFIGURE_PERM]:
        raise Fail(f'expected exactly one declared permission ({CONFIGURE_PERM}), '
                   f'got {declared}')
    print('  requests no permissions at all; declares only the CONFIGURE permission')

    print('OK: every boot-critical invariant holds')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Fail as e:
        print(f'FAIL: {e}', file=sys.stderr)
        sys.exit(1)
