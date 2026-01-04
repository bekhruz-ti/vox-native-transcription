"""
Input STT - Speech-to-Text Desktop Tool

A native Windows STT tool that captures audio and inserts transcribed
text wherever the cursor is positioned.

Features:
- Global hotkey activation (default: Ctrl+Shift+Space)
- Real-time transcription with text injection
- Automatic silence detection
- Windows 11-style toast notifications
- System tray integration
"""

__version__ = "0.1.0"

from .audio import AudioRecorder
from .providers import GenAIProvider, OpenAIProvider

# Core components
from .core import (
    HotkeyManager,
    RecordingSession,
    SessionState,
    SilenceDetector,
    FocusDetector,
    TextInjector,
)

# Configuration
from .config import Settings

__all__ = [
    # Audio
    "AudioRecorder",
    # Providers
    "GenAIProvider", 
    "OpenAIProvider",
    # Core
    "HotkeyManager",
    "RecordingSession",
    "SessionState",
    "SilenceDetector",
    "FocusDetector",
    "TextInjector",
    # Config
    "Settings",
]

