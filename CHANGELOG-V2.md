# MicroView V2 → V3 改动说明

> 本文档供 AI 辅助开发时回溯改动。附上本文档和 `*-copy.py` 备份文件即可了解原始状态。

---

## V3 改动（2026-06-22）

### 问题
V2 中设置面板 LIF 区域仍是固定 Ch0-Ch5 按索引配色，与实际通道名（Green/Red/...）脱节，且用户修改颜色不生效（因为 `_guess_color` 中 LUTName 自动检测优先级高于用户 LIF 设置）。

### 改动文件

| 文件 | 改动 | 备份 |
|------|------|------|
| `core/image_processor.py` | `_load_user_lif_colors()` 返回 `dict{name: RGB}` 替代 `list`；`_guess_color()` 用户 LIF 映射插到步骤 2（内置关键词之前） | `core/image_processor-copy.py` (V1) |
| `ui/settings_dialog.py` | LIF 区域：固定 Ch0-Ch5 → 动态行（标签=通道名，下拉框=颜色）；存储格式 `list` → `dict{name: chinese_color}` | `ui/settings_dialog-copy.py` |
| `ui/controls.py` | 按钮 checked 色用 `_guess_color()` 替代硬编码索引色 | `ui/controls-copy.py` |
| `ui/main_window.py` | `_on_settings()` 传 `lif_channel_names` + 保存后刷新按钮；`_do_render()` 去掉 `(Ch0)` 后缀 | `ui/main_window-copy.py` (V1) |

### 新优先级
```
1. 用户 ND2 名称映射
2. 用户 LIF 名称映射（精确匹配）  ← 新增，在关键词之前
3. 内置关键词（dapi/fitc/green/red...）
4. LUTName 自动检测（显微镜元数据）
5. 索引兜底
```

---

## V2 改动（2026-06-22）

### 问题

2026-06-22

## 问题背景

LIF 格式文件的通道颜色显示错误。

### 具体现象

| LIF 文件 | 通道数 | 实际通道 | 默认显示颜色 | 期望颜色 |
|----------|--------|---------|-------------|---------|
| BA1-1 CD34.lif | 3 | ch1, ch2, ch3 | 蓝/绿/红 | 蓝/绿/红 ✓ |
| 376+CXCL5.lif | 2 | ch1, ch2 | 蓝/绿 | **绿/红** ✗ |

### 原因

- LIF XML 元数据中的 `ChannelDescription` 元素包含 `LUTName` 属性（显微镜操作者在采集时指定的通道颜色，如 `"Blue"`, `"Green"`, `"Red"`）
- `376+CXCL5.lif` 的 LUTName 是 `["Green", "Red"]`，`BA1-1 CD34.lif` 的是 `["Blue", "Green", "Red"]`
- 原代码**完全忽略 LUTName**，只用数组顺序索引（0→蓝, 1→绿, 2→红）分配颜色
- 3 通道文件恰好 LUTName 与默认顺序相同所以看不出问题；2 通道文件因为只有 Green/Red，按顺序分配成蓝/绿，错误

### 另一个混淆点

- 设置面板的 LIF 颜色选项标签是 `Ch0, Ch1, Ch2...`（0-based 数组索引）
- 查看器中通道标签是 `Ch1, Ch2, Ch3...`（1-based 计数）
- 用户改设置 `Ch0` 实际影响查看器里的 `Ch1`，产生一位偏移混淆

---

## 修改的文件

### 1. `core/lif_reader.py` — 核心改动：提取 LUTName

**备份文件：** `core/lif_reader-copy.py`

**改动内容：**
- `read_lif_metadata()` 中，新增从 `lif.xml_root` 遍历所有 `ChannelDescription` 元素提取 `LUTName`
- 将 LUTName 用做 `channel_names`（例如 `["Green", "Red"]` 替代原来的 `["Ch1", "Ch2"]`）
- 如果 LUTName 为空字符串，回退到泛用名称 `Ch{i+1}`

**改动位置：** 第 28-54 行

### 2. `core/image_processor.py` — 新增 LUTName→RGB 颜色映射

**备份文件：** `core/image_processor-copy.py`

**改动内容：**
- 新增 `_LUT_NAME_MAP` 字典：英文颜色名 → RGB 元组
  - `"Blue"`, `"Green"`, `"Red"`, `"Cyan"`, `"Magenta"`, `"Yellow"`, `"Gray"`, `"Grey"`
- 在 `_guess_color()` 中，步骤 2（内置名称匹配）和步骤 3（用户 LIF 索引颜色）之间插入步骤 2.5：
  直接检查 `name` 是否在 `_LUT_NAME_MAP` 中，命中则直接返回对应 RGB

**颜色分配优先级（最终）：**
1. 用户自定义 ND2 名称映射（设置面板 ND2 部分）
2. 内置名称关键词匹配（dapi/fitc/green/red/...）
3. **【新增】LUTName 精确匹配**（`"Green"`→绿色, `"Red"`→红色...）
4. 兜底：用户 LIF 索引颜色（设置面板 Ch0-Ch5）

**改动位置：** 第 25-32 行（新增 map），第 90-95 行（新增匹配步骤）

### 3. `ui/main_window.py` — 查看器标签加数组索引后缀

**备份文件：** `ui/main_window-copy.py`

**改动内容：**
- `_do_render()` 中，传给 `viewer.display_image()` 的通道标签从 `"Green"` 改为 `"Green (Ch0)"` 格式
- 这样用户在查看器中能看到 `Green (Ch0)`，直接对应设置面板中的 `Ch0` 选项

**改动位置：** 第 476-479 行

---

## 未修改的文件

以下文件不受影响，逻辑保持不变：

| 文件 | 原因 |
|------|------|
| `core/nd2_reader.py` | ND2 文件路径完全不变 |
| `core/scanner.py` | `channel_names` 格式兼容，缓存会自动失效重建 |
| `ui/settings_dialog.py` | Ch0-Ch5 按索引配色逻辑不变，但现在查看器标签能与之对应 |
| `ui/controls.py` | 通道按钮直接使用 `channel_names`，会自动显示 LUTName |
| `ui/viewer.py` | 纯展示层，接收 `filtered_names` 作为标签 |
| `ui/sidebar.py` | 不受影响 |

---

## 导出信息

- **文件名：** `MicroViewV2.app`
- **位置：** `dist/MicroViewV2.app`
- **版本号：** 2.0.0
- **Bundle ID：** `com.microview.app.v2`
- **构建文件：** `build.spec`（已修改 name 和版本号）

---

## 如何回退到 V1

三个备份文件即 V1 原始代码：
- `core/lif_reader-copy.py` → 改回 `core/lif_reader.py`
- `core/image_processor-copy.py` → 改回 `core/image_processor.py`
- `ui/main_window-copy.py` → 改回 `ui/main_window.py`

然后修改 `build.spec` 中三个位置（`name='MicroView'`, `'MicroView.app'`, 版本号 `'1.0.0'`），重新执行 `pyinstaller build.spec --noconfirm`。
