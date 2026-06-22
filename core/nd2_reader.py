"""
ND2 file reader — wraps the `nd2` library to extract metadata and pixel data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class ND2Metadata:
    """Structured metadata extracted from an ND2 file."""
    filepath: Path
    filename: str
    acquisition_date: Optional[datetime] = None
    channel_count: int = 1
    channel_names: list = field(default_factory=list)
    width: int = 0
    height: int = 0
    z_slices: int = 1
    dtype: str = "uint16"
    pixel_size_um: Optional[float] = None


def read_metadata(filepath: str | Path) -> Optional[ND2Metadata]:
    """
    Open an ND2 file and extract metadata without loading full pixel data.
    Returns None if the file cannot be read.
    """
    try:
        import nd2
    except ImportError:
        raise ImportError("nd2 library is required. Install with: pip install nd2")

    filepath = Path(filepath)
    try:
        with nd2.ND2File(str(filepath)) as f:
            sizes = f.sizes
            meta = ND2Metadata(
                filepath=filepath,
                filename=filepath.name,
                channel_count=sizes.get('C', 1),
                width=sizes.get('X', 0),
                height=sizes.get('Y', 0),
                z_slices=sizes.get('Z', 1),
            )

            # Try to get acquisition date
            try:
                meta.acquisition_date = f.acquisition_date()
            except Exception:
                pass

            # Fall back to file modification time
            if meta.acquisition_date is None:
                ts = filepath.stat().st_mtime
                meta.acquisition_date = datetime.fromtimestamp(ts)

            # Channel names
            try:
                raw_channels = f.metadata.channels
                if raw_channels:
                    meta.channel_names = []
                    for c in raw_channels:
                        try:
                            name = c.channel.name if hasattr(c, 'channel') and c.channel else f"Ch{len(meta.channel_names)+1}"
                        except Exception:
                            name = f"Ch{len(meta.channel_names)+1}"
                        meta.channel_names.append(name)
            except Exception:
                meta.channel_names = [f"Channel {i+1}" for i in range(meta.channel_count)]

            # Pixel size
            try:
                cal = f.metadata.calibration
                if cal and hasattr(cal, 'x'):
                    meta.pixel_size_um = cal.x
            except Exception:
                pass

            return meta

    except Exception as e:
        print(f"Warning: Could not read metadata from {filepath}: {e}")
        return None


def read_pixels(
    filepath: str | Path,
    channel: int | None = None,
    z_slice: int = 0,
    timepoint: int = 0,
) -> np.ndarray:
    """
    Read pixel data from an ND2 file.
    Returns the full multi-dimensional numpy array.
    """
    try:
        import nd2
    except ImportError:
        raise ImportError("nd2 library is required.")

    filepath = Path(filepath)
    with nd2.ND2File(str(filepath)) as f:
        data = f.asarray()

    return data


def get_2d_slice(
    data: np.ndarray,
    channel: int = 0,
    z_slice: int = 0,
    timepoint: int = 0,
    channel_count: int = 1,
) -> np.ndarray:
    """
    Extract a 2-D slice from an N-D ND2 array.

    ND2 arrays typically follow (C, Y, X) or (C, Z, Y, X) ordering.
    """
    ndim = data.ndim

    if ndim == 2:
        # Already 2-D (single channel, Y, X)
        return data
    elif ndim == 3:
        # Could be (C, Y, X) or (Z, Y, X)
        # If channel_count > 1, first dim is channels
        if data.shape[0] <= 100 and channel_count > 1:
            ch = min(channel, data.shape[0] - 1)
            return data[ch]
        elif data.shape[0] <= 100:
            # Probably Z-stack with single channel
            z = min(z_slice, data.shape[0] - 1)
            return data[z]
        else:
            # Large first dim — probably Y, X with very tall image
            return data
    elif ndim == 4:
        # Assume (C, Z, Y, X) or (C, T, Y, X)
        ch = min(channel, data.shape[0] - 1)
        z = min(z_slice, data.shape[1] - 1)
        return data[ch, z]
    elif ndim >= 5:
        # (C, Z, T, Y, X) or similar
        ch = min(channel, data.shape[0] - 1)
        z = min(z_slice, data.shape[1] - 1) if data.shape[1] > 1 else 0
        t = min(timepoint, data.shape[2] - 1) if data.shape[2] > 1 else 0
        idx = (ch, z, t) + (0,) * (ndim - 5)
        result = data[idx]
        return result

    return data
