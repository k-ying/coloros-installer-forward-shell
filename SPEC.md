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
3. ~~**打成模块**~~ → **已完成**。**v0.3 真机验证通过**：ColorOS 17 / PLK110 正常开机，且
   `ls -l /system_ext/priv-app/OppoPackageInstaller/` 显示的确实是壳（16727 字节），
   `dumpsys package` 也按我们的值解析（`versionCode=17000001`）。**架构成立**。
4. ~~**转发逻辑**~~ → **已完成并真机验证**：intent 复制 + `setComponent(null)` + `setPackage` + try/catch。
   装上 InstallerX 后 NP管理器 触发的安装确实被转发过去了。
5. ~~**自动发现 + 优先级列表**~~ → **已完成并真机验证**（转发侧）：保存列表 → 内置 `PREFERRED`
   → 唯一候选 → null（回退到写死的目标包）。**枚举侧的显示 bug 见 §12，v0.4 修复。**
6. ~~**配置存储 + `ConfigureActivity`**~~ → **已完成**（签名级权限保护）。
   ~~**WebUI**~~ → **已完成**（`module/webroot/index.html`，自动搜索 + 勾选，显示顺序即优先级；
   还会保留"已选但本次没发现"的包）。秘密代码入口**未做** —— v1 的图形界面只有 WebUI；
   没有 WebView 桥的管理器可以用 `am start` 配置（README 有写）。
7. **未做**：「目标没装」时的内置兜底安装器（见 §8.1）。

**真机验证状态**：

- ~~开机自检是否通过~~ → **通过**（v0.3，ColorOS 17 / PLK110）
- ~~`cmp=com.android.packageinstaller/.InstallStart` 能否被 NP管理器 成功调用~~ → **通过**
- ~~转发过去之后 InstallerX 是否真的走 Root 模式~~ → **通过**
- ~~当前 KernelSU 管理器版本上 `ksu.exec` 桥是否可用~~ → **可用**（状态文件确实被写出来了）
- ~~**待验证**：`cos-ifs.txt` 里能否列出候选安装器（v0.4 的修复目标，验收命令见 §12）~~ →
  **已验证**。v0.4 真机输出 3 行，标签也对：
  `app.pwhs.universalinstaller|软件包安装程序`、`com.rosan.installer.x.revived|InstallerX Revived`、
  `top.bienvenido.saas.i18n|元萝卜`。
- **待验证**：content URI 授权在**多文件分享**（`ClipData` 多条）时目标能否读到全部 URI——
  现在已**显式重授**：`getData()` 加上 `ClipData` 的每一项，只在 scheme 是 `content`
  且我们确实持有授权时才授，整段 best-effort（失败只记日志，不崩）；转发的 intent 另外带上
  读权限 flag 作为第二道保险。

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

**后续更正（见 §12）**：包可见性其实**一直没有成为障碍**。真机 `dumpsys` 显示系统会把手写 mimeType
的 `<queries>` 规范化成 `dat=content://*/...`，于是 InstallerX 与 Universal Installer **本来就在我们的
可见列表里**。当时之所以怀疑可见性，是被一个逻辑取反 bug 误导了（§12）。所以"WebUI 代解析组件"
这条优化**不是必需项**，只是可选的健壮性提升。

---

## 12. 事故记录：候选安装器列表恒为空（v0.4 修复，2026-10-07）

**现象**：v0.3 真机上，壳能开机、能挂载、装上 InstallerX 后能正常转发安装；但 WebUI 的候选列表
**永远是空的**，状态文件内容恒为：

```
selected=
```

（文件被正常写出、权限正常、`selected=` 行存在 —— 所以看起来是"枚举没查到东西"。）

**被排除的假设**：一开始判断是**包可见性**（我们的 `<queries>` 里没写 scheme，而目标 filter 要求
`scheme=content|file`）。两条真机证据把这个假设推翻了：

```sh
su -c 'dumpsys package com.android.packageinstaller' | sed -n '/^Queries:/,/queryable via interaction/p'
```

```
    queriesIntents=[Intent { act=android.intent.action.INSTALL_PACKAGE dat=content://*/...
                    , Intent { act=android.intent.action.VIEW dat=content://*/... }]
Queries:
  queries via component:
    com.android.packageinstaller:
      app.pwhs.universalinstaller      ← 本来就看得到
      com.rosan.installer.x.revived    ← 本来就看得到
```

系统把只写了 `mimeType` 的声明规范化成了 `dat=content://*/...`，两个安装器都在可见列表里；
而 `cmd package query-activities` 用**同一个 intent** 在 shell/root 下能查到 4 个组件。
**可见性和 filter 匹配都通** → 问题只能在应用自己的代码里。

**真正的 bug**：`ConfigureActivity.writeStateFile()` 枚举循环里，**`contains` 那一行的分支极性反了**：

```smali
invoke-virtual {v6, v7}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
move-result v7
if-nez v7, :loop_next        # equals==1（是自己）→ 跳过 emit   ← 这一行本来就是对的

invoke-virtual {v3, v6}, Ljava/util/ArrayList;->contains(Ljava/lang/Object;)Z
move-result v7
if-eqz v7, :loop_next        # v0.3 的 BUG：contains==0（还没输出过）反而跳过 emit
```

`:loop_next` 就是"跳过 emit、进入下一轮"。`if-nez` 表示"值非 0 就跳"，而 `contains` 返回 1
恰好表示"已经输出过、该跳过"，所以这里必须是 `if-nez`。错版把判据取反，于是**每个还没见过的候选
都在第二道检查上被丢掉**，`seen` 永远为空 → 零候选 —— 与观察完全一致。v0.1 / v0.2 / v0.3 都带这个 bug。

**注意：`equals` 那一行原本是对的。** 两行的正确写法**都是 `if-nez`**（两个谓词返回 1 都表示
"该跳过 emit"）。这一点下面教训 5 还会再提。

**怎么才看出来的**：读 smali 源码"看着是对的"，是**把真机上跑的那个 APK 反编译出来**才发现的：

```sh
java -jar apktool.jar d -f -o /tmp/dec dist/cos-ifs.apk
grep -n -A6 'ArrayList;->contains' /tmp/dec/smali/.../ConfigureActivity.smali
```

**为什么机器校验没拦住**：`audit_smali.py` 当时只检查 invoke opcode 与可见性，不检查分支极性。
现在加了**第二道检查**：把 `writeStateFile()` 里 `equals` / `contains` 之后紧跟的分支 opcode
都钉成 `if-nez`，并对**两行各自**做过反证测试（注入错误极性 → 精确报出文件/行号/应有 opcode
→ 退出码 1）。
这道检查**刻意只扫 `writeStateFile()` 这一个方法** —— `contains` 的极性是上下文相关的：
`ForwardActivity.pickTarget()` 里 `pkgs.contains(pkg)` 返回 1 表示"这确实是个候选包"，
那里用 `if-eqz` 是**对的**，全局扫描会误报，而误报会让人开始忽略这道检查。

**教训**：

1. **取反类 bug 不会汇编报错、不会崩、不写日志**，只在"结果为空"上体现，而且极容易被误判成
   权限/可见性这类"环境问题"。凡是"查询结果恒为空"的现象，都要把**代码逻辑本身**列入嫌疑，
   并且用**产物**（反编译 dex）而不是源码去确认。
2. **校验要能反证，且要收紧到目标方法**。宽泛的规则会误报，误报的校验等于没有校验。
3. **崩溃证据在 `/data/system/dropbox/` 跨重启保留**（logcat 缓冲区重启就没了）。这次就在里面
   挖到了 v0.1 那次的 `VerifyError`（`writeStateFile` 调 private `probeIntent`，整个类被校验器
   拒绝）—— 印证了 §11 的崩溃修复是对的。排查时应该先看这里：
   ```sh
   adb shell 'su -c "ls -lt /data/system/dropbox/ | head -30"'
   ```
4. 顺带记录：**v0.2 开机循环没有在 dropbox 里留下任何 `system_server_crash`**，所以元凶仍是
   未定（§11）。两条改动只能继续一起回退。
5. **修取反 bug 的时候我自己又改错了一次，而且差点就这么提交了。** 当时我判断"两行都反了"，
   于是把 `equals` 那行从（本来正确的）`if-nez` 改成了 `if-eqz` —— 那是**相反方向的同一个 bug**：
   会把自己当候选、把所有真实候选丢掉。抓到它的不是反证测试，而是**拿真机真实的 4 条候选数据
   把循环模拟跑了一遍**：

   ```
   v0.3 (equals if-nez, contains if-eqz): []
   我改错的版本 (eqz, nez)             : ['com.android.packageinstaller']   ← 只有自己
   v0.4 正确 (nez, nez)                : [3 个真实候选]
   ```

   这里有个更值得记住的点：**反证测试只能证明"校验与我脑中的理解一致"，证明不了理解本身正确**。
   当时 `audit_smali.py` 的极性表和我的错误理解完全一致，所以两个方向的反证都"通过"了。
   对布尔极性这类东西，**必须用真实数据把逻辑跑一遍**，光做注入式反证是不够的。
   （上面的模拟脚本就是 §12 里那段 Python，改几个字符即可复用。）

**v0.4 验收命令**（刷入并重启后，只读）：

```sh
su -c 'am start -n com.android.packageinstaller/.Configure --ez refresh true'
su -c 'cat /data/data/com.android.packageinstaller/files/cos-ifs.txt'
```

期望：**至少 1 行 `candidate=`**。本机实测应有 3 行（`app.pwhs.universalinstaller`、
`com.rosan.installer.x.revived`、`top.bienvenido.saas.i18n`）。若仍为空，下一步就是查
`queryIntentActivities` 在本进程内的返回值（在 `writeStateFile` 里打一行 `Log.i` 记录 list 尺寸）。

---

## 13. 转发目标改为确定性选择（v0.5，2026-10-07）

**背景**：v0.4 让枚举恢复正常之后，真机文件里出现 3 个候选，其中一个是**元萝卜**
（`top.bienvenido.saas.i18n`）—— 一个下围棋的 app，它居然也声明了 `INSTALL_PACKAGE` 的 filter。
这一下把 v0.3 里两处"顺手"的启发式变成了真实风险。

**v0.3 的 `pickTarget()` 顺序**：保存列表 → 内置 `PREFERRED` → **唯一候选** → null。
其中前两级都有一道 `candidates.contains(pkg)` 过滤，也就是"**只有壳自己看得见的包才算数**"。

**两个问题**：

1. **显式选择会被静默跳过。** 候选列表受包可见性过滤（v0.4 期间实测到过只返回 1 个的时刻）。
   一旦壳看不见用户选的那个包，`contains` 不成立 → 该选择被跳过 → 落到下一级。
   用户只会在日志里看到最终的赢家，**永远看不到"你的选择被跳过了"**。
2. **"唯一候选"根本不是证据。** 元萝卜就是反例：如果机器上只剩它一个可见候选，安装会被静默
   转发给它。这个分支原本是为了"只装了 InstallerX 时省事"，但 `PREFERRED` 已经覆盖了那几种
   命名，所以它带来的只有风险。

**v0.5 的做法**：`pickTarget()` 只做一件事 —— 取保存列表里第一个非空白项，没有就返回 null
（调用方回落到写死的 `TARGET_PACKAGE` = InstallerX Revived）。

```smali
# 第一项非空白即为目标；不再查 queryIntentActivities
if-eqz v2, :loop_next          # null 项 -> 跳过
invoke-virtual {v3}, Ljava/lang/String;->length()I
move-result v3
if-eqz v3, :loop_next          # 空白项 -> 跳过（length()==0 必须用 if-eqz）
return-object v2
```

**为什么可以完全不看可见性**：`startActivity()` **不要求目标可见**（真机已证：v0.3 时期壳枚举
为空、却仍把安装成功转发给了 InstallerX）。所以显式选择直接采信；如果那个包已经卸载，
启动会失败并落到既有的 Toast。**发现候选这件事交给 WebUI**（它以 root 运行，看得见全部安装器），
壳只负责执行被告知的目标。

**边界**：代价是"只装了 Universal Installer、又没在 WebUI 里勾过"时，壳不会自动改用它，而是
弹 Toast —— 那时去 WebUI 勾一下即可。这比"静默转发给一个下围棋的 app"好得多。

**新增的机器校验**：`length()` 这一行第一次又被写成了 `if-nez`（**本项目第三次犯同一个极性错误**），
所以 `audit_smali.py` 的检查 2 从"只扫 `writeStateFile()`"升级成一张
**（文件 + 方法 + 锚点 + 应有 opcode）** 规则表，现在钉住 3 条：

| 文件 | 方法 | 锚点 | 必须 | 含义 |
|---|---|---|---|---|
| `ConfigureActivity` | `writeStateFile` | `String.equals` | `if-nez` | ==1 表示是自己 → 跳过 emit |
| `ConfigureActivity` | `writeStateFile` | `ArrayList.contains` | `if-nez` | ==1 表示已输出过 → 跳过 emit |
| `ForwardActivity` | `pickTarget` | `String.length` | `if-eqz` | ==0 表示空白项 → 跳过 |

三条各自都做了反证测试（改错极性 → 精确报出文件/行号/应有 opcode → 退出码 1）。
