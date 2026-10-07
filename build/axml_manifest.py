"""Structured AndroidManifest (AXML) extractor.

Usage: python3 .apkwork/manifest.py <AndroidManifest.xml> [--components|--perms|--application]

Prints a resolved component/permission view that axml.py cannot produce
(axml.py discards attribute namespaces and only flattens tags).
"""
import struct, sys

def parse_strings(buf, off):
    t, hs, sz = struct.unpack_from('<HHI', buf, off)
    cnt, sty, flags, sstart, stystart = struct.unpack_from('<IIIII', buf, off+8)
    offs = struct.unpack_from('<%dI' % cnt, buf, off+hs)
    utf8 = bool(flags & (1<<8))
    base = off + sstart
    out = []
    for o in offs:
        p = base + o
        if utf8:
            n = buf[p]; p += 1
            if n & 0x80:
                n = ((n & 0x7f) << 8) | buf[p]; p += 1
            out.append(buf[p:p+n].decode('utf-8', 'replace'))
        else:
            n = struct.unpack_from('<H', buf, p)[0]; p += 2
            if n & 0x8000:
                n = ((n & 0x7fff) << 16) | struct.unpack_from('<H', buf, p)[0]; p += 2
            out.append(buf[p:p+n*2].decode('utf-16-le', 'replace'))
    return out


class Node:
    __slots__ = ('tag', 'attrs', 'kids')
    def __init__(self, tag, attrs):
        self.tag = tag; self.attrs = attrs; self.kids = []
    def get(self, name, default=None):
        return self.attrs.get(name, default)
    def find(self, tag):
        return [k for k in self.kids if k.tag == tag]
    def dump(self, ind=0):
        pad = '  ' * ind
        nm = self.get('name')
        extra = ''
        if nm:
            extra += f' name={nm}'
        for k in ('targetActivity', 'exported', 'enabled', 'authorities', 'process',
                  'permission', 'sharedUserId'):
            v = self.get(k)
            if v is not None:
                extra += f' {k}={v}'
        print(f'{pad}<{self.tag}{extra}>')
        for c in self.kids:
            if c.tag in ('intent-filter', 'meta-data', 'uses-permission',
                         'uses-permission-sdk-23', 'uses-permission-sdk-m'):
                continue
            c.dump(ind+1)


def parse(path):
    buf = open(path, 'rb').read()
    t, hs, sz = struct.unpack_from('<HHI', buf, 0)
    strings, resmap = [], []
    root = None
    stack = []
    pos = hs
    while pos < sz:
        ct, chs, csz = struct.unpack_from('<HHI', buf, pos)
        if csz == 0:
            break
        if ct == 0x0001:
            strings = parse_strings(buf, pos)
        elif ct == 0x0180:
            n = (csz - chs) // 4
            resmap = list(struct.unpack_from('<%dI' % n, buf, pos+chs))
        elif ct == 0x0102:
            ns, name = struct.unpack_from('<II', buf, pos+16)
            attrStart, attrSize, attrCount = struct.unpack_from('<HHH', buf, pos+24)
            abase = pos + 16 + attrStart
            attrs = {}
            for i in range(attrCount):
                ao = abase + i*attrSize
                ans, anm, raw = struct.unpack_from('<III', buf, ao)
                dt = buf[ao+15]
                data = struct.unpack_from('<I', buf, ao+16)[0]
                nm = strings[anm] if anm < len(strings) else '?'
                val = strings[raw] if (raw != 0xFFFFFFFF and raw < len(strings)) else None
                if val is None:
                    if dt == 0x12:   val = 'true' if data else 'false'
                    elif dt == 0x10: val = str(struct.unpack('<i', struct.pack('<I', data))[0])
                    elif dt == 0x11: val = hex(data)
                    elif dt == 0x01: val = f'@ref/0x{data:08x}'
                    else:            val = f'<t{dt:#x}:{data:#x}>'
                attrs[nm] = val
            node = Node(strings[name] if name < len(strings) else '?', attrs)
            if stack:
                stack[-1].kids.append(node)
            else:
                root = node
            stack.append(node)
        elif ct == 0x0103:
            if stack:
                stack.pop()
        pos += csz
    return root


def main():
    path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else '--all'
    root = parse(path)
    print(f'# package={root.get("package")}  versionCode={root.get("versionCode")} '
          f'versionName={root.get("versionName")}')
    if root.get('sharedUserId'):
        print(f'# sharedUserId={root.get("sharedUserId")}')
    if root.get('coreApp'):
        print(f'# coreApp={root.get("coreApp")}')
    app = root.find('application')
    app = app[0] if app else None

    if mode in ('--all', '--perms'):
        ups = [c for c in root.kids if c.tag.startswith('uses-permission')]
        print(f'\n## uses-permission ({len(ups)})')
        for c in ups:
            print(f'   {c.get("name")}   [{c.tag}]')
        decl = root.find('permission')
        if decl:
            print(f'\n## declared <permission> ({len(decl)})')
            for c in decl:
                print(f'   {c.get("name")}  protectionLevel={c.get("protectionLevel")}')

    if app is not None and mode in ('--all', '--application'):
        for k in ('name', 'label', 'theme', 'allowBackup', 'extractNativeLibs',
                  'requestLegacyExternalStorage', 'usesCleartextTraffic',
                  'networkSecurityConfig', 'debuggable', 'process',
                  'android:sharedUserId'):
            v = app.get(k)
            if v is not None:
                print(f'# application.{k} = {v}')

    if mode in ('--all', '--components'):
        for kind in ('activity-alias', 'activity', 'receiver', 'service', 'provider'):
            nodes = app.find(kind) if app else []
            if not nodes:
                continue
            print(f'\n## {kind} ({len(nodes)})')
            for n in nodes:
                nm = n.get('name') or ''
                ta = n.get('targetActivity')
                line = f'   {nm}'
                if ta:
                    line += f'  -> target={ta}'
                flags = []
                for k in ('exported', 'enabled', 'launchMode', 'permission', 'process',
                          'authorities', 'directBootAware'):
                    if n.get(k) is not None:
                        flags.append(f'{k}={n.get(k)}')
                if flags:
                    line += '  [' + ' '.join(flags) + ']'
                print(line)
                for f in n.find('intent-filter'):
                    acts = [a.get('name') for a in f.find('action')]
                    cats = [a.get('name') for a in f.find('category')]
                    data = []
                    for d in f.find('data'):
                        data.append(','.join(f'{k}={v}' for k, v in d.attrs.items()
                                             if k in ('scheme', 'host', 'port', 'path',
                                                      'pathPattern', 'pathPrefix',
                                                      'mimeType')))
                    pr = f.get('priority')
                    s = f'        filter prio={pr or "0"} act={acts}'
                    if cats:
                        s += f' cat={[c.split(".")[-1] for c in cats]}'
                    if data:
                        s += f' data={data}'
                    print(s)


if __name__ == '__main__':
    main()
