from machine import Pin, UART, ADC
from neopixel import NeoPixel
import network
import espnow
import time
import struct
from adc_sub import ADC_substitute

gps = UART(2, baudrate=9600, tx=17, rx=16)

battery_adc = ADC(Pin(35))
battery_adc.atten(ADC.ATTN_11DB)
battery_adc.width(ADC.WIDTH_12BIT)

def read_battery():
    raw_sum = 0
    for _ in range(10):
        raw_sum += battery_adc.read()
    raw_adc = raw_sum // 10
    
    voltage_at_pin = (raw_adc / 4095.0) * 3.3
    battery_voltage = voltage_at_pin * 2.0
    
    battery_pct = ((battery_voltage - 3.3) / (4.2 - 3.3)) * 100
    return max(0, min(100, int(battery_pct)))

np = NeoPixel(Pin(13), 12)
FIRST_LED = 0

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.connect("Ittek5glab4c", "gruppe4c")

print("Connecting WiFi...")
timeout = 10
while not sta.isconnected() and timeout > 0:
    time.sleep(1)
    timeout -= 1

if sta.isconnected():
    print(f"WiFi: {sta.ifconfig()[0]}")
    channel = sta.config('channel')
    print(f"Channel: {channel}")
    print(f"Main skal være på samme channel ({channel}) for ESP-NOW!")
else:
    print("WiFi failed!")

MAIN_MAC = b'\x38\x18\x2B\x80\x6F\x18'

e = espnow.ESPNow()
e.active(True)
e.add_peer(MAIN_MAC)

mac = sta.config('mac')
main_mac_str = ':'.join(['%02X' % b for b in MAIN_MAC])
print(f"Sending to: {main_mac_str}\n")

light_on = False
last_receive = 0
gps_lat = None
gps_lon = None
TIMEOUT = 2000
GPS_SEND_INTERVAL = 1000
last_gps_send = 0
BAT_SEND_INTERVAL = 10000
last_bat_send = 0

print("System ready\n")

def update_gps():
    global gps_lat, gps_lon
    
    while gps.any():
        line = gps.readline()
        if not line:
            continue
            
        try:
            sentence = line.decode('ascii', 'ignore').strip()
            
            if sentence.startswith('$GPRMC') and ',A,' in sentence:
                parts = sentence.split(',')
                
                if len(parts) >= 7:
                    lat_raw = parts[3]
                    lat_dir = parts[4]
                    lon_raw = parts[5]
                    lon_dir = parts[6]
                    
                    if lat_raw and lon_raw:
                        lat_deg = int(lat_raw[:2])
                        lat_min = float(lat_raw[2:])
                        gps_lat = lat_deg + lat_min / 60
                        if lat_dir == 'S':
                            gps_lat = -gps_lat
                        
                        lon_deg = int(lon_raw[:3])
                        lon_min = float(lon_raw[3:])
                        gps_lon = lon_deg + lon_min / 60
                        if lon_dir == 'W':
                            gps_lon = -gps_lon
                        
                        print(f"GPS: {gps_lat:.5f}, {gps_lon:.5f}")
                        return True
        except:
            pass
    
    return False

def send_gps_to_main():
    if gps_lat is not None and gps_lon is not None:
        msg = struct.pack('ff', gps_lat, gps_lon)
        try:
            e.send(MAIN_MAC, msg)
            print(f"[ESP-NOW] GPS sent to main: {gps_lat:.5f}, {gps_lon:.5f}")
            time.sleep_ms(10)
        except Exception as err:
            print(f"[ESP-NOW] Send error: {err}")

def set_light(brightness_pct):
    global light_on
    r = int(brightness_pct * 2.55)
    for i in range(FIRST_LED):
        np[i] = (0, 0, 0)
    for i in range(FIRST_LED, 12):
        np[i] = (r, 0, 0)
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
    
    update_gps()
    
    # FIX: Fjernet duplikeret bat_pct læsning - læses kun når den skal sendes
    
    if time.ticks_diff(now, last_gps_send) > GPS_SEND_INTERVAL:
        if gps_lat is not None:
            send_gps_to_main()
            last_gps_send = now

    if time.ticks_diff(now, last_bat_send) > BAT_SEND_INTERVAL:
        bat_pct = read_battery()
        msg = struct.pack('B', bat_pct)
        try:
            e.send(MAIN_MAC, msg)
        except:
            pass
        last_bat_send = now
    
    host, msg = e.recv(0)
    
    if msg:
        try:
            ldr_value, brightness, light_byte = struct.unpack('HBB', msg)
            should_light = bool(light_byte)
            last_receive = now
            
            print(f"[ESP-NOW] Light cmd: LDR={ldr_value}, Brightness={brightness}%, ON={should_light}")
            
            if should_light and not light_on:
                set_light(brightness)
            elif not should_light and light_on:
                turn_off_light()
            elif should_light:
                set_light(brightness)
                
        except Exception as err:
            print(f"[ESP-NOW] Light cmd error: {err}")
    
    if light_on and time.ticks_diff(now, last_receive) > TIMEOUT:
        turn_off_light()
    
    time.sleep(0.05)