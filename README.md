# OpenWrt 固件

基于 OpenWrt `main`，通过 GitHub Actions 编译以下设备的固件：

| 设备 | 配置 | 升级镜像 |
| --- | --- | --- |
| ASUS RT-ACRH17（RT-AC42U） | `acrh17.config` | `asus_rt-ac42u-squashfs-sysupgrade.bin` |
| x86-64（UEFI、ext4） | `x86.config` | `x86-64-generic-ext4-combined-efi.img.gz` |
| GL.iNet GL-MT6000 | `mt6000.config` | `glinet_gl-mt6000-squashfs-sysupgrade.bin` |

## 下载与构建

在 [Releases](https://github.com/realqhc/openwrt-builder/releases) 下载对应设备的固件，并使用同一版本的 `sha256sums` 校验。升级前备份配置，确认设备型号及镜像类型。

手动构建：进入 **Actions → Build OpenWrt → Run workflow**。一次运行依次编译三台设备，也会按工作流中的计划自动构建。每次构建更新 OpenWrt 与 feeds，因此不同批次的软件版本可能变化。

## 软件源规则

- 代理核心、相关工具和规则数据优先使用 [Passwall 软件源](https://github.com/Openwrt-Passwall/openwrt-passwall-packages)。明确选择的配方见 [`scripts/passwall-packages.py`](scripts/passwall-packages.py)。
- 其他包继续使用原有软件源；Go 工具链保留单独指定的来源。新增同名包需审核后加入优先列表，不自动覆盖系统基础库。
- 构建检查实际软件源和版本，发布前核对固件包清单。检查失败时不发布该固件。
- 每个 Release 附带 `proxy-packages.json`、`feeds.buildinfo` 和软件包 `.manifest`，可查询实际使用的来源、提交及版本。

设备软件选择在各自的 `.config` 文件中；自定义 feeds 和构建调整分别位于 `diy-part1.sh`、`diy-part2.sh`。
