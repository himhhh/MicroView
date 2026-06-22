"""
File scanner — recursively scans a folder for ND2 files, extracts metadata,
and maintains a cached index for fast subsequent launches.
"""

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .nd2_reader import read_metadata, ND2Metadata


# Cache location
CACHE_DIR = Path.home() / "Library" / "Application Support" / "ND2Browser"
CACHE_FILE = CACHE_DIR / "file_index.json"


def _ensure_cache_dir() -> None:
    """Create the cache directory if it doesn't exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_cache() -> dict:
    """Load cached file index from disk. Returns empty dict if no cache exists."""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception:
        return {}


def save_cache(cache: dict) -> None:
    """Save the file index cache to disk."""
    _ensure_cache_dir()
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"Warning: Could not save cache: {e}")


def scan_folder(
    root_path: str | Path,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    use_cache: bool = True,
) -> dict[str, dict]:
    """
    Recursively scan a folder for *.nd2 files and extract metadata.

    Args:
        root_path: Root folder to scan.
        progress_callback: Called with (current, total, filename) during scan.
        use_cache: If True, use cached metadata for files that haven't changed.

    Returns:
        A dict mapping filepath (str) to a dict with keys:
        - filename, filepath, date (iso str), channel_count,
          channel_names, width, height, z_slices
    """
    root = Path(root_path).expanduser().resolve()
    cache = load_cache() if use_cache else {}

    # Find all ND2 files
    raw_nd2 = sorted(root.rglob("*.nd2"), key=lambda p: p.name.lower())
    raw_upper = sorted(root.rglob("*.ND2"), key=lambda p: p.name.lower())

    # Filter out macOS resource-fork files (._*) and hidden files
    nd2_files = []
    seen = set()
    for f in raw_nd2 + raw_upper:
        # Skip macOS resource fork files and hidden files
        if f.name.startswith('._') or f.name.startswith('.'):
            continue
        # Skip files inside hidden directories
        parts = f.parts
        if any(p.startswith('._') or (p.startswith('.') and p != '..') for p in parts[:-1]):
            continue
        if f not in seen:
            seen.add(f)
            nd2_files.append(f)

    # Re-sort
    nd2_files.sort(key=lambda p: p.name.lower())

    # Also find LIF files
    lif_raw = sorted(root.rglob("*.lif"), key=lambda p: p.name.lower())
    lif_up = sorted(root.rglob("*.LIF"), key=lambda p: p.name.lower())
    lif_files = [f for f in lif_raw + lif_up if not f.name.startswith('._')]
    lif_files = sorted(set(lif_files), key=lambda p: p.name.lower())

    all_files = list(nd2_files) + list(lif_files)
    total = len(all_files)
    result = {}

    for i, filepath in enumerate(all_files):
        key = str(filepath)
        if progress_callback:
            progress_callback(i + 1, total, filepath.name)

        # Check cache — use file modification time as version
        try:
            mtime = filepath.stat().st_mtime
        except OSError:
            continue

        cached_entry = cache.get(key)
        if cached_entry and cached_entry.get('_mtime') == mtime:
            # Cache hit — reuse
            entry = dict(cached_entry)
            entry.pop('_mtime', None)
            result[key] = entry
            continue

        # Read metadata (ND2 or LIF) — try/except per file
        try:
            suffix = filepath.suffix.lower()
            if suffix == '.lif':
                from .lif_reader import read_lif_metadata
                lif_metas = read_lif_metadata(filepath)
                if not lif_metas:
                    print(f"Warning: No images found in LIF file: {filepath.name}")
                for j, lif_meta in enumerate(lif_metas):
                    key = f"{filepath}:::{lif_meta.image_name}"
                    entry = {
                        'filename': f"{filepath.name} [{lif_meta.image_name}]",
                        'filepath': str(filepath), 'lif_image_index': j,
                        'date': lif_meta.acquisition_date.isoformat() if lif_meta.acquisition_date else None,
                        'channel_count': lif_meta.channel_count,
                        'channel_names': lif_meta.channel_names,
                        'width': lif_meta.width, 'height': lif_meta.height,
                        'z_slices': lif_meta.z_slices, 'pixel_size_um': None, '_idx_key': key,
                    }
                    cache[key] = {**entry, '_mtime': mtime}
                    result[key] = entry
            else:
                meta = read_metadata(filepath)
                if meta is None:
                    continue

                entry = {
            'filename': meta.filename,
            'filepath': key,
            'date': meta.acquisition_date.isoformat() if meta.acquisition_date else None,
            'channel_count': meta.channel_count,
            'channel_names': meta.channel_names,
            'width': meta.width,
            'height': meta.height,
            'z_slices': meta.z_slices,
            'pixel_size_um': meta.pixel_size_um,
            'lif_image_index': -1,
            '_idx_key': key,
        }

            # Store in cache
            cache[key] = {**entry, '_mtime': mtime}
            result[key] = entry
        except Exception as e:
            print(f"Warning: Skipping {filepath.name}: {e}")
            continue

    # Save updated cache
    if use_cache:
        save_cache(cache)

    return result


def group_by_date(
    file_index: dict[str, dict],
) -> dict[str, list[dict]]:
    """
    Group files by year-month for sidebar display.

    Returns a dict like:
        {"2026-06": [entry1, entry2], "2026-05": [entry3]}
    Sorted newest-first.
    """
    groups = defaultdict(list)
    for entry in file_index.values():
        date_str = entry.get('date')
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str)
                group_key = dt.strftime("%Y-%m")
            except (ValueError, TypeError):
                group_key = "日期未知"
        else:
            group_key = "日期未知"
        groups[group_key].append(entry)

    # Sort groups newest first
    sorted_groups = dict(
        sorted(groups.items(), key=lambda x: x[0], reverse=True)
    )

    # Sort entries within each group by date (newest first)
    for key in sorted_groups:
        sorted_groups[key].sort(
            key=lambda e: e.get('date', ''),
            reverse=True,
        )

    return sorted_groups



def build_folder_tree(
    file_index: dict[str, dict],
    root_path: str | Path,
) -> dict:
    """Build folder tree. ND2 -> files[], LIF -> lif_containers{} grouped by .lif file."""
    from pathlib import Path
    root = Path(root_path).resolve()
    def _node(n, p):
        return {"name": n, "path": p, "folders": {}, "files": [], "lif_containers": {}}
    tree = _node(root.name, str(root))

    for filepath_str, entry in file_index.items():
        real_path = entry.get("filepath", filepath_str)
        fp = Path(real_path)
        is_lif = entry.get("lif_image_index", -1) >= 0
        try:
            rel = fp.relative_to(root)
        except ValueError:
            _place(tree, entry, is_lif)
            continue
        parts = rel.parts
        cur = tree
        for i, part in enumerate(parts[:-1]):
            if part not in cur["folders"]:
                cur["folders"][part] = _node(part, str(root / Path(*parts[:i+1])))
            cur = cur["folders"][part]
        _place(cur, entry, is_lif)
    return tree


def _place(node, entry, is_lif):
    """Add entry to node: LIF -> lif_containers, ND2 -> files."""
    if is_lif:
        lp = entry.get("filepath", "")
        ln = Path(lp).name
        if lp not in node["lif_containers"]:
            node["lif_containers"][lp] = {"name": ln, "path": lp, "images": []}
        node["lif_containers"][lp]["images"].append(entry)
        node["lif_containers"][lp]["images"].sort(key=lambda e: e.get("lif_image_index", 0))
    else:
        node["files"].append(entry)
