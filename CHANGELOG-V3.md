# MicroView V3 — ImageJ/Fiji 集成

## 改动日期

2026-06-23

## 新增功能

### "🔬 ImageJ" 按钮

控制栏新增绿色按钮，位于 **重置** 和 **导出 Merge** 之间。点击后将当前图像发送到 ImageJ/Fiji 打开。

### ImageJ/Fiji 设置面板

在 视图 → 设置 底部新增 `ImageJ/Fiji` 配置区：

| 配置项 | 说明 | QSettings key |
|--------|------|---------------|
| 路径 | Fiji/ImageJ 可执行文件位置 | `imagej_path` |
| LIF 打开方式 | 下拉4选1 | `imagej_lif_mode` |
| 应用调整 | 是否应用 LUT/亮度/对比度（非"完整LIF"时显示） | `imagej_apply_adjustments` |

**打开方式选项（ND2 和 LIF 通用）：**
1. **完整文件** — 传原始文件（.nd2 或 .lif），参数调整不应用
2. **当前 Merge** — 导出合成图 TIFF
3. **所有通道** — 每个启用通道一张 TIFF
4. **Merge + 所有通道** — 全部导出

**临时文件命名**（参考批量导出规则）：
- ND2: `{文件名}_Merge.tif` / `{文件名}_Ch1.tif`
- LIF: `{lif文件名}-{Series名}_Merge.tif` / `{lif文件名}-{Series名}_Ch1.tif`

---

## 修改文件

| 文件 | 改动 |
|------|------|
| `ui/controls.py` | 新增 `imagej_requested` 信号 + 按钮（第25行 + 第210行后） |
| `ui/main_window.py` | 新增 `_on_open_in_imagej()` 方法 + 信号连接 |
| `ui/settings_dialog.py` | 新增 ImageJ/Fiji 配置区（路径、LIF方式、动态提示） |
| `build.spec` | 名称改为 `MicroViewTest.app` |

### 临时文件

导出模式生成的临时 TIFF 存 `/tmp/microview_*.tif`，每次覆盖。

### 按钮位置

```
[重置] [🔬 ImageJ] [💾 导出 Merge] [📸 导出通道] [📦 批量导出]
```
