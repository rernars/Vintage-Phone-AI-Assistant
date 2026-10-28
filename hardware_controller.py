"""Hardware driver for FeTAp 791 rotary dial and hook switch on Raspberry Pi."""

import time
import threading
import logging
import config

try:
    from gpiozero import Button
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logging.warning("gpiozero not available; running in simulated hardware mode.")

logger = logging.getLogger(__name__)

class FeTApHardware:
    """Decodes Hook Switch (Gabel) and Rotary Dial (Nummernschalter NS 38)."""

    def __init__(self, on_hook_change=None, on_digit_dialed=None, on_dial_start=None):
        self.on_hook_change = on_hook_change          # Callback: func(is_off_hook: bool)
        self.on_digit_dialed = on_digit_dialed        # Callback: func(digit: int)
        self.on_dial_start = on_dial_start            # Callback: func()

        self.pulse_count = 0
        self.last_pulse_time = 0.0
        self.dial_timer = None
        self._lock = threading.Lock()

        if GPIO_AVAILABLE:
            # FeTAp 791 Hook Switch:
            # Wire between GPIO_HOOK and GND (pull_up=True)
            # Handset lifted -> switch connects to GND (is_pressed = True)
            self.hook_button = Button(
                config.GPIO_HOOK,
                pull_up=True,
                bounce_time=config.DEBOUNCE_HOOK
            )
            self.hook_button.when_pressed = self._handle_hook_off
            self.hook_button.when_released = self._handle_hook_on

            # FeTAp 791 Dial Impulskontakt (nsi):
            # Normally closed; pulses open when returning.
            self.nsi_button = Button(
                config.GPIO_DIAL_NSI,
                pull_up=True,
                bounce_time=config.DEBOUNCE_PULSE
            )
            self.nsi_button.when_pressed = self._handle_nsi_pulse

            # FeTAp 791 Dial Arbeitskontakt (nsa):
            # Closes as soon as dial wheel leaves resting position.
            self.nsa_button = Button(
                config.GPIO_DIAL_NSA,
                pull_up=True,
                bounce_time=config.DEBOUNCE_HOOK
            )
            self.nsa_button.when_pressed = self._handle_nsa_active
        else:
            logger.info("Mocking FeTAp hardware interface.")

    @property
    def is_off_hook(self) -> bool:
        if GPIO_AVAILABLE:
            return self.hook_button.is_pressed
        return True

    def _handle_hook_off(self):
        logger.info("Handset lifted (Off-Hook)")
        if self.on_hook_change:
            self.on_hook_change(True)

    def _handle_hook_on(self):
        logger.info("Handset placed on cradle (On-Hook)")
        with self._lock:
            if self.dial_timer:
                self.dial_timer.cancel()
                self.dial_timer = None
            self.pulse_count = 0
        if self.on_hook_change:
            self.on_hook_change(False)

    def _handle_nsa_active(self):
        logger.info("Dial wheel rotation started")
        if self.on_dial_start:
            self.on_dial_start()

    def _handle_nsi_pulse(self):
        with self._lock:
            self.pulse_count += 1
            self.last_pulse_time = time.time()
            logger.debug(f"nsi pulse detected, count={self.pulse_count}")

            if self.dial_timer:
                self.dial_timer.cancel()

            # Schedule evaluation when pulses cease
            self.dial_timer = threading.Timer(config.DIAL_TIMEOUT, self._finalize_digit)
            self.dial_timer.start()

    def _finalize_digit(self):
        with self._lock:
            count = self.pulse_count
            self.pulse_count = 0
            self.dial_timer = None

        if count == 0:
            return

        # German NS 38 pulse encoding:
        # 1 pulse = 1, 2 pulses = 2, ..., 9 pulses = 9, 10 pulses = 0
        digit = 0 if count == 10 else count
        logger.info(f"Dialed digit recognized: {digit} (from {count} pulses)")

        if self.on_digit_dialed:
            self.on_digit_dialed(digit)

    def cleanup(self):
        if GPIO_AVAILABLE:
            self.hook_button.close()
            self.nsi_button.close()
            self.nsa_button.close()
