"""
ElevenLabs Provider for Speech-to-Text transcription.

This module implements the GenAIProvider interface using ElevenLabs' Scribe API
for both batch and real-time streaming transcription.

Real-time transcription uses the official ElevenLabs SDK with WebSocket streaming.

Reference: https://elevenlabs.io/docs/developers/guides/cookbooks/speech-to-text/streaming
"""

import asyncio
import base64
import os
import queue
import threading
from pathlib import Path
from typing import Generator, List, Optional

import requests
from elevenlabs import ElevenLabs
from elevenlabs.realtime.scribe import AudioFormat

from .base import (
    GenAIProvider,
    RealtimeTranscriptionOutput,
    TranscriptionError,
    TranscriptionOutputType,
    TranscriptionStatus,
)


class ElevenLabsProvider(GenAIProvider):
    """
    ElevenLabs-based speech-to-text provider.
    
    Uses ElevenLabs Scribe API for transcription:
    - Batch: REST API for file transcription
    - Real-time: WebSocket streaming with the official SDK
    
    Features:
    - True real-time streaming
    - Partial transcripts as you speak
    - Built-in Voice Activity Detection (VAD)
    - Ultra-low latency
    
    Attributes:
        api_key: ElevenLabs API key.
        model: Model to use (default: "scribe_v2_realtime").
    """
    
    # API endpoints
    BATCH_URL = "https://api.elevenlabs.io/v1/speech-to-text"
    
    # Supported audio formats
    SUPPORTED_FORMATS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".flac"}
    
    # Audio configuration
    SAMPLE_RATE = 16000  # 16kHz
    CHANNELS = 1         # Mono
    SAMPLE_WIDTH = 2     # 16-bit = 2 bytes
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "scribe_v2_realtime"
    ):
        """
        Initialize the ElevenLabs provider.
        
        Args:
            api_key: ElevenLabs API key. If None, reads from ELEVENLABS_API_KEY env var.
            model: Model for transcription (default: "scribe_v2_realtime").
        
        Raises:
            ValueError: If no API key is provided or found in environment.
        """
        self._api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self._api_key:
            raise ValueError(
                "ElevenLabs API key is required. Set ELEVENLABS_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self._model = model
        self._client = ElevenLabs(api_key=self._api_key)
    
    @property
    def name(self) -> str:
        """Get the provider name."""
        return "ElevenLabs"
    
    def is_available(self) -> bool:
        """
        Check if the ElevenLabs provider is available.
        
        Returns:
            True if API key is valid and service is reachable.
        """
        try:
            # Check user info endpoint to validate API key
            response = requests.get(
                "https://api.elevenlabs.io/v1/user",
                headers={"xi-api-key": self._api_key},
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def transcribe_batch(
        self,
        audio_path: str,
        language: Optional[str] = None
    ) -> str:
        """
        Transcribe an audio file using ElevenLabs Scribe API.
        
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
                files = {
                    "file": (path.name, audio_file, "audio/mpeg")
                }
                
                data = {
                    "model_id": "scribe_v1"  # Batch uses scribe_v1
                }
                
                if language:
                    data["language_code"] = language
                
                response = requests.post(
                    self.BATCH_URL,
                    headers={"xi-api-key": self._api_key},
                    files=files,
                    data=data,
                    timeout=300  # 5 minute timeout for large files
                )
                
                if response.status_code != 200:
                    raise TranscriptionError(
                        message=f"API error: {response.status_code} - {response.text}",
                        provider=self.name
                    )
                
                result = response.json()
                return result.get("text", "").strip()
                
        except requests.RequestException as e:
            raise TranscriptionError(
                message=f"Failed to transcribe audio: {str(e)}",
                provider=self.name,
                original_error=e
            )
    
    def transcribe_realtime(
        self,
        audio_stream: Generator[bytes, None, None],
        language: Optional[str] = None,
        chunk_duration: float = 1.5  # Ignored - ElevenLabs does true streaming
    ) -> Generator[RealtimeTranscriptionOutput, None, None]:
        """
        Transcribe audio in real-time using ElevenLabs SDK.
        
        Provides true streaming transcription with partial transcripts
        appearing as you speak, and committed transcripts when speech
        segments are detected as complete (via VAD).
        
        Note: chunk_duration is ignored - ElevenLabs provides true streaming
        and doesn't need chunked batching like OpenAI Whisper.
        
        Args:
            audio_stream: Generator yielding PCM16 audio chunks (16kHz, mono, 16-bit).
            language: Optional ISO-639-1 language code (e.g., 'en', 'es').
            chunk_duration: Ignored (for API compatibility with OpenAI provider).
        
        Yields:
            RealtimeTranscriptionOutput with cumulative transcription.
        
        Raises:
            ConnectionError: If WebSocket connection fails.
            TranscriptionError: If transcription fails.
        """
        # Queue to bridge async SDK with sync generator
        result_queue: queue.Queue[Optional[RealtimeTranscriptionOutput]] = queue.Queue()
        error_holder: list[Optional[Exception]] = [None]
        
        def run_async_transcription():
            """Run the async transcription in a separate thread."""
            try:
                asyncio.run(self._async_transcribe_realtime(
                    audio_stream, result_queue, language
                ))
            except Exception as e:
                error_holder[0] = e
                result_queue.put(None)  # Signal completion
        
        # Start async transcription in background thread
        thread = threading.Thread(target=run_async_transcription, daemon=True)
        thread.start()
        
        # Yield results from queue
        last_output: Optional[RealtimeTranscriptionOutput] = None
        while True:
            try:
                result = result_queue.get(timeout=30)  # 30 second timeout
                if result is None:
                    break
                last_output = result
                yield result
            except queue.Empty:
                # Timeout waiting for results
                break
        
        # Wait for thread to complete
        thread.join(timeout=5)
        
        # Check for errors
        if error_holder[0] is not None:
            # Yield error output before raising
            yield RealtimeTranscriptionOutput(
                type=TranscriptionOutputType.CUMULATIVE,
                chunks=last_output.chunks.copy() if last_output else [],
                latest_transcription=last_output.latest_transcription if last_output else "",
                status=TranscriptionStatus.ERROR,
                final_transcription="",
            )
            raise TranscriptionError(
                message=f"Real-time transcription failed: {str(error_holder[0])}",
                provider=self.name,
                original_error=error_holder[0]
            )
    
    async def _async_transcribe_realtime(
        self,
        audio_stream: Generator[bytes, None, None],
        result_queue: queue.Queue[Optional[RealtimeTranscriptionOutput]],
        language: Optional[str] = None
    ) -> None:
        """
        Async implementation of real-time transcription using official SDK.
        
        Yields RealtimeTranscriptionOutput with cumulative text and chunks list.
        
        Args:
            audio_stream: Generator yielding audio chunks.
            result_queue: Queue to put RealtimeTranscriptionOutput objects into.
            language: Optional language code.
        """
        connection = None
        
        # Track cumulative text and all chunks
        committed_text = ""
        current_partial = ""
        chunks: List[str] = []  # Track all chunks
        
        try:
            # Connect using official SDK
            options = {
                "model_id": self._model,
                "sample_rate": self.SAMPLE_RATE,
                "audio_format": AudioFormat.PCM_16000,
            }
            
            if language:
                options["language_code"] = language
            
            connection = await self._client.speech_to_text.realtime.connect(options)
            print(f"[ELEVENLABS] Connected to realtime API")
            
            # Set up event handlers
            def on_partial(data):
                nonlocal current_partial
                text = data.get("text", "") if isinstance(data, dict) else getattr(data, 'text', '')
                # Note: partials are intermediate and don't add to chunks yet
                current_partial = text
                # Yield cumulative: committed + current partial
                cumulative = (committed_text + " " + current_partial).strip()
                print(f"[ELEVENLABS] Partial: '{text}' -> Cumulative: '{cumulative}'")
                result_queue.put(RealtimeTranscriptionOutput(
                    type=TranscriptionOutputType.CUMULATIVE,
                    chunks=chunks.copy(),
                    latest_transcription=cumulative,
                    status=TranscriptionStatus.IN_PROGRESS,
                    final_transcription="",
                ))
            
            def on_committed(data):
                nonlocal committed_text, current_partial, chunks
                text = data.get("text", "") if isinstance(data, dict) else getattr(data, 'text', '')
                # Add to committed text and chunks list
                chunks.append(text)  # Add the committed text as a chunk (can be "" for silence)
                if text:
                    committed_text = (committed_text + " " + text).strip()
                current_partial = ""
                print(f"[ELEVENLABS] Committed: '{text}' -> Total: '{committed_text}'")
                result_queue.put(RealtimeTranscriptionOutput(
                    type=TranscriptionOutputType.CUMULATIVE,
                    chunks=chunks.copy(),
                    latest_transcription=committed_text,
                    status=TranscriptionStatus.IN_PROGRESS,
                    final_transcription="",
                ))
            
            def on_error(error):
                error_msg = str(error)
                print(f"[ELEVENLABS] Error: {error_msg}")
            
            connection.on("partial_transcript", on_partial)
            connection.on("committed_transcript", on_committed)
            connection.on("error", on_error)
            
            # Send all audio chunks
            chunk_count = 0
            for chunk in audio_stream:
                if not chunk:
                    continue
                
                chunk_count += 1
                audio_base64 = base64.b64encode(chunk).decode("utf-8")
                await connection.send({"audio_base_64": audio_base64})
                await asyncio.sleep(0.01)
            
            print(f"[ELEVENLABS] Sent {chunk_count} chunks, committing...")
            
            # Commit to finalize transcription
            await connection.commit()
            
            # Wait for remaining transcriptions
            await asyncio.sleep(2)
            
            print(f"[ELEVENLABS] Final transcript: '{committed_text}'")
            
            # Yield final complete output
            result_queue.put(RealtimeTranscriptionOutput(
                type=TranscriptionOutputType.CUMULATIVE,
                chunks=chunks.copy(),
                latest_transcription=committed_text,
                status=TranscriptionStatus.COMPLETE,
                final_transcription=committed_text,
            ))
            
        except Exception as e:
            print(f"[ELEVENLABS] SDK error: {e}")
            import traceback
            traceback.print_exc()
            raise TranscriptionError(
                message=f"SDK error: {str(e)}",
                provider=self.name,
                original_error=e
            )
        finally:
            result_queue.put(None)  # Signal completion
            if connection:
                try:
                    await connection.close()
                except Exception:
                    pass
