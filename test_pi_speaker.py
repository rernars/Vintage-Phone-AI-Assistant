#!/usr/bin/env python3
"""Diagnostic script to test and find the active speaker on Raspberry Pi."""

import sys
import time
import numpy as np
import sounddevice as sd

print("=" * 60)
print("🔍 SOUNDDEVICE AUDIO DIAGNOSTIC")
print("=" * 60)

devices = sd.query_devices()
for idx, d in enumerate(devices):
    print(f"[{idx}] {d['name']} (In: {d['max_input_channels']}, Out: {d['max_output_channels']}, Default SR: {d['default_samplerate']})")

print("\nCurrent Default Device:", sd.default.device)

# Unmute mixer
import subprocess
for c in ["Master", "Speaker", "Headphone", "PCM", "Playback"]:
    subprocess.run(["amixer", "sset", c, "100%", "unmute"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Test tone: 440 Hz beep
sr = 48000
duration = 1.5
t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
tone = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

# Play on all devices with output channels
print("\n🔊 Testing playback on each available output device...")
for idx, d in enumerate(devices):
    if d['max_output_channels'] > 0:
        print(f"\n--> Playing 1.5s beep on Device [{idx}] '{d['name']}'...")
        try:
            sd.play(tone, samplerate=sr, device=idx, blocking=True)
            print(f"    Finished playing on Device [{idx}]. Did you hear it?")
        except Exception as e:
            # Try 44100
            try:
                t2 = np.linspace(0, duration, int(44100 * duration), endpoint=False, dtype=np.float32)
                tone2 = (0.5 * np.sin(2 * np.pi * 440 * t2)).astype(np.float32)
                sd.play(tone2, samplerate=44100, device=idx, blocking=True)
                print(f"    Finished playing on Device [{idx}] at 44.1kHz.")
            except Exception as e2:
                print(f"    Failed on Device [{idx}]: {e2}")

print("\nDone testing.")
