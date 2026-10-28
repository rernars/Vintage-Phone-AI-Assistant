"""Test script to record 3 seconds and playback immediately."""
import sounddevice as sd
import numpy as np

print("Recording 3 seconds from microphone (Index 1: MacBook Pro-Mikrofon)...")
rec = sd.rec(16000 * 3, samplerate=16000, channels=1, dtype="int16", device=1, blocking=True)
rms = float(np.sqrt(np.mean(rec.astype(float)**2)))
max_val = int(np.max(np.abs(rec)))

print(f"Recorded! Max amplitude: {max_val}, RMS volume: {rms}")
if max_val == 0:
    print("❌ Silence! Microphone is muted or macOS privacy blocked it.")
else:
    print("🔊 Playing back recorded audio...")
    sd.play(rec, samplerate=16000, blocking=True)
    print("Done!")
