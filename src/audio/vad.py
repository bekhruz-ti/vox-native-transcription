"""
Voice Activity Detection (VAD) module.

This module provides speech detection functionality using:
1. WebRTC VAD - Google's lightweight, fast voice activity detector
2. Energy-based thresholding - A fast pre-filter for quiet audio

Used to filter out background noise before sending audio to transcription.
"""

import numpy as np
from typing import Optional

import webrtcvad

# Lazy-load VAD instance
_vad_instance: Optional[webrtcvad.Vad] = None


def _get_vad(aggressiveness: int = 1) -> webrtcvad.Vad:
    """
    Get or create WebRTC VAD instance.
    
    Args:
        aggressiveness: VAD aggressiveness mode (0-3).
                        0 = least aggressive (most permissive)
                        3 = most aggressive (filters more)
    
    Returns:
        WebRTC VAD instance.
    """
    global _vad_instance
    
    if _vad_instance is None:
        _vad_instance = webrtcvad.Vad()
    
    _vad_instance.set_mode(aggressiveness)
    return _vad_instance


def _threshold_to_aggressiveness(threshold: float) -> int:
    """
    Map vad_threshold (0-1) to WebRTC aggressiveness (0-3).
    
    Lower threshold = more permissive = lower aggressiveness.
    
    Args:
        threshold: Speech detection threshold (0-1).
    
    Returns:
        WebRTC aggressiveness mode (0-3).
    """
    return min(3, max(0, int(threshold * 3)))

def audio_energy(pcm_bytes: bytes) -> float:
    """
    Calculate RMS energy of audio chunk.
    
    This is a fast pre-filter to discard very quiet audio
    before running the VAD.
    
    Args:
        pcm_bytes: Raw PCM16 audio data (16-bit signed integers).
    
    Returns:
        RMS energy value. Higher = louder audio.
        Typical values:
        - Silence: 0-100
        - Background noise: 100-500
        - Soft speech: 500-2000
        - Normal speech: 2000-10000
        - Loud speech: 10000+
    """
    if not pcm_bytes:
        return 0.0
    
    # Convert bytes to numpy array of int16 samples
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    
    if len(samples) == 0:
        return 0.0
    
    # Calculate RMS (root mean square)
    rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
    return float(rms)


def has_speech_energy(pcm_bytes: bytes, threshold: float = 100.0) -> bool:
    """
    Quick energy-based check for potential speech.
    
    Args:
        pcm_bytes: Raw PCM16 audio data.
        threshold: Minimum RMS energy to consider as potential speech.
                   Default 100 filters only very quiet/silent audio.
    
    Returns:
        True if audio energy is above threshold.
    """
    return audio_energy(pcm_bytes) >= threshold


def has_speech_vad(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    threshold: float = 0.3
) -> bool:
    """
    Check if audio contains speech using WebRTC VAD.
    
    WebRTC VAD requires frames of exactly 10, 20, or 30 ms.
    This function automatically chunks audio into proper frame sizes.
    
    Args:
        pcm_bytes: Raw PCM16 audio data (16kHz, mono, 16-bit).
        sample_rate: Sample rate of audio (8000, 16000, 32000, or 48000).
        threshold: Speech detection threshold (0-1).
                   Lower = more permissive, catches more speech.
                   Default 0.3 is permissive to avoid missing speech.
    
    Returns:
        True if speech is detected in any frame.
    """
    if not pcm_bytes:
        return False
    
    # Validate sample rate
    if sample_rate not in (8000, 16000, 32000, 48000):
        # Fallback to energy-based detection
        return has_speech_energy(pcm_bytes)
    
    try:
        aggressiveness = _threshold_to_aggressiveness(threshold)
        vad = _get_vad(aggressiveness)
        
        # WebRTC VAD requires 10, 20, or 30 ms frames
        # Use 30ms frames for better accuracy
        # samples_per_frame = sample_rate * frame_duration_ms / 1000
        frame_duration_ms = 30
        samples_per_frame = sample_rate * frame_duration_ms // 1000
        bytes_per_frame = samples_per_frame * 2  # 16-bit = 2 bytes
        
        # Process audio in frames
        num_frames = len(pcm_bytes) // bytes_per_frame
        
        if num_frames == 0:
            # Audio too short, check if we can use 10ms frame
            frame_duration_ms = 10
            samples_per_frame = sample_rate * frame_duration_ms // 1000
            bytes_per_frame = samples_per_frame * 2
            num_frames = len(pcm_bytes) // bytes_per_frame
            
            if num_frames == 0:
                # Still too short, fallback to energy
                return has_speech_energy(pcm_bytes)
        
        # Check each frame for speech
        for i in range(num_frames):
            start = i * bytes_per_frame
            end = start + bytes_per_frame
            frame = pcm_bytes[start:end]
            
            if vad.is_speech(frame, sample_rate):
                return True
        
        return False
        
    except Exception:
        # Fallback to energy-based detection on error
        return has_speech_energy(pcm_bytes)


def has_speech(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    energy_threshold: float = 100.0,
    vad_threshold: float = 0.3,
    use_vad: bool = True
) -> bool:
    """
    Combined speech detection using energy pre-filter and VAD.
    
    This is the recommended function for filtering audio before transcription.
    It first checks energy (fast), then runs VAD only if energy is sufficient.
    
    Args:
        pcm_bytes: Raw PCM16 audio data (16kHz, mono, 16-bit).
        sample_rate: Sample rate of audio (default 16000).
        energy_threshold: Minimum RMS energy to process (default 100).
        vad_threshold: Speech detection threshold for VAD (default 0.3).
        use_vad: Whether to use WebRTC VAD (default True).
                 If False, only energy threshold is used.
    
    Returns:
        True if speech is detected in the audio chunk.
    """
    # Step 1: Quick energy check (very fast)
    if not has_speech_energy(pcm_bytes, energy_threshold):
        return False
    
    # Step 2: VAD check if enabled
    if use_vad:
        return has_speech_vad(pcm_bytes, sample_rate, vad_threshold)
    
    # Energy check passed and VAD disabled
    return True


class VoiceActivityDetector:
    """
    Voice Activity Detector with configurable thresholds.
    
    Provides a reusable object for detecting speech in audio chunks.
    Combines fast energy-based pre-filtering with WebRTC VAD.
    
    Attributes:
        energy_threshold: Minimum RMS energy to process.
        vad_threshold: Speech detection threshold (0-1).
        enable_vad: Whether to use WebRTC VAD.
        sample_rate: Expected sample rate of audio.
    """
    
    def __init__(
        self,
        energy_threshold: float = 100.0,
        vad_threshold: float = 0.3,
        enable_vad: bool = True,
        sample_rate: int = 16000
    ):
        """
        Initialize the Voice Activity Detector.
        
        Args:
            energy_threshold: Minimum RMS energy to process (default 100).
            vad_threshold: Speech detection threshold (default 0.3).
            enable_vad: Use WebRTC VAD (default True).
            sample_rate: Expected audio sample rate (default 16000).
        """
        self.energy_threshold = energy_threshold
        self.vad_threshold = vad_threshold
        self.enable_vad = enable_vad
        self.sample_rate = sample_rate
        self._aggressiveness = _threshold_to_aggressiveness(vad_threshold)
        
        # Pre-initialize VAD if enabled
        if enable_vad:
            _get_vad(self._aggressiveness)
    
    def has_speech(self, pcm_bytes: bytes) -> bool:
        """
        Check if audio chunk contains speech.
        
        Args:
            pcm_bytes: Raw PCM16 audio data.
        
        Returns:
            True if speech is detected.
        """
        return has_speech(
            pcm_bytes=pcm_bytes,
            sample_rate=self.sample_rate,
            energy_threshold=self.energy_threshold,
            vad_threshold=self.vad_threshold,
            use_vad=self.enable_vad
        )
    
    def get_energy(self, pcm_bytes: bytes) -> float:
        """
        Get the RMS energy of an audio chunk.
        
        Args:
            pcm_bytes: Raw PCM16 audio data.
        
        Returns:
            RMS energy value.
        """
        return audio_energy(pcm_bytes)
    
    def get_speech_probability(self, pcm_bytes: bytes) -> float:
        """
        Get speech detection ratio from VAD across all frames.
        
        Note: WebRTC VAD returns binary speech/no-speech, not probability.
        This returns the ratio of frames detected as speech (0-1).
        
        Args:
            pcm_bytes: Raw PCM16 audio data.
        
        Returns:
            Ratio of frames with speech (0-1), or -1 if VAD not available.
        """
        if not pcm_bytes or not self.enable_vad:
            return -1.0
        
        if self.sample_rate not in (8000, 16000, 32000, 48000):
            return -1.0
        
        try:
            vad = _get_vad(self._aggressiveness)
            
            # Use 30ms frames
            frame_duration_ms = 30
            samples_per_frame = self.sample_rate * frame_duration_ms // 1000
            bytes_per_frame = samples_per_frame * 2
            
            num_frames = len(pcm_bytes) // bytes_per_frame
            
            if num_frames == 0:
                return -1.0
            
            speech_frames = 0
            for i in range(num_frames):
                start = i * bytes_per_frame
                end = start + bytes_per_frame
                frame = pcm_bytes[start:end]
                
                if vad.is_speech(frame, self.sample_rate):
                    speech_frames += 1
            
            return speech_frames / num_frames
            
        except Exception:
            return -1.0
