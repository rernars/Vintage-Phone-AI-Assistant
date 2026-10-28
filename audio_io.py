"""Audio I/O handler supporting sounddevice (cross-platform PC & Mac) and PyAudio."""

import math
import struct
import threading
import time
import numpy as np
import config

try:
    import sounddevice as sd
    BACKEND = "sounddevice"
except ImportError:
    try:
        import pyaudio
        BACKEND = "pyaudio"
    except ImportError:
        BACKEND = "none"

class TelephoneAudio:
    def __init__(self):
        self.sample_rate = config.AUDIO_SAMPLE_RATE
        self.channels = config.AUDIO_CHANNELS
        self.chunk_size = config.AUDIO_CHUNK_SIZE
        self.backend = BACKEND
        
        self.tone_thread = None
        self.stop_tone_event = threading.Event()
        self.pa = None

        if self.backend == "pyaudio":
            import pyaudio
            self.pa = pyaudio.PyAudio()

    def generate_sine_wave_np(self, freq: float, duration: float, volume: float = 0.35) -> np.ndarray:
        """Generates float32 sine wave array for sounddevice."""
        t = np.linspace(0, duration, int(self.sample_rate * duration), endpoint=False, dtype=np.float32)
        return (volume * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)

    def _play_tone_sd(self, pattern: list[tuple[float, float, float]]):
        """Pattern player using sounddevice."""
        stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype='float32'
        )
        stream.start()

        while not self.stop_tone_event.is_set():
            for freq, sound_duration, silence_duration in pattern:
                if self.stop_tone_event.is_set():
                    break
                if sound_duration > 0:
                    samples = self.generate_sine_wave_np(freq, sound_duration, volume=0.3)
                    # Write in 50ms blocks to check cancellation
                    step = int(self.sample_rate * 0.05)
                    for i in range(0, len(samples), step):
                        if self.stop_tone_event.is_set():
                            break
                        stream.write(samples[i:i+step])
                if silence_duration > 0 and not self.stop_tone_event.is_set():
                    silence = np.zeros(int(self.sample_rate * silence_duration), dtype=np.float32)
                    step = int(self.sample_rate * 0.05)
                    for i in range(0, len(silence), step):
                        if self.stop_tone_event.is_set():
                            break
                        stream.write(silence[i:i+step])
        stream.stop()
        stream.close()

    def start_dial_tone(self):
        """German Wählton: Continuous 425 Hz."""
        self.stop_tone()
        self.stop_tone_event.clear()
        self.tone_thread = threading.Thread(
            target=self._play_tone_sd,
            args=([(config.TONE_FREQ_HZ, 1.0, 0.0)],),
            daemon=True
        )
        self.tone_thread.start()

    def start_ringing_tone(self):
        """German Freiton: 425 Hz, 1.0s tone, 4.0s pause."""
        self.stop_tone()
        self.stop_tone_event.clear()
        self.tone_thread = threading.Thread(
            target=self._play_tone_sd,
            args=([(config.TONE_FREQ_HZ, 1.0, 4.0)],),
            daemon=True
        )
        self.tone_thread.start()

    def start_busy_tone(self):
        """German Besetztton: 425 Hz, 0.48s tone, 0.48s pause."""
        self.stop_tone()
        self.stop_tone_event.clear()
        self.tone_thread = threading.Thread(
            target=self._play_tone_sd,
            args=([(config.TONE_FREQ_HZ, 0.48, 0.48)],),
            daemon=True
        )
        self.tone_thread.start()

    def stop_tone(self):
        self.stop_tone_event.set()
        if self.tone_thread and self.tone_thread.is_alive():
            self.tone_thread.join(timeout=0.4)
        self.tone_thread = None

    def play_raw_audio(self, audio_bytes: bytes, sample_rate: int = None):
        """Plays 16-bit PCM or WAV audio through speaker."""
        self.stop_tone()
        rate = sample_rate or self.sample_rate
        # Check if WAV header is present (RIFF)
        if audio_bytes.startswith(b'RIFF'):
            import io, soundfile as sf
            data, sr = sf.read(io.BytesIO(audio_bytes), dtype='float32')
            sd.play(data, samplerate=sr, blocking=True)
            return

        # Raw int16 PCM
        int16_arr = np.frombuffer(audio_bytes, dtype=np.int16)
        float_arr = (int16_arr / 32768.0).astype(np.float32)
        sd.play(float_arr, samplerate=rate, blocking=True)

    def record_chunk(self, duration_sec: float) -> bytes:
        """Records a chunk of audio as 16-bit PCM."""
        frames = int(self.sample_rate * duration_sec)
        rec = sd.rec(frames, samplerate=self.sample_rate, channels=1, dtype='int16', blocking=True)
        return rec.tobytes()

    def close(self):
        self.stop_tone()
        if self.pa:
            self.pa.terminate()
