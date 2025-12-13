# tail_light_test.py - Test MOSFET baglygte
from machine import Pin, PWM
import time

# Configuration
TAIL_LIGHT_PIN = 23  # Skift til din GPIO

# Test 1: Simple ON/OFF
print("\n=== Test 1: ON/OFF ===")
tail = Pin(TAIL_LIGHT_PIN, Pin.OUT)

tail.value(1)
print("ON - Check LED")
time.sleep(2)

tail.value(0)
print("OFF")
time.sleep(1)

# Test 2: Blink
print("\n=== Test 2: Blink (5x) ===")
for i in range(5):
    tail.value(1)
    time.sleep(0.2)
    tail.value(0)
    time.sleep(0.2)
print("Blink done")

# Test 3: PWM (hvis MOSFET understøtter)
print("\n=== Test 3: PWM Fade ===")
tail_pwm = PWM(Pin(TAIL_LIGHT_PIN), freq=1000)

# Fade up
for duty in range(0, 1024, 50):
    tail_pwm.duty(duty)
    time.sleep(0.05)

# Fade down
for duty in range(1023, -1, -50):
    tail_pwm.duty(duty)
    time.sleep(0.05)

tail_pwm.deinit()
print("\nTest complete")