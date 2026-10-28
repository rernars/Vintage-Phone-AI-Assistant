"""Interactive PC Simulator for FeTAp 791 AI Phone.

Test dial tone, rotary dial, speech recording, and Gemini voice responses
directly on your computer without any physical telephone hardware.
"""

import time
import sys
import threading
import numpy as np

import config
from audio_io import TelephoneAudio
from gemini_voice import GeminiVoiceSession

def main():
    print("=" * 65)
    print("📞 FeTAp 791 Rotary Phone Simulator (Interactive PC Mode)")
    print("=" * 65)
    print("Commands:")
    print("  [h]      : Lift Handset (starts German 425 Hz dial tone)")
    print("  [1]      : Dial '1' (rings and connects to Gemini AI Agent)")
    print("  [t]      : Talk to Gemini (records 4 seconds from mic and answers)")
    print("  [0, 2-9] : Dial other numbers (plays German busy tone)")
    print("  [q]      : Hang up / Quit")
    print("=" * 65)

    audio = TelephoneAudio()
    voice_session = None
    is_off_hook = False
    in_conversation = False

    try:
        while True:
            prompt = "\nPhone State: [CONNECTED] Talk (t), Hang up (q) > " if in_conversation else "\nPhone Action (h: Lift, 1: Dial 1, q: Quit) > "
            cmd = input(prompt).strip().lower()

            if cmd == 'h':
                if not is_off_hook:
                    is_off_hook = True
                    print("\n[🔊 Handset lifted]: Playing German 425 Hz Wählton (Dial tone)...")
                    audio.start_dial_tone()
                else:
                    print("Handset is already lifted.")

            elif cmd == '1':
                if not is_off_hook:
                    print("Lift handset first! (type 'h')")
                    continue
                print("\n[Rotary Dial 1]: Dial tone stops. Ringing Freiton...")
                audio.start_ringing_tone()
                time.sleep(2.0)
                audio.stop_tone()

                print("[Connecting to Gemini Voice Agent...]")
                try:
                    voice_session = GeminiVoiceSession(audio)
                    voice_session.start()
                    in_conversation = True
                    print("[Connected! Speaking greeting through your speakers...]")
                    voice_session.speak("Hallo! Hier ist dein Wählscheibentelefon. Wie kann ich dir helfen?")
                    print("\n👉 Now type 't' and press Enter to talk into your microphone!")
                except Exception as e:
                    print(f"Error connecting to Gemini: {e}")
                    audio.start_busy_tone()

            elif cmd == 't':
                if not in_conversation:
                    print("You must lift the handset (h) and dial 1 first!")
                    continue
                print("\n[🎙️ Recording 4 seconds from your microphone... Speak now!]")
                pcm_audio = audio.record_chunk(duration_sec=4.0)
                print("[⏳ Querying Gemini...]")
                voice_session.run_turn(pcm_audio)

            elif cmd in ['0', '2', '3', '4', '5', '6', '7', '8', '9']:
                if is_off_hook:
                    print(f"\n[Rotary Dial {cmd}]: Unknown extension. Playing busy tone (Besetztton)...")
                    audio.start_busy_tone()
                else:
                    print("Lift handset first! (type 'h')")

            elif cmd == 'q':
                print("\n[Handset replaced on cradle]: Hanging up...")
                if voice_session:
                    voice_session.stop()
                    voice_session = None
                audio.stop_tone()
                in_conversation = False
                is_off_hook = False
                break

    finally:
        audio.close()
        print("Simulator ended.")

if __name__ == "__main__":
    main()
