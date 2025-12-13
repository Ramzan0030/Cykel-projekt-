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

peer_mac = b'\x38\x18\x2B\x80\x6F\x18'  # FRONT MAC
e = espnow.ESPNow()
e.active(True)
e.add_peer(peer_mac)

# STATE
light_on = False
last_receive = 0
gps_lat = None
gps_lon = None
TIMEOUT = 2000

# FUNCTIONS
def parse_gprmc(sentence):
    parts = sentence.split(',')
    if len(parts) < 9 or parts[2] != 'A':
        return None
    
    lat_raw = parts[3]
    if len(lat_raw) < 4:
        return None
    lat = int(lat_raw[:2]) + float(lat_raw[2:]) / 60
    if parts[4] == 'S':
        lat = -lat
    
    lon_raw = parts[5]
    if len(lon_raw) < 4:
        return None
    
    dot_pos = lon_raw.find('.')
    if dot_pos >= 5:
        lon = int(lon_raw[:3]) + float(lon_raw[3:]) / 60
    elif dot_pos >= 4:
        lon = int(lon_raw[:2]) + float(lon_raw[2:]) / 60
    else:
        return None
    
    if parts[6] == 'W':
        lon = -lon
    
    return lat, lon

def update_gps():
    global gps_lat, gps_lon
    if gps.any():
        line = gps.readline()
        try:
            sentence = line.decode('ascii').strip()
            if sentence.startswith('$GPRMC') or sentence.startswith('$GNRMC'):
                result = parse_gprmc(sentence)
                if result:
                    gps_lat, gps_lon = result
                    return True
        except:
            pass
    return False

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

print("Bag ESP32 running (GPS receiver)...\n")

while True:
    now = time.ticks_ms()
    
    # GPS UPDATE
    update_gps()
    
    # ESP-NOW RECEIVE
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