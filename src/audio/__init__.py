"""
Audio recording and processing module.

This module provides audio capture functionality for the STT application.
"""

from .recorder import AudioRecorder
from .vad import (
    VoiceActivityDetector,
    has_speech,
    has_speech_energy,
    has_speech_vad,
    audio_energy,
)

__all__ = [
    "AudioRecorder",
    "VoiceActivityDetector",
    "has_speech",
    "has_speech_energy",
    "has_speech_vad",
    "audio_energy",
]

