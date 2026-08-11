"""
Core module for Input-STT application.

Contains the main business logic components:
- HotkeyManager: Global keyboard shortcut handling
- RecordingSession: Recording lifecycle orchestration
- SilenceDetector: Audio silence detection
- TextInjector: Keyboard simulation for text input
"""

from .hotkey_manager import HotkeyManager
from .silence_detector import SilenceDetector
from .text_injector import TextInjector
from .session import RecordingSession, SessionState

__all__ = [
    "HotkeyManager",
    "RecordingSession",
    "SessionState",
    "SilenceDetector",
    "TextInjector",
]


