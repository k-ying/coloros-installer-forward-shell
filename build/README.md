# build/ —— 如何构建 COS-IFS 的壳 APK

壳是我们自己写的 app（一个 manifest + 少量 smali），所以这里**没有上游 APK 要改**，
流程很短：`smali → APK → 对齐 → 嫁接签名块`。

```
shim/                    壳的源码：AndroidManifest.xml + apktool.yml + smali/
build/build_shim.sh      产出可用的壳 APK
build/graftsig.py        把原厂 APK 的签名块移植过来（从姊妹项目原样复用）
work/                    构建工作区（git 忽略）
dist/                    产出的 APK（git 忽略）
```

## 需要自备的两样东西（都来自你自己的设备）

| 原料 | 说明 |
|---|---|
| `work/OppoPackageInstaller.apk` | 你设备上的 `/system_ext/priv-app/OppoPackageInstaller/OppoPackageInstaller.apk`，**只为取签名块** |
| `work/fw/1.apk` | apktool 的 framework。见下 |

壳的 manifest 里全是 `android:` 属性，aapt2 必须能解析它们，所以**构建必须要有 framework**：

```sh
su -c 'cp /system/framework/framework-res.apk /sdcard/Download/'
adb pull /sdcard/Download/framework-res.apk work/framework-res.apk
java -jar apktool.jar if work/framework-res.apk -p work/fw
```

（`work/fw/1.apk` 就是这一步的产物。姊妹项目里那份也能直接用。）

## 依赖

JDK（**构建壳需要能跑 `java -jar apktool.jar`，JRE 就够**；写 smali 不需要 JDK 的编译器）、
[apktool](https://github.com/iBotPeaches/Apktool) 3.x、以及
[uber-apk-signer](https://github.com/patrickfav/uber-apk-signer)（只用来 zipalign）。

**不需要 Android SDK，也不需要 gradle** —— 这正是选择纯 smali 路线的原因。

## 跑

```sh
JAVA=/path/to/java \
APKTOOL=/path/to/apktool.jar \
SIGNER=/path/to/uber-apk-signer.jar \
  bash build/build_shim.sh
```

产物：`dist/cos-ifs.apk`。`graftsig.py` 会打印四项校验，都应为 `OK`：

- 输出的签名块与 donor **逐字节一致**
- 所有 zip 条目偏移**未改变**
- zip CRC 全通过
- `.so` 条目对齐检查

## 两个已经踩过的坑

**① `shim/apktool.yml` 必须声明 `usesFramework.ids: [1]`。**

少了它，apktool **不会把 framework 传给 aapt2**（命令行里根本没有 `-I`），于是**每一个**
`android:` 属性都报 `attribute android:xxx not found`，最后 `exit code 1`。
报错形式很有迷惑性 —— 看起来像 manifest 写错了，其实不是。

**② `versionInfo.versionCode` 必须是裸整数。**

写成 `'17000001'`（带引号）会直接抛 `NumberFormatException`。

## 关于 `versionCode` / `versionName`

壳的版本号**刻意钉死**成设备已记录的 `17000001` / `17.0.1`，否则会在 `packages.xml` 里
记下一个版本变更。查你自己设备的值：

```sh
su -c 'dumpsys package com.android.packageinstaller | grep -m1 version'
```

## 顺带一提：产物有多小

壳 APK 目前约 **12 KB**，而姊妹项目的方案要塞进去一个 **6.1 MB** 的 InstallerX。
这正是这个方案的意义 —— 上游 InstallerX 怎么更新，都和这个壳无关了。
