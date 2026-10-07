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

**③ XML 注释里不能出现 `--`（双连字符）。**

aapt2 只会报一句语焉不详的 `not well-formed (invalid token)`，看不出是哪一行。
**这个坑在本项目里踩了两次**，所以 `build_shim.sh` 开头加了一个前置检查，会直接给出明确报错，
不用再去读 aapt2 的输出。

## 构建时的自动断言（为什么不能只靠肉眼）

有两道机器校验，都会在 `build_shim.sh` 里自动跑。

**第一道：`build/audit_smali.py`（构建一开始就跑）。** 它检查我们自己 smali 里的每一次自调用，
opcode 和方法的可见性是否匹配 —— `private` 方法必须用 `invoke-direct`，其余用 `invoke-virtual`。

这条规则值得单独写个脚本，是因为**它错了 smali 照样汇编通过**，只在运行时抛
`IllegalAccessError`。0.1 就是这么发的：`ConfigureActivity` 用 `invoke-virtual` 调用了自己
`private` 的 `probeIntent()`，于是这个 activity 一进去就崩，状态文件永远写不出来，WebUI 显示
成"没有候选安装器"—— 而且**任何地方都不报错**。不做机器校验，只有刷一次机才会暴露。
（该脚本自己也做过反证测试：把 bug 注入回去，它会精确报出文件、行号和应有的 opcode。）

同一个脚本还有**第二道检查：候选枚举循环的分支极性。** `writeStateFile()` 里
`String.equals` 的结果必须用 `if-eqz` 消费、`ArrayList.contains` 的结果必须用 `if-nez`
（两者都是"为真就跳过 emit"）。0.3 及之前这两行**互换了极性**，于是每个候选都在第一道检查上被
丢掉、`seen` 永远为空 → WebUI 永远没有候选，而状态文件却照常写成 `selected=`，
**看起来像包可见性或权限问题**。同样做过反证测试。

这道检查**刻意只扫 `writeStateFile()` 一个方法**：`contains` 的极性是上下文相关的 ——
`ForwardActivity.pickTarget()` 里 `pkgs.contains(pkg)==1` 表示"这确实是候选包"，
那里用 `if-eqz` 是**对的**。全局扫描会误报，而误报会让人开始忽略这道检查。

**第二道：`build/verify_shim.py`（构建最后一步）。** 它直接解析**刚产出的 APK 的二进制 manifest**
并断言这些不变量：

- 包名 / `versionCode` / `versionName` 是钉死的值
- **安装器查询恰好命中 1 个组件**（`file://` 与 `content://` 两种形式分别校验，且必须指向同一个组件
  —— 查询用的是哪种 scheme 在不同 AOSP 版本间有差异）
- **卸载器查询恰好命中 1 个组件**
- 4 个给调用方的别名存在、exported、且**没有 intent-filter**（加了就会多出一次命中）
- `Configure` 别名与它的目标都存在、exported、且**各自都带**签名级权限（别名是独立组件，
  只在目标上声明权限不保证能拦住）
- 壳**不申请任何权限**，只声明那一个权限

为什么值得为它单独写个工具：**这几条里任何一条错了，开机时系统里就是 0 个安装器 → 卡开机** ——
这是本项目唯一真正的砖风险。姊妹项目当初靠人工核对，有过一次险情。这个校验器自己做过反证测试：
喂给它一个"多了一个安装器组件"的 manifest，它会失败并**把两个命中的组件都列出来**。

（`build/axml_manifest.py` 是二进制 AXML 解析器，复用自姊妹项目，GPL-3.0。）

## 关于 `versionCode` / `versionName`

壳的版本号**刻意钉死**成设备已记录的 `17000001` / `17.0.1`，否则会在 `packages.xml` 里
记下一个版本变更。查你自己设备的值：

```sh
su -c 'dumpsys package com.android.packageinstaller | grep -m1 version'
```

## 构建是可复现的（逐字节）

除了签名块取自**你自己设备**那份原厂 APK，其余全过程都是确定的：条目内容、CRC、压缩方式、
偏移、zipalign 填充、以及每次都能得到同一份的签名块。唯一的非确定性来自 zip 头里印的
编译时刻，所以 `build_shim.sh` 最后会用 `normalize_zip_time.py` **原地**把那 4 个字节改写成固定值
（原地改而不是重建 zip，是为了不破坏对齐与偏移 —— 今天没有原生库无所谓，将来有就是隐雷）。

实测：相隔一分钟的两次完整构建，归一化前哈希不同，归一化后**逐字节相同**。

因此 —— **同一份上游源码 + 同一份 donor（即同一版本固件）→ 同一个 hash**。
换了固件或 donor 就会不同，因为签名块必然不同。文档里出现的哈希都应该按这个前提理解。

## 顺带一提：产物有多小

壳 APK 目前约 **16.7 KB**，整个模块约 **23 KB**，而姊妹项目的方案要塞进去一个 **6.1 MB** 的
InstallerX（模块 4.7 MB）。这正是这个方案的意义 —— 上游 InstallerX 怎么更新，都和这个壳无关了。
