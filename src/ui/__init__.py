"""
UI module for Input-STT application.

Contains PySide6-based UI components:
- STTApplication: Main application class
- SystemTray: System tray icon and menu
- MicIndicator: Recording indicator overlay
- ToastNotification: Transcription result toast
- SettingsDialog: Settings configuration
"""

from .app import STTApplication
from .system_tray import SystemTray

__all__ = [
    "STTApplication",
    "SystemTray",
]


