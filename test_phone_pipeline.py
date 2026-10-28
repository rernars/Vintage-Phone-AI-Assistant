"""Interactive Voice Assistant Pipeline with Native Gemini Voice."""

import time
import math
import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
import config
from gemini_voice import GeminiVoiceSession
from audio_io import TelephoneAudio

def main():
    print("=" * 65)
    print("📞 FeTAp 791 Rotary Phone - 100% NATIVE GEMINI VOICE")
    print("=" * 65)

    audio = TelephoneAudio()
    session = GeminiVoiceSession(audio)
    session.start()

    print("\n[🔊 Handset Lifted]: Playing German 425 Hz dial tone...")
    audio.start_dial_tone()
    time.sleep(1.5)
    
    print("\n[📞 Dialing 1]: Ringing...")
    audio.start_ringing_tone()
    time.sleep(1.5)
    audio.stop_tone()

    # Gemini answers with its real native voice!
    session.speak("Hallo! Hier ist dein Wählscheibentelefon. Ich höre dich, wie kann ich dir helfen?")

    # Voice loop with automatic speech detection (VAD)
    silence_threshold = 400   # Sensitivity for mic
    silence_timeout = 1.2     # seconds of silence to trigger response
    min_speech_duration = 0.5
    input_device = 1          # MacBook Pro-Mikrofon

    print("\n" + "=" * 65)
    print("🎙️ MICROPHONE IS LISTENING: Speak into your mic anytime!")
    print("   When you stop talking, Gemini will reply with its native voice.")
    print("   Press Ctrl+C to hang up.")
    print("=" * 65 + "\n")

    try:
        while True:
            chunk_size = 1024
            recorded_chunks = []
            speaking = False
            silence_start = None

            with sd.InputStream(samplerate=16000, channels=1, dtype='int16', device=input_device, blocksize=chunk_size) as stream:
                while True:
                    data, overflowed = stream.read(chunk_size)
                    samples = data[:, 0]
                    rms = float(np.sqrt(np.mean(samples.astype(float)**2)))

                    if rms > silence_threshold:
                        if not speaking:
                            print("\n[🗣️ You started speaking...]", end="", flush=True)
                            speaking = True
                        recorded_chunks.append(data.copy())
                        silence_start = None
                    elif speaking:
                        recorded_chunks.append(data.copy())
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start >= silence_timeout:
                            print(" [Done speaking!]")
                            break

            if speaking and recorded_chunks:
                all_samples = np.concatenate(recorded_chunks, axis=0)
                duration = len(all_samples) / 16000
                if duration >= min_speech_duration:
                    print(f"[⏳ Sending audio to Gemini...]")
                    session.run_turn(all_samples.tobytes())
                    print("\n🎙️ Listening again...")

    except KeyboardInterrupt:
        print("\n\n[Handset Replaced]: Call ended.")
    finally:
        session.stop()
        audio.close()

if __name__ == "__main__":
    main()
