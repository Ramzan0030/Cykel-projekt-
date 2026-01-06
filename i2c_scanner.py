"""
I2C SCANNER - Find alle I2C enheder på bussen
Brug dette til at finde din LCD hvis det er en I2C LCD i stedet for parallel
"""

from machine import Pin, I2C
import time

print("\n" + "="*60)
print("I2C BUS SCANNER")
print("="*60)

# Test begge I2C busser
buses = [
    {"id": 0, "scl": 18, "sda": 19, "name": "I2C0 (Educaboard main)"},
    {"id": 1, "scl": 22, "sda": 21, "name": "I2C1 (Alternative)"},
]

all_devices = []

for bus_config in buses:
    print(f"\n📡 Scanning {bus_config['name']}...")
    print(f"   SCL: GPIO {bus_config['scl']}")
    print(f"   SDA: GPIO {bus_config['sda']}")
    
    try:
        i2c = I2C(bus_config['id'], 
                  scl=Pin(bus_config['scl']), 
                  sda=Pin(bus_config['sda']), 
                  freq=100000)
        time.sleep(0.1)
        
        devices = i2c.scan()
        
        if devices:
            print(f"   ✓ Found {len(devices)} device(s):")
            for addr in devices:
                device_name = "Unknown"
                
                # Common I2C addresses
                if addr == 0x27 or addr == 0x3F:
                    device_name = "LCD (PCF8574 I2C backpack)"
                elif addr == 0x40:
                    device_name = "INA219 (current sensor)"
                elif addr == 0x68:
                    device_name = "MPU6050 (accelerometer)"
                elif addr == 0x23:
                    device_name = "BH1750 (light sensor)"
                elif addr == 0x50:
                    device_name = "EEPROM (Educaboard built-in)"
                elif addr == 0x08:
                    device_name = "Unknown (Educaboard built-in)"
                
                print(f"     - 0x{addr:02X} ({addr}) - {device_name}")
                all_devices.append((bus_config['name'], addr, device_name))
        else:
            print("   ⚠️ No devices found")
            
    except Exception as e:
        print(f"   ❌ Bus error: {e}")

print("\n" + "="*60)
print("SUMMARY")
print("="*60)

if all_devices:
    print("\nAll detected I2C devices:")
    for bus, addr, name in all_devices:
        print(f"  {bus:30s} 0x{addr:02X} - {name}")
    
    # Check for LCD
    lcd_found = False
    for bus, addr, name in all_devices:
        if "LCD" in name:
            lcd_found = True
            print(f"\n✓ LCD FOUND at address 0x{addr:02X} on {bus}")
            print(f"  This is an I2C LCD, NOT a parallel LCD!")
            print(f"  You need to use I2C LCD library, not GpioLcd")
            break
    
    if not lcd_found:
        print("\n⚠️ No LCD found on I2C buses")
        print("   Your LCD might be:")
        print("   1. Parallel LCD (using GPIO pins directly)")
        print("   2. Not powered on")
        print("   3. Connected to wrong pins")
else:
    print("\n❌ NO I2C devices detected!")
    print("   Check:")
    print("   - SDA/SCL wiring")
    print("   - Pull-up resistors (usually built into I2C backpack)")
    print("   - Power supply to devices")

print("\n" + "="*60)
print("\nNEXT STEPS:")
print("  1. If LCD found at 0x27 or 0x3F → Use I2C LCD code")
print("  2. If no LCD found → Test parallel LCD pins")
print("  3. If parallel LCD → Continue with hardware debug")
