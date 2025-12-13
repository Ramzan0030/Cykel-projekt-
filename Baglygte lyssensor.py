from machine import Pin
from neopixel import NeoPixel
import network
import espnow
import time
import struct

# ============================================================================
# HARDWARE SETUP
# ============================================================================
print("\n" + "="*50)
print("BAG ESP32 - DEBUG MODE")
print("="*50)

# Test NeoPixel FØRST
print("\nTesting NeoPixel connection...")
try:
    np = NeoPixel(Pin(13), 12)
    print("✓ NeoPixel object created")
    
    # Test alle LEDs RØD
    print("Testing all LEDs RED...")
    for i in range(12):
        np[i] = (50, 0, 0)  # Rød
    np.write()
    print("✓ All LEDs should be RED now")
    time.sleep(2)
    
    # Sluk alle
    print("Turning off all LEDs...")
    for i in range(12):
        np[i] = (0, 0, 0)
    np.write()
    print("✓ All LEDs OFF")
    time.sleep(1)
    
except Exception as e:
    print(f"✗ NeoPixel ERROR: {e}")
    import sys
    sys.exit()

FIRST_LED = 0

# ============================================================================
# ESP-NOW SETUP
# ============================================================================
sta = network.WLAN(network.STA_IF)
sta.active(True)

peer_mac = b'\x38\x18\x2B\x80\x6F\x18'

e = espnow.ESPNow()
e.active(True)
e.add_peer(peer_mac)

print(f"\nMy MAC: 68:25:DD:E9:B7:D8")
print(f"Listening for: 38:18:2B:80:6F:18")
print("="*50 + "\n")

# ============================================================================
# STATE
# ============================================================================
light_on = False
last_receive = 0
TIMEOUT = 2000

# ============================================================================
# FUNCTIONS
# ============================================================================
def set_light(brightness_pct):
    global light_on
    print(f"\n>>> set_light() called with brightness={brightness_pct}%")
    
    r = int(brightness_pct * 2.55)
    print(f"    Calculated R value: {r}")
    
    # Sluk defekte LEDs
    for i in range(FIRST_LED):
        np[i] = (0, 0, 0)
        print(f"    LED {i}: OFF (skipped)")
    
    # Tænd aktive LEDs
    for i in range(FIRST_LED, 12):
        np[i] = (r, 0, 0)
        print(f"    LED {i}: RED ({r}, 0, 0)")
    
    np.write()
    print(f"    np.write() executed")
    
    light_on = True
    print(f"    light_on = {light_on}")

def turn_off_light():
    global light_on
    print(f"\n>>> turn_off_light() called")
    
    for i in range(12):
        np[i] = (0, 0, 0)
    np.write()
    light_on = False
    print(f"    All LEDs OFF, light_on = {light_on}")

# ============================================================================
# MAIN LOOP
# ============================================================================
print("Bag ESP32 running - waiting for front...\n")
print("DEBUG: Verbose output enabled\n")

packet_count = 0

while True:
    now = time.ticks_ms()
    
    # ========================================================================
    # RECEIVE ESP-NOW DATA
    # ========================================================================
    host, msg = e.recv(0)
    
    if msg:
        packet_count += 1
        print(f"\n[Packet #{packet_count}] Received {len(msg)} bytes")
        
        try:
            # Unpack binary data
            ldr_value, brightness, light_byte = struct.unpack('HBB', msg)
            should_light = bool(light_byte)
            
            print(f"  Unpacked: LDR={ldr_value}, Brightness={brightness}%, Light_byte={light_byte} (should_light={should_light})")
            
            last_receive = now
            
            # ====================================================================
            # ACTUATE LIGHT
            # ====================================================================
            print(f"  Current state: light_on={light_on}")
            
            if should_light and not light_on:
                print(f"  → Action: TURN ON")
                set_light(brightness)
                
            elif not should_light and light_on:
                print(f"  → Action: TURN OFF")
                turn_off_light()
                
            elif should_light and light_on:
                print(f"  → Action: UPDATE BRIGHTNESS")
                set_light(brightness)
            else:
                print(f"  → Action: NO CHANGE")
            
        except Exception as ex:
            print(f"  ✗ Parse error: {ex}")
            import sys
            sys.print_exception(ex)
    
    # ========================================================================
    # TIMEOUT CHECK
    # ========================================================================
    if light_on and time.ticks_diff(now, last_receive) > TIMEOUT:
        print(f"\n⚠️ TIMEOUT: No data for {TIMEOUT}ms")
        turn_off_light()
    
    time.sleep(0.05)