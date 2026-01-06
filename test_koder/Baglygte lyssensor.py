from machine import Pin, UART
from neopixel import NeoPixel
import network
import espnow
import time
import struct

# GPS
gps = UART(2, baudrate=9600, tx=17, rx=16)

# NeoPixel
np = NeoPixel(Pin(13), 12)
FIRST_LED = 0

# ESP-NOW
sta = network.WLAN(network.STA_IF)
sta.active(True)

FORLYGTE_MAC = b'\x38\x18\x2B\x80\x6F\x18'  # FRONT MAC
MAIN_MAC = b'\x24\x6F\x28\x7A\xBC\xE4'  # UPDATE TO YOUR MAIN EDUCABOARD MAC

e = espnow.ESPNow()
e.active(True)
e.add_peer(FORLYGTE_MAC)
e.add_peer(MAIN_MAC)

# STATE
light_on = False
last_receive = 0
gps_lat = None
gps_lon = None
TIMEOUT = 2000
GPS_SEND_INTERVAL = 1000
last_gps_send = 0

print("Baglygte ESP32 running...")
print("Waiting for GPS fix...")

# FUNCTIONS
def parse_gprmc(sentence):
    try:
        parts = sentence.split(',')
        if len(parts) < 9 or parts[2] != 'A':
            return None
        
        lat_raw = parts[3]
        lon_raw = parts[5]
        
        if not lat_raw or not lon_raw or len(lat_raw) < 4 or len(lon_raw) < 4:
            return None
        
        # Latitude
        lat_deg = int(lat_raw[:2])
        lat_min = float(lat_raw[2:])
        lat = lat_deg + lat_min / 60
        if parts[4] == 'S':
            lat = -lat
        
        # Longitude
        if len(lon_raw) >= 5 and lon_raw[4] == '.':
            lon_deg = int(lon_raw[:3])
            lon_min = float(lon_raw[3:])
        else:
            lon_deg = int(lon_raw[:2])
            lon_min = float(lon_raw[2:])
        
        lon = lon_deg + lon_min / 60
        if parts[6] == 'W':
            lon = -lon
        
        return lat, lon
    except:
        return None

def update_gps():
    global gps_lat, gps_lon
    
    # Read all available data
    while gps.any():
        line = gps.readline()
        if not line:
            continue
            
        try:
            sentence = line.decode('ascii', 'ignore').strip()
            
            # Only process complete GPRMC/GNRMC sentences (must contain checksum *)
            if (sentence.startswith('$GPRMC') or sentence.startswith('$GNRMC')) and '*' in sentence:
                result = parse_gprmc(sentence)
                if result:
                    gps_lat, gps_lon = result
                    print(f"✓ GPS: {gps_lat:.5f}, {gps_lon:.5f}")
                    return True
        except:
            pass
    
    return False

def send_gps_to_main():
    """Send GPS coordinates to Main via ESP-NOW"""
    if gps_lat is not None and gps_lon is not None:
        msg = struct.pack('ff', gps_lat, gps_lon)
        try:
            e.send(MAIN_MAC, msg)
        except:
            pass

def set_light(brightness_pct):
    global light_on
    r = int(brightness_pct * 2.55)
    for i in range(FIRST_LED):
        np[i] = (0, 0, 0)
    for i in range(FIRST_LED, 12):
        np[i] = (r, 0, 0)  # RØD
    np.write()
    light_on = True

def turn_off_light():
    global light_on
    for i in range(12):
        np[i] = (0, 0, 0)
    np.write()
    light_on = False

while True:
    now = time.ticks_ms()
    
    # GPS UPDATE
    if update_gps():
        if time.ticks_diff(now, last_gps_send) > GPS_SEND_INTERVAL:
            send_gps_to_main()
            last_gps_send = now
    
    # ESP-NOW RECEIVE from forlygte
    host, msg = e.recv(0)
    
    if msg:
        try:
            ldr_value, brightness, light_byte = struct.unpack('HBB', msg)
            should_light = bool(light_byte)
            last_receive = now
            
            if should_light and not light_on:
                set_light(brightness)
                print(f"🔴 BAG ON ({brightness}%)")
            elif not should_light and light_on:
                turn_off_light()
                print(f"⚫ BAG OFF")
            elif should_light:
                set_light(brightness)
                
        except Exception as e:
            print(f"Parse error: {e}")
    
    # TIMEOUT SAFETY
    if light_on and time.ticks_diff(now, last_receive) > TIMEOUT:
        turn_off_light()
    
    time.sleep(0.05)