"""Configuration settings for FeTAp 791 Rotary Phone AI Agent."""

import os
from pathlib import Path

# Load environment variables from .env file if present
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# --- Gemini API Configuration ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.6-flash"  # Or gemini-2.0-flash
SYSTEM_INSTRUCTION = (
    "Du bist ein intelligenter persönlicher Assistent, der über ein historisches Wählscheibentelefon "
    "(Deutsche Bundespost FeTAp 791) erreichbar ist. "
    "Antworte natürlich, kurz und prägnant wie bei einem authentischen Telefongespräch. "
    "Verwende keine Emojis oder Markdown-Sonderzeichen, da der Text als Sprache ausgegeben wird."
)

# --- Raspberry Pi GPIO Pin Configuration (BCM numbering) ---
# FeTAp 791 hook switch (Gabelumschalter)
# Connected to GND and GPIO pin with internal pull-up.
# Handset on hook = contact open (3.3V / HIGH), Handset lifted = contact closed (GND / LOW)
GPIO_HOOK = 17

# FeTAp 791 Rotary Dial (Nummernschalter NS 38)
# nsi: Nummernschalter-Impulskontakt (opens on each pulse during dial return)
GPIO_DIAL_NSI = 22
# nsa: Nummernschalter-Arbeitskontakt (closes as soon as wheel is rotated away from rest)
GPIO_DIAL_NSA = 27

# Debounce & dial timings
DEBOUNCE_HOOK = 0.05
DEBOUNCE_PULSE = 0.02
DIAL_TIMEOUT = 0.45  # Seconds after last pulse to consider digit completed

# --- Audio Configuration ---
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_CHUNK_SIZE = 1024

# Authentic German Federal Post (Deutsche Bundespost) tone frequency
TONE_FREQ_HZ = 425  # Standard 425 Hz for Wählton and Freiton
