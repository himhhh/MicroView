# MicroView — 添加新显微镜格式 Protocol

按以下 4 步操作，添加新格式支持。

---

## 第 1 步：安装读取库

```bash
pip install <library>
```

在 `requirements.txt` 中添加一行。

---

## 第 2 步：创建 `core/<format>_reader.py`

命名：`core/czi_reader.py`、`core/zvi_reader.py` 等。

必须提供两个函数：

### `read_metadata(filepath) -> list[Metadata]`

```python
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

@dataclass
class Metadata:
    filepath: Path
    filename: str
    image_name: str = ""               # 多图格式用，单图留空
    acquisition_date: datetime | None = None
    channel_count: int = 1
    channel_names: list = field(default_factory=list)  # ["DAPI", "FITC"]
    width: int = 0
    height: int = 0
    z_slices: int = 1

def read_metadata(filepath):
    """返回 Metadata 列表。单图格式返回 [meta]，多图格式返回多个。"""
    filepath = Path(filepath)
    results = []
    try:
        # TODO: 打开文件，读取每个图像
        # for each image in file:
        #     meta = Metadata(
        #         filepath=filepath,
        #         filename=filepath.name,
        #         image_name="Image001",        # 多图时填写
        #         acquisition_date=datetime.now(),
        #         channel_count=3,
        #         channel_names=["DAPI", "FITC", "TxRed"],
        #         width=2048,
        #         height=2048,
        #         z_slices=1,
        #     )
        #     results.append(meta)
        pass
    except Exception as e:
        print(f"Warning: {filepath}: {e}")
    return results
```

### `read_pixels(filepath, image_index=0) -> np.ndarray`

```python
import numpy as np

def read_pixels(filepath, image_index=0):
    """返回 numpy 数组。形状：(C, Y, X) 或 (C, Z, Y, X)。dtype: uint16。"""
    filepath = Path(filepath)
    # TODO: 打开文件，读取指定 image_index
    # data = ...
    # return data  # shape: (channels, height, width)
    return np.zeros((1, 512, 512), dtype=np.uint16)
```

### 完整模板

```python
"""
<Format> reader for MicroView.
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import numpy as np

@dataclass
class Metadata:
    filepath: Path
    filename: str
    image_name: str = ""
    acquisition_date: datetime | None = None
    channel_count: int = 1
    channel_names: list = field(default_factory=list)
    width: int = 0
    height: int = 0
    z_slices: int = 1


def read_metadata(filepath):
    filepath = Path(filepath)
    results = []
    try:
        from <library> import <Reader>
        # === YOUR CODE HERE ===
        pass
    except Exception as e:
        print(f"Warning: {filepath}: {e}")
    return results


def read_pixels(filepath, image_index=0):
    filepath = Path(filepath)
    try:
        from <library> import <Reader>
        # === YOUR CODE HERE ===
        pass
    except Exception as e:
        print(f"Warning: {filepath}: {e}")
    return np.zeros((1, 512, 512), dtype=np.uint16)
```

**关键约束**：
- `read_metadata` 返回 **list**（即使只有 1 张图）
- `read_pixels` 返回的数组 shape 必须是 `(C, Y, X)` 或 `(C, Z, Y, X)`，dtype **uint16**
- 日期用 `datetime.fromtimestamp(filepath.stat().st_mtime)` 兜底
- 通道名列表长度必须等于 `channel_count`

---

## 第 3 步：修改 `core/scanner.py`

三处修改：

### 3a. 添加文件搜索（约第 90 行）

```python
# 在 lif_files 定义后添加：
xxx_files = [f for f in root.rglob("*.xxx") if not f.name.startswith("._")]
xxx_upper = [f for f in root.rglob("*.XXX") if not f.name.startswith("._")]
xxx_files = sorted(set(xxx_files + xxx_upper), key=lambda p: p.name.lower())
```

### 3b. 加入 all_files 列表

```python
all_files = list(nd2_files) + list(lif_files) + list(xxx_files)
```

### 3c. 添加格式判断（约第 120 行，`elif suffix == '.lif'` 之后）

```python
elif suffix == '.xxx':
    from .xxx_reader import read_metadata as read_xxx_meta
    metas = read_xxx_meta(filepath)
    for j, meta in enumerate(metas):
        key = f"{filepath}:::{meta.image_name or meta.filename}"
        entry = {
            'filename': f"{filepath.name} [{meta.image_name}]" if meta.image_name else filepath.name,
            'filepath': str(filepath),
            '<format>_image_index': j,      # 用格式名，如 czi_image_index
            'date': meta.acquisition_date.isoformat() if meta.acquisition_date else None,
            'channel_count': meta.channel_count,
            'channel_names': meta.channel_names,
            'width': meta.width,
            'height': meta.height,
            'z_slices': meta.z_slices,
            'pixel_size_um': None,
            '_idx_key': key,
        }
        cache[key] = {**entry, '_mtime': mtime}
        result[key] = entry
```

---

## 第 4 步：修改 `ui/main_window.py`

一处修改，在 `_on_file_selected` 中（约第 270 行），`lif_idx` 分支后添加：

```python
xxx_idx = entry.get('xxx_image_index', -1)
if xxx_idx >= 0:
    from core.xxx_reader import read_pixels as read_xxx_px
    real_fp = entry.get('filepath', filepath)
    raw_data = read_xxx_px(real_fp, image_index=xxx_idx)
```

同时在批量导出 `_on_batch_export` 中添加对应导入。

---

## 第 5 步：构建配置

### build.spec（macOS）和 build_windows.spec（Windows）

```python
hiddenimports=[..., 'core.xxx_reader', '<library>', ...]
datas=[..., ('core/xxx_reader.py', 'core'), ...]
```

---

## 验证清单

- [ ] `read_metadata` 返回 list，每个元素有正确的 channel_count/names/width/height
- [ ] `read_pixels` 返回 uint16，(C, Y, X) 或 (C, Z, Y, X)
- [ ] 文件能被扫描器发现（左下角统计显示新格式计数）
- [ ] 点击文件能正常显示图像
- [ ] 导出功能正常
- [ ] 暗黑/亮色模式正常
