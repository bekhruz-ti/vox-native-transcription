"""
GenAI Providers for Speech-to-Text transcription.

This module contains abstract base classes and concrete implementations
for various STT providers (OpenAI, ElevenLabs, etc.)
"""

from .base import (
    GenAIProvider,
    RealtimeTranscriptionOutput,
    TranscriptionError,
    TranscriptionOutputType,
    TranscriptionStatus,
)
from .openai_provider import OpenAIProvider
from .elevenlabs_provider import ElevenLabsProvider

__all__ = [
    "GenAIProvider",
    "RealtimeTranscriptionOutput",
    "TranscriptionError",
    "TranscriptionOutputType",
    "TranscriptionStatus",
    "OpenAIProvider",
    "ElevenLabsProvider",
]

