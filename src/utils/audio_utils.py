"""
Audio utility functions for processing and converting audio data.

This module provides helpers for handling audio input in the correct
format for the OpenAI Realtime API (PCM16, 16kHz, mono).
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np


class AudioFormat(Enum):
    """Supported audio formats."""
    PCM16 = "pcm16"
    WAV = "wav"
    MP3 = "mp3"
    WEBM = "webm"
    M4A = "m4a"


@dataclass
class AudioConfig:
    """Audio configuration for recording and processing."""
    sample_rate: int = 16000  # 16kHz for OpenAI Realtime API
    channels: int = 1         # Mono
    dtype: np.dtype = np.int16  # 16-bit PCM
    chunk_duration_ms: int = 100  # Chunk duration in milliseconds
    
    @property
    def chunk_size(self) -> int:
        """Calculate the number of samples per chunk."""
        return int(self.sample_rate * self.chunk_duration_ms / 1000)
    
    @property
    def chunk_bytes(self) -> int:
        """Calculate the number of bytes per chunk."""
        return self.chunk_size * self.channels * 2  # 2 bytes per sample for int16


# Default configuration for OpenAI Realtime API
DEFAULT_AUDIO_CONFIG = AudioConfig()


def convert_to_pcm16(
    audio_data: np.ndarray,
    source_sample_rate: int,
    target_sample_rate: int = 16000
) -> bytes:
    """
    Convert audio data to PCM16 format suitable for OpenAI Realtime API.
    
    Args:
        audio_data: NumPy array of audio samples.
        source_sample_rate: Original sample rate of the audio.
        target_sample_rate: Target sample rate (default: 16000 for OpenAI).
    
    Returns:
        PCM16 encoded audio as bytes.
    """
    # Resample if necessary
    if source_sample_rate != target_sample_rate:
        # Simple resampling using linear interpolation
        duration = len(audio_data) / source_sample_rate
        target_length = int(duration * target_sample_rate)
        audio_data = np.interp(
            np.linspace(0, len(audio_data), target_length),
            np.arange(len(audio_data)),
            audio_data
        )
    
    # Convert to mono if stereo
    if len(audio_data.shape) > 1 and audio_data.shape[1] > 1:
        audio_data = np.mean(audio_data, axis=1)
    
    # Normalize to int16 range
    if audio_data.dtype == np.float32 or audio_data.dtype == np.float64:
        audio_data = (audio_data * 32767).astype(np.int16)
    elif audio_data.dtype != np.int16:
        audio_data = audio_data.astype(np.int16)
    
    return audio_data.tobytes()


def validate_audio_format(file_path: str) -> tuple[bool, Optional[str]]:
    """
    Validate that an audio file is in a supported format.
    
    Args:
        file_path: Path to the audio file.
    
    Returns:
        Tuple of (is_valid, error_message).
        If valid, error_message is None.
    """
    path = Path(file_path)
    
    if not path.exists():
        return False, f"File not found: {file_path}"
    
    if not path.is_file():
        return False, f"Path is not a file: {file_path}"
    
    supported_extensions = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}
    
    if path.suffix.lower() not in supported_extensions:
        return False, (
            f"Unsupported format: {path.suffix}. "
            f"Supported: {', '.join(supported_extensions)}"
        )
    
    return True, None


def get_audio_duration(file_path: str) -> Optional[float]:
    """
    Get the duration of an audio file in seconds.
    
    Note: This is a basic implementation. For accurate duration,
    consider using a library like pydub or librosa.
    
    Args:
        file_path: Path to the audio file.
    
    Returns:
        Duration in seconds, or None if unable to determine.
    """
    path = Path(file_path)
    
    if not path.exists():
        return None
    
    # For WAV files, we can calculate duration from file size
    if path.suffix.lower() == ".wav":
        try:
            # Read WAV header
            with open(file_path, "rb") as f:
                # Skip RIFF header
                f.read(4)  # "RIFF"
                f.read(4)  # file size
                f.read(4)  # "WAVE"
                
                # Find fmt chunk
                while True:
                    chunk_id = f.read(4)
                    if not chunk_id:
                        return None
                    chunk_size = int.from_bytes(f.read(4), "little")
                    
                    if chunk_id == b"fmt ":
                        f.read(2)  # audio format
                        channels = int.from_bytes(f.read(2), "little")
                        sample_rate = int.from_bytes(f.read(4), "little")
                        byte_rate = int.from_bytes(f.read(4), "little")
                        f.read(chunk_size - 14)  # skip rest of fmt chunk
                    elif chunk_id == b"data":
                        data_size = chunk_size
                        duration = data_size / byte_rate
                        return duration
                    else:
                        f.read(chunk_size)  # skip unknown chunk
                        
        except Exception:
            return None
    
    # For other formats, return None (would need additional libraries)
    return None


def create_audio_chunk_generator(
    audio_data: bytes,
    chunk_size: int = 3200  # ~100ms at 16kHz
):
    """
    Create a generator that yields audio chunks.
    
    Args:
        audio_data: Complete audio data as bytes.
        chunk_size: Size of each chunk in bytes.
    
    Yields:
        Audio chunks of the specified size.
    """
    for i in range(0, len(audio_data), chunk_size):
        yield audio_data[i:i + chunk_size]

