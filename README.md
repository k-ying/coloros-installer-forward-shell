# COS-IFS

**C**olor**OS** — **I**nstaller **F**orward **S**hell

> ColorOS（OPPO / 一加）系统安装器的**转发壳**。它占用 `com.android.packageinstaller` 的"入口契约"，
> 把安装 / 卸载请求原样转发给你**自己安装**的第三方安装器（InstallerX Revived、Universal Installer……）。

**为什么做这个**：另一种做法（[coloros-installerx-installer](https://github.com/k-ying/coloros-installerx-installer)）
是把**整个 InstallerX APK** 改名、嫁接签名块之后塞进系统分区。代价是上游每发一版我们就要重建一次 ——
而 26.09 到 26.10 只隔了 5 天。COS-IFS 把两件事拆开：

| | 胖方案 | COS-IFS |
|---|---|---|
| 入口契约（包名 + 组件名） | 由被改名的 InstallerX 提供 | 由**壳**提供，永久冻结 |
| 签名块 | 嫁接原厂块 | **同样嫁接**（结构性约束，省不掉） |
| 应用本体 | 打包在模块里 | **用户自己装的 app** |
| 上游更新后要做什么 | 重建 + 重新发版 + 重刷 | **什么都不用做** |
| 模块体积 | 4.7 MB（内含 6.1 MB 的 APK） | **13 KB**（内含 17 KB 的 APK） |

## ⚠️ 状态：尚未在真机验证

代码写完了、每一步都做了构建与静态验证（反汇编核对控制流、组件计数核对、签名块逐字节比对），
但**还没有在任何设备上开机测试过**。第一次刷入请务必先看清下面的「退路」。

## 要求

- **KernelSU 或 APatch**（Magisk 不适用）
- 元模块 [Hybrid Mount](https://github.com/Hybrid-Mount/meta-hybrid_mount)（本模块依赖它的挂载机制）
- 本模块的后端设为 **VFS**
- 你自己装好的一个第三方安装器（默认优先找 `com.rosan.installer.x.revived`，也会自动发现别的）
- 板子上原本有 `/system_ext/priv-app/OppoPackageInstaller/OppoPackageInstaller.apk`

## 安装

1. 先装元模块 **Hybrid Mount** 并重启。（若原来装的是 `meta-overlayfs` 等，先卸掉 —— 同时只能有一个元模块。）
2. 刷入 `cos-ifs-module-v0.1.zip` 并重启。
3. 在 Hybrid Mount 的「模块」页把本模块的「模块默认」设为 **VFS**，保存后重启。
   **不要**动全局默认后端（保持 OverlayFS）。
4. 验证：

```sh
su -c 'ls -l /system_ext/priv-app/OppoPackageInstaller/'
```

- 大小**远小于 100000** = 壳已挂上
- **8979504** = 原版安装器仍在（模块没生效，机器一切正常）

## 配置要转发给谁

壳会**自动发现**所有能处理 `INSTALL_PACKAGE` 的安装器。选择顺序是：

1. **你保存的列表**（按你排的顺序）
2. 内置优先级列表（`com.rosan.installer.x.revived` → `com.rosan.installer.x` → `com.rosan.installer`）
3. 如果设备上只有**一个**候选，就用它

配置界面是 **KernelSU 管理器的 WebUI**：模块页 → WebUI。它会列出设备上发现的安装器，
勾选即可，**显示顺序就是优先级**。

配置存在壳自己的 app 数据里（因为系统 app **读不到** `/data/adb`）。不想用 WebUI 时也可以直接命令壳：

```sh
su -c 'am start -n com.android.packageinstaller/.Configure --es targets "com.rosan.installer.x.revived"'
su -c 'cat /data/data/com.android.packageinstaller/files/cos-ifs.txt'   # 看当前状态与候选
```

（该 activity 由**签名级权限**保护，所以只有 root / 同证书的调用者能用 —— 避免任意应用把转发目标改成它自己。）

## 退路

1. **只让替换失效**：Hybrid Mount →「模块」→ 本模块 →「模块默认」→ **忽略** → 重启。原版安装器立刻回来。
2. **KSU 安全模式**：开机第一屏出现后，**连按「音量下」3 次**（按下松开 ×3）。
3. **recovery**：
   ```sh
   mount /data
   rm -rf /data/adb/modules/cos-ifs
   ```

模块不写任何分区、不禁用任何系统组件，卸载即完全还原。

## 工作原理

壳是一个我们**自己写**的小 app（manifest + 少量 smali，无资源）：

- **恰好 1 个**组件匹配安装器查询（`INSTALL_PACKAGE` + `DEFAULT` + content/apk）→ `ForwardActivity`
- **恰好 1 个**匹配卸载器查询（`UNINSTALL_PACKAGE`/`DELETE` + `DEFAULT` + package）→ `ForwardUninstallActivity`
  （开机自检要求"有且只有 1 个系统安装器"；踩过的坑：禁用组件 → 0 个安装器 → 卡开机）
- 4 个给调用方用的别名（`InstallStart` 等）**不带 intent-filter** —— 显式 `cmp=` 调用只看组件是否存在
- APK 必须携带**原厂签名块**（证书连续性，否则会被判不兼容而丢包 → 卡开机），由 `build/graftsig.py` 完成

因为 manifest 是我们自己写的：**不需要改 `resources.arsc` 的包名**、**不申请任何权限**（没有 privapp
allowlist 风险）、也没有需要收窄的贪婪 filter。

## 构建

见 [`build/README.md`](build/README.md)。**不需要 Android SDK、不需要 gradle** ——
`apktool.jar` 自带 smali 与 `aapt2`，签名块嫁接只用 Python。

## 许可

GPL-3.0（`build/graftsig.py` 复用自姊妹项目，见 [`LICENSE`](LICENSE)）。

## 另见

- [`SPEC.md`](SPEC.md) —— 设计说明、硬约束、决策记录、已知风险
- 姊妹项目 [coloros-installerx-installer](https://github.com/k-ying/coloros-installerx-installer) —— 胖方案，仍然可用
- ⚠️ **两者不能同时启用**，都会占用 `com.android.packageinstaller`
