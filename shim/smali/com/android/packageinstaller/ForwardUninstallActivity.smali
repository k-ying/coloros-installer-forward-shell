.class public Lcom/android/packageinstaller/ForwardUninstallActivity;
.super Landroid/app/Activity;
.source "ForwardUninstallActivity.java"

# SKELETON. Same as ForwardActivity but for ACTION_UNINSTALL_PACKAGE / ACTION_DELETE
# (scheme "package"). It is a separate class only so that the two boot self-check
# queries each resolve to exactly one component; the forwarding logic will be shared.
# See SPEC.md 3.1 and 4.

.method public constructor <init>()V
    .locals 0
    invoke-direct {p0}, Landroid/app/Activity;-><init>()V
    return-void
.end method

.method protected onCreate(Landroid/os/Bundle;)V
    .locals 0
    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V
    invoke-virtual {p0}, Landroid/app/Activity;->finish()V
    return-void
.end method
