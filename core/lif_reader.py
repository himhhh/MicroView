"""Leica LIF file reader — wraps `readlif` library."""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import numpy as np

@dataclass
class LIFMetadata:
    filepath: Path
    filename: str
    image_name: str
    acquisition_date: Optional[datetime] = None
    channel_count: int = 1
    channel_names: list = field(default_factory=list)
    width: int = 0
    height: int = 0
    z_slices: int = 1


def read_lif_metadata(filepath: str | Path) -> list[LIFMetadata]:
    try:
        from readlif.reader import LifFile
    except ImportError:
        raise ImportError("readlif is required. pip install readlif")
    filepath = Path(filepath)
    results = []
    try:
        lif = LifFile(str(filepath))

        # Extract LUTName from all ChannelDescription elements in the LIF XML.
        # These reflect the color assigned by the microscope operator during
        # acquisition (e.g. "Blue", "Green", "Red").
        all_lut_names = []
        for elem in lif.xml_root.iter():
            if 'ChannelDescription' in elem.tag:
                all_lut_names.append(elem.attrib.get('LUTName', ''))

        lut_idx = 0
        for img in lif.get_iter_image():
            try:
                dims = img.dims
                w = dims.x if hasattr(dims, 'x') else 0
                h = dims.y if hasattr(dims, 'y') else 0
                nz = dims.z if hasattr(dims, 'z') else 1
                nch = getattr(img, 'channels', 1) or 1

                # Use LUTName if present, fall back to generic Ch{i+1}
                img_lut_names = all_lut_names[lut_idx:lut_idx + nch]
                lut_idx += nch
                ch_names = [
                    name if name else f"Ch{i+1}"
                    for i, name in enumerate(img_lut_names)
                ]
                # Date: just use file mtime, avoid fragile metadata parsing
                date = datetime.fromtimestamp(filepath.stat().st_mtime)
                meta = LIFMetadata(
                    filepath=filepath, filename=filepath.name,
                    image_name=getattr(img, 'name', f'Image_{len(results)}'),
                    acquisition_date=date, channel_count=nch,
                    channel_names=ch_names, width=w, height=h, z_slices=nz,
                )
                results.append(meta)
            except Exception as e:
                print(f"Warning: Could not read image in LIF {filepath}: {e}")
                continue
    except Exception as e:
        print(f"Warning: Could not open LIF file {filepath}: {e}")
    return results


def read_lif_pixels(filepath: str | Path, image_index: int = 0) -> np.ndarray:
    try:
        from readlif.reader import LifFile
    except ImportError:
        raise ImportError("readlif is required.")
    filepath = Path(filepath)
    lif = LifFile(str(filepath))
    images = list(lif.get_iter_image())
    if image_index >= len(images):
        raise IndexError(f"Image {image_index} out of range ({len(images)} images)")
    img = images[image_index]
    nch = getattr(img, 'channels', 1) or 1
    nz = img.dims.z if hasattr(img.dims, 'z') else 1
    frames = []
    for c in range(nch):
        ch_frames = []
        for z in range(nz):
            try:
                ch_frames.append(np.array(img.get_frame(z=z, t=0, c=c)))
            except Exception:
                try:
                    ch_frames.append(np.array(img.get_frame(c=c)))
                except Exception:
                    ch_frames.append(np.zeros((1, 1), dtype=np.uint16))
        ch_data = np.stack(ch_frames) if len(ch_frames) > 1 else ch_frames[0]
        frames.append(ch_data)
    if len(frames) > 1:
        return np.stack(frames)
    return frames[0]
