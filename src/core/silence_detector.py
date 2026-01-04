"""
Silence detection for automatic recording stop.

Analyzes audio chunks to detect extended periods of silence,
which can trigger automatic recording termination.
"""

import math
from typing import Optional

import numpy as np


class SilenceDetector:
    """
    Detects silence in audio streams.
    
    Analyzes PCM16 audio chunks and tracks consecutive silent periods.
    Returns True when silence exceeds the configured duration threshold.
    
    Example:
        detector = SilenceDetector(threshold_db=-40.0, silence_duration=2.0)
        
        for chunk in audio_stream:
            if detector.feed(chunk):
                print("Silence detected - stopping recording")
                break
    """
    
    # Maximum amplitude for 16-bit signed audio
    MAX_AMPLITUDE = 32768.0
    
    def __init__(
        self,
        threshold_db: float = -40.0,
        silence_duration: float = 2.0,
        sample_rate: int = 16000,
        chunk_size: int = 1600,  # ~100ms at 16kHz
        grace_period: float = 0.5,  # Don't trigger on initial silence
    ):
        """
        Initialize the silence detector.
        
        Args:
            threshold_db: Volume threshold in dB below which audio is considered silent.
                         Typical values: -40 to -50 dB.
            silence_duration: Seconds of continuous silence required to trigger detection.
            sample_rate: Audio sample rate in Hz.
            chunk_size: Number of samples per audio chunk.
            grace_period: Seconds at the start to ignore silence (prevents
                         triggering on the gap before user starts speaking).
        """
        self._threshold_db = threshold_db
        self._silence_duration = silence_duration
        self._sample_rate = sample_rate
        self._chunk_size = chunk_size
        self._grace_period = grace_period
        
        # Calculate chunk duration
        self._chunk_duration = chunk_size / sample_rate
        
        # Calculate how many consecutive silent chunks trigger detection
        self._silence_chunks_required = int(silence_duration / self._chunk_duration)
        self._grace_chunks = int(grace_period / self._chunk_duration)
        
        # State tracking
        self._consecutive_silent_chunks = 0
        self._total_chunks_processed = 0
        self._is_triggered = False
    
    @property
    def threshold_db(self) -> float:
        """Get the silence threshold in dB."""
        return self._threshold_db
    
    @property
    def silence_duration(self) -> float:
        """Get the required silence duration in seconds."""
        return self._silence_duration
    
    @property
    def is_triggered(self) -> bool:
        """Check if silence has been detected."""
        return self._is_triggered
    
    @property
    def current_silence_duration(self) -> float:
        """Get the current accumulated silence duration in seconds."""
        return self._consecutive_silent_chunks * self._chunk_duration
    
    def feed(self, audio_chunk: bytes) -> bool:
        """
        Analyze an audio chunk for silence.
        
        Args:
            audio_chunk: PCM16 audio data (16-bit signed, little-endian).
        
        Returns:
            True if silence duration threshold has been exceeded, False otherwise.
        """
        if self._is_triggered:
            return True
        
        self._total_chunks_processed += 1
        
        # Calculate RMS volume of the chunk
        rms = self._calculate_rms(audio_chunk)
        db = self._rms_to_db(rms)
        
        # Check if this chunk is silent
        is_silent = db < self._threshold_db
        
        if is_silent:
            self._consecutive_silent_chunks += 1
        else:
            self._consecutive_silent_chunks = 0
        
        # Check if we've exceeded the silence threshold
        # (but only after the grace period)
        if (self._total_chunks_processed > self._grace_chunks and
            self._consecutive_silent_chunks >= self._silence_chunks_required):
            self._is_triggered = True
            return True
        
        return False
    
    def reset(self) -> None:
        """
        Reset the detector state.
        
        Call this when starting a new recording session.
        """
        self._consecutive_silent_chunks = 0
        self._total_chunks_processed = 0
        self._is_triggered = False
    
    def _calculate_rms(self, audio_chunk: bytes) -> float:
        """
        Calculate the Root Mean Square (RMS) of audio data.
        
        Args:
            audio_chunk: PCM16 audio data.
        
        Returns:
            RMS value (0.0 to ~32768.0 for 16-bit audio).
        """
        if not audio_chunk:
            return 0.0
        
        # Convert bytes to numpy array of 16-bit integers
        try:
            samples = np.frombuffer(audio_chunk, dtype=np.int16)
        except ValueError:
            return 0.0
        
        if len(samples) == 0:
            return 0.0
        
        # Calculate RMS
        samples_float = samples.astype(np.float64)
        mean_square = np.mean(samples_float ** 2)
        rms = np.sqrt(mean_square)
        
        return rms
    
    def _rms_to_db(self, rms: float) -> float:
        """
        Convert RMS value to decibels.
        
        Args:
            rms: RMS amplitude value.
        
        Returns:
            Volume in dB (relative to max amplitude).
            Returns -100 for silence/zero RMS.
        """
        if rms <= 0:
            return -100.0
        
        # Convert to dB relative to max amplitude
        db = 20 * math.log10(rms / self.MAX_AMPLITUDE)
        return db
    
    def get_volume_db(self, audio_chunk: bytes) -> float:
        """
        Get the volume of an audio chunk in dB.
        
        Utility method for debugging or visualization.
        
        Args:
            audio_chunk: PCM16 audio data.
        
        Returns:
            Volume in dB.
        """
        rms = self._calculate_rms(audio_chunk)
        return self._rms_to_db(rms)


