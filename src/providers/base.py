"""
Abstract base class for GenAI providers.

This module defines the interface that all GenAI providers must implement
for speech-to-text transcription functionality.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Generator, List, Optional

from pydantic import BaseModel


class TranscriptionOutputType(str, Enum):
    """Type of real-time transcription output."""
    INCREMENTAL = "incremental"  # Returns only the latest chunk
    CUMULATIVE = "cumulative"    # Returns entire transcript up to this point


class TranscriptionStatus(str, Enum):
    """Status of the transcription."""
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


class RealtimeTranscriptionOutput(BaseModel):
    """
    Standardized output for real-time transcription.
    
    Handles both incremental (chunk-only) and cumulative (full transcript) 
    output types from different providers.
    
    Attributes:
        type: Whether the output is incremental or cumulative.
        chunks: List of all transcribed chunks so far.
        latest_transcription: Full transcript up to this point (for both
                              cumulative and incremental types).
        status: Current status of the transcription.
        final_transcription: Only populated when status is COMPLETE.
    """
    type: TranscriptionOutputType
    chunks: List[str] = []
    latest_transcription: str = ""
    status: TranscriptionStatus
    final_transcription: str = ""


class GenAIProvider(ABC):
    """
    Abstract base class for GenAI transcription providers.
    
    All STT providers (OpenAI, Google, Azure, local Whisper, etc.) must
    inherit from this class and implement the required transcription methods.
    """
    
    @abstractmethod
    def transcribe_batch(
        self,
        audio_path: str,
        language: Optional[str] = None
    ) -> str:
        """
        Transcribe an audio file to text (non-streaming).
        
        This method processes the entire audio file and returns the complete
        transcription as a single string.
        
        Args:
            audio_path: Path to the audio file to transcribe.
                       Supported formats depend on the provider implementation.
            language: Optional language code (e.g., 'en', 'es', 'fr').
                     If None, the provider will auto-detect the language.
        
        Returns:
            The complete transcription text.
        
        Raises:
            FileNotFoundError: If the audio file does not exist.
            ValueError: If the audio format is not supported.
            TranscriptionError: If transcription fails.
        """
        pass
    
    @abstractmethod
    def transcribe_realtime(
        self,
        audio_stream: Generator[bytes, None, None],
        language: Optional[str] = None
    ) -> Generator["RealtimeTranscriptionOutput", None, None]:
        """
        Transcribe audio in real-time with streaming output.
        
        This method accepts a generator that yields audio chunks and returns
        a generator that yields RealtimeTranscriptionOutput objects as 
        transcription progresses.
        
        Args:
            audio_stream: A generator that yields audio data chunks as bytes.
                         Audio should be in PCM16 format (16kHz, mono, 16-bit).
            language: Optional language code (e.g., 'en', 'es', 'fr').
                     If None, the provider will auto-detect the language.
        
        Yields:
            RealtimeTranscriptionOutput objects containing transcription data,
            status, and type information.
        
        Raises:
            ConnectionError: If connection to the transcription service fails.
            ValueError: If the audio format is invalid.
            TranscriptionError: If transcription fails.
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the provider is properly configured and available.
        
        Returns:
            True if the provider can be used for transcription, False otherwise.
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the name of this provider.
        
        Returns:
            A human-readable name for this provider (e.g., "OpenAI Whisper").
        """
        pass


class TranscriptionError(Exception):
    """
    Exception raised when transcription fails.
    
    Attributes:
        message: Human-readable error message.
        provider: Name of the provider that raised the error.
        original_error: The original exception, if any.
    """
    
    def __init__(
        self,
        message: str,
        provider: str = "Unknown",
        original_error: Optional[Exception] = None
    ):
        self.message = message
        self.provider = provider
        self.original_error = original_error
        super().__init__(f"[{provider}] {message}")

