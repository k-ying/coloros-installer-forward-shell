# ForwardShell

> ColorOS（OPPO / 一加）系统安装器**转发壳**。占用 `com.android.packageinstaller` 的"入口契约"，
> 把安装 / 卸载请求转发给你自己安装的第三方安装器（InstallerX Revived、Universal Installer……）。

**为什么做这个**：现有做法（[coloros-installerx-installer](https://github.com/k-ying/coloros-installerx-installer)）
是把**整个 InstallerX APK** 改名、嫁接签名块之后塞进系统分区。代价是上游每发一版，我们就要重建、重新打包、重新发版
—— 而 26.09 到 26.10 只隔了 5 天。

本方案把两件事拆开：

| | 现在（胖方案） | ForwardShell |
|---|---|---|
| 入口契约（包名 + 组件名） | 由被改名的 InstallerX 提供 | 由**壳**提供，永久冻结 |
| 签名块 | 嫁接 OPPO 原厂块 | **同样嫁接**（结构性约束，省不掉） |
| 应用本体 | 打包在模块里 | **用户自己装的 app** |
| 上游更新后要做什么 | 重建 + 重新发版 + 重刷 | **什么都不用做** |

- 设计说明、硬约束、未决项：[`SPEC.md`](SPEC.md)

> ⚠️ **不能与胖方案同时启用** —— 两者都要占用 `com.android.packageinstaller`。

## 状态

草案阶段。构建工具链路线见 SPEC 第 7 节（目前倾向"纯 smali + apktool"，因为本机没有任何 Android SDK，
而 `apktool.jar` 自带 `aapt2` 与 smali）。
