#!/usr/bin/env python3
"""FeTAp 791 Rotary Phone AI Assistant for Raspberry Pi 3B.

Integrates:
- Hook switch (Gabelumschalter) on GPIO 17
- Rotary dial (Nummernschalter NS 38: nsi on GPIO 22, nsa on GPIO 27)
  OR modern rotary encoder
- USB Sound Card (Microphone & Handset Speaker)
- Authentic German Federal Post (Deutsche Bundespost) tones (Wählton, Freiton, Besetztton)
- Hands-Free Gemini 3.8 Live Voice Chat (VAD speech detection & native audio)
"""

import asyncio
import os
import sys
import time
import threading
import logging
import queue
from collections import deque
from typing import Optional, List
import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types

# Auto-load .env file if present
from pathlib import Path
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    except Exception:
        pass

API_KEY = os.getenv("GEMINI_API_KEY", "")

# ---------------------------------------------------------------------------
# Hardware & Audio Configuration
# ---------------------------------------------------------------------------
GPIO_HOOK = 17       # Pin 11: Hook switch (Gabel). Connect to GND.
HOOK_INVERTED = True # True: Handset on cradle presses switch; Handset lifted releases switch.
GPIO_DIAL_NSI = 22   # Pin 15: Rotary dial pulse contact (nsi / CLK). Connect to GND.
GPIO_DIAL_NSA = 27   # Pin 13: Rotary dial off-normal contact (nsa / DT). Connect to GND.

# Audio sampling
SAMPLE_RATE_IN = 16000    # Mic capture rate (16 kHz for Gemini)
SAMPLE_RATE_OUT = 24000   # Gemini native audio output rate (24 kHz)
CHUNK_SIZE = 1024

# Volume levels (adjustable for your handset earpiece)
VOLUME_SPEECH = 0.9       # Gentle, clear volume for handset earpiece
VOLUME_TONES = 0.12       # Subtle dial and ringing tones (425 Hz)

def unmute_system_audio():
    """Unmutes ALSA hardware mixer and sets volume to a comfortable 75%."""
    import subprocess
    for control in ["Master", "Speaker", "Headphone", "PCM", "Playback"]:
        try:
            subprocess.run(["amixer", "sset", control, "75%", "unmute"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

# Voice Activity Detection (VAD) - Dual-threshold Hysteresis
TRIGGER_THRESHOLD = 520   # RMS to START speaking (avoids background noise)
HOLD_THRESHOLD = 320      # Lower RMS to KEEP speaking (prevents cutting off on quiet syllables)
SILENCE_TIMEOUT = 1.0     # 1.0s of sustained silence required before finalizing turn (comfortable human pause)
MIN_SPEECH_DURATION = 0.35 # Minimum seconds of speech to send
PRE_SPEECH_CHUNKS = 5     # Pre-speech audio ring-buffer (~320ms) to keep first syllable

class StreamingAudioPlayer:
    """Non-blocking background audio streamer.
    Plays Gemini voice chunks immediately as they arrive over the WebSocket,
    without waiting for the full turn to finish, and keeps asyncio event loop free."""
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.is_playing = threading.Event()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        try:
            with sd.OutputStream(samplerate=self.sample_rate, channels=1, dtype="float32") as stream:
                while not self.stop_event.is_set():
                    try:
                        chunk = self.queue.get(timeout=0.04)
                    except queue.Empty:
                        continue
                    if chunk is not None and len(chunk) > 0:
                        self.is_playing.set()
                        stream.write(chunk)
                    if self.queue.empty():
                        self.is_playing.clear()
        except Exception as e:
            logger.debug(f"Streaming player worker ended: {e}")

    def play_chunk(self, float_samples: np.ndarray):
        self.is_playing.set()
        self.queue.put(float_samples)

    def is_busy(self) -> bool:
        return self.is_playing.is_set() or not self.queue.empty()

    def clear(self):
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
        self.is_playing.clear()

    def close(self):
        self.stop_event.set()
        self.clear()

# Tone frequencies (German Post standard)
TONE_FREQ_HZ = 425

# Gemini Model and Multilingual Language Profiles
GEMINI_MODEL = "gemini-3.8-live"

LANGUAGE_PROFILES = {
    1: {
        "name": "Deutsch",
        "voice": "Aoede",
        "system_prompt": (
            "Du bist ein intelligenter, sympathischer Assistent an einem historischen deutschen "
            "Wählscheibentelefon (FeTAp 791). Antworte stets sympathisch, klar, prägnant "
            "und kurz auf Deutsch (maximal 1 bis 2 Sätze), passend zu einem authentischen Telefonat."
        ),
    },
    2: {
        "name": "English",
        "voice": "Puck",
        "system_prompt": (
            "You are a friendly, intelligent personal assistant reached through a vintage rotary telephone. "
            "Always respond naturally, clearly, and concisely in English (maximum 1 to 2 sentences), like in a real phone conversation."
        ),
    },
    3: {
        "name": "Türkçe",
        "voice": "Kore",
        "system_prompt": (
            "Sen tarihi bir çevirmeli telefonda (FeTAp 791) hizmet veren samimi ve zeki bir kişisel asistansın. "
            "Her zaman dostça, net ve kısa bir şekilde Türkçe olarak (en fazla 1-2 cümle) gerçek bir telefon görüşmesi gibi yanıt ver."
        ),
    }
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("FeTAp791")

def configure_usb_audio():
    """Finds USB audio device index and sets it as the default input and output."""
    try:
        devices = sd.query_devices()
        usb_in = None
        usb_out = None
        for idx, dev in enumerate(devices):
            name = dev.get("name", "").lower()
            # Common USB soundcard naming: 'usb', 'c-media', 'audio device', 'headset'
            if any(k in name for k in ["usb", "c-media", "dongle", "card"]):
                if dev.get("max_input_channels", 0) > 0 and usb_in is None:
                    usb_in = idx
                if dev.get("max_output_channels", 0) > 0 and usb_out is None:
                    usb_out = idx

        if usb_in is not None or usb_out is not None:
            cur_in, cur_out = sd.default.device
            target_in = usb_in if usb_in is not None else cur_in
            target_out = usb_out if usb_out is not None else cur_out
            sd.default.device = (target_in, target_out)
            logger.info(f"🎧 Bound to USB Audio Device: Input={target_in} ({devices[target_in]['name']}), Output={target_out} ({devices[target_out]['name']})")
        else:
            logger.info(f"Using default system audio devices: {sd.default.device}")
    except Exception as e:
        logger.warning(f"Could not scan audio devices: {e}")

configure_usb_audio()

def detect_audio_hardware():
    """Detects supported sample rates on current audio card (handles 48kHz USB cards)."""
    in_rate = 16000
    for r in [16000, 48000, 44100]:
        try:
            sd.check_input_settings(samplerate=r, channels=1, dtype="int16")
            in_rate = r
            break
        except Exception:
            continue

    out_rate = 24000
    for r in [24000, 48000, 44100]:
        try:
            sd.check_output_settings(samplerate=r, channels=1, dtype="float32")
            out_rate = r
            break
        except Exception:
            continue

    logger.info(f"Hardware Audio Rates detected: Mic capture={in_rate} Hz, Speaker={out_rate} Hz")
    return in_rate, out_rate

HW_RATE_IN, HW_RATE_OUT = detect_audio_hardware()

def resample_to_16k(audio_arr: np.ndarray, orig_rate: int) -> np.ndarray:
    """Downsamples captured audio to 16 kHz PCM for Gemini."""
    if orig_rate == 16000:
        return audio_arr
    elif orig_rate == 48000:
        return audio_arr[::3]
    elif orig_rate == 44100:
        indices = np.round(np.linspace(0, len(audio_arr) - 1, int(len(audio_arr) * 16000 / 44100))).astype(int)
        return audio_arr[indices]
    return audio_arr

def resample_from_24k(audio_arr: np.ndarray, target_rate: int) -> np.ndarray:
    """Upsamples Gemini 24 kHz audio to hardware output rate (e.g. 48 kHz)."""
    if target_rate == 24000:
        return audio_arr
    elif target_rate == 48000:
        return np.repeat(audio_arr, 2)
    elif target_rate == 44100:
        indices = np.round(np.linspace(0, len(audio_arr) - 1, int(len(audio_arr) * 44100 / 24000))).astype(int)
        return audio_arr[indices]
    return audio_arr

# Check for GPIO
try:
    from gpiozero import Button
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("gpiozero not found. Running in simulation mode (PC/Mac).")


# ---------------------------------------------------------------------------
# Tone Generator (Wählton, Freiton, Besetztton)
# ---------------------------------------------------------------------------
class TonePlayer:
    """Non-blocking tone generator using sounddevice."""

    def __init__(self, sample_rate=HW_RATE_OUT):
        self.sample_rate = sample_rate
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def _play_pattern(self, pattern: List[tuple[float, float, float]]):
        """Pattern is list of (freq_hz, sound_duration_sec, pause_duration_sec)."""
        try:
            with sd.OutputStream(samplerate=self.sample_rate, channels=1, dtype="float32") as stream:
                while not self.stop_event.is_set():
                    for freq, sound_len, pause_len in pattern:
                        if self.stop_event.is_set():
                            break
                        if sound_len > 0:
                            t = np.linspace(0, sound_len, int(self.sample_rate * sound_len), endpoint=False, dtype=np.float32)
                            samples = (VOLUME_TONES * np.sin(2 * np.pi * freq * t)).astype(np.float32)
                            step = int(self.sample_rate * 0.05)
                            for i in range(0, len(samples), step):
                                if self.stop_event.is_set():
                                    break
                                stream.write(samples[i:i + step])
                        if pause_len > 0 and not self.stop_event.is_set():
                            silence = np.zeros(int(self.sample_rate * pause_len), dtype=np.float32)
                            step = int(self.sample_rate * 0.05)
                            for i in range(0, len(silence), step):
                                if self.stop_event.is_set():
                                    break
                                stream.write(silence[i:i + step])
        except Exception as e:
            logger.debug(f"Tone playback stopped: {e}")

    def start_dial_tone(self):
        """Continuous 425 Hz German dial tone (Wählton)."""
        self.stop()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._play_pattern, args=([(TONE_FREQ_HZ, 1.0, 0.0)],), daemon=True)
        self.thread.start()

    def start_ringing_tone(self):
        """German ringing tone (Freiton): 1s tone, 4s pause."""
        self.stop()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._play_pattern, args=([(TONE_FREQ_HZ, 1.0, 4.0)],), daemon=True)
        self.thread.start()

    def start_busy_tone(self):
        """German busy tone (Besetztton): 0.48s tone, 0.48s pause."""
        self.stop()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._play_pattern, args=([(TONE_FREQ_HZ, 0.48, 0.48)],), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.3)
        self.thread = None


# ---------------------------------------------------------------------------
# FeTAp 791 Hardware Driver (Hook Switch & Rotary Dial)
# ---------------------------------------------------------------------------
class HardwareInterface:
    def __init__(self, on_off_hook, on_on_hook, on_digit):
        self.on_off_hook = on_off_hook
        self.on_on_hook = on_on_hook
        self.on_digit = on_digit

        self.pulse_count = 0
        self.dial_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

        if GPIO_AVAILABLE:
            # Hook switch: contact to GND with pull-up.
            self.hook = Button(GPIO_HOOK, pull_up=True, bounce_time=0.05)
            if HOOK_INVERTED:
                # Handset on cradle presses switch -> on_hook
                # Handset lifted releases switch -> off_hook
                self.hook.when_released = self._hook_off
                self.hook.when_pressed = self._hook_on
            else:
                self.hook.when_pressed = self._hook_off
                self.hook.when_released = self._hook_on

            # Rotary dial pulse (nsi)
            self.nsi = Button(GPIO_DIAL_NSI, pull_up=True, bounce_time=0.02)
            self.nsi.when_pressed = self._nsi_pulse

            # Rotary dial active (nsa)
            self.nsa = Button(GPIO_DIAL_NSA, pull_up=True, bounce_time=0.05)
            logger.info(f"GPIO hardware initialized (Hook: GPIO17 [inverted={HOOK_INVERTED}], NSI: GPIO22, NSA: GPIO27).")
        else:
            self.hook = None
            self.nsi = None
            self.nsa = None

    @property
    def is_off_hook(self) -> bool:
        if GPIO_AVAILABLE and self.hook:
            return not self.hook.is_pressed if HOOK_INVERTED else self.hook.is_pressed
        return True

    def _hook_off(self):
        logger.info("📞 Handset LIFTED (Off-Hook)")
        self.on_off_hook()

    def _hook_on(self):
        logger.info("📴 Handset PLACED ON CRADLE (On-Hook)")
        with self._lock:
            if self.dial_timer:
                self.dial_timer.cancel()
                self.dial_timer = None
            self.pulse_count = 0
        self.on_on_hook()

    def _nsi_pulse(self):
        with self._lock:
            self.pulse_count += 1
            if self.dial_timer:
                self.dial_timer.cancel()
            # 0.45s after last pulse = digit finished
            self.dial_timer = threading.Timer(0.45, self._finalize_digit)
            self.dial_timer.start()

    def _finalize_digit(self):
        with self._lock:
            count = self.pulse_count
            self.pulse_count = 0
            self.dial_timer = None

        if count == 0:
            return
        # 10 pulses = 0 in German pulse dialing
        digit = 0 if count == 10 else count
        logger.info(f"🔢 Dialed digit recognized: {digit}")
        self.on_digit(digit)


# ---------------------------------------------------------------------------
# FeTAp 791 Main Application Controller
# ---------------------------------------------------------------------------
class FeTApLiveApp:
    def __init__(self):
        self.tones = TonePlayer()
        self.loop = asyncio.get_event_loop()
        self.current_call_task: Optional[asyncio.Task] = None
        self.call_active = False
        self.auto_connect_timer: Optional[threading.Timer] = None

        self.hardware = HardwareInterface(
            on_off_hook=self.handle_off_hook,
            on_on_hook=self.handle_on_hook,
            on_digit=self.handle_digit
        )

    def handle_off_hook(self):
        """Called immediately when user lifts handset."""
        self.tones.start_dial_tone()
        # If user doesn't dial within 4 seconds, auto-connect to Gemini
        if self.auto_connect_timer:
            self.auto_connect_timer.cancel()
        self.auto_connect_timer = threading.Timer(4.0, self._auto_connect)
        self.auto_connect_timer.start()

    def handle_on_hook(self):
        """Called immediately when handset is placed down."""
        if self.auto_connect_timer:
            self.auto_connect_timer.cancel()
            self.auto_connect_timer = None

        self.tones.stop()
        self.call_active = False

        if self.current_call_task and not self.current_call_task.done():
            logger.info("Terminating active Gemini Live call...")
            self.loop.call_soon_threadsafe(self.current_call_task.cancel)
            self.current_call_task = None

    def _auto_connect(self):
        if self.hardware.is_off_hook and not self.call_active:
            logger.info("Auto-dial timer expired -> Connecting to Gemini Live automatically.")
            self.handle_digit(1)

    def handle_digit(self, digit: int):
        """Handles dialed number (e.g. 1 = Gemini Live)."""
        if self.auto_connect_timer:
            self.auto_connect_timer.cancel()
            self.auto_connect_timer = None

        self.tones.stop()

        if self.call_active:
            logger.info(f"Ignored digit {digit} (call already in progress).")
            return

        if digit in (1, 2, 3, 4, 5, 6, 7, 8, 9, 0):
            # Play ringing tone (Freiton) briefly
            self.tones.start_ringing_tone()
            # Start call asynchronously on event loop
            self.current_call_task = self.loop.create_task(self._start_gemini_call(digit))
        else:
            self.tones.start_busy_tone()

    async def _start_gemini_call(self, dialed_digit: int):
        self.call_active = True
        api_key = API_KEY or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            logger.error("GEMINI_API_KEY is not set!")
            self.tones.start_busy_tone()
            self.call_active = False
            return

        client = genai.Client(api_key=api_key)

        # Select language profile: 1=Deutsch, 2=English, 3=Türkçe (defaults to Deutsch)
        profile = LANGUAGE_PROFILES.get(dialed_digit, LANGUAGE_PROFILES[1])
        lang_name = profile["name"]
        voice_name = profile["voice"]
        system_prompt = profile["system_prompt"]

        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=system_prompt)]
            )
        )

        try:
            # Simulate ringing for 1.5 seconds
            await asyncio.sleep(1.5)
            self.tones.stop()

            if not self.hardware.is_off_hook:
                return

            logger.info(f"Connecting to {GEMINI_MODEL} Live for [{lang_name}] with voice '{voice_name}'...")
            player = StreamingAudioPlayer(sample_rate=HW_RATE_OUT)
            try:
                async with client.aio.live.connect(model=GEMINI_MODEL, config=live_config) as session:
                    logger.info(f"✅ Call established with Gemini in [{lang_name}]! Microphone is active.")

                    mic_chunk = int(CHUNK_SIZE * (HW_RATE_IN / 16000))
                    recent_frames = deque(maxlen=PRE_SPEECH_CHUNKS)

                    with sd.InputStream(samplerate=HW_RATE_IN, channels=1, dtype="int16", blocksize=mic_chunk) as mic:
                        while self.call_active and self.hardware.is_off_hook:
                            speaking = False
                            speech_frames = []
                            silence_start = None

                            # VAD listening loop with Schmitt-Trigger Hysteresis
                            while self.call_active and self.hardware.is_off_hook:
                                data, _ = mic.read(mic_chunk)
                                samples = data[:, 0]
                                rms = float(np.sqrt(np.mean(samples.astype(float) ** 2)))

                                if not speaking:
                                    # Require TRIGGER_THRESHOLD to start recording
                                    if rms >= TRIGGER_THRESHOLD:
                                        print(f" [🗣️ {lang_name} speaking...]", end="", flush=True)
                                        speaking = True
                                        speech_frames = list(recent_frames)  # Include pre-speech lead-in!
                                        speech_frames.append(samples.copy())
                                        silence_start = None
                                    else:
                                        recent_frames.append(samples.copy())
                                else:
                                    # Already speaking: keep recording
                                    speech_frames.append(samples.copy())
                                    if rms >= HOLD_THRESHOLD:
                                        # Active or quiet syllables -> keep turn active, reset silence timer
                                        silence_start = None
                                    else:
                                        # Below hold threshold -> start/check silence countdown
                                        if silence_start is None:
                                            silence_start = time.time()
                                        elif time.time() - silence_start >= SILENCE_TIMEOUT:
                                            print(" [Done]")
                                            break
                                await asyncio.sleep(0.001)

                            if not self.call_active or not self.hardware.is_off_hook:
                                break

                            # Process speech turn
                            if speaking and speech_frames:
                                raw_audio = np.concatenate(speech_frames)
                                audio_16k = resample_to_16k(raw_audio, HW_RATE_IN)
                                duration = len(audio_16k) / SAMPLE_RATE_IN
                                if duration >= MIN_SPEECH_DURATION:
                                    logger.info(f"Sending {duration:.1f}s audio turn to Gemini...")
                                    await session.send_client_content(
                                        turns=[
                                            types.Content(
                                                role="user",
                                                parts=[types.Part.from_bytes(data=audio_16k.astype(np.int16).tobytes(), mime_type="audio/pcm;rate=16000")]
                                            )
                                        ],
                                        turn_complete=True
                                    )

                                    # Stream Gemini's audio chunks into player immediately as they arrive
                                    started_playback = False
                                    async for response in session.receive():
                                        if not self.call_active or not self.hardware.is_off_hook:
                                            break
                                        sc = response.server_content
                                        if sc and sc.model_turn:
                                            for part in sc.model_turn.parts:
                                                if part.inline_data and part.inline_data.data:
                                                    if not started_playback:
                                                        logger.info("🔊 Gemini reply started streaming...")
                                                        started_playback = True
                                                    pcm_24k = np.frombuffer(part.inline_data.data, dtype=np.int16)
                                                    pcm_out = resample_from_24k(pcm_24k, HW_RATE_OUT)
                                                    float_chunk = (pcm_out.astype(np.float32) / 32768.0) * VOLUME_SPEECH
                                                    float_chunk = np.clip(float_chunk, -1.0, 1.0)
                                                    player.play_chunk(float_chunk)
                                        if sc and sc.turn_complete:
                                            break

                                    # Wait for streaming playback queue to drain (non-blocking!)
                                    while player.is_busy() and self.call_active and self.hardware.is_off_hook:
                                        await asyncio.sleep(0.04)

                                    # Drain any acoustic echo / old frames from mic before listening again
                                    try:
                                        while mic.read_available > 0:
                                            mic.read(mic.read_available)
                                    except Exception:
                                        pass
                                    recent_frames.clear()

            finally:
                player.close()

        except asyncio.CancelledError:
            logger.info("Call ended (handset replaced).")
        except Exception as e:
            logger.error(f"Error during call: {e}")
            if self.hardware.is_off_hook:
                self.tones.start_busy_tone()
        finally:
            self.tones.stop()
            self.call_active = False

    async def run(self):
        logger.info("=" * 60)
        logger.info("☎️  FeTAp 791 Rotary Phone AI is ready on Raspberry Pi 3B!")
        logger.info("   - Lift handset to hear the dial tone.")
        logger.info("   - Dial '1' (or wait 4s) for Deutsch 🇩🇪")
        logger.info("   - Dial '2' for English 🇬🇧")
        logger.info("   - Dial '3' for Türkçe 🇹🇷")
        logger.info("   - Hang up to end the call at any time.")
        logger.info("   - Press Ctrl+C to stop.")
        logger.info("=" * 60)

        # If running on PC without GPIO for test, trigger an off-hook after 2 seconds
        if not GPIO_AVAILABLE:
            logger.info("💡 Note: Running without GPIO. Lift/hangup can be simulated.")

        while True:
            await asyncio.sleep(1)


def main():
    unmute_system_audio()
    app = FeTApLiveApp()
    try:
        app.loop.run_until_complete(app.run())
    except KeyboardInterrupt:
        logger.info("\nExiting FeTAp 791 controller.")
    finally:
        app.tones.stop()


if __name__ == "__main__":
    main()
