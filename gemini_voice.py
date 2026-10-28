"""Gemini Voice Agent Handler for FeTAp 791 using Gemini Live API."""

import io
import os
import wave
import logging
import asyncio
import queue
import threading
import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
import config

logger = logging.getLogger(__name__)

class GeminiLiveSession:
    """Real-time bidirectional Gemini Live session for FeTAp 791."""

    def __init__(self):
        api_key = config.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required.")
        
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash-native-audio-latest"
        self.session = None
        self.spk_queue = queue.Queue()
        self.out_stream = None
        self.recv_task = None
        self.loop = None
        self.thread = None

    def start(self):
        """Starts the audio output stream and background event loop."""
        def spk_callback(outdata, frames, time_info, status):
            try:
                data = self.spk_queue.get_nowait()
                if len(data) < len(outdata):
                    outdata[:len(data)] = data
                    outdata[len(data):].fill(0)
                else:
                    outdata[:] = data[:len(outdata)]
            except queue.Empty:
                outdata.fill(0)

        self.out_stream = sd.OutputStream(
            samplerate=24000,
            channels=1,
            dtype='int16',
            blocksize=1024,
            callback=spk_callback
        )
        self.out_stream.start()

    def stop(self):
        if self.out_stream:
            self.out_stream.stop()
            self.out_stream.close()
            self.out_stream = None

# Backward compatibility alias
GeminiVoiceSession = GeminiLiveSession
