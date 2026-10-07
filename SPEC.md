# COS-IFS — 设计说明

> 状态：草案 v0.1。
> 标 **[未决]** 的是需要拍板的，标 **[未验证]** 的是我没有实测依据的，其余都有证据。
> 证据来源：`coloros-installerx-installer` 项目的真机验证记录 + KernelSU 上游源码 + Hybrid Mount 文档。

## 0. 已定决策（2026-10-07）

| 项 | 决定 | 理由 |
|---|---|---|
| 构建工具链 | **纯 smali + apktool** | 本机无 Android SDK、无 `javac`；`apktool.jar` 内置 `prebuilt/linux/aapt2` 与 smali → **零额外下载** |
| 目标选择（v1） | 自动发现 → 优先级列表 → 系统选择器 | 零配置即可用；用户换安装器也不必改代码 |
| WebUI | **v1 就做**：自动搜索列表 + 勾选 | 桥在 KernelSU 上已被 Hybrid Mount 验证可用 |
| 配置存储 | 壳自己的 app 数据目录 | 系统 app 读不到 `/data/adb`（见 §5） |
| 缩写 | **COS-IFS** | 避免与 SMB/CIFS 混淆 |


---

## 1. 要解决的问题

胖方案把整个 InstallerX APK 改名 + 嫁接签名后塞进
`/system_ext/priv-app/OppoPackageInstaller/OppoPackageInstaller.apk`。于是：

> 上游 InstallerX 每发一版，我们就得重建 → 重新打包 → 重新发版 → 用户重刷。

这不是假想：`26.09` 发布于 2026-09-30，`26.10.cb9a24d` 在 **2026-10-05** 就发了。

## 2. 思路：把"入口契约"和"应用本体"拆开

- **入口契约**：包名 `com.android.packageinstaller` + 那几个被显式 `cmp=` 调用的组件名。
  **这部分永远不变。**
- **应用本体**：InstallerX 的 dex / res / assets。**这部分每次上游更新都变。**

所以只做一个**极小的、永久冻结的壳**占住入口契约，收到请求后**转发**给用户自己安装的第三方安装器。

### 附带收益

- 壳**不申请任何权限** → 没有 privapp allowlist 风险（胖方案里必须裁掉 4 个权限）
- **不需要改 `resources.arsc` 的包名** —— 壳从一开始就用对包名写 manifest（胖方案里这是个二进制补丁）
- 不需要收窄贪婪 `VIEW` 过滤器（manifest 是我们自己写的）
- **没有 GPL 问题** —— 壳是我们自己的代码，不再转分发上游 APK

## 3. 硬约束（每条都有前车之鉴）

**3.1 开机自检：恰好 1 个系统安装器组件**

`getRequiredInstallerLPr()` 要求"有且只有 1 个系统组件"匹配安装器查询。实测坑：把 `InstallStart` 禁用掉
→ 系统里 0 个安装器 → **卡开机**（真机踩过，靠第三方 recovery 救回）。

⇒ 壳里必须**恰好 1 个**组件匹配 `INSTALL_PACKAGE + DEFAULT + content/apk`，
**恰好 1 个**匹配卸载查询（`UNINSTALL_PACKAGE`/`DELETE` + `DEFAULT` + `package` scheme）。
给多个组件加 filter、或给一个组件加多个 filter 都要先确认计数语义（见胖方案 SPEC 里的分析：计数器数的是**组件**不是 filter）。

**3.2 签名连续性：必须嫁接原厂签名块**

`com.android.packageinstaller` 在 `packages.xml` 里已记录 OPPO 的证书；
`PackageManagerServiceUtils.verifySignatures` **没有系统包豁免**，且 `SCAN_INITIAL` 会绕过
key-set 逃生口 → 自己重签会被判不兼容 → 包被丢弃 → 0 个安装器 → 卡开机。

⇒ 壳 APK **必须**携带从设备自己那份原厂 APK 里提取的签名块。
这一条是结构性的，**任何方案都省不掉**。工具：`build/graftsig.py`（从姊妹项目原样复用，已验证）。

**3.3 不能自环**

壳自己声明了 `INSTALL_PACKAGE`。如果转发时不锁定目标包，intent 解析会命中**壳自己** → 无限循环。

⇒ 强制 `intent.setPackage(target)`；并且在解析结果等于自己时直接放弃（给错误提示）。

## 4. 转发契约

收到 intent 之后：

1. 复制原始 intent：`action` / `data` / `type` / `categories` / `extras` / `clipData` / `flags`
2. **重新把 content URI 权限授予目标包** —— `FLAG_GRANT_READ_URI_PERMISSION` 的授权
   **不会随转发转移**，这是最容易踩的坑。要 `grantUriPermission(target, uri, ...)`，
   并处理 `clipData` 里的 URI。
3. `setPackage(target)` 然后 `startActivity`
4. `finish()`

**[未决] 目标选择策略**：

- **A**（建议 v1）：自动发现。枚举所有能处理 `INSTALL_PACKAGE` 的包，排除自己。
  - 只有 1 个候选 → 直接转发
  - 多个候选 → 按内置优先级列表挑（InstallerX 相关包名优先）
  - 列表也没命中 → 弹系统选择器
- **B**：只认内置优先级列表
- **C**：每次弹选择器

注意 **4.1**：Android 11+ 有包可见性限制，要枚举别的安装器需要在壳的 manifest 里声明
`<queries>`（`INSTALL_PACKAGE` + apk mimeType），否则 `queryIntentActivities` 返回空。

## 5. 配置存在哪里 —— 这一条决定了 WebUI 能不能用

**关键限制**：壳是普通系统 app（跑在自己的 uid 下），**读不到 `/data/adb/`** ——
该目录是 `0700 root`，且 SELinux 对 app 域访问 `adb_data_file` 基本不给权限。

所以"**WebUI 写配置文件 → 壳读它**"这个设计**不成立**。

可行的是**反过来**：配置由**壳自己**存（`SharedPreferences`，落在
`/data/data/com.android.packageinstaller/`），外部界面只是**命令**壳去设置它：

```sh
am start -n com.android.packageinstaller/.Configure --es targets "com.rosan.installer.x.revived,…"
```

这样无论入口是 WebUI、`action.sh` 还是秘密代码，**存储始终在 app 自己手里**。

### 5.1 WebUI 与壳之间的约定（v1 采用）

既然 WebUI 不能直接写壳的存储、壳也读不到 `/data/adb`，两者之间就只留**最窄的一条缝**：

- **写**（WebUI → 壳）：**不走文件，走 intent，让壳自己存**：
  ```sh
  am start -n com.android.packageinstaller/.Configure --es targets "com.rosan.installer.x.revived,…"
  ```
  WebUI 里就是 `ksu.exec(...)` 跑这一行 —— **跨域写文件的风险完全避开**（app 写自己的存储永远合法）。
- **读**（壳 → WebUI）：壳把"候选列表 + 当前勾选"写进自己的 `files/cos-ifs.txt`，
  WebUI 用 `ksu.exec('cat /data/data/com.android.packageinstaller/files/cos-ifs.txt')` 读回来渲染。
  **root 读 app 数据目录是常规操作**（备份类工具都这么干），比写安全得多。
- **发现**（谁枚举候选）：**必须由壳做**，不要让 WebUI 去解析 `pm` / `cmd package` 的输出。
  壳手里有 `PackageManager`，还能正确处理 Android 11+ 的 `<queries>` 可见性；shell 里拼字符串既脆又会漏。

于是职责很干净：**壳负责发现与存储，WebUI 只负责画一个带勾选的列表并调用 `am start`。**

> 兼容性：`ksu.exec` 是 KernelSU 管理器的 WebView 桥，APatch 等不保证有 ——
> 所以壳自己的秘密代码入口（`*#*#…`）**必须一并保留**，作为无 WebUI 时的配置途径。

## 6. 可配置入口

| 入口 | 成本 | 依赖 | 备注 |
|---|---|---|---|
| 自动发现 + 优先级列表 | 低 | 无 | **建议 v1 就靠这个**，零 UI |
| `action.sh`（管理器的"操作"按钮） | 极低 | KernelSU / APatch 的 action 支持 | 一个按钮打开设置界面 |
| 秘密代码 `*#*#…` | 低 | 无 | 胖方案里已用 `*#*#46789#*#*` |
| **WebUI**（`webroot/index.html` + `ksu.exec`） | 中 | **WebView 桥只有 KernelSU 管理器提供**，APatch 不保证 **[未验证]** | 只是"薄启动器"，不是存储 |
| 原生设置 Activity（app 内） | 高 | 要编译 Android UI 代码 | 最通用，但最贵 |

**结论（已定）**：v1 就做 WebUI，形态是"**自动搜索出来的候选列表 + 勾选**"，按 §5.1 的约定与壳通信。
WebUI 只是**薄启动器**而不是配置存储；它的桥只有 KernelSU 管理器提供，所以秘密代码入口要一并保留兜底。

## 7. 构建工具链 —— 目前最大的未决项

本机现状（已核实）：

- **没有任何 Android SDK**，没有 gradle
- **没有 `javac`** —— `.tools/` 里那个 `jdk-21.0.12.1+1-jre` 是**纯 JRE**（只有 `java`/`keytool`/…），
  PATH 里也没有别的 JDK
- `.tools/apktool.jar` **内置了 `prebuilt/linux/aapt2`**，而且 apktool `b` 会把 smali 汇编成 dex
- 姊妹项目的构建流水线**从来没有编译过代码**（只做反编译 + 改字节 + 打包）

也就是说"怎么把壳编译出来"是**新增能力需求**。

| 路线 | 需要什么 | 评价 |
|---|---|---|
| **A. 纯 smali + apktool** | 只要 `apktool.jar`（已内置 smali 与 aapt2） | **零额外下载**，完全自包含，和姊妹项目一个哲学；代价是源码难写难读 |
| **B. Java + Android SDK** | JDK + `android.jar` + d8/aapt2 | 源码干净；但 **`android.jar` 不在 Maven 上**，本地编译拿不到 → 这条路天然适合放 **CI**（GitHub Actions 自带 SDK） |
| **C. Java + 手写框架 stub 编译** | JDK + 自写 stub 类 | 可行但脆弱（stub 签名与真机不符会运行时 `NoSuchMethodError`），不推荐 |

**决定**：走 **A（纯 smali + apktool）**。先只写转发 Activity（不含 UI），把
「壳能产出来 + 签名块对得上 + 能挂上去 + 开机自检通过 + 转发有效」这几件事依次验证掉；
配置界面再按 §5.1 加 `ConfigureActivity` 与 WebUI。
smali 若真的维护不下去再切 **B + GitHub Actions** —— 转发逻辑本身很短，届时按 Java 重写即可。

## 8. 已知风险 / [未验证]

1. **目标没装时怎么办** —— 壳自己不会安装。转发失败必须给**明确提示**，否则就是那个"点了没反应"的老症状。
   **[未决]** 要不要给壳加一个"最小内置安装器"作为兜底（走 `PackageInstaller` session + 用户确认）？
2. **Root 模式的真实体验** —— 上游 README 写明 InstallerX 支持 Root 模式
   （*"Root: can perform all privileged operations, but may be slower because of cold `app_process` startup"*），
   但我**没有实测过**转发之后它是否真的走 Root、以及慢到什么程度。
   这一条是方案 3 的核心假设，**建议在写壳之前先用现有设备验证一次**。
3. **APatch 的 WebUI / action 支持**未核对。
4. **用户可能换用别的安装器**（Universal Installer 等）—— 自动发现能覆盖，硬编码包名不能。
5. **壳自己也是个系统 app**，它也需要 metamodule + VFS 才能挂上去 —— 这一层依赖不变
   （Hybrid Mount + 本模块后端设 VFS，见姊妹项目文档）。

## 9. 与姊妹项目的关系

`coloros-installerx-installer`（胖方案）**保留不动**，继续可用、继续是"官方安装器"路线的参考实现。
ForwardShell 是另一条路。**两者不能同时启用** —— 都会占用 `com.android.packageinstaller`。

`build/graftsig.py` 从姊妹项目原样复用（也因此本仓库沿用 GPL-3.0）。

## 10. 进度

1. ~~**[先验证]** 用户版 InstallerX 的 Root 模式~~ → **已验证**（实测：可用、速度与系统模式体感相当、没有逐次确认弹窗）。
2. ~~**打通构建**~~ → **已完成**。手写 smali 工程（零 res）→ `apktool b` → 对齐 → `graftsig.py` 嫁接。
3. ~~**打成模块**~~ → **已完成**（`cos-ifs-module-v0.1.zip`）。真机开机验证**待用户执行**。
4. ~~**转发逻辑**~~ → **已完成**：intent 复制 + `setComponent(null)` + `setPackage` + try/catch 包住启动。
5. ~~**自动发现 + 优先级列表**~~ → **已完成**：保存列表 → 内置 `PREFERRED` → 唯一候选 → null（此时回退到写死的目标包）。
6. ~~**配置存储 + `ConfigureActivity`**~~ → **已完成**（签名级权限保护）。
   ~~**WebUI**~~ → **已完成**（`module/webroot/index.html`，自动搜索 + 勾选，显示顺序即优先级；
   还会保留"已选但本次没发现"的包）。秘密代码入口**未做** —— v1 的图形界面只有 WebUI；
   没有 WebView 桥的管理器可以用 `am start` 配置（README 有写）。
7. **未做**：「目标没装」时的内置兜底安装器（见 §8.1）。

**全部待真机验证事项**：

- 开机自检是否通过（组件计数已在静态层面核对，但没上过机）
- `cmp=com.android.packageinstaller/.InstallStart` 能否被 NP管理器 成功调用
- 转发过去之后 InstallerX 是否真的走 Root 模式
- content URI 授权：现在已经**显式重授** —— `getData()` 加上 `ClipData` 的每一项，只在 scheme 是
  `content` 且我们确实持有授权时才授，整段 best-effort（失败只记日志，不崩）；转发的 intent 另外带上
  读权限 flag 作为第二道保险。真机上要确认的是**多文件分享**（`ClipData` 多条）时目标能否读到全部 URI。
- 当前 KernelSU 管理器版本上 `ksu.exec` 桥是否可用（WebUI 依赖它）

---

## 11. 事故记录：v0.2 开机循环（2026-10-07）

**现象**：v0.1 刷入后正常开机、WebUI 可用；v0.2 刷入后**开机循环**，靠 KernelSU 安全模式救回。

**定位**：v0.1 → v0.2 的 manifest 差异**只有两处**（`git diff` 确认），两处都已回退：

1. **新增 `<uses-permission android:name="android.permission.QUERY_ALL_PACKAGES"/>`** ← 主要嫌疑
2. 两个 `<queries><intent>` 里各加了 `<data android:scheme="content"/>` 与 `scheme="file"`

同一区间内 smali 只把 `ConfigureActivity.probeIntent` 从 `private` 改成 `public`，**不可能影响开机**
（而且 dex 代码也不会在开机时执行 —— 壳没有 receiver、没有 service、没有 boot 触发点）。

**三条教训（第一条已变成硬断言）**：

1. **绝不往这个 priv-app 里加权限。** 姊妹项目当初花大力气裁掉 4 个权限，正是因为"给系统 priv-app 加权限"
   属于**能搞挂开机的那个类别**。我为了"保险"反方向加了一条，判断错了。
   `verify_shim.py` 现在把"不得申请任何权限"变成硬断言，删掉这条规则需要显式改校验器。
2. **改动要贴着"已知能开机的那一版"走。** 当两个改动里不知道哪个是元凶时，**两个都回退**，
   之后一次只加回一个。v0.3 = v0.1 的 manifest（**逐字节一致**，`git diff` 为 0 行）+ 唯一该保留的崩溃修复。
3. **`<queries>` 不是"改了没风险"的地方** —— 它就在 manifest 里，改它等于改这个包的解析输入。

**还没确定的**：到底哪一处是元凶（两处都回退了，所以没能二分）。有一个持久的证据可以定性：
`/data/system/dropbox/` 里的 `system_server_crash` / `system_server_watchdog` 条目**跨重启保留**，
而 logcat 缓冲区在重启时就没了。

**包可见性该怎么做（不动 manifest 的前提下）**：WebUI 本身以 root 运行，让它自己解析组件
（`cmd package resolve-activity …`），把**组件名**通过 `am start --es components …` 交给壳，
壳用 `setComponent()` 转发。**带显式 `ComponentName` 的 intent 完全不受包可见性过滤** ——
这样既不需要在 `<queries>` 里声明 scheme，也不需要那条权限。等核心链路真机跑通再实现。
