# MicroView — Microscope Image Browser

简洁直观的显微镜图像浏览器，支持 Nikon ND2 和 Leica LIF 格式。跨平台（macOS / Windows）。

## 功能

- 📁 文件夹树形浏览，LIF 作为可展开容器
- 🎨 智能通道颜色（DAPI→蓝、TxRed→红、FITC→绿）
- 🔄 多通道同步缩放/平移
- 🎚️ 单通道独立亮度/对比度，每文件记忆
- ☀️🌙 亮色/暗黑模式
- 💾📸📦 三种导出（Merge / 通道 / 批量）

## macOS 安装

1. 下载 `MicroView.app` → 拖入 `/Applications`
2. 首次打开如提示安全警告，前往 系统设置 → 隐私与安全性 → 仍要打开
3. 关联文件：右键 .nd2/.lif → 打开方式 → MicroView → 始终以此方式打开

## Windows 安装

1. 下载 `MicroView.zip` → 解压到任意位置
2. 运行 `MicroView.exe`
3. 关联文件：右键 .nd2/.lif → 打开方式 → 选择 MicroView.exe

## Windows 构建

在 Windows 上安装 Python 3.12 + 依赖后运行：
```
pip install -r requirements.txt
pyinstaller build_windows.spec
```
输出在 `dist/MicroView/`

## 技术栈

Python 3.12 + PySide6 + nd2/readlif + NumPy + PyInstaller
