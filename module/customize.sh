#!/system/bin/sh
# Informational only: this script never aborts and never changes anything.
# Without a metamodule the module simply mounts nothing, so the device still boots
# with the untouched stock installer -- a missing metamodule is not an error.

print() { command -v ui_print >/dev/null 2>&1 && ui_print "$1"; }

META=/data/adb/metamodule
TARGET=/system_ext/priv-app/OppoPackageInstaller/OppoPackageInstaller.apk

if [ -e "$META" ]; then
    M=$(readlink "$META" 2>/dev/null || echo present)
    print "- metamodule detected: $M"
    case "$M" in
        *hybrid_mount*|*hybrid-mount*|*Hybrid*)
            print "- Hybrid Mount found; set this module's backend to VFS, then reboot."
            print "- 已检测到 Hybrid Mount：请把本模块后端设为 VFS，然后重启。"
            ;;
        *)
            print "! This does not look like Hybrid Mount."
            print "! 本模块支持的元模块是 Hybrid Mount，且本模块后端必须设为 VFS。"
            ;;
    esac
else
    print "! No KernelSU/APatch metamodule found ($META is missing)."
    print "! Install Hybrid Mount first, then reinstall this module."
    print "! 未检测到元模块：请先安装 Hybrid Mount，再重新安装本模块。"
    print "! Nothing has been changed: the stock OPPO installer stays in use."
fi

print "- currently installed installer:"
print "  $(ls -l $TARGET 2>/dev/null || echo '<not found>')"
print "- after a reboot a size well under 100000 means the shell is mounted."
print "- 8979504 means the stock installer is still in place (nothing was replaced)."
print "- backend reminder: VFS, not OverlayFS or Magic Mount."

true
