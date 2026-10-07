# COS-IFS

**C**olor**OS** — **I**nstaller **F**orward **S**hell

> ColorOS（OPPO / 一加）系统安装器的**转发壳**。占用 `com.android.packageinstaller` 的"入口契约"，
> 把安装 / 卸载请求转发给你自己安装的第三方安装器（InstallerX Revived、Universal Installer……）。

**为什么做这个**：现有做法（[coloros-installerx-installer](https://github.com/k-ying/coloros-installerx-installer)）
是把**整个 InstallerX APK** 改名、嫁接签名块之后塞进系统分区。代价是上游每发一版，我们就要重建、重新打包、重新发版
—— 而 26.09 到 26.10 只隔了 5 天。

本方案把两件事拆开：

| | 胖方案 | COS-IFS |
|---|---|---|
| 入口契约（包名 + 组件名） | 由被改名的 InstallerX 提供 | 由**壳**提供，永久冻结 |
| 签名块 | 嫁接 OPPO 原厂块 | **同样嫁接**（结构性约束，省不掉） |
| 应用本体 | 打包在模块里 | **用户自己装的 app** |
| 上游更新后要做什么 | 重建 + 重新发版 + 重刷 | **什么都不用做** |

## 已定决策

| 项 | 决定 |
|---|---|
| 构建工具链 | **纯 smali + apktool**（本机无 Android SDK、无 `javac`；`apktool.jar` 内置 `aapt2` 与 smali） |
| 目标选择（v1） | 自动发现所有 `INSTALL_PACKAGE` handler → 内置优先级列表 → 系统选择器 |
| WebUI | **v1 就做**：自动搜索列表 + 勾选（KernelSU 管理器打开） |
| 配置存储 | 壳自己的 app 数据目录（系统 app **读不到** `/data/adb`，见 SPEC §5） |

设计与未决项详见 [`SPEC.md`](SPEC.md)。

> ⚠️ **不能与胖方案同时启用** —— 两者都要占用 `com.android.packageinstaller`。
