"""Main application orchestrator for FeTAp 791 Rotary Phone AI Agent."""

import time
import sys
import logging
import threading
from enum import Enum, auto

import config
from audio_io import TelephoneAudio
from hardware_controller import FeTApHardware
from gemini_voice import GeminiVoiceSession

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("FeTAp791")

class PhoneState(Enum):
    ON_HOOK = auto()        # Cradle down, system quiescent
    OFF_HOOK = auto()       # Cradle lifted, playing dial tone (Wählton)
    DIALING = auto()        # User is rotating dial, dial tone silenced
    CONNECTING = auto()     # Ringing tone (Freiton)
    CONNECTED = auto()      # In conversation with Gemini AI
    BUSY = auto()           # Error or invalid number, playing busy tone (Besetztton)

class FeTApApp:
    def __init__(self):
        self.state = PhoneState.ON_HOOK
        self.audio = TelephoneAudio()
        self.hardware = FeTApHardware(
            on_hook_change=self.on_hook_event,
            on_digit_dialed=self.on_digit_event,
            on_dial_start=self.on_dial_start_event
        )
        self.voice_session = None
        self.listen_thread = None
        self.stop_listen_event = threading.Event()

    def on_hook_event(self, is_off_hook: bool):
        if is_off_hook:
            logger.info(">>> Handset picked up")
            self.state = PhoneState.OFF_HOOK
            self.audio.start_dial_tone()
        else:
            logger.info("<<< Handset hung up")
            self.state = PhoneState.ON_HOOK
            self.stop_conversation()
            self.audio.stop_tone()

    def on_dial_start_event(self):
        if self.state in (PhoneState.OFF_HOOK, PhoneState.BUSY):
            logger.info("Dial wheel turned; silencing dial/busy tone.")
            self.state = PhoneState.DIALING
            self.audio.stop_tone()

    def on_digit_event(self, digit: int):
        logger.info(f"Digit dialed: {digit}")
        if self.state != PhoneState.DIALING and self.state != PhoneState.OFF_HOOK:
            return

        if digit == 1:
            logger.info("Number '1' selected! Connecting to Gemini AI Agent...")
            self.state = PhoneState.CONNECTING
            self.audio.start_ringing_tone()
            # Simulate a brief ring-back before AI answers
            threading.Timer(2.0, self.start_conversation).start()
        else:
            logger.warning(f"Unassigned number: {digit}. Playing busy tone.")
            self.state = PhoneState.BUSY
            self.audio.start_busy_tone()

    def start_conversation(self):
        if self.state != PhoneState.CONNECTING:
            return
        self.state = PhoneState.CONNECTED
        self.audio.stop_tone()
        logger.info("Connected to Gemini Agent. Starting speech loop.")

        try:
            self.voice_session = GeminiVoiceSession(self.audio)
            self.voice_session.start()
        except Exception as e:
            logger.error(f"Failed to initialize Gemini session: {e}")
            self.state = PhoneState.BUSY
            self.audio.start_busy_tone()
            return

        # Play greeting
        self.voice_session.play_tts_text("Hallo! Hier ist dein Telefonassistent. Was kann ich für dich tun?")

        # Start continuous voice listening loop
        self.stop_listen_event.clear()
        self.listen_thread = threading.Thread(target=self._speech_loop, daemon=True)
        self.listen_thread.start()

    def _speech_loop(self):
        """Monitors handset microphone, detects voice activity, and queries Gemini."""
        mic_stream = self.audio.open_record_stream()
        silence_threshold = 1200  # Adjust for handset mic sensitivity
        max_silence_duration = 1.4  # Seconds of silence after speech to consider turn finished
        min_speech_duration = 0.5

        logger.info("Handset microphone active. Listening...")

        while not self.stop_listen_event.is_set() and self.state == PhoneState.CONNECTED:
            recorded_chunks = []
            has_speech = False
            silence_start = None

            while not self.stop_listen_event.is_set() and self.state == PhoneState.CONNECTED:
                try:
                    data = mic_stream.read(config.AUDIO_CHUNK_SIZE, exception_on_overflow=False)
                except Exception:
                    continue

                # Measure RMS volume
                count = len(data) // 2
                shorts = [int.from_bytes(data[i*2:(i+1)*2], byteorder='little', signed=True) for i in range(count)]
                rms = (sum(s * s for s in shorts) / count) ** 0.5

                if rms > silence_threshold:
                    if not has_speech:
                        logger.info("Speech detected, recording turn...")
                        has_speech = True
                    recorded_chunks.append(data)
                    silence_start = None
                elif has_speech:
                    recorded_chunks.append(data)
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= max_silence_duration:
                        # User stopped speaking
                        break

            if has_speech and recorded_chunks and self.state == PhoneState.CONNECTED:
                audio_bytes = b"".join(recorded_chunks)
                duration = len(audio_bytes) / (config.AUDIO_SAMPLE_RATE * 2)
                if duration >= min_speech_duration:
                    logger.info(f"Captured {duration:.2f}s of audio, querying Gemini...")
                    self.voice_session.run_turn(audio_bytes)

        mic_stream.stop_stream()
        mic_stream.close()

    def stop_conversation(self):
        self.stop_listen_event.set()
        if self.voice_session:
            self.voice_session.stop()
            self.voice_session = None

    def run(self):
        logger.info("FeTAp 791 AI Phone is ready.")
        logger.info("Lift the handset and dial '1' to speak to Gemini.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down FeTAp 791...")
        finally:
            self.stop_conversation()
            self.audio.close()
            self.hardware.cleanup()

if __name__ == "__main__":
    app = FeTApApp()
    app.run()
