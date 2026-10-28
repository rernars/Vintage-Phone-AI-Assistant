"""Clean, hands-free Gemini 3.8 Live Voice Chat.

Automatic Voice Activity Detection:
- Starts listening automatically when you speak.
- Detects when you stop speaking and sends the audio to Gemini 3.8 Live.
- Plays back Gemini 3.8 Live's native voice response.
- No buttons or Enter presses required!
"""

import asyncio
import sys
import time
import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
import config

MODEL = "gemini-3.8-live"
RATE_IN = 16000
RATE_OUT = 24000

# VAD parameters
SILENCE_THRESHOLD = 450      # RMS volume threshold to trigger speech detection
SILENCE_TIMEOUT = 1.1        # Seconds of silence after speaking to consider turn finished
MIN_SPEECH_DURATION = 0.5    # Minimum seconds of audio to send
CHUNK_SIZE = 1024

async def main():
    print("=" * 60)
    print("🎙️ GEMINI 3.8 LIVE - HANDS-FREE VOICE CONVERSATION")
    print("=" * 60)

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text="Du bist ein intelligenter, hilfsbereiter KI-Assistent. Antworte immer direkt, sympathisch und kurz auf Deutsch in 1 bis 2 Sätzen.")]
        )
    )

    print(f"Connecting to {MODEL}...")
    async with client.aio.live.connect(model=MODEL, config=live_config) as session:
        print("Connected to Gemini 3.8 Live!\n")
        print("=" * 60)
        print("🟢 MICROPHONE IS ACTIVE: Just start speaking anytime!")
        print("   When you stop talking, Gemini will automatically answer.")
        print("   Press Ctrl+C to exit.")
        print("=" * 60 + "\n")

        # Open non-blocking mic stream
        with sd.InputStream(samplerate=RATE_IN, channels=1, dtype='int16', blocksize=CHUNK_SIZE) as mic:
            while True:
                speaking = False
                speech_frames = []
                silence_start = None

                # 1. Listen loop: detect start of speech and end of speech
                while True:
                    data, _ = mic.read(CHUNK_SIZE)
                    samples = data[:, 0]
                    rms = float(np.sqrt(np.mean(samples.astype(float)**2)))

                    if rms > SILENCE_THRESHOLD:
                        if not speaking:
                            print("[🗣️ Listening... speaking detected]", end="", flush=True)
                            speaking = True
                        speech_frames.append(data.copy())
                        silence_start = None
                    elif speaking:
                        speech_frames.append(data.copy())
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start >= SILENCE_TIMEOUT:
                            print(" [Done speaking!]")
                            break

                # 2. If valid speech recorded, send turn to Gemini 3.8 Live
                if speaking and speech_frames:
                    all_audio = np.concatenate(speech_frames, axis=0)
                    duration = len(all_audio) / RATE_IN

                    if duration >= MIN_SPEECH_DURATION:
                        print(f"⏳ Sending {duration:.1f}s to Gemini 3.8 Live...")
                        await session.send_client_content(
                            turns=[
                                types.Content(
                                    role="user",
                                    parts=[types.Part.from_bytes(data=all_audio.tobytes(), mime_type="audio/pcm;rate=16000")]
                                )
                            ],
                            turn_complete=True
                        )

                        # Receive native audio stream
                        audio_chunks = []
                        async for response in session.receive():
                            sc = response.server_content
                            if sc and sc.model_turn:
                                for part in sc.model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        audio_chunks.append(part.inline_data.data)
                            if sc and sc.turn_complete:
                                break

                        if audio_chunks:
                            full_audio = b"".join(audio_chunks)
                            print(f"🔊 Gemini 3.8 Live speaking...")
                            samples = np.frombuffer(full_audio, dtype=np.int16)
                            sd.play(samples, samplerate=RATE_OUT, blocking=True)
                            print("Done.\n")
                        else:
                            print("No audio received.\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExited.")
