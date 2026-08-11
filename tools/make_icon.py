"""
Generate the Windows application icon from the system tray artwork.

Renders the same waveform mark the tray uses at every size Windows asks for
(taskbar, desktop, search results, alt-tab) and packs them into one .ico.

Run: python tools/make_icon.py
"""

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtWidgets import QApplication

from src.ui.system_tray import SystemTray, render_waveform_pixmap

# Windows picks the closest match from these; 256 is used by large desktop icons.
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
OUT = ROOT / "src" / "ui" / "resources" / "icons" / "app.ico"


def png_bytes(size: int) -> bytes:
    pixmap = render_waveform_pixmap(size, SystemTray.COLOR_IDLE, SystemTray.BG_COLOR)
    # The QByteArray must outlive the QBuffer that wraps it.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.ReadWrite)
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError(f"failed to encode {size}px frame as PNG")
    buffer.close()
    return bytes(storage)


def build_ico(frames: dict[int, bytes]) -> bytes:
    # ICONDIR, then one ICONDIRENTRY per frame, then the PNG payloads.
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)

    entries, payloads = b"", b""
    for size, data in sorted(frames.items()):
        entries += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,  # 0 encodes 256 in the ICO format
            size if size < 256 else 0,
            0,      # palette size, 0 for PNG frames
            0,      # reserved
            1,      # colour planes
            32,     # bits per pixel
            len(data),
            offset,
        )
        payloads += data
        offset += len(data)

    return header + entries + payloads


def main() -> int:
    QApplication(sys.argv)  # QPixmap needs a running Qt application
    frames = {size: png_bytes(size) for size in SIZES}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build_ico(frames))

    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")
    print("frames:", ", ".join(f"{s}px" for s in sorted(frames)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
