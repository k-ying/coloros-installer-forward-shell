.class public Lcom/android/packageinstaller/ForwardActivity;
.super Landroid/app/Activity;
.source "ForwardActivity.java"

# COS-IFS forwarder.
#
# Takes whatever install intent reached us, works out which third-party installer to
# hand it to, and re-dispatches it. See SPEC.md 4.
#
# Notes that are load-bearing:
#
#   * setComponent(null) is REQUIRED, not defensive. Callers send
#     cmp=com.android.packageinstaller/.InstallStart, and a component surviving the
#     copy constructor would beat setPackage() and send the intent straight back here.
#     See SPEC.md 3.3.
#
#   * The copy constructor preserves the original flags, so
#     FLAG_GRANT_READ_URI_PERMISSION rides along and the system re-grants the content
#     URI to the target on our behalf -- we hold the grant the caller gave us. If device
#     testing shows grants still getting lost, add an explicit grantUriPermission()
#     wrapped in try/catch (it throws SecurityException when we do not hold the grant).
#
#   * pickTarget() runs the discovery described in SPEC 4.1 and never returns our own
#     package; onCreate falls back to TARGET_PACKAGE if discovery comes up empty, which
#     also covers the case where package-visibility rules hide everything from us.

.field private static final TARGET_PACKAGE:Ljava/lang/String; = "com.rosan.installer.x.revived"

# Only used as the probe URI's authority/scheme; never opened.
.field private static final PROBE_URI:Ljava/lang/String; = "content://cos.ifs/probe.apk"

.field private static final APK_MIME:Ljava/lang/String; = "application/vnd.android.package-archive"

.field private static final PREFERRED:[Ljava/lang/String;

.method static constructor <clinit>()V
    .locals 3

    const/4 v0, 0x3

    new-array v0, v0, [Ljava/lang/String;

    const/4 v1, 0x0

    const-string v2, "com.rosan.installer.x.revived"

    aput-object v2, v0, v1

    const/4 v1, 0x1

    const-string v2, "com.rosan.installer.x"

    aput-object v2, v0, v1

    const/4 v1, 0x2

    const-string v2, "com.rosan.installer"

    aput-object v2, v0, v1

    sput-object v0, Lcom/android/packageinstaller/ForwardActivity;->PREFERRED:[Ljava/lang/String;

    return-void
.end method

.method public constructor <init>()V
    .locals 0

    invoke-direct {p0}, Landroid/app/Activity;-><init>()V

    return-void
.end method

# Which package should receive the forwarded intent?  Returns null when nothing
# suitable is installed (or nothing is visible to us).
.method public pickTarget()Ljava/lang/String;
    .locals 11

    # Intent probe = new Intent(ACTION_INSTALL_PACKAGE);
    new-instance v0, Landroid/content/Intent;

    const-string v1, "android.intent.action.INSTALL_PACKAGE"

    invoke-direct {v0, v1}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    # probe.addCategory(CATEGORY_DEFAULT);
    const-string v1, "android.intent.category.DEFAULT"

    invoke-virtual {v0, v1}, Landroid/content/Intent;->addCategory(Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v1

    # probe.setDataAndType(Uri.parse(PROBE_URI), APK_MIME);
    sget-object v1, Lcom/android/packageinstaller/ForwardActivity;->PROBE_URI:Ljava/lang/String;

    invoke-static {v1}, Landroid/net/Uri;->parse(Ljava/lang/String;)Landroid/net/Uri;

    move-result-object v1

    sget-object v2, Lcom/android/packageinstaller/ForwardActivity;->APK_MIME:Ljava/lang/String;

    invoke-virtual {v0, v1, v2}, Landroid/content/Intent;->setDataAndType(Landroid/net/Uri;Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v1

    # List<ResolveInfo> cands = getPackageManager().queryIntentActivities(probe, 0);
    invoke-virtual {p0}, Landroid/app/Activity;->getPackageManager()Landroid/content/pm/PackageManager;

    move-result-object v1

    const/4 v2, 0x0

    invoke-virtual {v1, v0, v2}, Landroid/content/pm/PackageManager;->queryIntentActivities(Landroid/content/Intent;I)Ljava/util/List;

    move-result-object v0

    if-eqz v0, :none

    # List<String> pkgs = new ArrayList<>();
    new-instance v1, Ljava/util/ArrayList;

    invoke-direct {v1}, Ljava/util/ArrayList;-><init>()V

    # for (int i = 0; i < cands.size(); i++)
    const/4 v2, 0x0

    :loop
    invoke-interface {v0}, Ljava/util/List;->size()I

    move-result v3

    if-ge v2, v3, :loop_end

    invoke-interface {v0, v2}, Ljava/util/List;->get(I)Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Landroid/content/pm/ResolveInfo;

    iget-object v3, v3, Landroid/content/pm/ResolveInfo;->activityInfo:Landroid/content/pm/ActivityInfo;

    if-eqz v3, :loop_next

    iget-object v3, v3, Landroid/content/pm/ActivityInfo;->packageName:Ljava/lang/String;

    invoke-virtual {v1, v3}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    move-result v4

    :loop_next
    add-int/lit8 v2, v2, 0x1

    goto :loop

    # pkgs.remove(getPackageName());   <- never forward to ourselves
    :loop_end
    invoke-virtual {p0}, Landroid/app/Activity;->getPackageName()Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v1, v2}, Ljava/util/ArrayList;->remove(Ljava/lang/Object;)Z

    move-result v3

    # for (String p : PREFERRED) if (pkgs.contains(p)) return p;
    sget-object v2, Lcom/android/packageinstaller/ForwardActivity;->PREFERRED:[Ljava/lang/String;

    array-length v3, v2

    const/4 v4, 0x0

    :ploop
    if-ge v4, v3, :ploop_end

    aget-object v5, v2, v4

    invoke-virtual {v1, v5}, Ljava/util/ArrayList;->contains(Ljava/lang/Object;)Z

    move-result v6

    if-eqz v6, :ploop_next

    return-object v5

    :ploop_next
    add-int/lit8 v4, v4, 0x1

    goto :ploop

    # if (pkgs.size() == 1) return pkgs.get(0);
    :ploop_end
    invoke-virtual {v1}, Ljava/util/ArrayList;->size()I

    move-result v2

    const/4 v3, 0x1

    if-ne v2, v3, :none

    const/4 v2, 0x0

    invoke-virtual {v1, v2}, Ljava/util/ArrayList;->get(I)Ljava/lang/Object;

    move-result-object v2

    check-cast v2, Ljava/lang/String;

    return-object v2

    :none
    const/4 v0, 0x0

    return-object v0
.end method

.method protected onCreate(Landroid/os/Bundle;)V
    .locals 6

    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V

    # Intent in = getIntent();
    invoke-virtual {p0}, Landroid/app/Activity;->getIntent()Landroid/content/Intent;

    move-result-object v0

    if-eqz v0, :no_intent

    # Intent fwd = new Intent(in);
    new-instance v1, Landroid/content/Intent;

    invoke-direct {v1, v0}, Landroid/content/Intent;-><init>(Landroid/content/Intent;)V

    # fwd.setComponent(null);   <- otherwise the incoming component wins
    const/4 v2, 0x0

    invoke-virtual {v1, v2}, Landroid/content/Intent;->setComponent(Landroid/content/ComponentName;)Landroid/content/Intent;

    move-result-object v4

    # String target = pickTarget(); if (target == null) target = TARGET_PACKAGE;
    invoke-virtual {p0}, Lcom/android/packageinstaller/ForwardActivity;->pickTarget()Ljava/lang/String;

    move-result-object v2

    if-nez v2, :have_target

    sget-object v2, Lcom/android/packageinstaller/ForwardActivity;->TARGET_PACKAGE:Ljava/lang/String;

    # fwd.setPackage(target);
    :have_target
    invoke-virtual {v1, v2}, Landroid/content/Intent;->setPackage(Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v4

    :try_start
    invoke-virtual {p0, v1}, Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V
    :try_end
    .catch Ljava/lang/Exception; {:try_start .. :try_end} :catch

    invoke-virtual {p0}, Landroid/app/Activity;->finish()V

    return-void

    # Log.e("COS-IFS", "forward failed, target = " + target);
    :catch
    const-string v3, "COS-IFS"

    new-instance v4, Ljava/lang/StringBuilder;

    invoke-direct {v4}, Ljava/lang/StringBuilder;-><init>()V

    const-string v5, "forward failed, target = "

    invoke-virtual {v4, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v5

    invoke-virtual {v4, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v5

    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v5

    invoke-static {v3, v5}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I

    move-result v5

    invoke-virtual {p0}, Landroid/app/Activity;->finish()V

    return-void

    :no_intent
    invoke-virtual {p0}, Landroid/app/Activity;->finish()V

    return-void
.end method
