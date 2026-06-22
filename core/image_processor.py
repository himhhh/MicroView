"""
Image processor — channel extraction, LUT pseudo-coloring,
merge compositing, and brightness/contrast adjustments.
"""

import numpy as np
from typing import Optional


# ── LUT / Channel colors ───────────────────────────────────────

# Default channel colors (by index)
_CHANNEL_COLORS = [
    (0, 0, 255),     # Ch0 → Blue (DAPI/nucleus)
    (0, 255, 0),     # Ch1 → Green (FITC/GFP)
    (255, 0, 0),     # Ch2 → Red (TxRed/mCherry)
    (0, 255, 255),   # Ch3 → Cyan
    (255, 0, 255),   # Ch4 → Magenta
    (255, 255, 0),   # Ch5 → Yellow
]

_CHANNEL_HEX = ["#3498DB", "#2ECC71", "#E74C3C", "#00BCD4", "#E91E63", "#FFC107"]


_COLOR_NAME_MAP = {
    "蓝色": (0, 0, 255), "绿色": (0, 255, 0), "红色": (255, 0, 0),
    "青色": (0, 255, 255), "品红": (255, 0, 255), "黄色": (255, 255, 0),
}

# Direct mapping from LIF LUTName (English colour names in ChannelDescription)
_LUT_NAME_MAP = {
    "Blue": (0, 0, 255),       "Green": (0, 255, 0),
    "Red": (255, 0, 0),        "Cyan": (0, 255, 255),
    "Magenta": (255, 0, 255),  "Yellow": (255, 255, 0),
    "Gray": (128, 128, 128),   "Grey": (128, 128, 128),
}


def _load_user_nd2_colors():
    """Load user-defined ND2 name→color mapping from QSettings."""
    try:
        from PySide6.QtCore import QSettings
        import json
        raw = QSettings("MicroView", "MicroView").value("nd2_channel_colors")
        if raw:
            return {k: _COLOR_NAME_MAP.get(v, (0, 0, 255))
                    for k, v in json.loads(raw).items()}
    except Exception:
        pass
    return {}


def _load_user_lif_colors():
    """Load user-defined LIF name→color mapping from QSettings (dict format).

    Returns dict {channel_name: (R,G,B) tuple}.
    Old list-based format (pre-V3) is silently ignored — the index→color
    mapping cannot be recovered without channel names from that era."""
    try:
        from PySide6.QtCore import QSettings
        import json
        raw = QSettings("MicroView", "MicroView").value("lif_channel_colors")
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {k: _COLOR_NAME_MAP.get(v, (0, 0, 255))
                        for k, v in parsed.items()}
            # Old list format — return empty, LUTName auto-detection takes over
    except Exception:
        pass
    return {}


def _guess_color(name: str, index: int) -> tuple:
    """Assign channel color with priority:
    1. User ND2 name mapping   2. User LIF name mapping
    3. Built-in name heuristics 4. LUTName auto-detection
    5. Index fallback (_CHANNEL_COLORS)
    """
    n = name.lower()

    # 1. User-defined ND2 name mapping (case-insensitive substring)
    nd2_map = _load_user_nd2_colors()
    for pattern, color in nd2_map.items():
        if pattern.lower() in n:
            return color

    # 2. User-defined LIF name mapping (exact match, case-insensitive)
    #    Must come before built-in heuristics so user overrides win.
    lif_map = _load_user_lif_colors()
    if lif_map:
        for stored_name, color in lif_map.items():
            if stored_name.lower() == n:
                return color

    # 3. Built-in name heuristics
    if any(k in n for k in ['dapi', 'hoechst', 'bf', 'bright', '405', 'blue']):
        return nd2_map.get('dapi', (0, 0, 255))
    if any(k in n for k in ['fitc', 'gfp', 'green', '488', 'egfp', 'alexafluor488']):
        return nd2_map.get('fitc', (0, 255, 0))
    if any(k in n for k in ['txred', 'mcherry', 'rfp', 'red', '594', 'cy3',
                             'alexafluor594', 'alexa 594', 'tdtomato', 'dsred']):
        return nd2_map.get('txred', (255, 0, 0))
    if any(k in n for k in ['cy5', 'cfp', 'cyan']):
        return nd2_map.get('cy5', (0, 255, 255))
    if any(k in n for k in ['magenta', 'farred']):
        return nd2_map.get('magenta', (255, 0, 255))

    # 4. LUTName direct mapping (from LIF ChannelDescription metadata,
    #    e.g. "Green" / "Red" / "Blue").
    lut_color = _LUT_NAME_MAP.get(name)
    if lut_color is not None:
        return lut_color

    # 5. Index fallback — built-in defaults for unnamed channels
    return _CHANNEL_COLORS[index % len(_CHANNEL_COLORS)]


def get_channel_color(name: str, index: int) -> tuple:
    """Public: get (R, G, B) color for a channel."""
    return _guess_color(name, index)


def get_channel_hex(name: str, index: int) -> str:
    """Public: get hex color for a channel."""
    c = _guess_color(name, index)
    return f"#{c[0]:02X}{c[1]:02X}{c[2]:02X}"


def _detect_nch(data: np.ndarray) -> int:
    ndim = data.ndim
    if ndim <= 2:
        return 1
    if ndim == 3:
        return data.shape[0] if data.shape[0] <= 100 else 1
    if ndim == 4:
        return data.shape[0] if data.shape[0] <= 100 else 1
    return data.shape[0] if data.shape[0] <= 100 else 1


def _get_ch(data: np.ndarray, ch: int, z: int) -> np.ndarray:
    """Extract a 2-D channel slice from N-D array."""
    ndim = data.ndim
    if ndim == 2:
        return data
    elif ndim == 3:
        if data.shape[0] <= 100:
            return data[min(ch, data.shape[0] - 1)]
        return data
    elif ndim == 4:
        c = min(ch, data.shape[0] - 1)
        zz = min(z, data.shape[1] - 1)
        return data[c, zz]
    elif ndim >= 5:
        c = min(ch, data.shape[0] - 1)
        zz = min(z, data.shape[1] - 1) if data.shape[1] > 1 else 0
        idx = (c, zz) + (0,) * (ndim - 4)
        return data[idx]
    return data


# ── Core functions ─────────────────────────────────────────────

def normalize_to_8bit(data: np.ndarray, auto: bool = True,
                      p_lo: float = 0.1, p_hi: float = 99.9) -> np.ndarray:
    """Percentile-stretch to 0–255 uint8."""
    d = data.astype(np.float64)
    if auto:
        lo, hi = np.percentile(d, (p_lo, p_hi))
        if hi > lo:
            d = (d - lo) / (hi - lo)
        else:
            d = np.zeros_like(d)
    else:
        mn, mx = d.min(), d.max()
        if mx > mn:
            d = (d - mn) / (mx - mn)
        else:
            d = np.zeros_like(d)
    return np.clip(d * 255, 0, 255).astype(np.uint8)


def apply_bc(img: np.ndarray, brightness: float = 0.0,
             contrast: float = 1.0) -> np.ndarray:
    """Brightness (-100..+100) & contrast (0.1..3.0) on uint8.

    DEPRECATED — kept for backward compat. Use apply_levels() instead.
    """
    f = img.astype(np.float64)
    m = f.mean()
    f = m + contrast * (f - m) + brightness
    return np.clip(f, 0, 255).astype(np.uint8)


def apply_levels(img: np.ndarray, black_point: float = 0.0,
                 white_point: float = 255.0) -> np.ndarray:
    """Linear level stretch: black_point maps to 0, white_point maps to 255.

    black_point, white_point are in input pixel space (0–255 for uint8 data).
    Values below black_point clip to 0; above white_point clip to 255.
    """
    if white_point <= black_point:
        return img
    f = img.astype(np.float64)
    f = (f - black_point) / (white_point - black_point) * 255.0
    return np.clip(f, 0, 255).astype(np.uint8)


def apply_lut(gray: np.ndarray, color: tuple) -> np.ndarray:
    """Color a 2-D uint8 grayscale image with an RGB LUT."""
    h, w = gray.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    f = gray.astype(np.float32) / 255.0
    for c in range(3):
        rgb[:, :, c] = (f * color[c]).astype(np.uint8)
    return rgb


# ── Public API ─────────────────────────────────────────────────

def get_channel_display(
    raw: np.ndarray, channel: int = 0, z: int = 0,
    brightness: float = 0.0, contrast: float = 1.0,
    black_point: float = 0.0, white_point: float = 255.0,
    colored: bool = True,
    channel_name: str = "",
) -> np.ndarray:
    """Return display-ready single-channel image (gray or LUT-colored).

    Prefer ``black_point``/``white_point`` for levels adjustment.
    ``brightness``/``contrast`` are deprecated but kept for backward compat.
    """
    ch2d = _get_ch(raw, channel, z)
    gray = normalize_to_8bit(ch2d)
    # Chain: levels first (LUT), then BC fine-tune
    if black_point != 0.0 or white_point != 255.0:
        gray = apply_levels(gray, black_point, white_point)
    gray = apply_bc(gray, brightness, contrast)
    if colored:
        color = _guess_color(channel_name, channel)
        return apply_lut(gray, color)
    return gray


def get_merge_display(
    raw: np.ndarray, z: int = 0,
    brightness: float = 0.0, contrast: float = 1.0,
    ch_brightness: Optional[list] = None,
    ch_contrast: Optional[list] = None,
    ch_black: Optional[list] = None,
    ch_white: Optional[list] = None,
    channel_names: Optional[list] = None,
) -> np.ndarray:
    """
    Create an RGB merge using per-channel LUT colors (matches preview).

    Each channel's LUT color (via _guess_color) determines which RGB
    component(s) it contributes to, same as _do_render() in main_window.
    """
    nch = _detect_nch(raw)
    h, w = raw.shape[-2], raw.shape[-1]
    rgb = np.zeros((h, w, 3), dtype=np.float64)

    use_levels = (ch_black is not None or ch_white is not None)
    # Pad per-channel lists to nch (different files may have different channel counts)
    def _pad(lst, default, target_len):
        if lst is None:
            return [default] * target_len
        result = list(lst)
        while len(result) < target_len:
            result.append(default)
        return result

    cb = _pad(ch_brightness, brightness, nch)
    cc = _pad(ch_contrast, contrast, nch)
    cblk = _pad(ch_black, 0.0, nch)
    cwht = _pad(ch_white, 255.0, nch)
    names = channel_names or [f"Ch{i}" for i in range(nch)]

    def _adjust(ch_data, i):
        if use_levels:
            return apply_levels(ch_data, cblk[i], cwht[i])
        return apply_bc(ch_data, cb[i], cc[i])

    for i in range(min(nch, 3)):
        ci = normalize_to_8bit(_get_ch(raw, i, z))
        ci_f = _adjust(ci, i).astype(np.float64)
        color = _guess_color(names[i] if i < len(names) else "", i)
        # Channel contributes to RGB components based on its LUT color
        for comp in range(3):
            if color[comp] > 0:
                rgb[:, :, comp] = np.maximum(rgb[:, :, comp],
                    ci_f * (color[comp] / 255.0))

    # Handle 4+ channels: same color-based blending
    for i in range(3, nch):
        ci = normalize_to_8bit(_get_ch(raw, i, z))
        ci_f = _adjust(ci, i).astype(np.float64)
        color = _guess_color(names[i] if i < len(names) else "", i)
        for comp in range(3):
            if color[comp] > 0:
                rgb[:, :, comp] = np.maximum(rgb[:, :, comp],
                    ci_f * (color[comp] / 255.0))

    return np.clip(rgb, 0, 255).astype(np.uint8)


def get_all_channels(
    raw: np.ndarray, z: int = 0,
    brightness: float = 0.0, contrast: float = 1.0,
    channel_names: list = None,
) -> list[np.ndarray]:
    """Return LUT-colored single-channel images for all channels."""
    nch = _detect_nch(raw)
    names = channel_names or [f"Ch{i}" for i in range(nch)]
    return [
        get_channel_display(raw, ch, z, brightness, contrast, colored=True,
                            channel_name=names[ch] if ch < len(names) else "")
        for ch in range(nch)
    ]


# Backward compat
extract_channel_display = get_channel_display
create_merge_rgb = get_merge_display
apply_adjustments_8bit = apply_bc
