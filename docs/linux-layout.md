# Linux 目录与 Vulkan 约定

应用的用户文件遵循 [XDG Base Directory 0.8](https://specifications.freedesktop.org/basedir/latest/)。
空值或相对路径的 XDG 变量被忽略，使用规范默认值；新建应用目录权限为 0700，不改已有目录权限。

| 文件类别 | 默认路径 |
| --- | --- |
| 非 GSettings 的偏好、可信程序、用户组件来源 | `~/.config/bottles/data.yml` |
| GSettings | 交给原生 GSettings 后端；常见为 `~/.config/dconf/user`，不复制进 data.yml |
| 应用日志、崩溃报告 | `~/.local/state/bottles/{journal.yml,crash.log}` |
| 下载包、仓库清单缓存和可重新生成的模板 | `~/.cache/bottles/{temp,templates}` |
| 容器路径索引、共享运行库/图形组件与 Eagle 数据库 | `~/.local/share/bottles/` |
| 桌面入口和图标 | 标准 XDG data 下的 `applications/` 与 `icons/` |

尊重 `XDG_CONFIG_HOME`、`XDG_DATA_HOME`、`XDG_CACHE_HOME`、`XDG_STATE_HOME`。
Flatpak 的 XDG 目录已经按应用隔离，直接使用各自根目录，不再追加 `bottles/`：例如宿主的 `~/.var/app/com.usebottles.bottles/data/bottles.sqlite` 与 `config/data.yml`。原生安装保留表中的 `bottles/` 应用命名空间。Wine 访问含尾随点或空格的宿主路径时，使用等价的 `/var/data` 挂载路径；用户选择的容器目录不被重排。
容器内部的 `bottle.yml`、Windows 目录、注册表、程序及着色器缓存属于 Wine 环境，不搬进应用配置目录。
容器没有默认存放目录。创建时必须选择已有的空目录，该目录直接作为根目录，不追加名称、不创建占位目录。
目标必须可读、可写、可进入，不另外限制所有者或模式位。创建、导入、复制和恢复均保留用户所选目录的权限，不提权、不更改父目录或所有权，也不依据根目录模式位拒绝父目录已隔离的容器。新建的普通子目录和文件遵循当前 umask，不主动扩大访问权限。
容器配置、程序库、运行统计与容器缓存分别存放在根目录的 `bottle.yml`、`library.yml`、`process_metrics.sqlite` 与 `cache/`；Gamescope 和注册表临时脚本位于 `cache/temp/`。
配置使用独立标识，不保存容器的绝对位置或本次启动参数；改名保持标识，移动目录后可重新导入。外部程序路径仍由用户负责保持有效。
应用数据根目录中的 `bottles.sqlite` 只登记当前用户选择的路径与显示名称。读取索引不创建数据库；磁盘不可用时保留登记并显示错误。
复制会获得新标识并从空的运行统计开始；备份恢复保留原标识。
“从列表移除”只删除登记；“删除文件”会停止容器并删除它的目录。容器之间不共享 prefix 或个人数据。

现有 Bottles 容器通过选择目录原地导入，不复制文件、不运行 Wine、不修改配置。配置重建、完整备份恢复与复制均须另选空目标目录。

```sh
bottles-cli new --bottle-name Office --environment application --path /opt/username/Wine
bottles-cli import --path /opt/username/Wine
bottles-cli list bottles
bottles-cli forget --bottle <UUID>
```

Flatpak 需要获得所选宿主目录的实际访问权限；文档 portal 的临时路径不能作为持久容器路径。权限不足时报告错误，不退回另一个目录。

系统安装遵守 Meson 的 `prefix/datadir/localedir` 与所选 Python 解释器的安装规则：

| 类别 | 安装位置 |
| --- | --- |
| `bottles` Python 包及其子包 | `python.get_install_dir()` 下的 `bottles/`，用 `python.install_sources()` 安装 |
| GUI/CLI 启动器 | `${bindir}/bottles`、`${bindir}/bottles-cli` |
| GResource、Eagle 只读数据库与规则 | `${datadir}/bottles/resources/` |
| 系统 runner | `${datadir}/bottles/runners/<名称>/`；由构建时的 prefix/datadir 确定，不附加其它前缀的目录 |
| 用户 runner | 用户在设置的 Runners 页就地登记名称与目录；不设默认存放位置，不复制、不更新、不删除 runner 文件 |

`site-packages` / `dist-packages` 的实际路径由解释器和打包者确定，不拼接 Python 版本或固定 `/usr/lib`。发行版可用 Meson 的 `-Dpython.purelibdir=...` 选择其规则；没有把 Bottles 作为稳定公共 Python API 的承诺。
静态资源不是 Python 模块，不把资源目录加入 `sys.path`。启动器只加入构建时确定的 Python 安装目录，资源路径与模块路径分别配置。
Eagle 内置数据库与规则不再从 Python 文件的父目录猜测位置。

系统 runner 的 share 位置为与 Steam compatibilitytools.d 对应的下游打包约定。FHS 的 share 一般用于架构无关静态数据，Wine 目录包含架构相关 ELF，因此不能声称该选择由 FHS 要求。保持路径约定清晰并由架构专属的包/扩展供应。
Flatpak 内系统 runner 为 `/app/share/bottles/runners/<名称>`；只扫描当前运行环境的系统目录，不访问宿主环境；不把用户 XDG_DATA_DIRS 冒充为系统供应目录。用户通过 `--user` 安装的扩展挂载到该系统位置后仍按系统来源处理。
系统目录只读，应用只创建用户目录；包管理器负责系统位置。

依据：[Meson Python 模块](https://mesonbuild.com/Python-module.html)、[Python 私有模块安装规则](https://www.debian.org/doc/packaging-manuals/python-policy/#programs-shipping-private-modules)、[FHS share](https://specifications.freedesktop.org/fhs/latest/usrShare.html)、[Flatpak 扩展](https://docs.flatpak.org/en/latest/extension.html)。
新增文件应审查其配置、数据、状态或缓存属性。Meson 的安装测试核对实际安装边界；XDG 行为由回归测试覆盖。
原生构建不以 `/.flatpak-info` 为前提；构建测试及前端资源加载方法统一见 [development.md](development.md)。

应用直接使用当前配置格式，不自动迁移旧布局或配置。磁盘上的旧文件保持原样；配置、缓存和状态只在各自当前目录创建。修改 XDG 环境相当于选用另一套用户目录。

Vulkan 通过 `ctypes` 加载系统 `libvulkan.so.1`，调用
[`vkCreateInstance`](https://docs.vulkan.org/refpages/latest/refpages/vkCreateInstance.html) 与
[`vkEnumeratePhysicalDevices`](https://docs.vulkan.org/refpages/latest/refpages/vkEnumeratePhysicalDevices.html)。
不要求桌面显示连接、附加层或扩展；由 Vulkan loader 处理 ICD 和环境变量。成功创建的实例总会销毁。
不解析外部命令，不把 ICD JSON 文件存在视为能力证据，Flatpak 清单也不再编译 Vulkan-Tools。

该探测覆盖当前 Python 进程 ABI 的 Vulkan 1.0 实例与设备枚举。软件 Vulkan 设备同样是有效实现；它不证明 32 位驱动、WSI 呈现、特定 DXVK 所需扩展或游戏性能。
原诊断入口返回原生探测摘要；不再输出 `vulkaninfo` 的完整硬件报告。结果按进程缓存，驱动环境改变后重启应用。

用户 runner 只读取显式登记项，不扫描应用数据目录。登记保存独立标识、名称和绝对路径；修改名称或位置保持标识，已配置容器无需重选。失效登记保留可编辑；容器仍在使用时不允许取消登记。系统 runner 与当前环境 PATH Wine 继续自动发现，并优先于用户登记项。

程序库只汇总各已登记容器内的 `library.yml`，不再读取或写入应用数据根目录下的全局 `library.yml`。同一程序 ID 可存在于不同容器，去重只在所属容器内进行。

HIDRAW 设备偏好通过通用 Wine 的 `HKLM\System\CurrentControlSet\Services\winebus\EnableHidraw` 多字符串值设置，不依赖 runner 名称或 Proton 环境变量。它是 Wine 的设备偏好，并非按设备隔离的权限边界；Flatpak 独立沙箱的 HIDRAW 访问需要更广的设备权限。注册表导入使用容器内的私有临时文件，结束后清理。


## 容器身份

`bottle.yml` 中的 `Id` 是容器的稳定 UUID。名称用于显示和名称校验，路径用于访问文件；内部实例、运行记录、缓存和列表排序均按 UUID 区分。改名、移动并重新登记后 UUID 不变；复制容器生成新的容器 UUID，保留程序与程序库条目 ID。

程序库汇总以 `(容器 UUID, 条目 ID)` 为键，各容器的 `library.yml` 仍只保存自身条目 ID。封面引用和删除检查仅在所属容器内进行。桌面入口及 Steam 快捷方式以容器 UUID 与程序 ID 确定身份，名称变化不再生成另一个入口。

CLI 的 `--bottle` 参数使用 UUID；通过 `bottles-cli list bottles` 查看名称、UUID 和位置。`import --path` 接收待登记目录，`forget --bottle` 以 UUID 取消登记，包括暂时不可用的目录。旧名称参数、路径排序键及旧快捷方式不提供兼容或迁移。

## 容器内组件布局

组件按用途而非下载包的目录结构安装：

```text
<容器>/
├── drive_c/windows/
│   ├── system32/                    # Wine 对应架构的 Windows DLL
│   └── syswow64/                    # win64 容器中的 32 位 DLL
├── components/
│   └── latencyflex/
│       ├── lib/x86_64-linux-gnu/liblatencyflex_layer.so
│       └── share/vulkan/implicit_layer.d/latencyflex.json
└── cache/temp/component-*/          # 一次操作的准备文件，结束后清理
```

`components/<组件标识>/` 只保存该组件需要的私有文件，保持一份当前安装结果，不再按版本叠加目录。原生库使用 `lib/<ABI>/`，组件私有的 Windows DLL 使用 `lib/<Windows 架构>/`，所需的可执行辅助程序使用 `bin/`，只读资源使用 `share/`。没有对应文件就不创建空目录。需要被 Windows 程序常规导入的 DLL 仍进入 Wine 的系统目录；不得为规整应用目录而改动 Wine 的内部布局。

下载包中的 `layer/usr/`、源代码、构建日志及其它无关内容不照搬。共享数据目录只作为这些 prefix 安装组件的安装源和缓存；安装时解引用来源软链接，Vulkan 清单的库路径改为组件目录内的相对路径。组件自己的目录不可链接到容器外。DLL 卸载所需的原始文件备份继续由 DLL 安装器管理，不是更新失败的事务回滚。

新增含原生库的 DLL 组件只需声明源文件到上述布局的映射；清单等元数据在准备阶段处理。它使用与普通 DLL 组件相同的安装器，不另写下载、文件快照或版本回退流程。D7VK 仅保留 Wine `ddraw` 与别名的必要文件处理，配置保存与错误语义使用共同入口。

GUI 选择、CLI 版本选项及参数开关、组件更新入口均调用 `set_dll_component`。安装与更换版本先校验并准备完整文件，再逐文件替换、写 overrides，成功后才保存版本和启用状态。禁用则恢复或移除 DLL、清除 overrides、删除该组件私有目录，成功后才保存禁用状态。首次失败立即停止并报告；文件与 Wine 注册表之间不提供整体事务，不自动重装旧版。完整备份保留实际的 prefix 安装组件。`Lossless.dll` 属于依赖宿主 lsfg-vk 层的运行时素材，不纳入此组件布局或自包含备份要求；缺少对应层时禁用该可选功能，不能使 prefix 的基本启动依赖它。

组件自包含指当前支持的基础 Wine 环境下，其安装结果不依赖应用缓存中的文件；目录布局本身不等于宿主能力可移植。依赖特定宿主能力的可选运行时需要单独检测。

WineBridge、Bottles runtime 及反作弊 runtime 保持共享使用，不复制到容器。系统或登记的 Wine runner、宿主驱动及 Steam 提供的 runtime 仍属于外部系统集成。
