.class public Lcom/android/packageinstaller/ForwardActivity;
.super Landroid/app/Activity;
.source "ForwardActivity.java"

# COS-IFS forwarder.
#
# Takes whatever install intent reached us and re-dispatches it to the user's own
# third-party installer. See SPEC.md 4.
#
# Design notes that matter here:
#
#   * The copy constructor preserves the original flags, INCLUDING
#     FLAG_GRANT_READ_URI_PERMISSION. Because we hold the URI grant the caller gave
#     us, handing the same flag on to the target lets the system re-grant it on our
#     behalf. If device testing shows grants still getting lost, add an explicit
#     grantUriPermission() here (wrapped in try/catch: it throws SecurityException
#     when we do not actually hold the grant).
#
#   * setComponent(null) is REQUIRED. The incoming intent usually names us
#     explicitly (callers send cmp=com.android.packageinstaller/.InstallStart), and
#     a component the copy carried over would win over setPackage() and send the
#     intent straight back to this activity. See SPEC.md 3.3.
#
#   * startActivity is wrapped so that a missing target degrades into a log line
#     instead of a crash. A visible error message arrives with ConfigureActivity.

.field private static final TARGET_PACKAGE:Ljava/lang/String; = "com.rosan.installer.x.revived"

.method public constructor <init>()V
    .locals 0
    invoke-direct {p0}, Landroid/app/Activity;-><init>()V
    return-void
.end method

.method protected onCreate(Landroid/os/Bundle;)V
    .locals 5

    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V

    # Intent in = getIntent();
    invoke-virtual {p0}, Landroid/app/Activity;->getIntent()Landroid/content/Intent;
    move-result-object v0

    # if (in == null) { finish(); return; }
    if-eqz v0, :no_intent

    # Intent fwd = new Intent(in);
    new-instance v1, Landroid/content/Intent;
    invoke-direct {v1, v0}, Landroid/content/Intent;-><init>(Landroid/content/Intent;)V

    # fwd.setComponent(null);   <- otherwise the incoming component wins
    const/4 v2, 0x0
    invoke-virtual {v1, v2}, Landroid/content/Intent;->setComponent(Landroid/content/ComponentName;)Landroid/content/Intent;
    move-result-object v4

    # fwd.setPackage(TARGET_PACKAGE);
    sget-object v2, Lcom/android/packageinstaller/ForwardActivity;->TARGET_PACKAGE:Ljava/lang/String;
    invoke-virtual {v1, v2}, Landroid/content/Intent;->setPackage(Ljava/lang/String;)Landroid/content/Intent;
    move-result-object v4

    :try_start
    # startActivity(fwd);
    invoke-virtual {p0, v1}, Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V
    :try_end
    .catch Ljava/lang/Exception; {:try_start .. :try_end} :catch

    invoke-virtual {p0}, Landroid/app/Activity;->finish()V
    return-void

    :catch
    # Log.e("COS-IFS", "forward failed for " + TARGET_PACKAGE);
    const-string v2, "COS-IFS"
    new-instance v3, Ljava/lang/StringBuilder;
    invoke-direct {v3}, Ljava/lang/StringBuilder;-><init>()V
    const-string v4, "forward failed, target = "
    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-result-object v4
    sget-object v4, Lcom/android/packageinstaller/ForwardActivity;->TARGET_PACKAGE:Ljava/lang/String;
    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-result-object v4
    invoke-virtual {v3}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v3
    invoke-static {v2, v3}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I
    move-result v4

    invoke-virtual {p0}, Landroid/app/Activity;->finish()V
    return-void

    :no_intent
    invoke-virtual {p0}, Landroid/app/Activity;->finish()V
    return-void
.end method
