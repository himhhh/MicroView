# MicroView

> 为 ND2 / LIF 显微图像而生的轻量浏览、校正与导出工具。

Nikon 官方软件可以打开 ND2 文件，但连续浏览整个实验文件夹时，往往缺少便于切换的侧边栏列表；多通道窗口需要逐个整理和拖放，导出前的显示调整也不够集中。

MicroView 专注于把这段工作流变得顺手：**扫描文件夹 → 从侧边栏连续切换图像 → 同时查看 Merge 与单通道 → 调整显示 → 导出或交给 ImageJ/Fiji。**

它不是为了取代专业显微图像分析平台，而是为“快速看图、选图、统一显示和导出”提供更连贯的体验。

## 功能亮点

### ND2 与 LIF 浏览

- 支持 Nikon `.nd2` 与 Leica `.lif`。
- 每个 LIF Series 都能作为独立图像浏览。
- 递归扫描文件夹，并用树状侧边栏管理实验数据。

### 多通道预览与显示控制

- 同时显示 Merge 与各个单通道图像，支持同步缩放与平移。
- 可单独查看 Merge；调整显示参数时保留当前缩放和位置。
- 独立控制每个通道的开关、LUT 黑场/白场、亮度和对比度。
- 自动识别常见通道命名和 Leica LUTName：DAPI/Hoechst、GFP/FITC、RFP/mCherry、Blue、Green、Red 等。
- 支持自定义 ND2 与 LIF 通道颜色映射。

### 全局显示设置

默认情况下，每张图像或 LIF Series 都保留独立的显示配置。

启用“应用到全局”后，当前图片的通道开关、LUT 范围、亮度和对比度会在本次软件运行中应用到之后实际打开的图片或 Series。该功能采用惰性应用：不会预加载、遍历或刷新全部图片。

### 比例尺与导出

- 预览和导出图像均可添加比例尺。
- 可设置比例尺位置、长度、颜色、粗细、字体、字号和文字标签。
- 支持 PNG 与 TIFF；可导出 Merge、单独通道或两者组合。
- Merge 使用的通道可与单通道导出独立配置。
- 支持批量导出、通道筛选、统一显示参数和比例尺。

### ImageJ / Fiji 集成

可从 MicroView 直接在 ImageJ/Fiji 中打开原始 ND2/LIF、当前 Merge、当前启用通道或组合结果。

> 打开原始 ND2/LIF 文件需要 Fiji/ImageJ 已安装 Bio-Formats。

## 安装

### macOS

1. 下载 `MicroView.app`，拖入“应用程序”文件夹。
2. 首次运行如出现安全提示，在“系统设置 → 隐私与安全性”中选择仍要打开。

### Windows

1. 下载并解压 `MicroView.zip`。
2. 运行 `MicroView.exe`。

## 快速开始

1. 打开包含 ND2 或 LIF 文件的文件夹。
2. 在左侧文件树选择图像或 LIF Series。
3. 在底部控制区调整通道开关、LUT、亮度和对比度。
4. 在预览区检查 Merge 与单通道效果。
5. 使用“导出 Merge”“导出通道”或“批量导出”生成结果。
6. 如需进一步分析，点击 ImageJ 按钮交给 Fiji/ImageJ。

## 构建

### macOS

```bash
pip install -r requirements.txt
pyinstaller build.spec
```

构建结果：`dist/MicroView.app`

### Windows

最简单的方式是在 Windows 上双击项目根目录的 `build.bat`。脚本会自动创建虚拟环境、安装依赖、构建程序，并在成功后打开 `MicroView.exe` 所在文件夹。

也可以手动运行：

```bash
pip install -r requirements.txt
pyinstaller build-windows.spec
```

构建结果：`dist/MicroView/`

## 技术栈

Python · PySide6 · NumPy · nd2 · readlif · Pillow · PyInstaller

## 致谢

- [ImageJ](https://imagej.net/)
- [Fiji](https://fiji.sc/)
- [Bio-Formats](https://www.openmicroscopy.org/bio-formats/)
- [nd2](https://github.com/tlambert03/nd2)
