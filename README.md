# ☎️ FeTAp 791 - Vintage Rotary Phone AI Voice Assistant

Turn a classic **Deutsche Bundespost FeTAp 791**(or any)  rotary telephone into an interactive, real-time AI voice assistant powered by **Google Gemini 3.8 Live** running on a **Raspberry Pi 3B** (probably a little overkill).

---

## Features

- **Authentic Telephony Experience**:
  - Lift the handset to hear the classic **German dial tone**.
  - Authentic dial tone silence upon rotating the dial, and ringing tone during call establishment.
  - Hanging up immediately disconnects the live session and mutes all audio.
- **Multilingual Rotary Dialing**:
  - Dial **`1`** (or wait 4 seconds): 🇩🇪 **German Assistant** (Voice: *Aoede*)
  - Dial **`2`**: 🇬🇧 **English Assistant** (Voice: *Puck*)
  - Dial **`3`**: 🇹🇷 **Turkish Assistant** (Voice: *Kore*)
- **Real-Time Bidirectional Audio Streaming**:
  - Gemini's voice streams chunk-by-chunk directly into the handset earpiece with sub-second latency.
- **Dual-Threshold Voice Activity Detection (Hysteresis VAD)**:
  - Smart Schmitt-trigger design prevents accidental cutoffs during natural speaking pauses.
  - Pre-speech circular buffer (~320 ms) guarantees that the very first syllable of every sentence is preserved.
  - Automatic microphone flush after playback prevents acoustic feedback.
- **Hardware Resampling Engine**:
  - Automatically adapts standard 48 kHz USB sound cards to Gemini Live's native 16 kHz input / 24 kHz output.
- **Auto-Start on Boot**:
  - Production-ready `systemd` service starts the phone seamlessly on power-up.

---

## 🛠️ Hardware & Pinout

### Bill of Materials
- **Raspberry Pi 3 Model B / 3B+ / 4** with Raspberry Pi OS Lite (64-bit) or Debian Trixie (64-bit)
- **FeTAp 791** (or similar vintage German rotary telephone with NS 38 dial)
- **USB Audio Adapter** (e.g., C-Media CM108 USB sound card with 3.5mm mic in and audio out)
- Jumper wires

### GPIO Connection Diagram

All switches connect between their GPIO pin and **GND** (internal pull-up resistors are enabled in software):

| FeTAp 791 Contact | Raspberry Pi Pin | Function |
| :--- | :--- | :--- |
| **Hook Switc** | **GPIO 17** (Pin 11) & **GND** (Pin 9) | Detects handset lifted / placed on cradle |
| **Rotary Encoder Signal Pins** | **GPIO 22** (Pin 15) & **GND** (Pin 14) | Decodes pulse dialing (1-10 pulses) |
| **Rotary encoder turning detector** | **GPIO 27** (Pin 13) & **GND** (Pin 14) | Silences dial tone when wheel starts turning |
| **Handset Microphone** | USB Sound Card **Mic In** (3.5mm) | Captures user speech |
| **Handset Earpiece** | USB Sound Card **Headphone Out** (3.5mm) | Plays Gemini voice & dial tones |

---

## 🚀 Quick Start Guide

### 1. Raspberry Pi System Dependencies
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv portaudio19-dev libasound2-dev gpiod python3-libgpiod alsa-utils swig python3-dev liblgpio-dev libportaudio2
```

### 2. Clone and Setup Environment
```bash
git clone https://github.com/rernars/Vintage-Phone-AI-Assistant.git
cd fetap791-gemini-live

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Gemini API Key
Create your `.env` file:
```bash
cp .env.example .env
nano .env
```
Paste your Gemini API key from [Google AI Studio](https://aistudio.google.com/):
```env
GEMINI_API_KEY="AIzaSy..."
```

### 4. Run Interactively
```bash
python3 pi_fetap_live.py
```

---

## ⚙️ Automatic Startup on Boot (systemd)

To make your phone run as an appliance every time the Pi powers on:

1. Copy the service unit:
```bash
sudo cp fetap.service /etc/systemd/system/
```
2. Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fetap.service
```
3. View live status and logs:
```bash
sudo systemctl status fetap.service
journalctl -u fetap.service -f
```
---

NOTE: Most coding part of this project was done by AI, it might have bugs since its still in development.


