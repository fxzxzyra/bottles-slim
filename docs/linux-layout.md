# Linux 目录与 Vulkan 约定

应用的用户文件遵循 [XDG Base Directory 0.8](https://specifications.freedesktop.org/basedir/latest/)。
空值或相对路径的 XDG 变量被忽略，使用规范默认值；新建应用目录权限为 0700，不改已有目录权限。

| 文件类别 | 默认路径 |
| --- | --- |
| 非 GSettings 的偏好、可信程序、用户组件来源 | `~/.config/bottles/data.yml` |
| GSettings | 交给原生 GSettings 后端；常见为 `~/.config/dconf/user`，不复制进 data.yml |
| 应用日志、崩溃报告 | `~/.local/state/bottles/{journal.yml,crash.log}` |
| 下载包、仓库清单缓存和可重新生成的模板 | `~/.cache/bottles/{temp,templates}` |
| 瓶子路径索引、用户 runner/运行库/图形组件与 Eagle 数据库 | `~/.local/share/bottles/` |
| 桌面入口和图标 | 标准 XDG data 下的 `applications/` 与 `icons/` |

尊重 `XDG_CONFIG_HOME`、`XDG_DATA_HOME`、`XDG_CACHE_HOME`、`XDG_STATE_HOME`。
Flatpak 内沿用其提供的 XDG 环境，保留 Wine 路径兼容处理；用户自定义容器位置不被重排。
容器内部的 `bottle.yml`、Windows 目录、注册表、程序及着色器缓存属于 Wine 环境，不搬进应用配置目录。
瓶子没有默认存放目录。创建时必须选择已有的空目录，该目录直接作为根目录，不追加名称、不创建占位目录。
目标必须属于当前用户；创建时将空根目录设为 0700，不提权、不更改父目录或所有权。导入要求根目录已经私有且可读写，不自动修改权限。
瓶子配置、程序库、运行统计与瓶子缓存分别存放在根目录的 `bottle.yml`、`library.yml`、`process_metrics.sqlite` 与 `cache/`；Gamescope 和注册表临时脚本位于 `cache/temp/`。
配置使用独立标识，不保存瓶子的绝对位置或本次启动参数；改名保持标识，移动目录后可重新导入。外部程序路径仍由用户负责保持有效。
`${XDG_DATA_HOME}/bottles/bottles.sqlite` 只登记当前用户选择的路径与显示名称。读取索引不创建数据库；磁盘不可用时保留登记并显示错误。
复制会获得新标识并从空的运行统计开始；备份恢复保留原标识。
“从列表移除”只删除登记；“删除文件”会停止瓶子并删除它的目录。瓶子之间不共享 prefix 或个人数据。

现有 Bottles 瓶子通过选择目录原地导入，不复制文件、不运行 Wine、不修改配置。第三方 Wine prefix 的转换、配置重建、完整备份恢复与复制均须另选空目标目录。

```sh
bottles-cli new --bottle-name Office --environment application --path /opt/username/Wine
bottles-cli import --path /opt/username/Wine
bottles-cli forget --path /opt/username/Wine
```

Flatpak 需要获得所选宿主目录的实际访问权限；文档 portal 的临时路径不能作为持久瓶子路径。权限不足时报告错误，不退回另一个目录。

系统安装遵守 Meson 的 `prefix/datadir/localedir` 与所选 Python 解释器的安装规则：

| 类别 | 安装位置 |
| --- | --- |
| `bottles` Python 包及其子包 | `python.get_install_dir()` 下的 `bottles/`，用 `python.install_sources()` 安装 |
| GUI/CLI 启动器 | `${bindir}/bottles`、`${bindir}/bottles-cli` |
| GResource、Eagle 只读数据库与规则 | `${datadir}/bottles/resources/` |
| 系统 runner | `${datadir}/bottles/runners/<名称>/`；由构建时的 prefix/datadir 确定，不附加其它前缀的目录 |
| 用户 runner | `${XDG_DATA_HOME}/bottles/runners/<名称>/`，另可登记外部目录 |

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
