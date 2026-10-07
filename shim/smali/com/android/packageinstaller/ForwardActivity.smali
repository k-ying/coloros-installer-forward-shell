.class public Lcom/android/packageinstaller/ForwardActivity;
.super Landroid/app/Activity;
.source "ForwardActivity.java"

# SKELETON. This currently does nothing but finish; the forwarding logic
# (intent copy + grantUriPermission + setPackage + startActivity) is the next step.
# See SPEC.md 4.
#
# Reminder for whoever writes it: the target package MUST be pinned with
# setPackage()/setComponent(). Without it the resolver can pick this very
# component and the intent loops forever. See SPEC.md 3.3.

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
