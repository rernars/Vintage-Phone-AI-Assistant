"""Quick 1-turn automated voice test."""
import time
import sounddevice as sd
from audio_io import TelephoneAudio
from gemini_voice import GeminiVoiceSession

def main():
    print("Testing audio output and Gemini API connection...")
    audio = TelephoneAudio()
    session = GeminiVoiceSession(audio)
    session.start()
    
    print("1. Playing greeting TTS...")
    session.speak("Hallo! Dein Telefonassistent ist bereit.")
    
    print("2. Recording 3 seconds of audio from your microphone... Speak something now!")
    chunk = audio.record_chunk(duration_sec=3.0)
    
    print("3. Querying Gemini with your voice recording...")
    session.run_turn(chunk)
    
    print("Done!")

if __name__ == "__main__":
    main()
