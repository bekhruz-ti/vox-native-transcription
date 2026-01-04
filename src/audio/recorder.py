"""
Audio Recorder for capturing microphone input.

This module provides the AudioRecorder class for capturing audio from
the system microphone in formats suitable for speech-to-text transcription.
"""

import queue
import threading
import wave
from pathlib import Path
from typing import Generator, Optional

import numpy as np
import sounddevice as sd

from ..utils.audio_utils import AudioConfig, DEFAULT_AUDIO_CONFIG


class AudioRecorder:
    """
    Records audio from the microphone for speech-to-text transcription.
    
    Supports two recording modes:
    1. Streaming mode (`record()`) - yields audio chunks for real-time transcription
    2. File mode (`record_to_file()`) - records to WAV file for batch transcription
    
    Audio is captured in PCM16 format (16kHz, mono, 16-bit) by default,
    which is compatible with OpenAI's Realtime API.
    
    Example usage (streaming mode):
        recorder = AudioRecorder()
        recorder.start()
        for chunk in recorder.record():
            # Process audio chunk
            pass
        recorder.stop()
    
    Example usage (file mode):
        recorder = AudioRecorder()
        path = recorder.record_to_file("output.wav", max_duration=10.0)
    """
    
    def __init__(
        self,
        config: Optional[AudioConfig] = None,
        device: Optional[int] = None
    ):
        """
        Initialize the AudioRecorder.
        
        Args:
            config: Audio configuration. Uses default (16kHz, mono, PCM16) if None.
            device: Audio input device index. Uses system default if None.
                   Call get_audio_devices() to see available devices.
        """
        self._config = config or DEFAULT_AUDIO_CONFIG
        self._device = device
        
        self._is_recording = False
        self._audio_queue: queue.Queue[Optional[bytes]] = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._recording_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # For file recording
        self._recorded_frames: list[bytes] = []
    
    @property
    def config(self) -> AudioConfig:
        """Get the audio configuration."""
        return self._config
    
    @property
    def is_recording(self) -> bool:
        """Check if recording is currently active."""
        return self._is_recording
    
    def start(self) -> None:
        """
        Start recording audio from the microphone.
        
        Audio chunks will be available via the record() generator.
        Call stop() to end recording.
        
        Raises:
            RuntimeError: If recording is already in progress.
            OSError: If the audio device cannot be opened.
        """
        if self._is_recording:
            raise RuntimeError("Recording is already in progress")
        
        self._stop_event.clear()
        self._is_recording = True
        
        # Clear any old data from the queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
        
        # Create audio stream
        try:
            self._stream = sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                dtype=np.int16,
                blocksize=self._config.chunk_size,
                device=self._device,
                callback=self._audio_callback
            )
            self._stream.start()
        except Exception as e:
            self._is_recording = False
            raise OSError(f"Failed to open audio device: {e}") from e
    
    def stop(self) -> None:
        """
        Stop recording audio.
        
        This will close the audio stream and signal the record() generator
        to stop yielding chunks.
        """
        self._stop_event.set()
        self._is_recording = False
        
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        
        # Signal end of stream
        self._audio_queue.put(None)
    
    def record(self) -> Generator[bytes, None, None]:
        """
        Generate audio chunks from the microphone.
        
        This is a generator that yields PCM16 audio data chunks.
        Each chunk is approximately 100ms of audio (configurable via AudioConfig).
        
        The generator will continue yielding until stop() is called.
        
        Yields:
            bytes: PCM16 audio data chunks.
        
        Example:
            recorder = AudioRecorder()
            recorder.start()
            try:
                for chunk in recorder.record():
                    # Send chunk to transcription service
                    transcribe(chunk)
            finally:
                recorder.stop()
        """
        while self._is_recording or not self._audio_queue.empty():
            try:
                chunk = self._audio_queue.get(timeout=0.5)
                if chunk is None:
                    break
                yield chunk
            except queue.Empty:
                if not self._is_recording:
                    break
                continue
    
    def record_to_file(
        self,
        output_path: str,
        max_duration: Optional[float] = None
    ) -> str:
        """
        Record audio to a WAV file.
        
        This is a blocking operation that records until stop() is called
        (from another thread) or max_duration is reached.
        
        Args:
            output_path: Path where the WAV file will be saved.
            max_duration: Maximum recording duration in seconds.
                         If None, records until stop() is called.
        
        Returns:
            The path to the saved WAV file.
        
        Raises:
            RuntimeError: If recording is already in progress.
            OSError: If the audio device or file cannot be opened.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        self._recorded_frames = []
        frames_to_record = None
        
        if max_duration is not None:
            frames_to_record = int(max_duration * self._config.sample_rate / self._config.chunk_size)
        
        self.start()
        
        try:
            frame_count = 0
            for chunk in self.record():
                self._recorded_frames.append(chunk)
                frame_count += 1
                
                if frames_to_record is not None and frame_count >= frames_to_record:
                    break
        finally:
            self.stop()
        
        # Write to WAV file
        self._save_wav(str(path))
        
        return str(path)
    
    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: dict,
        status: sd.CallbackFlags
    ) -> None:
        """
        Callback function for the audio stream.
        
        This is called by sounddevice whenever new audio data is available.
        """
        if status:
            # Handle any stream errors (underflow, overflow, etc.)
            pass
        
        if not self._stop_event.is_set():
            # Convert to bytes and add to queue
            audio_bytes = indata.tobytes()
            self._audio_queue.put(audio_bytes)
    
    def _save_wav(self, path: str) -> None:
        """
        Save recorded frames to a WAV file.
        
        Args:
            path: Path to save the WAV file.
        """
        if not self._recorded_frames:
            return
        
        audio_data = b"".join(self._recorded_frames)
        
        with wave.open(path, "wb") as wf:
            wf.setnchannels(self._config.channels)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self._config.sample_rate)
            wf.writeframes(audio_data)
    
    @staticmethod
    def get_audio_devices() -> list[dict]:
        """
        Get a list of available audio input devices.
        
        Returns:
            List of dictionaries containing device information:
            - index: Device index (use this for the device parameter)
            - name: Device name
            - channels: Maximum input channels
            - sample_rate: Default sample rate
        """
        devices = []
        device_list = sd.query_devices()
        
        for i, device in enumerate(device_list):
            if device["max_input_channels"] > 0:
                devices.append({
                    "index": i,
                    "name": device["name"],
                    "channels": device["max_input_channels"],
                    "sample_rate": device["default_samplerate"]
                })
        
        return devices
    
    @staticmethod
    def get_default_device() -> Optional[dict]:
        """
        Get information about the default input device.
        
        Returns:
            Dictionary with device information, or None if no input device.
        """
        try:
            default_idx = sd.default.device[0]  # Input device index
            if default_idx is None or default_idx < 0:
                return None
            
            device = sd.query_devices(default_idx)
            return {
                "index": default_idx,
                "name": device["name"],
                "channels": device["max_input_channels"],
                "sample_rate": device["default_samplerate"]
            }
        except Exception:
            return None
    
    def __enter__(self) -> "AudioRecorder":
        """Context manager entry - starts recording."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - stops recording."""
        self.stop()

