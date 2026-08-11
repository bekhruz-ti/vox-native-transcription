"""
Recording session orchestrator.

Coordinates the recording lifecycle, integrating audio recording,
speech-to-text transcription, silence detection, and text injection.
"""

import io
import threading
import wave
from enum import Enum, auto
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal, QThread, QMutex, QWaitCondition

from ..providers.base import (
    RealtimeTranscriptionOutput,
    TranscriptionOutputType,
    TranscriptionStatus,
)


class SessionState(Enum):
    """Recording session states."""
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class RecordingWorker(QThread):
    """
    Background worker thread for recording and transcription.
    
    Runs the audio recording loop and STT processing in a separate thread
    to keep the UI responsive.
    """
    
    # Signals
    audio_chunk = Signal(bytes)   # Emitted for each audio chunk
    text_update = Signal(object)  # Emits RealtimeTranscriptionOutput
    finished_recording = Signal() # Emitted when recording stops
    error = Signal(str)           # Emitted on error
    
    def __init__(
        self,
        recorder,  # AudioRecorder
        provider,  # GenAIProvider
        silence_detector,  # SilenceDetector
        language: Optional[str] = None,
        realtime_mode: bool = True,
        parent: Optional[QObject] = None,
    ):
        """
        Initialize the recording worker.
        
        Args:
            recorder: AudioRecorder instance.
            provider: GenAIProvider instance for transcription.
            silence_detector: SilenceDetector instance.
            language: Language code for transcription.
            realtime_mode: If True, use real-time transcription.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._recorder = recorder
        self._provider = provider
        self._silence_detector = silence_detector
        self._language = language
        self._realtime_mode = realtime_mode
        
        self._stop_requested = False
        self._mutex = QMutex()
        self._audio_buffer: list[bytes] = []
    
    def run(self) -> None:
        """Main worker thread execution."""
        print(f"[WORKER] Starting, realtime_mode={self._realtime_mode}")
        try:
            self._stop_requested = False
            self._audio_buffer = []
            self._silence_detector.reset()
            
            # Start recording
            print("[WORKER] Starting recorder...")
            self._recorder.start()
            print("[WORKER] Recorder started")
            
            if self._realtime_mode:
                self._run_realtime()
            else:
                self._run_batch()
            
        except Exception as e:
            print(f"[WORKER] Error: {e}")
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            # Ensure recorder is stopped
            print("[WORKER] Stopping recorder...")
            try:
                self._recorder.stop()
            except Exception:
                pass
            print("[WORKER] Emitting finished_recording")
            self.finished_recording.emit()
    
    def _run_realtime(self) -> None:
        """Run real-time transcription mode."""
        print("[WORKER] Running real-time transcription...")
        chunk_count = 0
        try:
            # Create a generator that yields audio chunks
            def audio_generator():
                nonlocal chunk_count
                for chunk in self._recorder.record():
                    if self._stop_requested:
                        print(f"[WORKER] Stop requested after {chunk_count} chunks")
                        break
                    
                    chunk_count += 1
                    if chunk_count % 20 == 0:
                        print(f"[WORKER] Recorded {chunk_count} chunks...")
                    
                    # Emit chunk for other listeners (e.g., silence detector)
                    self.audio_chunk.emit(chunk)
                    
                    # Check for silence
                    if self._silence_detector.feed(chunk):
                        print(f"[WORKER] Silence detected after {chunk_count} chunks")
                        self._stop_requested = True
                        break
                    
                    yield chunk
            
            # Run transcription - provider now yields RealtimeTranscriptionOutput
            print("[WORKER] Starting transcription...")
            text_count = 0
            last_output = None
            for output in self._provider.transcribe_realtime(
                audio_generator(),
                language=self._language,
                chunk_duration=1.5,  # Faster feedback (every 1.5 seconds)
            ):
                last_output = output
                text_count += 1
                status_str = output.status.value if output.status else "None"
                preview = output.latest_transcription[:50] if output.latest_transcription else ""
                print(f"[WORKER] Output #{text_count}: status={status_str}, text='{preview}...'")
                
                # Always emit the output for UI/session to process
                self.text_update.emit(output)
                
                # Stop after receiving COMPLETE
                if output.status == TranscriptionStatus.COMPLETE:
                    print(f"[WORKER] COMPLETE received, breaking loop")
                    break
                    
                # If stop requested and not complete, break
                if self._stop_requested:
                    print(f"[WORKER] Stop requested, breaking loop")
                    break
            
            print(f"[WORKER] Transcription loop ended, {text_count} updates")
            
            # If we never got COMPLETE, emit one now with the last known text
            if last_output and last_output.status != TranscriptionStatus.COMPLETE:
                print(f"[WORKER] No COMPLETE received, emitting synthetic COMPLETE")
                final_output = RealtimeTranscriptionOutput(
                    type=last_output.type,
                    chunks=last_output.chunks.copy(),
                    latest_transcription=last_output.latest_transcription,
                    status=TranscriptionStatus.COMPLETE,
                    final_transcription=last_output.latest_transcription,
                )
                self.text_update.emit(final_output)
                
        except Exception as e:
            print(f"[WORKER] Real-time error: {e}")
            import traceback
            traceback.print_exc()
            self.error.emit(f"Real-time transcription error: {e}")
    
    def _run_batch(self) -> None:
        """Run batch transcription mode (record first, transcribe after)."""
        print("[WORKER] Running batch transcription...")
        chunk_count = 0
        try:
            # Collect all audio
            for chunk in self._recorder.record():
                if self._stop_requested:
                    print(f"[WORKER] Stop requested after {chunk_count} chunks")
                    break
                
                chunk_count += 1
                if chunk_count % 20 == 0:
                    print(f"[WORKER] Recorded {chunk_count} chunks...")
                
                self.audio_chunk.emit(chunk)
                self._audio_buffer.append(chunk)
                
                # Check for silence
                if self._silence_detector.feed(chunk):
                    self._stop_requested = True
                    break
            
            # Transcribe collected audio
            if self._audio_buffer:
                wav_data = self._create_wav(b"".join(self._audio_buffer))
                
                # Create temporary file-like object
                wav_file = io.BytesIO(wav_data)
                wav_file.name = "recording.wav"
                
                # Use batch transcription via temp file approach
                # For simplicity, write to temp file
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(wav_data)
                    temp_path = f.name
                
                try:
                    text = self._provider.transcribe_batch(temp_path, self._language)
                    # Wrap in RealtimeTranscriptionOutput for consistent handling
                    output = RealtimeTranscriptionOutput(
                        type=TranscriptionOutputType.CUMULATIVE,
                        chunks=[text] if text else [],
                        latest_transcription=text,
                        status=TranscriptionStatus.COMPLETE,
                        final_transcription=text,
                    )
                    self.text_update.emit(output)
                finally:
                    import os
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
                        
        except Exception as e:
            self.error.emit(f"Batch transcription error: {e}")
    
    def _create_wav(self, pcm_data: bytes) -> bytes:
        """Convert PCM16 data to WAV format."""
        wav_buffer = io.BytesIO()
        
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(pcm_data)
        
        wav_buffer.seek(0)
        return wav_buffer.getvalue()
    
    def request_stop(self) -> None:
        """Request the worker to stop recording."""
        self._stop_requested = True
        self._recorder.stop()


class RecordingSession(QObject):
    """
    Orchestrates the complete recording and transcription workflow.
    
    Manages:
    - Recording lifecycle (start, stop, toggle)
    - Audio recording via AudioRecorder
    - Speech-to-text via GenAIProvider
    - Silence detection
    - Text injection into the focused application
    
    Signals:
        state_changed: Emitted when session state changes.
        text_chunk: Emitted for incremental text (real-time mode).
        transcription_complete: Emitted when transcription finishes.
        error: Emitted on error.
    
    Example:
        session = RecordingSession(recorder, provider)
        session.text_chunk.connect(on_text)
        session.toggle()  # Start recording
        # ... user speaks ...
        session.toggle()  # Stop recording
    """
    
    # Signals
    state_changed = Signal(SessionState)
    text_chunk = Signal(object)  # Emits RealtimeTranscriptionOutput
    transcription_complete = Signal(str)
    error = Signal(str)
    
    def __init__(
        self,
        recorder,  # AudioRecorder
        provider,  # GenAIProvider
        text_injector=None,   # TextInjector
        language: Optional[str] = None,
        silence_threshold_db: float = -40.0,
        silence_duration: float = 2.0,
        realtime_mode: bool = True,
        parent: Optional[QObject] = None,
    ):
        """
        Initialize the recording session.
        
        Args:
            recorder: AudioRecorder instance.
            provider: GenAIProvider instance.
            text_injector: Optional TextInjector instance.
            language: Language code for transcription.
            silence_threshold_db: Silence detection threshold.
            silence_duration: Seconds of silence to trigger stop.
            realtime_mode: If True, use real-time transcription.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        
        self._recorder = recorder
        self._provider = provider
        self._text_injector = text_injector
        self._language = language
        self._realtime_mode = realtime_mode
        
        # Create silence detector
        from .silence_detector import SilenceDetector
        self._silence_detector = SilenceDetector(
            threshold_db=silence_threshold_db,
            silence_duration=silence_duration,
            grace_period=1.5,  # Don't trigger on first 1.5 seconds of silence
        )
        
        # State
        self._state = SessionState.IDLE
        self._worker: Optional[RecordingWorker] = None
        self._last_text = ""
        self._output_type: Optional[TranscriptionOutputType] = None
        self._final_text = ""
    
    @property
    def state(self) -> SessionState:
        """Get the current session state."""
        return self._state
    
    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._state == SessionState.RECORDING
    
    def toggle(self) -> None:
        """
        Toggle recording state.
        
        If idle, starts recording.
        If recording, stops recording.
        """
        if self._state == SessionState.IDLE:
            self.start()
        elif self._state == SessionState.RECORDING:
            self.stop()
    
    def start(self) -> None:
        """
        Start a new recording session.
        
        The transcription is typed into whatever currently has keyboard focus,
        and mirrored in the toast so it can still be copied by clicking.
        """
        if self._state != SessionState.IDLE:
            return
        
        # Reset state
        self._last_text = ""
        self._output_type = None
        self._final_text = ""
        self._silence_detector.reset()
        
        if self._text_injector:
            self._text_injector.reset_incremental()
        
        use_realtime = self._realtime_mode
        print(f"[SESSION] use_realtime={use_realtime}")
        
        # Create and start worker
        self._worker = RecordingWorker(
            recorder=self._recorder,
            provider=self._provider,
            silence_detector=self._silence_detector,
            language=self._language,
            realtime_mode=use_realtime,
        )
        
        # Connect signals
        self._worker.text_update.connect(self._on_text_update)
        self._worker.finished_recording.connect(self._on_recording_finished)
        self._worker.error.connect(self._on_error)
        
        # Update state and start
        self._set_state(SessionState.RECORDING)
        self._worker.start()
    
    def stop(self) -> None:
        """Stop the current recording session."""
        if self._state != SessionState.RECORDING:
            return
        
        if self._worker:
            self._worker.request_stop()
            # State will change to PROCESSING when worker emits finished
    
    def cancel(self) -> None:
        """Cancel the current recording without processing."""
        if self._worker:
            self._worker.request_stop()
        
        self._set_state(SessionState.IDLE)
        self._worker = None
    
    def _set_state(self, new_state: SessionState) -> None:
        """Update the session state and emit signal."""
        if self._state != new_state:
            self._state = new_state
            self.state_changed.emit(new_state)
    
    def _on_text_update(self, output: RealtimeTranscriptionOutput) -> None:
        """Handle transcription output from worker."""
        self._output_type = output.type
        self._last_text = output.latest_transcription
        
        # Debug logging
        status_str = output.status.value if output.status else "None"
        type_str = output.type.value if output.type else "None"
        print(f"[SESSION] Received: type={type_str}, status={status_str}, "
              f"text='{output.latest_transcription[:30] if output.latest_transcription else ''}...'")
        
        # Emit for UI (toast updates)
        self.text_chunk.emit(output)
        
        # Handle text injection based on output type
        if self._text_injector:
            if output.type == TranscriptionOutputType.CUMULATIVE:
                # CUMULATIVE: ONLY inject on COMPLETE - no live updates
                if output.status == TranscriptionStatus.COMPLETE:
                    final_text = output.final_transcription or output.latest_transcription or ""
                    if final_text:
                        print(f"[SESSION] Injecting final CUMULATIVE text: '{final_text[:50]}...'")
                        self._text_injector.inject(final_text)
                else:
                    print(f"[SESSION] CUMULATIVE IN_PROGRESS - not injecting (waiting for COMPLETE)")
            else:  # INCREMENTAL
                # INCREMENTAL: Append the newest chunk immediately (live updates)
                if output.chunks:
                    newest_chunk = output.chunks[-1]
                    if newest_chunk:
                        print(f"[SESSION] Injecting INCREMENTAL chunk: '{newest_chunk}'")
                        self._text_injector.inject(newest_chunk)
        
        # Track completion
        if output.status == TranscriptionStatus.COMPLETE:
            # Use final_transcription if available, otherwise latest_transcription
            self._final_text = output.final_transcription or output.latest_transcription or ""
            print(f"[SESSION] COMPLETE received, final_text='{self._final_text[:50] if self._final_text else ''}...'")
        elif output.status == TranscriptionStatus.ERROR:
            print(f"[SESSION] ERROR status received")
    
    def _on_recording_finished(self) -> None:
        """Handle recording completion."""
        # Brief processing state
        self._set_state(SessionState.PROCESSING)
        
        # Use final_text if available, otherwise last_text
        final_text = self._final_text or self._last_text or ""
        
        # Always emit completion (even if empty - UI will show "No Audio Detected")
        self.transcription_complete.emit(final_text)
        
        # Clean up
        self._worker = None
        self._output_type = None
        self._final_text = ""
        self._set_state(SessionState.IDLE)
    
    def _on_error(self, message: str) -> None:
        """Handle error from worker."""
        self.error.emit(message)
        self._set_state(SessionState.IDLE)
        self._worker = None


