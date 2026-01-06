"""
LCD Test Program
Test og diagnosticer LCD display på educaboard
"""

from machine import Pin
from gpio_lcd import GpioLcd
from time import sleep

# LCD pins på educaboard (fast loddet)
print("Initializing LCD...")
lcd = GpioLcd(
    rs_pin=Pin(27), 
    enable_pin=Pin(25),
    d4_pin=Pin(33), 
    d5_pin=Pin(32), 
    d6_pin=Pin(21), 
    d7_pin=Pin(22),
    num_lines=4, 
    num_columns=20
)

print("LCD initialized!")
print("\nTest 1: Clear screen and basic text")
sleep(1)

# Test 1: Basic characters
lcd.clear()
lcd.putstr("LCD Test Program")
sleep(2)

# Test 2: All lines
print("\nTest 2: Writing to all 4 lines")
lcd.clear()
lcd.putstr("Line 0: 12345678901")  # 20 chars max
lcd.move_to(0, 1)
lcd.putstr("Line 1: ABCDEFGHIJK")
lcd.move_to(0, 2)
lcd.putstr("Line 2: Numbers 123")
lcd.move_to(0, 3)
lcd.putstr("Line 3: !@#$%^&*()")
sleep(3)

# Test 3: Danske tegn (kan være problematisk)
print("\nTest 3: Danish characters")
lcd.clear()
lcd.putstr("Danske tegn:")
lcd.move_to(0, 1)
lcd.putstr("AEO: ae o")  # Prøv uden special chars først
lcd.move_to(0, 2)
lcd.putstr("Tall: 123")
sleep(3)

# Test 4: Numbers and formatting
print("\nTest 4: Formatted numbers (som på cykel)")
lcd.clear()
lcd.putstr("Spd:12.5 Dir:180.0")
lcd.move_to(0, 1)
lcd.putstr("55.1234,12.5678")
lcd.move_to(0, 2)
lcd.putstr("Bat:85% Temp:22C")
lcd.move_to(0, 3)
lcd.putstr("Runtime: 9.5h")
sleep(3)

# Test 5: Cycling display (som på cykel i brug)
print("\nTest 5: Simulating bicycle data")
for i in range(5):
    speed = 12.5 + i * 2.3
    direction = 45.0 + i * 15
    battery = 85 - i * 5
    temp = 22 + i
    
    lcd.clear()
    lcd.putstr(f"Spd:{speed:4.1f} Dir:{direction:5.1f}")
    lcd.move_to(0, 1)
    lcd.putstr("55.1234,12.5678")
    lcd.move_to(0, 2)
    lcd.putstr(f"Bat:{battery}% Temp:{temp}C")
    lcd.move_to(0, 3)
    lcd.putstr(f"Runtime: {10-i*2:.1f}h")
    
    print(f"  Update {i+1}/5: Speed={speed:.1f}, Battery={battery}%")
    sleep(2)

# Done
print("\nTest complete!")
lcd.clear()
lcd.putstr("Test Complete!")
lcd.move_to(0, 2)
lcd.putstr("LCD OK")
sleep(2)
lcd.clear()

print("\nHvis du ser korrekte tal og bogstaver, virker LCD'en!")
print("Hvis du ser maerkelige tegn, check:")
print("  1. LCD pins korrekt tilsluttet (27,25,33,32,21,22)")
print("  2. Strom til LCD")
print("  3. Kontrast indstilling på LCD")
