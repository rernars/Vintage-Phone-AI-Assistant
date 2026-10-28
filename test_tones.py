"""Test utility to verify dial tone and digit pulse decoding logic without hardware."""

import sys
import time
from hardware_controller import FeTApHardware

def test_digit_simulation():
    print("Testing NS 38 pulse decoding simulation...")
    received_digits = []
    
    hw = FeTApHardware(
        on_digit_dialed=lambda d: received_digits.append(d)
    )

    # Simulate dialing '1' (1 pulse on nsi)
    hw._handle_nsi_pulse()
    time.sleep(0.6)  # wait for DIAL_TIMEOUT

    assert received_digits == [1], f"Expected [1], got {received_digits}"
    print("Test passed: Dialing '1' successfully decoded.")

    # Simulate dialing '0' (10 pulses on nsi)
    for _ in range(10):
        hw._handle_nsi_pulse()
        time.sleep(0.04)
    time.sleep(0.6)

    assert received_digits == [1, 0], f"Expected [1, 0], got {received_digits}"
    print("Test passed: Dialing '0' (10 pulses) successfully decoded.")
    print("All simulated hardware tests succeeded!")

if __name__ == "__main__":
    test_digit_simulation()
