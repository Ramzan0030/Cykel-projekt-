"""
PARALLEL LCD HARDWARE DIAGNOSTIC
Tester hver pin individuelt og verificerer LCD initialization sequence
"""

from machine import Pin
import time

print("\n" + "="*60)
print("PARALLEL LCD HARDWARE DIAGNOSTIC")
print("="*60)

# LCD Pin configuration
LCD_PINS = {
    'RS': 27,
    'E': 25,
    'D4': 33,
    'D5': 32,
    'D6': 21,
    'D7': 22
}

print("\n1. TESTING INDIVIDUAL PINS")
print("-" * 60)

pins = {}
for name, gpio in LCD_PINS.items():
    try:
        pin = Pin(gpio, Pin.OUT)
        pin.value(0)
        pins[name] = pin
        print(f"✓ GPIO {gpio:2d} ({name:3s}) - Initialized")
    except Exception as e:
        print(f"❌ GPIO {gpio:2d} ({name:3s}) - FAILED: {e}")
        exit()

print("\n2. PIN TOGGLE TEST (watch LCD pins with multimeter)")
print("-" * 60)
print("Each pin will toggle HIGH/LOW 3 times...")

for name, pin in pins.items():
    print(f"  Testing {name} (GPIO {LCD_PINS[name]})...", end="")
    for i in range(3):
        pin.value(1)
        time.sleep(0.1)
        pin.value(0)
        time.sleep(0.1)
    print(" Done")

print("\n3. TIMING TEST - LCD ENABLE PULSE")
print("-" * 60)
print("Testing Enable (E) pin pulse timing...")

def lcd_enable_pulse():
    """Correct LCD enable pulse timing"""
    pins['E'].value(1)
    time.sleep_us(1)  # Min 450ns high time
    pins['E'].value(0)
    time.sleep_us(100)  # Min 37us between pulses

for i in range(5):
    lcd_enable_pulse()
    print(f"  Pulse {i+1}/5")
    time.sleep(0.5)

print("\n4. LCD INITIALIZATION SEQUENCE")
print("-" * 60)
print("Attempting proper LCD initialization (HD44780 protocol)...")

def lcd_write_nibble(data, rs=0):
    """Write 4 bits to LCD"""
    pins['RS'].value(rs)
    pins['D4'].value((data >> 0) & 1)
    pins['D5'].value((data >> 1) & 1)
    pins['D6'].value((data >> 2) & 1)
    pins['D7'].value((data >> 3) & 1)
    lcd_enable_pulse()

def lcd_write_byte(data, rs=0):
    """Write 8 bits to LCD (two nibbles)"""
    lcd_write_nibble(data >> 4, rs)
    lcd_write_nibble(data & 0x0F, rs)

print("  Step 1: Wait 40ms after power-on...")
time.sleep_ms(40)

print("  Step 2: Set to 8-bit mode (3 times)...")
for i in range(3):
    lcd_write_nibble(0x03)
    time.sleep_ms(5)
    print(f"    Sent 0x03 ({i+1}/3)")

print("  Step 3: Set to 4-bit mode...")
lcd_write_nibble(0x02)
time.sleep_ms(1)

print("  Step 4: Function Set (4-bit, 2 lines, 5x8 font)...")
lcd_write_byte(0x28)
time.sleep_ms(1)

print("  Step 5: Display OFF...")
lcd_write_byte(0x08)
time.sleep_ms(1)

print("  Step 6: Clear Display...")
lcd_write_byte(0x01)
time.sleep_ms(2)

print("  Step 7: Entry Mode (increment, no shift)...")
lcd_write_byte(0x06)
time.sleep_ms(1)

print("  Step 8: Display ON (display on, cursor off, blink off)...")
lcd_write_byte(0x0C)
time.sleep_ms(1)

print("\n5. WRITING TEST MESSAGE")
print("-" * 60)
print("Writing 'HELLO' to LCD...")

# Clear display again
lcd_write_byte(0x01)
time.sleep_ms(2)

# Write 'HELLO'
test_message = "HELLO"
for char in test_message:
    lcd_write_byte(ord(char), rs=1)
    time.sleep_ms(1)
    print(f"  Wrote '{char}' (0x{ord(char):02X})")

print("\n6. BACKLIGHT TEST (if connected)")
print("-" * 60)
print("NOTE: This code doesn't control backlight.")
print("If LCD has backlight control, it might be on:")
print("  - Separate pin (needs transistor)")
print("  - Built-in (always on)")
print("  - Potentiometer for contrast")

print("\n" + "="*60)
print("DIAGNOSTIC COMPLETE")
print("="*60)

print("\nRESULTS:")
print("  If you see 'HELLO' on LCD:")
print("    ✓ Hardware is working")
print("    ✓ Pin connections are correct")
print("    → Problem is in main.py LCD initialization")
print()
print("  If you see NOTHING on LCD:")
print("    ❌ Check these common issues:")
print()
print("    1. CONTRAST - Adjust potentiometer on LCD backpack")
print("       (Turn fully clockwise, then back slightly)")
print()
print("    2. POWER - Verify LCD has:")
print("       - VCC connected to 5V")
print("       - GND connected to GND")
print()
print("    3. WIRING - Double-check pin connections:")
for name, gpio in LCD_PINS.items():
    print(f"       GPIO {gpio} → LCD {name}")
print()
print("    4. LCD TYPE - Verify it's:")
print("       - HD44780 compatible")
print("       - Parallel LCD (not I2C)")
print()
print("    5. BACKLIGHT - Check if backlight LED is on")
print("       (Screen should glow even without text)")

print("\n" + "="*60)
