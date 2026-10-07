#!/usr/bin/env bash
# Build the COS-IFS shell APK: a tiny forwarder holding the
# com.android.packageinstaller entry-point contract.
#
# The output keeps:
#   * our own manifest and smali (there is no upstream APK to patch)
#   * the STOCK system APK's APK Signing Block, so that PMS reads exactly the same
#     certificates it already has cached for com.android.packageinstaller
#
# Inputs (override through the environment):
#   SRC      shim project tree (AndroidManifest.xml + apktool.yml + smali/)  [shim]
#   FW       apktool framework dir, must contain 1.apk                      [work/fw]
#   DONOR    stock APK from YOUR OWN device (signature block source)        [work/OppoPackageInstaller.apk]
#   JAVA     java 21 binary                                                 [java]
#   APKTOOL  apktool jar                                                    [apktool.jar]
#   SIGNER   uber-apk-signer jar (zipalign only)                            [signer.jar]
#   OUT      output APK                                                     [dist/cos-ifs.apk]
set -euo pipefail
cd "$(dirname "$0")/.."
HERE=$(cd "$(dirname "$0")" && pwd)

SRC=${SRC:-shim}
FW=${FW:-work/fw}
DONOR=${DONOR:-work/OppoPackageInstaller.apk}
JAVA=${JAVA:-java}
APKTOOL=${APKTOOL:-apktool.jar}
SIGNER=${SIGNER:-signer.jar}
WORK=${WORK:-work}
OUT=${OUT:-dist/cos-ifs.apk}
JHOMEDIR=${JHOMEDIR:-$PWD/$WORK/home}

for f in "$DONOR" "$FW/1.apk"; do
    [ -e "$f" ] || { echo "missing input: $f  -- see build/README.md" >&2; exit 1; }
done

mkdir -p "$WORK" "$(dirname "$OUT")"

# 1) manifest + smali -> APK.
#    apktool caches its previous output in <SRC>/build/apk/ and does NOT invalidate that
#    cache when the smali changes (it just says "smali has not changed"), so drop it
#    first. This is the same trap the sibling project documents for its own cache.
#    If this step instead fails with a wall of "attribute android:... not found", the
#    framework is not reaching aapt2 -- check that shim/apktool.yml still declares
#    usesFramework.ids: [1].
rm -rf "$SRC/build"
rm -f "$WORK/shim-unsigned.apk"
"$JAVA" -Duser.home="$JHOMEDIR" -jar "$APKTOOL" b "$SRC" -p "$FW" -o "$WORK/shim-unsigned.apk"

# 2) zipalign, by way of uber-apk-signer.  The signature produced here is discarded
#    in step 3; this step exists only to align the zip.
#    Do not assume the output file name: uber-apk-signer rewrites it (it strips a
#    trailing "-unsigned"), so take whatever .apk it actually produced.
rm -rf "$WORK/shim-signed" && mkdir -p "$WORK/shim-signed"
"$JAVA" -Duser.home="$JHOMEDIR" -jar "$SIGNER" -a "$WORK/shim-unsigned.apk" -o "$WORK/shim-signed" >&2
SIGNED=$(ls "$WORK"/shim-signed/*.apk 2>/dev/null | head -1)
[ -n "$SIGNED" ] || { echo "signer produced no .apk in $WORK/shim-signed" >&2; exit 1; }

# 3) graft the STOCK system APK's signing block in place of ours.  This is what keeps
#    the signer certificates identical to what the device already recorded.
python3 "$HERE/graftsig.py" \
    "$SIGNED" \
    "$DONOR" \
    "$OUT"
