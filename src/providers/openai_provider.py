"""
OpenAI Provider for Speech-to-Text transcription.

This module implements the GenAIProvider interface using OpenAI's Whisper API
for both batch and chunked real-time transcription.

Includes Voice Activity Detection (VAD) to filter out background noise.
"""

import io
import os
import wave
from pathlib import Path
from typing import Generator, List, Optional

from openai import OpenAI

from .base import (
    GenAIProvider,
    RealtimeTranscriptionOutput,
    TranscriptionError,
    TranscriptionOutputType,
    TranscriptionStatus,
)

# Import VAD for noise filtering
try:
    from ..audio.vad import VoiceActivityDetector, has_speech
    VAD_AVAILABLE = True
except ImportError:
    VAD_AVAILABLE = False


class OpenAIProvider(GenAIProvider):
    """
    OpenAI-based speech-to-text provider.
    
    Uses OpenAI Whisper API for both batch and chunked real-time transcription.
    
    Attributes:
        api_key: OpenAI API key.
        whisper_model: Model to use for Whisper API (default: "whisper-1").
    """
    
    # Supported audio formats for Whisper API
    SUPPORTED_FORMATS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}
    
    # Audio configuration for PCM16
    SAMPLE_RATE = 16000  # 16kHz
    CHANNELS = 1         # Mono
    SAMPLE_WIDTH = 2     # 16-bit = 2 bytes
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        whisper_model: str = "whisper-1",
        enable_vad: bool = True,
        vad_threshold: float = 0.3,
        energy_threshold: float = 100.0
    ):
        """
        Initialize the OpenAI provider.
        
        Args:
            api_key: OpenAI API key. If None, reads from OPENAI_API_KEY env var.
            whisper_model: Model for transcription (default: "whisper-1").
            enable_vad: Enable Voice Activity Detection to filter noise (default: True).
            vad_threshold: Speech probability threshold for VAD (0-1, default: 0.3).
                           Lower = more permissive, catches more speech.
            energy_threshold: Minimum RMS energy to process audio (default: 100).
                              Filters out only very quiet/silent audio.
        
        Raises:
            ValueError: If no API key is provided or found in environment.
        """
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self._api_key or self._api_key == "your_openai_api_key_here":
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self._whisper_model = whisper_model
        self._client = OpenAI(api_key=self._api_key)
        
        # VAD configuration
        self._enable_vad = enable_vad and VAD_AVAILABLE
        self._vad_threshold = vad_threshold
        self._energy_threshold = energy_threshold
        self._vad: Optional[VoiceActivityDetector] = None
        
        # Initialize VAD if enabled
        if self._enable_vad:
            try:
                self._vad = VoiceActivityDetector(
                    energy_threshold=energy_threshold,
                    vad_threshold=vad_threshold,
                    enable_vad=True,
                    sample_rate=self.SAMPLE_RATE
                )
            except Exception as e:
                print(f"Warning: Could not initialize VAD: {e}")
                self._enable_vad = False
    
    @property
    def name(self) -> str:
        """Get the provider name."""
        return "OpenAI"
    
    def is_available(self) -> bool:
        """
        Check if the OpenAI provider is available.
        
        Performs a simple API validation check.
        
        Returns:
            True if API key is valid and service is reachable.
        """
        try:
            # Simple validation - try to list models
            self._client.models.list()
            return True
        except Exception:
            return False
    
    def transcribe_batch(
        self,
        audio_path: str,
        language: Optional[str] = None
    ) -> str:
        """
        Transcribe an audio file using OpenAI Whisper API.
        
        Args:
            audio_path: Path to the audio file.
            language: Optional ISO-639-1 language code (e.g., 'en', 'es').
        
        Returns:
            The complete transcription text.
        
        Raises:
            FileNotFoundError: If audio file doesn't exist.
            ValueError: If audio format is not supported.
            TranscriptionError: If API call fails.
        """
        path = Path(audio_path)
        
        # Validate file exists
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Validate format
        if path.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported audio format: {path.suffix}. "
                f"Supported formats: {', '.join(self.SUPPORTED_FORMATS)}"
            )
        
        try:
            with open(audio_path, "rb") as audio_file:
                # Prepare transcription parameters
                params = {
                    "model": self._whisper_model,
                    "file": audio_file,
                    "response_format": "text"
                }
                
                if language:
                    params["language"] = language
                
                # Call Whisper API
                transcription = self._client.audio.transcriptions.create(**params)
                
                return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
                
        except Exception as e:
            raise TranscriptionError(
                message=f"Failed to transcribe audio: {str(e)}",
                provider=self.name,
                original_error=e
            )
    
    def transcribe_realtime(
        self,
        audio_stream: Generator[bytes, None, None],
        language: Optional[str] = None,
        chunk_duration: float = 3.0
    ) -> Generator[RealtimeTranscriptionOutput, None, None]:
        """
        Transcribe audio in near-real-time using chunked Whisper API calls.
        
        Collects audio for `chunk_duration` seconds, then sends to Whisper API.
        Uses Voice Activity Detection (VAD) to filter out background noise.
        This provides progressive transcription with text appearing every few seconds.
        
        Args:
            audio_stream: Generator yielding PCM16 audio chunks (16kHz, mono, 16-bit).
            language: Optional ISO-639-1 language code (e.g., 'en', 'es').
            chunk_duration: Seconds of audio to collect before transcribing (default: 3.0).
        
        Yields:
            RealtimeTranscriptionOutput with incremental transcription.
            Each output contains all chunks so far (including "" for silent chunks).
        
        Raises:
            TranscriptionError: If transcription fails.
        """
        # Calculate samples needed for chunk_duration
        samples_per_chunk = int(self.SAMPLE_RATE * chunk_duration)
        bytes_per_chunk = samples_per_chunk * self.SAMPLE_WIDTH
        
        buffer = io.BytesIO()
        current_bytes = 0
        chunks: List[str] = []  # Track all chunks (including "" for silence)
        full_transcript = ""  # Track cumulative transcript for final output
        
        try:
            for audio_bytes in audio_stream:
                if not audio_bytes:
                    continue
                
                buffer.write(audio_bytes)
                current_bytes += len(audio_bytes)
                
                # Check if we have enough audio for a chunk
                if current_bytes >= bytes_per_chunk:
                    pcm_data = buffer.getvalue()
                    
                    # VAD check: if no speech detected, record as silence
                    if self._enable_vad and self._vad:
                        if not self._vad.has_speech(pcm_data):
                            # No speech detected - append empty string for silence
                            chunks.append("")
                            yield RealtimeTranscriptionOutput(
                                type=TranscriptionOutputType.INCREMENTAL,
                                chunks=chunks.copy(),
                                latest_transcription=full_transcript,
                                status=TranscriptionStatus.IN_PROGRESS,
                                final_transcription="",
                            )
                            buffer = io.BytesIO()
                            current_bytes = 0
                            continue
                    
                    # Create WAV from buffer and transcribe
                    wav_bytes = self._create_wav(pcm_data)
                    text = self._transcribe_chunk(wav_bytes, language)
                    
                    # Append chunk (text or "" if transcription returned empty)
                    chunks.append(text)
                    if text:
                        full_transcript = (full_transcript + " " + text).strip()
                    
                    yield RealtimeTranscriptionOutput(
                        type=TranscriptionOutputType.INCREMENTAL,
                        chunks=chunks.copy(),
                        latest_transcription=full_transcript,
                        status=TranscriptionStatus.IN_PROGRESS,
                        final_transcription="",
                    )
                    
                    # Reset buffer
                    buffer = io.BytesIO()
                    current_bytes = 0
            
            # Transcribe any remaining audio
            if current_bytes > 0:
                pcm_data = buffer.getvalue()
                
                # VAD check for remaining audio
                if self._enable_vad and self._vad:
                    if not self._vad.has_speech(pcm_data):
                        # No speech - append empty string for silence
                        chunks.append("")
                        yield RealtimeTranscriptionOutput(
                            type=TranscriptionOutputType.INCREMENTAL,
                            chunks=chunks.copy(),
                            latest_transcription=full_transcript,
                            status=TranscriptionStatus.IN_PROGRESS,
                            final_transcription="",
                        )
                    else:
                        wav_bytes = self._create_wav(pcm_data)
                        text = self._transcribe_chunk(wav_bytes, language)
                        chunks.append(text)
                        if text:
                            full_transcript = (full_transcript + " " + text).strip()
                        yield RealtimeTranscriptionOutput(
                            type=TranscriptionOutputType.INCREMENTAL,
                            chunks=chunks.copy(),
                            latest_transcription=full_transcript,
                            status=TranscriptionStatus.IN_PROGRESS,
                            final_transcription="",
                        )
                else:
                    wav_bytes = self._create_wav(pcm_data)
                    text = self._transcribe_chunk(wav_bytes, language)
                    chunks.append(text)
                    if text:
                        full_transcript = (full_transcript + " " + text).strip()
                    yield RealtimeTranscriptionOutput(
                        type=TranscriptionOutputType.INCREMENTAL,
                        chunks=chunks.copy(),
                        latest_transcription=full_transcript,
                        status=TranscriptionStatus.IN_PROGRESS,
                        final_transcription="",
                    )
            
            # Yield final complete output with full transcript
            yield RealtimeTranscriptionOutput(
                type=TranscriptionOutputType.INCREMENTAL,
                chunks=chunks.copy(),
                latest_transcription=full_transcript,
                status=TranscriptionStatus.COMPLETE,
                final_transcription=full_transcript,
            )
                    
        except Exception as e:
            # Yield error output before raising
            yield RealtimeTranscriptionOutput(
                type=TranscriptionOutputType.INCREMENTAL,
                chunks=chunks.copy(),
                latest_transcription=full_transcript,
                status=TranscriptionStatus.ERROR,
                final_transcription="",
            )
            raise TranscriptionError(
                message=f"Real-time transcription failed: {str(e)}",
                provider=self.name,
                original_error=e
            )
    
    def _create_wav(self, pcm_data: bytes) -> bytes:
        """
        Convert PCM16 data to WAV format in memory.
        
        Args:
            pcm_data: Raw PCM16 audio data (16kHz, mono, 16-bit).
        
        Returns:
            WAV file as bytes.
        """
        wav_buffer = io.BytesIO()
        
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(self.CHANNELS)
            wav_file.setsampwidth(self.SAMPLE_WIDTH)
            wav_file.setframerate(self.SAMPLE_RATE)
            wav_file.writeframes(pcm_data)
        
        wav_buffer.seek(0)
        return wav_buffer.getvalue()
    
    def _transcribe_chunk(
        self,
        wav_bytes: bytes,
        language: Optional[str] = None
    ) -> str:
        """
        Send WAV audio to Whisper API and return transcription.
        
        Args:
            wav_bytes: WAV file as bytes.
            language: Optional ISO-639-1 language code.
        
        Returns:
            Transcription text, or empty string if no speech detected.
        """
        # Create a file-like object with a name (required by OpenAI API)
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "audio.wav"
        
        try:
            params = {
                "model": self._whisper_model,
                "file": audio_file,
                "response_format": "text"
            }
            
            if language:
                params["language"] = language
            
            transcription = self._client.audio.transcriptions.create(**params)
            
            result = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
            return result
            
        except Exception as e:
            # Log error but don't fail the entire stream
            # Some chunks may have no speech or be too short
            return ""
