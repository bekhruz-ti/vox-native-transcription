"""
Voice Activity Detection (VAD) module.

This module provides speech detection functionality using:
1. Silero-VAD - A lightweight neural network-based VAD
2. Energy-based thresholding - A fast pre-filter for quiet audio

Used to filter out background noise before sending audio to transcription.
"""

import numpy as np
from typing import Optional

# Lazy-load torch to avoid slow imports
_vad_model = None
_vad_utils = None


def _load_silero_vad():
    """
    Lazy-load Silero-VAD model.
    
    Returns:
        Tuple of (model, utils) or (None, None) if loading fails.
    """
    global _vad_model, _vad_utils
    
    if _vad_model is not None:
        return _vad_model, _vad_utils
    
    try:
        import torch
        torch.set_num_threads(1)  # Limit CPU usage
        
        # Load Silero-VAD model from torch hub
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            trust_repo=True
        )
        
        _vad_model = model
        _vad_utils = utils
        return _vad_model, _vad_utils
        
    except Exception as e:
        print(f"Warning: Could not load Silero-VAD: {e}")
        return None, None


def audio_energy(pcm_bytes: bytes) -> float:
    """
    Calculate RMS energy of audio chunk.
    
    This is a fast pre-filter to discard very quiet audio
    before running the more expensive VAD model.
    
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
    Check if audio contains speech using Silero-VAD neural network.
    
    This is more accurate than energy-based detection but slower.
    Use after energy pre-filter for best performance.
    
    Note: Silero-VAD requires exactly 512 samples at 16kHz (32ms windows).
    This function automatically chunks audio into proper window sizes.
    
    Args:
        pcm_bytes: Raw PCM16 audio data (16kHz, mono, 16-bit).
        sample_rate: Sample rate of audio (default 16000).
        threshold: Speech probability threshold (0-1).
                   Lower = more permissive, catches more speech.
                   Default 0.3 is permissive to avoid missing speech.
    
    Returns:
        True if speech is detected with confidence above threshold.
    """
    model, utils = _load_silero_vad()
    
    if model is None:
        # Fallback to energy-based detection if VAD not available
        return has_speech_energy(pcm_bytes)
    
    try:
        import torch
        
        # Silero-VAD requires exactly 512 samples at 16kHz (or 256 at 8kHz)
        window_size = 512 if sample_rate == 16000 else 256
        
        # Convert bytes to float tensor (-1 to 1 range)
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        audio_float = samples.astype(np.float32) / 32768.0
        
        # If audio is shorter than window size, pad with zeros
        if len(audio_float) < window_size:
            audio_float = np.pad(audio_float, (0, window_size - len(audio_float)))
        
        # Process audio in 512-sample windows, check if any has speech
        max_prob = 0.0
        num_windows = len(audio_float) // window_size
        
        for i in range(num_windows):
            start = i * window_size
            end = start + window_size
            window = audio_float[start:end]
            
            audio_tensor = torch.from_numpy(window)
            prob = model(audio_tensor, sample_rate).item()
            max_prob = max(max_prob, prob)
            
            # Early exit if we find speech
            if prob >= threshold:
                return True
        
        return max_prob >= threshold
        
    except Exception as e:
        # Fallback to energy-based detection on error
        print(f"VAD error, falling back to energy: {e}")
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
        vad_threshold: Speech probability threshold for VAD (default 0.3).
        use_vad: Whether to use Silero-VAD (default True).
                 If False, only energy threshold is used.
    
    Returns:
        True if speech is detected in the audio chunk.
    """
    # Step 1: Quick energy check (very fast)
    if not has_speech_energy(pcm_bytes, energy_threshold):
        return False
    
    # Step 2: VAD check if enabled (more accurate but slower)
    if use_vad:
        return has_speech_vad(pcm_bytes, sample_rate, vad_threshold)
    
    # Energy check passed and VAD disabled
    return True


class VoiceActivityDetector:
    """
    Voice Activity Detector with configurable thresholds.
    
    Provides a reusable object for detecting speech in audio chunks.
    Combines fast energy-based pre-filtering with accurate neural VAD.
    
    Attributes:
        energy_threshold: Minimum RMS energy to process.
        vad_threshold: Speech probability threshold (0-1).
        enable_vad: Whether to use Silero-VAD neural network.
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
            vad_threshold: Speech probability threshold (default 0.3).
            enable_vad: Use Silero-VAD neural network (default True).
            sample_rate: Expected audio sample rate (default 16000).
        """
        self.energy_threshold = energy_threshold
        self.vad_threshold = vad_threshold
        self.enable_vad = enable_vad
        self.sample_rate = sample_rate
        
        # Pre-load VAD model if enabled
        if enable_vad:
            _load_silero_vad()
    
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
        Get max speech probability from VAD model across all windows.
        
        Args:
            pcm_bytes: Raw PCM16 audio data.
        
        Returns:
            Max speech probability (0-1), or -1 if VAD not available.
        """
        model, _ = _load_silero_vad()
        
        if model is None:
            return -1.0
        
        try:
            import torch
            
            # Silero-VAD requires exactly 512 samples at 16kHz
            window_size = 512 if self.sample_rate == 16000 else 256
            
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            audio_float = samples.astype(np.float32) / 32768.0
            
            # If audio is shorter than window size, pad with zeros
            if len(audio_float) < window_size:
                audio_float = np.pad(audio_float, (0, window_size - len(audio_float)))
            
            # Process audio in windows, return max probability
            max_prob = 0.0
            num_windows = len(audio_float) // window_size
            
            for i in range(num_windows):
                start = i * window_size
                end = start + window_size
                window = audio_float[start:end]
                
                audio_tensor = torch.from_numpy(window)
                prob = model(audio_tensor, self.sample_rate).item()
                max_prob = max(max_prob, prob)
            
            return max_prob
            
        except Exception:
            return -1.0

