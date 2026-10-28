"""Full Real-Time Bidirectional Gemini Live Audio Streamer.

Uses:
- Model: gemini-2.5-flash-native-audio-latest (Gemini Live)
- Local VAD + Explicit Activity Signaling (activity_start / activity_end)
- Non-blocking audio output queue for ultra-smooth 24kHz native playback
- Authentic FeTAp 791 telephone experience (dial tone, ringing, live conversation)
"""

import asyncio
import sys
import queue
import time
import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
import config

LIVE_MODEL = "gemini-2.5-flash-native-audio-latest"
SAMPLE_RATE_IN = 16000     # Gemini Live expects 16kHz PCM
SAMPLE_RATE_OUT = 24000    # Gemini Live returns 24kHz raw PCM audio

async def run_live_phone():
    print("=" * 65)
    print("📞 FeTAp 791 - GEMINI LIVE REALTIME VOICE ASSISTANT")
    print("=" * 65)

    # 1. Non-blocking audio output queue for sounddevice
    spk_queue = queue.Queue()

    def spk_callback(outdata, frames, time_info, status):
        try:
            data = spk_queue.get_nowait()
            if len(data) < len(outdata):
                outdata[:len(data)] = data
                outdata[len(data):].fill(0)
            else:
                outdata[:] = data[:len(outdata)]
        except queue.Empty:
            outdata.fill(0)

    out_stream = sd.OutputStream(
        samplerate=SAMPLE_RATE_OUT,
        channels=1,
        dtype='int16',
        blocksize=1024,
        callback=spk_callback
    )
    out_stream.start()

    # 2. Configure Gemini Live with explicit activity signaling
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    
    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
        ),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
        system_instruction=types.Content(
            parts=[
                types.Part.from_text(
                    text=(
                        "Du bist ein intelligenter persönlicher Assistent an einem Vintage Wählscheibentelefon "
                        "(FeTAp 791). Du sprichst fließend Deutsch. Antworte direkt, natürlich und freundlich "
                        "wie in einem echten Telefongespräch. Halte dich kurz und prägnant (1 bis 2 Sätze)."
                    )
                )
            ]
        )
    )

    print(f"Connecting to Gemini Live ({LIVE_MODEL})...")

    async with client.aio.live.connect(model=LIVE_MODEL, config=live_config) as session:
        print("\n✅ CONNECTED TO GEMINI LIVE!")

        # Start background receive task
        async def receive_loop():
            try:
                async for response in session.receive():
                    sc = response.server_content
                    if sc and sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data:
                                pcm_chunk = np.frombuffer(part.inline_data.data, dtype=np.int16)
                                for i in range(0, len(pcm_chunk), 1024):
                                    chunk = pcm_chunk[i:i+1024]
                                    if len(chunk) < 1024:
                                        chunk = np.pad(chunk, (0, 1024 - len(chunk)))
                                    spk_queue.put(chunk.reshape(-1, 1))
            except asyncio.CancelledError:
                pass

        recv_task = asyncio.create_task(receive_loop())

        # Greeting
        print("Gemini is answering the call...")
        await session.send_client_content(
            turns=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Nimm den Telefonhörer ab und begrüße den Anrufer kurz auf Deutsch.")]
                )
            ],
            turn_complete=True
        )

        print("\n" + "=" * 65)
        print("🎙️ LIVE MICROPHONE ACTIVE: Speak into your mic!")
        print("   Gemini will listen and answer automatically as soon as you pause.")
        print("   Press Ctrl+C to hang up.")
        print("=" * 65 + "\n")

        # Local Voice Detection Parameters
        silence_threshold = 450
        silence_duration_stop = 1.1
        min_speech_duration = 0.5
        chunk_size = 1024

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE_IN, channels=1, dtype='int16', device=1, blocksize=chunk_size) as mic:
                while True:
                    # Wait for speech to start
                    speaking = False
                    speech_frames = []
                    silence_start = None

                    while True:
                        data, _ = mic.read(chunk_size)
                        samples = data[:, 0]
                        rms = float(np.sqrt(np.mean(samples.astype(float)**2)))

                        if rms > silence_threshold:
                            if not speaking:
                                print("\n[🗣️ You are speaking...]", end="", flush=True)
                                speaking = True
                                # Signal Gemini that user started speaking
                                await session.send_realtime_input(activity_start=types.ActivityStart())
                            speech_frames.append(data.copy())
                            silence_start = None
                        elif speaking:
                            speech_frames.append(data.copy())
                            if silence_start is None:
                                silence_start = time.time()
                            elif time.time() - silence_start >= silence_duration_stop:
                                print(" [Done speaking!]")
                                break

                    # Stream buffered audio to Gemini Live
                    if speaking and speech_frames:
                        all_audio = np.concatenate(speech_frames, axis=0)
                        duration = len(all_audio) / SAMPLE_RATE_IN
                        if duration >= min_speech_duration:
                            raw_bytes = all_audio.tobytes()
                            for offset in range(0, len(raw_bytes), chunk_size * 2):
                                sub_chunk = raw_bytes[offset:offset + (chunk_size * 2)]
                                await session.send_realtime_input(
                                    audio=types.Blob(data=sub_chunk, mime_type="audio/pcm;rate=16000")
                                )
                            # Signal Gemini that user finished speaking
                            await session.send_realtime_input(activity_end=types.ActivityEnd())
                            print("[⏳ Gemini is responding...]")

        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nHanging up...")
        finally:
            recv_task.cancel()
            out_stream.stop()
            out_stream.close()

if __name__ == "__main__":
    try:
        asyncio.run(run_live_phone())
    except KeyboardInterrupt:
        print("\nCall ended.")
