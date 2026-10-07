# COS-IFS

**C**olor**OS** — **I**nstaller **F**orward **S**hell

> ColorOS（OPPO / 一加）系统安装器的**转发壳**。它占用 `com.android.packageinstaller` 的「入口契约」，
> 把安装 / 卸载请求原样转发给**你自己安装**的第三方安装器（InstallerX Revived、Universal Installer……）。
> 壳里**没有任何安装逻辑**，所以上游安装器怎么更新都与本模块无关。

## 两个仓库怎么选（先看这个）

同一件事有两种做法，仓库分开，**装一个就行**：

| | [coloros-installerx-installer](https://github.com/k-ying/coloros-installerx-installer)（胖方案） | **本仓库 COS-IFS**（转发壳） |
|---|---|---|
| 做法 | 把**整个 InstallerX APK** 改名 + 嫁接签名块后放进系统分区 | 一个 **17 KB 的壳**占住入口契约，把请求转发出去 |
| 安装器本体 | 模块里**打包好的那一版** | **你自己装的那个 app**（版本、fork 随你） |
| 上游发新版之后 | 重建 + 发版 + 重刷 | **什么都不用做** |
| 模块体积 | 4.7 MB | **25 KB** |
| 依赖 | Hybrid Mount 元模块 + 本模块后端设 VFS | 同左 |
| 适合 | 想「一个 zip 搞定、刷完就是系统安装器」，不想再装第二个 app | 本来就在用 InstallerX / Universal Installer，想让它接管系统安装，且不想每次跟上游重建 |
| 代价 | 版本**锁死在构建时那一版** | 需要你**先自己装好**一个第三方安装器；壳不做安装逻辑 |
| 真机验证 | v1.2（ColorOS 17 / PLK110） | v0.7（ColorOS 17 / PLK110） |

> ⚠️ **两者不能同时启用** —— 都占用 `com.android.packageinstaller`（同一个目标文件），
> 同时开会直接导致 Hybrid Mount 的启动规划失败。切换时把另一个**禁用**即可。

## 验证状态（v0.7，2026-10-07）

已在 **ColorOS 17 / 一加 15（PLK110）** 真机上逐项确认：

- ✅ 正常开机；壳**确实挂上**（`OppoPackageInstaller.apk` 从 8979504 变成 16727 字节）
- ✅ 系统按我们的值解析该包：`versionCode=17000001`、`versionName=17.0.1`
- ✅ NP管理器 触发的安装**被成功转发**到 InstallerX Revived，正常弹出安装界面
- ✅ WebUI 能列出机器上的候选安装器（实测 3 个：InstallerX Revived / Universal Installer / 元萝卜），标签正确
- ✅ 能在 WebUI 里**切换**转发目标并生效
- ✅ 候选枚举与 WebUI 读取都修好了：文件里有什么，界面就显示什么
- ✅ **卸载**也已实测：第一次卸载可能弹出**选择器**（别的 app 也声明了 `UNINSTALL_PACKAGE`），
  **勾上「默认」并选 COS-IFS** 即可；之后卸载都会直接走转发，交给你在 WebUI 里选定的那个安装器

**尚未实测**：content URI 授权在**多文件分享**（`ClipData` 多条）时，目标能否读到全部 URI。
组件层面已静态核对（恰好 1 个组件匹配卸载器查询）。

## 要求

- **KernelSU 或 APatch**（Magisk 不适用）
- 元模块 [Hybrid Mount](https://github.com/Hybrid-Mount/meta-hybrid_mount)
- 本模块的后端设为 **VFS**（全局默认后端保持 OverlayFS 不动）
- 你自己装好的一个第三方安装器（内置默认找 `com.rosan.installer.x.revived`）

### 两条硬前提（对不上就别刷）

**1. 你机器上那份原版安装器必须与构建时所用的一致。** 本模块的 APK 携带的是**原版 APK 的签名块**
（证书连续性）—— 签名对不上时 `PackageManagerService` 会把整个包丢弃 → 系统里 0 个安装器 →
后果与「禁用 `InstallStart`」完全相同。

```sh
su -c 'sha256sum /system_ext/priv-app/OppoPackageInstaller/OppoPackageInstaller.apk'
```

| 项 | 期望值 |
|---|---|
| 大小 | `8979504` 字节 |
| sha256 | `aeb253b93289bc3d10c46747b31358e58ea2325feb8a2e6143545f5e3b62b068` |

**对不上就自己重建一版**（见 [`build/README.md`](build/README.md)）：把 `work/OppoPackageInstaller.apk`
换成你机器上那份，`build/build_shim.sh` 会重新嫁接签名块。**不需要 Android SDK、不需要 gradle。**

**2. 同一时间只能有一个元模块。** 若你当前用的是 `meta-overlayfs` / `mountify` 等，装 Hybrid Mount 前
必须先卸掉 —— 这会影响你**所有**依赖挂载的模块，不只是本模块。

## 安装

1. 装元模块 **Hybrid Mount** → 重启。
2. 刷入 `cos-ifs-module-v0.7.zip`（Releases 页），然后打开 **Hybrid Mount 的 WebUI →「模块」页 → 点本模块
   → 后端设为 VFS → 点保存 → 重启**即可。**不要**动全局默认后端。
3. 重启后进入**本模块的 WebUI**，点「刷新」拉出候选安装器，**选一个**，点「保存」即可 —— **无需再重启**。
   > 刚刷完还没重启时，本模块自己的 WebUI 是进不去的（模块尚未生效），所以"选目标"这一步放在重启之后。

验证（可选，确认壳真的挂上了）：

```sh
su -c 'ls -l /system_ext/priv-app/OppoPackageInstaller/'
```

- **16727** = 壳已挂上（正常）
- **8979504** = 还是原版安装器（模块没生效，机器一切正常）

## 选择转发给哪个安装器

安装第 3 步就是全部操作。几条补充：

- **什么都没选** → 使用内置默认 `com.rosan.installer.x.revived`（InstallerX Revived）
- **安装和卸载用的是同一个目标**：卸载走的 `ForwardUninstallActivity` 继承同一套转发逻辑，
  所以这里选的安装器也负责卸载
- 这是**单选**，不是优先级列表：你选了谁，就转发给谁。目标已被卸载时会弹 Toast 提示，
  **不会**偷偷改用别的 app（系统安装器这个位置，确定性比容错重要）
- 保存后即时生效，**不需要重启**

不想用 WebUI（或管理器没有 WebView 桥）时可以直接命令壳：

```sh
su -c 'am start -n com.android.packageinstaller/.Configure --es targets "com.rosan.installer.x.revived"'
su -c 'am start -n com.android.packageinstaller/.Configure --ez refresh true'   # 重新枚举
su -c 'cat /data/data/com.android.packageinstaller/files/cos-ifs.txt'           # 看候选与当前选择
```

（这个 activity 由**签名级权限**保护，只有 root / 同证书的调用者能用 —— 避免任意应用把转发目标改成它自己。）

## 出问题 / 开不了机怎么办

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

- **恰好 1 个**组件匹配安装器查询 → `ForwardActivity`；**恰好 1 个**匹配卸载器查询 → `ForwardUninstallActivity`
  （开机自检要求「有且只有 1 个系统安装器」；禁用组件 → 0 个安装器 → 卡开机，这个坑踩过）
- 4 个给调用方用的别名（`InstallStart` 等）**不带 intent-filter** —— 显式 `cmp=` 调用只看组件是否存在
- 转发时复制原 intent → `setComponent(null)` → `setPackage(目标)`；`startActivity` **不需要**目标可见，
  所以转发目标只认你的显式选择，不依赖任何可见性判断
- APK 必须携带**原厂签名块**（证书连续性），由 `build/graftsig.py` 完成

因为 manifest 是我们自己写的：**不需要改 `resources.arsc` 的包名**、**不申请任何权限**（没有 privapp
allowlist 风险）、也没有需要收窄的贪婪 filter。构建时会跑两道机器校验（invoke opcode 与可见性、
分支极性规则表）并断言 6 项开机不变量，细节见 [`build/README.md`](build/README.md)。

## Releases

| 文件 | 大小 | sha256 |
|---|---|---|
| `cos-ifs-module-v0.7.zip` | 24695 | `db19ed6c8b1b6e0e2beba8a31a367b2488215ce1b730d203af4f26be45d197d6` |

zip 内的壳 APK：16727 字节，sha256 `5785d1acbd651d602abefa3b2b794e25dc7d5de7d945db15a9fc93964da91a1d`。

版本号就是**纯数字**（`0.7`），`module.prop` 的 `versionCode` 与它同步。

## 构建

见 [`build/README.md`](build/README.md)。**不需要 Android SDK、不需要 gradle** ——
`apktool.jar` 自带 smali 与 `aapt2`，签名块嫁接只用 Python。

## 许可

GPL-3.0（`build/graftsig.py` 复用自姊妹项目，见 [`LICENSE`](LICENSE)）。

## 另见

- [`SPEC.md`](SPEC.md) —— 设计说明、硬约束、决策记录、**事故记录**（踩过的坑、以及每个坑是怎么查出来的）
- 姊妹项目 [coloros-installerx-installer](https://github.com/k-ying/coloros-installerx-installer) —— 胖方案，把 InstallerX 本体打进模块
