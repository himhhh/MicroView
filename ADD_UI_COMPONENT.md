# MicroView — 新增 UI 控件 / 功能 Protocol

按以下步骤操作，确保新控件支持暗黑/明亮模式、跨平台字体、风格一致。

---

## 第 1 步：颜色 —— 必须支持暗黑/明亮模式

### 原则

**禁止**在控件中硬编码颜色字符串（`#CCC`、`#3c3c3c` 等）。必须通过以下方式获取当前主题颜色。

### 方式 A：在 `MainWindow` 方法内（推荐）

调用 `self._dlg_colors()` 获取 7 元组：

```python
C = self._dlg_colors()
# C[0] 对话框/列表背景   暗:#2d2d2d  亮:#FFFFFF
# C[1] 文字颜色         暗:#CCC     亮:#333
# C[2] 按钮背景         暗:#3c3c3c  亮:#e8e8e8
# C[3] 按钮文字         暗:#CCC     亮:#333
# C[4] 树/列表项背景    暗:#1e1e1e  亮:#FFFFFF
# C[5] 表头背景         暗:#2d2d2d  亮:#f0f0f0
# C[6] 输入框背景       暗:#3c3c3c  亮:#FFFFFF
```

使用示例：

```python
btn.setStyleSheet(
    f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;"
    f"border-radius:4px;padding:6px 16px;}}"
    f"QPushButton:hover{{background:{C[5]};}}"
)
```

### 方式 B：在独立 Widget 类内（如 ViewerWidget、ControlsWidget）

添加 `set_dark_mode(self, dark: bool)` 方法，在内部根据 `dark` 参数切换颜色：

```python
def set_dark_mode(self, dark: bool):
    self._dark_mode = dark
    bg = "#3a3a3a" if dark else "#e8e8e8"
    fg = "#CCC" if dark else "#555"
    self.some_button.setStyleSheet(
        f"QPushButton{{background:{bg};color:{fg};}}"
    )
```

并在 `MainWindow` 中连接：

```python
# 初始化时
self.your_widget.set_dark_mode(self.dark_mode)

# toggle_dark_mode() 中
self.your_widget.set_dark_mode(self.dark_mode)
```

### 方式 C：在 QSS 文件中（全局样式）

`resources/style_dark.qss` 和 `resources/style.qss` 中定义按 `objectName` 选择器的样式：

```css
/* style_dark.qss */
#myNewWidget { background: #2d2d2d; color: #CCC; }

/* style.qss */
#myNewWidget { background: #FFFFFF; color: #333; }
```

**适用场景**：固定位置的全局组件。

---

## 第 2 步：字体 —— 跨平台兼容

### 禁止

禁止使用 `-apple-system`、`SF Pro Text` 等 macOS 专有字体名。这些在 Windows 上不存在。

### 正确做法

```python
import sys
if sys.platform == 'win32':
    font_family = "Segoe UI, Microsoft YaHei, sans-serif"
    font_size = 10
else:
    font_family = "-apple-system, Helvetica Neue, SF Pro Text, sans-serif"
    font_size = 12
```

在 QSS 中：

```css
QWidget {
    font-family: -apple-system, "SF Pro Text", "Segoe UI", "Microsoft YaHei", sans-serif;
}
```

**注意**：`"Microsoft YaHei"` 支持中文，`"Segoe UI"` 是 Windows 11 默认西文字体。

---

## 第 3 步：信号 / 槽连接

遵循项目现有模式：

```python
# 在 ControlsWidget 中定义信号
class ControlsWidget(QWidget):
    my_action_requested = Signal(str)   # 携带参数
    something_changed = Signal()        # 无参数通知

# 在 __init__ 中连接按钮
self.my_btn.clicked.connect(lambda: self.my_action_requested.emit("param"))

# 在 MainWindow._setup_central_widget 中连接
self.controls.my_action_requested.connect(self._on_my_action)
```

**命名约定**：信号名以 `_requested`、`_changed`、`_clicked` 结尾。

---

## 第 4 步：对话框布局规范

### 结构模板

```python
dlg = QDialog(self)
dlg.setWindowTitle("对话框标题")
dlg.setMinimumSize(500, 400)
C = self._dlg_colors()
dlg.setStyleSheet(f"QDialog{{background:{C[0]};}}")
layout = QVBoxLayout(dlg)
layout.setSpacing(8)

# ── 内容区域 ──
layout.addWidget(QLabel("描述文字"))

# ... 你的控件 ...

# ── 按钮行 ──
btn_row = QHBoxLayout()
btn_row.addStretch()
cancel_btn = QPushButton("取消")
cancel_btn.setStyleSheet(
    f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;"
    f"border-radius:4px;padding:6px 16px;}}"
)
cancel_btn.clicked.connect(dlg.reject)
ok_btn = QPushButton("确定")
ok_btn.setStyleSheet(
    f"QPushButton{{background:#007AFF;color:#FFF;border:none;"
    f"border-radius:4px;padding:6px 20px;font-weight:600;}}"
    f"QPushButton:hover{{background:#0066D6;}}"
)
ok_btn.clicked.connect(dlg.accept)
btn_row.addWidget(cancel_btn)
btn_row.addWidget(ok_btn)
layout.addLayout(btn_row)

if dlg.exec() == QDialog.Accepted:
    # 处理结果
    pass
```

### 按钮层级

| 角色 | 样式 |
|------|------|
| 主操作（确定/导出） | 蓝底白字 `#007AFF` |
| 次要（取消） | 灰底 `C[2]` + 边框 |
| 危险（删除） | 红底 `#E74C3C`（如果使用） |

---

## 第 5 步：下拉框 / 组合框

```python
fmt_combo = QComboBox()
fmt_combo.addItems(["PNG", "TIFF"])
fmt_combo.setFixedWidth(90)  # 固定宽度防止截断
fmt_combo.setStyleSheet(
    f"QComboBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
    f"border-radius:3px;padding:4px 10px;font-size:13px;}}"
    f"QComboBox:hover{{background:{C[2]};}}"
    f"QComboBox QAbstractItemView{{background:{C[0]};color:{C[1]};"
    f"selection-background-color:#007AFF;padding:4px;}}"
)
```

---

## 第 6 步：树形控件

```python
tree = QTreeWidget()
tree.setHeaderLabels(["列1", "列2"])
tree.setStyleSheet(
    f"QTreeWidget{{background:{C[4]};color:{C[1]};border:1px solid #999;}}"
    f"QHeaderView::section{{background:{C[5]};color:{C[1]};"
    f"border:1px solid #ccc;padding:4px;font-weight:600;}}"
)
```

---

## 第 7 步：复选框 + 动态过滤区

```python
ch_filter_group = QGroupBox("分组标题")
ch_filter_group.setStyleSheet(f"QGroupBox{{font-weight:600;color:{C[1]};}}")
ch_filter_layout = QHBoxLayout(ch_filter_group)
# ... 动态添加/移除 checkbox ...

def _rebuild_filter():
    while ch_filter_layout.count():
        w = ch_filter_layout.takeAt(0)
        if w.widget(): w.widget().deleteLater()
    for name in available_items:
        cb = QCheckBox(name)
        cb.setChecked(True)
        ch_filter_layout.addWidget(cb)
```

---

## 第 8 步：构建配置

### macOS `build.spec`

```python
hiddenimports=[..., 'your_new_module', ...]
datas=[..., ('ui/your_new_file.py', 'ui'), ...]
```

### Windows `build_windows.spec`

同样更新，并确保 macOS 专用模块在 `excludes` 中：

```python
excludes=[..., 'Foundation', 'AppKit', 'pyobjc-core', ...]
```

---

## 第 9 步：跨平台保护

所有 macOS 专用代码必须用 `sys.platform` 包裹：

```python
if sys.platform == 'darwin':
    from Foundation import NSObject
    from AppKit import NSApplication
    # ... macOS-only code ...
```

Windows / Linux 代码同样：

```python
if sys.platform == 'win32':
    font.setFamilies(["Segoe UI", "Microsoft YaHei", "sans-serif"])
```

---

## 验证清单

- [ ] 暗黑模式下所有文字可读（浅色字 + 深色底）
- [ ] 明亮模式下所有文字可读（深色字 + 浅色底）
- [ ] 切换到另一种模式后立即生效（实时切换，无需重启）
- [ ] 下拉框文字不被截断（设 `setFixedWidth` 或 `setMinimumWidth`）
- [ ] 对话框按钮风格统一（主操作蓝底、取消灰底边框）
- [ ] 字体在 macOS 和 Windows 上均可正常显示中文
- [ ] macOS 专用代码有 `sys.platform == 'darwin'` 保护
- [ ] 新模块已添加到两个 `build.spec` 的 `hiddenimports`
- [ ] 双击打开文件功能未受影响
- [ ] 导出功能（Merge/通道/批量）未受影响
- [ ] 触控板捏合缩放和鼠标滚轮缩放均正常
