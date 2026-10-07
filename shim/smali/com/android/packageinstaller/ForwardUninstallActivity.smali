.class public Lcom/android/packageinstaller/ForwardUninstallActivity;
.super Lcom/android/packageinstaller/ForwardActivity;
.source "ForwardUninstallActivity.java"

# Same forwarding behaviour as ForwardActivity, reached through the uninstall side
# (ACTION_UNINSTALL_PACKAGE / ACTION_DELETE, scheme "package").
#
# It exists as a separate class purely so the boot self-check's two queries each
# resolve to exactly one component: the installer query must see ForwardActivity
# alone, and the uninstaller query must see this one alone. The logic is inherited,
# so there is nothing to duplicate.

.method public constructor <init>()V
    .locals 0
    invoke-direct {p0}, Lcom/android/packageinstaller/ForwardActivity;-><init>()V
    return-void
.end method
