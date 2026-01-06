from adc_sub import ADC_substitute
import time
import network
from machine import I2C, Pin, ADC, RTC
import math
import dht
import gc
from gpio_lcd import GpioLcd
from buzzer_music import music
from neopixel import NeoPixel
import ntptime
import urequests
import espnow
import struct

# ============================================================================
# CONFIGURATION
# ============================================================================
WIFI_SSID = "matt"
WIFI_PASS = "12345678"

TB_TOKEN = "Ctqwsp4GvIZWVD27u4eA"
TB_SERVER = "demo.thingsboard.io"

# ESP-NOw baglygte MAC
BAGLYGTE_MAC = b'\x68\x25\xDD\xE9\xB7\xD8'

# Timing
IDLE_TIME = 180_000
MOTION_CONFIRM = 5_000
MOTION_GRACE = 1_000
TELEMETRY_INTERVAL = 10_000
ALARM_TELEMETRY = 10_000
API_UPDATE = 600_000
ESPNOW_INTERVAL = 500

# Hardware pins
MPU_SCL = 26
MPU_SDA = 27
DHT11_PIN = 25
BATTERY_PIN = 34
INA219_I2C_ADDR = 0x40
LDR_PIN = 36
BRIGHTNESS_POT = 35

# Alarm hardware
ALARM_LED_PIN = 14
ALARM_BUZZER_PIN = 15
NEOPIXEL_PIN = 13
NEOPIXEL_COUNT = 12
NEOPIXEL_FIRST_LED = 0

# Thresholds
DARK_THRESHOLD = 3000
MOTION_THRESHOLD = 5000
LIGHT_IDLE_TIMEOUT = 180_000

# Battery
BATTERY_CAPACITY = 2000

# ADC calibration
X1, Y1 = 1703, 0
X2, Y2 = 2449, 100
ADC_A = (Y2 - Y1) / (X2 - X1)
ADC_B = Y2 - ADC_A * X2

TEST_MODE = False

# ============================================================================
# HARDWARE INIT
# ============================================================================
print("\n" + "="*50)
print("SMART BICYCLE MAIN SYSTEM")
print("="*50)

print("\n1. Initializing hardware...")

# I2C bus
i2c = I2C(0, scl=Pin(18), sda=Pin(19), freq=50000)
time.sleep(0.5)

i2c_mpu = I2C(1, scl=Pin(MPU_SCL), sda=Pin(MPU_SDA), freq=100000)
time.sleep(0.5)

"""
# ============================================================================
# DEBUG: SCAN I2C BUS
# ============================================================================
print("\n=== I2C BUS SCAN ===")
devices = i2c.scan()
if devices:
    print(f"Found devices: {[hex(d) for d in devices]}")
else:
    print("NO I2C DEVICES FOUND!")

print(f"Looking for MPU at 0x68...")
if 0x68 in devices:
    print("✓ MPU6050 DETECTED")
else:
    print("✗ MPU6050 NOT FOUND")
print("=" * 40 + "\n")
# ============================================================================
"""

# ============================================================================
# MPU INIT MED RETRY (efter LCD init frigiver I2C bus)
# ============================================================================
def init_mpu_with_retry():
    max_retries = 5
    for attempt in range(max_retries):
        try:
            devices = i2c_mpu.scan()  # ← ÆNDRET fra i2c
            print(f"   I2C scan: {[hex(d) for d in devices]}")
            
            if 0x68 not in devices:
                print(f"   Attempt {attempt+1}: MPU not visible")
                time.sleep(0.2)
                continue
            
            i2c_mpu.writeto_mem(0x68, 0x6B, b'\x00')  # ← ÆNDRET
            time.sleep(0.1)
            test = i2c_mpu.readfrom_mem(0x68, 0x75, 1)  # ← ÆNDRET
            print(f"   ✓ MPU6050 initialized (WHO_AM_I: {hex(test[0])})")
            return True
        except Exception as e:
            print(f"   Attempt {attempt+1} failed: {e}")
            time.sleep(0.3)
    
    return False

MPU_ADDR = 0x68
MPU_AVAILABLE = init_mpu_with_retry()

# INA219
INA219_AVAILABLE = True
ina219 = None 
try:
    devices = i2c.scan()
    print(f"I2C devices: {[hex(d) for d in devices]}")
    from ina219_lib import INA219
    ina219 = INA219(i2c, INA219_I2C_ADDR)
    print("   ✓ INA219 initialized")
except Exception as e:
    print(f"   ✗ INA219 init failed: {e}")
    INA219_AVAILABLE = False

# DHT11
dht_sensor = dht.DHT11(Pin(DHT11_PIN))

# LCD
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
print("   ✓ LCD initialized")

# LDR Light Sensor
ldr = ADC(Pin(LDR_PIN))
ldr.atten(ADC.ATTN_11DB)
print("   ✓ LDR sensor initialized")

# Brightness potmeter
pot = ADC(Pin(BRIGHTNESS_POT))
pot.atten(ADC.ATTN_11DB)
print("   ✓ Brightness pot initialized")

# Alarm LED
alarm_led = Pin(ALARM_LED_PIN, Pin.OUT)
alarm_led.value(0)

# NeoPixel
NEOPIXEL_AVAILABLE = False
try:
    np = NeoPixel(Pin(NEOPIXEL_PIN), NEOPIXEL_COUNT)
    for i in range(NEOPIXEL_FIRST_LED):
        np[i] = (0, 0, 0)
    for i in range(NEOPIXEL_FIRST_LED, NEOPIXEL_COUNT):
        np[i] = (0, 20, 0)
    np.write()
    NEOPIXEL_AVAILABLE = True
    print(f"   ✓ NeoPixel initialized")
except Exception as e:
    print(f"   ⚠️ NeoPixel failed: {e}")

# Buzzer
alarm_melody = "0 G5 2 0;2 E5 2 0;4 G5 2 0;6 E5 2 0;8 G5 2 0;10 E5 2 0;12 G5 2 0;14 E5 2 0"
alarm_sound = music(songString=alarm_melody, looping=True, tempo=2, duty=50000, pin=Pin(ALARM_BUZZER_PIN))
alarm_sound.stop()
print("   ✓ Alarm buzzer initialized")

battery_adc = ADC_substitute(BATTERY_PIN)
print("   ✓ Battery ADC initialized")

# ============================================================================
# STATE VARIABLES
# ============================================================================
system_enabled = True
auto_armed = False
alarm_active = False

last_motion = time.ticks_ms()
last_telemetry = 0
motion_start = 0
last_motion_detected = 0

# Light control
light_on = False
last_light_motion = time.ticks_ms()

# Alarm blink
last_alarm_blink = 0
alarm_led_state = False
ALARM_BLINK_RATE = 200

current_readings = []
MAX_CURRENT_READINGS = 10

# LCD rotation
lcd_screen = 0
last_lcd_rotation = 0
LCD_ROTATION_INTERVAL = 3000

# Sunrise/Sunset
sunrise_min = 0
sunset_min = 0
last_api_update = 0

# GPS data from baglygte
gps_lat = None
gps_lon = None

# ESP-NOW
last_espnow = 0

# MPU baseline
mpu_baseline = 0

# ============================================================================
# MPU CALIBRATION
# ============================================================================
def init_mpu_baseline():
    global mpu_baseline
    
    if not MPU_AVAILABLE:
        print("   ⚠️ MPU unavailable")
        return
    
    print("   Calibrating MPU6050...")
    lcd.clear()
    lcd.putstr("Calibrating MPU...")
    lcd.move_to(0, 1)
    lcd.putstr("Hold still!")
    
    readings = []
    
    for i in range(10):
        try:
            data = i2c_mpu.readfrom_mem(MPU_ADDR, 0x3B, 6)
            x = (data[0] << 8) | data[1]
            y = (data[2] << 8) | data[3]
            z = (data[4] << 8) | data[5]
            
            if x > 32767: x -= 65536
            if y > 32767: y -= 65536
            if z > 32767: z -= 65536
            
            readings.append(math.sqrt(x*x + y*y + z*z))
            
            lcd.move_to(0, 2)
            lcd.putstr(f"Sample {i+1}/10")
            
            time.sleep(0.05)
        except Exception as e:
            print(f"   ⚠️ Read failed: {e}")
    
    if readings:
        mpu_baseline = sum(readings) / len(readings)
        print(f"   ✓ MPU baseline: {mpu_baseline:.0f}")
        lcd.move_to(0, 3)
        lcd.putstr("Calibration OK!")
        time.sleep(1)

print("\n2. Calibrating MPU...")
init_mpu_baseline()

# ============================================================================
# WIFI & ESP-NOW
# ============================================================================
def connect_wifi():
    lcd.clear()
    lcd.putstr("Connecting WiFi...")
    lcd.move_to(0, 1)
    lcd.putstr(WIFI_SSID)
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    time.sleep(1)
    wlan.active(True)
    if wlan.isconnected():
        wlan.disconnect()
        time.sleep(1)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    
    timeout = 10
    while not wlan.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1
        lcd.move_to(0, 2)
        lcd.putstr(f"Timeout: {timeout}s    ")
    
    if not wlan.isconnected():
        lcd.move_to(0, 3)
        lcd.putstr("WiFi FAILED!")
        raise Exception("WiFi connection failed")
    
    ip = wlan.ifconfig()[0]
    print(f"   ✓ WiFi: {ip}")
    lcd.move_to(0, 2)
    lcd.putstr("Connected!")
    lcd.move_to(0, 3)
    lcd.putstr(ip)
    time.sleep(2)
    
    try:
        ntptime.settime()
        print("   ✓ NTP synced")
    except:
        print("   ⚠️ NTP sync failed")

print("\n3. Connecting WiFi...")
connect_wifi()

# MAC DEBUG
wlan = network.WLAN(network.STA_IF)
mac = wlan.config('mac')
mac_str = ':'.join(['%02X' % b for b in mac])
print("\n=== MAC ADDRESSES ===")
print("MAIN MAC:", mac_str)
print("Expected from baglygte: 24:6F:28:7A:BC:E4")
print("=====================\n")

# ESP-NOW setup
sta = network.WLAN(network.STA_IF)
e = espnow.ESPNow()
e.active(True)
e.add_peer(BAGLYGTE_MAC)
print("   ✓ ESP-NOW initialized")

# ============================================================================
# THINGSBOARD
# ============================================================================
print("\n4. Importing ThingsBoard...")
from uthingsboard.client import TBDeviceMqttClient

# ============================================================================
# FUNCTIONS
# ============================================================================
def read_current():
    global current_readings
    
    if not INA219_AVAILABLE or ina219 is None:
        return 0.0
    
    try:
        current = ina219.get_current()
        current = abs(current)
    except OSError:
        current = current_readings[-1] if current_readings else 0.0
    
    current_readings.append(current)
    if len(current_readings) > MAX_CURRENT_READINGS:
        current_readings.pop(0)
    
    return sum(current_readings) / len(current_readings)

def read_battery():
    raw_adc = battery_adc.read_adc()
    voltage = battery_adc.read_voltage()
    battery_voltage = voltage * 2.12
    
    print(f"[BAT DEBUG] ADC:{raw_adc} | ADC_V:{voltage:.3f}V | Calc:{battery_voltage:.2f}V")
    
    battery_pct = ((battery_voltage - 3.3) / (4.2 - 3.3)) * 100
    battery_pct = max(0, min(100, int(battery_pct)))
    return battery_pct

def calculate_runtime(battery_pct, current_ma):
    if current_ma <= 1:
        return None
    remaining_capacity = BATTERY_CAPACITY * (battery_pct / 100)
    return remaining_capacity / current_ma

def set_neopixel_color(r, g, b):
    if not NEOPIXEL_AVAILABLE:
        return
    for i in range(NEOPIXEL_FIRST_LED):
        np[i] = (0, 0, 0)
    for i in range(NEOPIXEL_FIRST_LED, NEOPIXEL_COUNT):
        np[i] = (r, g, b)
    np.write()

def set_neopixel_green():
    set_neopixel_color(0, 20, 0)

def set_neopixel_red():
    set_neopixel_color(50, 0, 0)

def set_neopixel_white(brightness_pct):
    if NEOPIXEL_AVAILABLE:
        val = int(brightness_pct * 2.55)
        for i in range(NEOPIXEL_FIRST_LED):
            np[i] = (0, 0, 0)
        for i in range(NEOPIXEL_FIRST_LED, NEOPIXEL_COUNT):
            np[i] = (val, val, val)
        np.write()

def set_neopixel_off():
    set_neopixel_color(0, 0, 0)

def start_alarm():
    global alarm_led_state, last_alarm_blink
    alarm_led.value(1)
    set_neopixel_red()
    alarm_led_state = True
    last_alarm_blink = time.ticks_ms()
    alarm_sound.resume()
    print("🚨 ALARM ACTIVATED")

def stop_alarm():
    alarm_led.value(0)
    set_neopixel_green()
    alarm_sound.stop()
    print("🟢 ALARM DEACTIVATED")

def update_alarm_blink():
    global alarm_led_state, last_alarm_blink
    
    if alarm_active:
        now = time.ticks_ms()
        if time.ticks_diff(now, last_alarm_blink) > ALARM_BLINK_RATE:
            alarm_led_state = not alarm_led_state
            alarm_led.value(1 if alarm_led_state else 0)
            
            if NEOPIXEL_AVAILABLE:
                if alarm_led_state:
                    set_neopixel_red()
                else:
                    set_neopixel_color(10, 0, 0)
            
            last_alarm_blink = now
            alarm_sound.tick()

def send_espnow(ldr_val, brightness, is_light_on):
    """Send light control data to baglygte"""
    light_byte = 1 if is_light_on else 0
    msg = struct.pack('HBB', ldr_val, brightness, light_byte)
    try:
        e.send(BAGLYGTE_MAC, msg)
    except:
        pass

def update_automatic_lights():
    """KRAV 16 & 17: LDR + Sunrise API + Motion detection"""
    global light_on, last_light_motion
    
    if not system_enabled or alarm_active:
        if light_on:
            set_neopixel_off()
            send_espnow(0, 0, False)
            light_on = False
        return
    
    now = time.ticks_ms()
    
    # Read sensors
    ldr_value = ldr.read()
    pot_value = pot.read()
    brightness = int((pot_value / 4095) * 100)
    
    # KRAV 17: Check darkness by LDR OR time (Sunrise API)
    is_dark_ldr = ldr_value < DARK_THRESHOLD
    
    rtc = RTC()
    now_time = rtc.datetime()
    current_min = now_time[4] * 60 + now_time[5]
    is_dark_time = current_min < sunrise_min or current_min > sunset_min
    
    is_dark = is_dark_ldr or is_dark_time
    
    # Check motion
    motion_detected = detect_motion()
    if motion_detected:
        last_light_motion = now
    
    idle_time = time.ticks_diff(now, last_light_motion)
    should_light = is_dark and (idle_time < LIGHT_IDLE_TIMEOUT)
    
    # Control lights
    if should_light and not light_on:
        set_neopixel_white(brightness)
        send_espnow(ldr_value, brightness, True)
        light_on = True
        print(f"💡 LIGHTS ON ({brightness}%)")
    elif not should_light and light_on:
        set_neopixel_off()
        send_espnow(ldr_value, brightness, False)
        light_on = False
        print(f"⚫ LIGHTS OFF")
    elif should_light and light_on:
        set_neopixel_white(brightness)

def update_sun_times(lat, lon):
    """KRAV 17: Sunrise/Sunset API"""
    global sunrise_min, sunset_min
    
    try:
        response = urequests.get(f"http://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&formatted=0")
        data = response.json()
        response.close()
        
        sunset_time = data['results']['sunset'].split('T')[1].split('+')[0]
        sunrise_time = data['results']['sunrise'].split('T')[1].split('+')[0]
        
        sunset_h, sunset_m = map(int, sunset_time.split(':')[:2])
        sunrise_h, sunrise_m = map(int, sunrise_time.split(':')[:2])
        
        sunset_h += 1  # CET
        sunrise_h += 1
        
        sunset_min = sunset_h * 60 + sunset_m
        sunrise_min = sunrise_h * 60 + sunrise_m
        
        print(f"☀️ Sunrise {sunrise_h:02d}:{sunrise_m:02d}, Sunset {sunset_h:02d}:{sunset_m:02d}")
        return True
    except Exception as e:
        print(f"API error: {e}")
        return False
    
    
#debug kode ændre igen
def receive_gps_from_baglygte():
    global gps_lat, gps_lon
    
    received = False
    while True:
        host, msg = e.recv(0)
        
        if msg is None:
            break
            
        # Accepter GPS fra enhver kilde hvis det er 8 bytes
        if len(msg) == 8:
            try:
                lat, lon = struct.unpack('ff', msg)
                
                if -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
                    gps_lat = lat
                    gps_lon = lon
                    received = True
                    host_str = ':'.join(['%02X' % b for b in host])
                    print("[MAIN] GPS received:", lat, lon, "from", host_str)
            except:
                pass
    
    return received

def on_server_side_rpc(req_id, method, params):
    global system_enabled, auto_armed, alarm_active, last_motion
    
    try:
        print(f"\n🔥 RPC: {method}={params}")
        
        reply_value = 'false'
        
        if method == 'getState':
            reply_value = str(system_enabled).lower()
            
        elif method == 'setState':
            new_state = params if isinstance(params, bool) else (params == 'true')
            
            if new_state:
                system_enabled = True
                last_motion = time.ticks_ms()
                print("🟢 ENABLED")
            else:
                system_enabled = False
                if alarm_active:
                    alarm_active = False
                    stop_alarm()
                if auto_armed:
                    auto_armed = False
                    set_neopixel_green()
                print("🔴 DISABLED")
                
            reply_value = str(system_enabled).lower()
        
        client.send_rpc_reply(req_id, reply_value)
        
    except Exception as e:
        print(f"RPC ERROR: {e}")

def connect_thingsboard():
    lcd.clear()
    lcd.putstr("Connecting TB...")
    
    client = TBDeviceMqttClient(TB_SERVER, access_token=TB_TOKEN)
    client.connect()
    client.set_server_side_rpc_request_handler(on_server_side_rpc)
    print("   ✓ ThingsBoard connected")
    
    lcd.move_to(0, 2)
    lcd.putstr("Connected!")
    time.sleep(1)
    
    return client

    # Test sending
    try:
        client.send_telemetry({'test': 'startup'})
        print("✅ ThingsBoard test send OK")
    except Exception as e:
        print(f"❌ ThingsBoard test FAILED: {e}")

def check_mqtt_connection():
    global client
    
    try:
        client.send_telemetry({'ping': time.ticks_ms()})
        return True
    except:
        try:
            client.disconnect()
            time.sleep(2)
            client = connect_thingsboard()
            return True
        except:
            return False

def detect_motion():
    global mpu_baseline
    
    if TEST_MODE:
        return True
    
    if not MPU_AVAILABLE:
        return False
    
    max_retries = 3
    retry_delay = 0.01
    
    for attempt in range(max_retries):
        try:
            data = i2c_mpu.readfrom_mem(MPU_ADDR, 0x3B, 6)  # ← ÆNDRET
            x = (data[0] << 8) | data[1]
            y = (data[2] << 8) | data[3]
            z = (data[4] << 8) | data[5]
            
            if x > 32767: x -= 65536
            if y > 32767: y -= 65536
            if z > 32767: z -= 65536
            
            current = math.sqrt(x*x + y*y + z*z)
            diff = abs(current - mpu_baseline)
            
            # Debug (fjern efter test)
            if diff > MOTION_THRESHOLD * 0.5:  # Kun print ved signifikant bevægelse
                print(f"[MPU] Diff: {diff:.0f} | Baseline: {mpu_baseline:.0f}")
            
            return diff > MOTION_THRESHOLD
            
        except OSError:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                return False
        except:
            return False
    
    return False

def read_temperature_humidity():
    try:
        dht_sensor.measure()
        return dht_sensor.temperature(), dht_sensor.humidity()
    except:
        return None, None

def update_lcd(battery, temp, humidity, runtime_str="N/A"):
    global lcd_screen
    
    try:
        lcd.clear()
        
        if alarm_active:
            lcd.putstr("!!! ALARM AKTIV !!!")
            lcd.move_to(0, 1)
            lcd.putstr("THEFT DETECTED!")
            lcd.move_to(0, 2)
            if gps_lat is not None:
                lcd.putstr(f"{gps_lat:.4f},{gps_lon:.4f}"[:20])
            else:
                lcd.putstr("GPS: NO FIX")
            lcd.move_to(0, 3)
            lcd.putstr("Stop via TB")
            return
        
        if lcd_screen == 0:
            lcd.putstr("=== SYSTEM STATUS ===")
            lcd.move_to(0, 1)
            if not system_enabled:
                lcd.putstr("State: DISABLED")
            elif auto_armed:
                lcd.putstr("State: AUTO-ARMED")
            else:
                lcd.putstr("State: ENABLED")
            lcd.move_to(0, 2)
            light_status = "ON" if light_on else "OFF"
            lcd.putstr(f"Light: {light_status}")
            lcd.move_to(0, 3)
            lcd.putstr(f"Bat:{battery}% T:{temp}C"[:20])
        
        elif lcd_screen == 1:
            lcd.putstr("=== POWER MONITOR ===")
            lcd.move_to(0, 1)
            lcd.putstr(f"Battery: {battery}%")
            lcd.move_to(0, 2)
            temp_str = f"{temp}C" if temp is not None else "N/A"
            humid_str = f"{humidity}%" if humidity is not None else "N/A"
            lcd.putstr(f"T:{temp_str} H:{humid_str}")
            lcd.move_to(0, 3)
            lcd.putstr(f"Runtime: {runtime_str}")
        
        elif lcd_screen == 2:
            lcd.putstr("=== GPS & LIGHT ===")
            ldr_val = ldr.read()
            pot_val = pot.read()
            bright = int((pot_val / 4095) * 100)
            lcd.move_to(0, 1)
            if gps_lat is not None:
                lcd.putstr(f"{gps_lat:.5f},{gps_lon:.5f}"[:20])
            else:
                lcd.putstr("GPS: Waiting...")
            lcd.move_to(0, 2)
            lcd.putstr(f"LDR:{ldr_val} Br:{bright}%"[:20])
            lcd.move_to(0, 3)
            lcd.putstr(f"Sun:{sunrise_min//60:02d}:{sunrise_min%60:02d}-{sunset_min//60:02d}:{sunset_min%60:02d}"[:20])
        
    except Exception as e:
        print(f"LCD error: {e}")

def send_telemetry(alarm=False):
    temp, humidity = read_temperature_humidity()
    battery = read_battery()
    current_ma = read_current()
    
        # BESKYT INA219 KALD
    if INA219_AVAILABLE and ina219 is not None:
        try:
            print(f"[DEBUG] INA219 raw current: {ina219.get_current():.2f}mA")
        except:
            print(f"[DEBUG] INA219 raw current: FEJL")
    else:
        print(f"[DEBUG] INA219 raw current: UNAVAILABLE")
    
    print(f"[DEBUG] Averaged current: {current_ma:.2f}mA")
    
    runtime = calculate_runtime(battery, current_ma)
    
    ldr_value = ldr.read()
    pot_value = pot.read()
    brightness = int((pot_value / 4095) * 100)
    
    telemetry = {
        'temp_dht': temp,
        'humidity': humidity,
        'battery_pct': battery,
        'current_ma': current_ma,
        'theft_alarm': alarm,
        'system_enabled': system_enabled,
        'auto_armed': auto_armed,
        'light_on': light_on,
        'light_brightness': brightness,
        'ldr_value': ldr_value,
        'sunrise_time': f"{sunrise_min//60:02d}:{sunrise_min%60:02d}",
        'sunset_time': f"{sunset_min//60:02d}:{sunset_min%60:02d}",
        'free_memory': gc.mem_free()
    }
    
    if gps_lat is not None and gps_lon is not None:
        telemetry['latitude'] = gps_lat
        telemetry['longitude'] = gps_lon
    
    if runtime is not None:
        telemetry['runtime_hours'] = runtime
    
    client.send_telemetry(telemetry)
    
    runtime_str = f"{runtime:.1f}h" if runtime else "N/A"
    update_lcd(battery, temp, humidity, runtime_str)
    
    # Calculate time since last motion
    idle_sec = time.ticks_diff(time.ticks_ms(), last_motion) // 1000
    idle_light_sec = time.ticks_diff(time.ticks_ms(), last_light_motion) // 1000
    
    if alarm:
        status = "🚨 ALARM"
    elif auto_armed:
        status = f"🟡 AUTO-ARMED (idle:{idle_sec}s)"
    elif system_enabled:
        status = f"🟢 ENABLED (idle:{idle_sec}s)"
    else:
        status = "🔴 DISABLED"
    
    gps_str = f"GPS:({gps_lat:.4f},{gps_lon:.4f})" if gps_lat else "GPS:NO FIX"
    print(f"{status}")
    print(f"  Light:{light_on} (idle:{idle_light_sec}s) LDR:{ldr_value} Bright:{brightness}%")
    print(f"  {gps_str} | Bat:{battery}% ({current_ma:.1f}mA)")

# ============================================================================
# MAIN
# ============================================================================
client = connect_thingsboard()

# ← TEST HER
print("\nTesting ThingsBoard connection...")
try:
    client.send_telemetry({'test': 'startup', 'timestamp': time.ticks_ms()})
    print("✅ ThingsBoard test send OK")
except Exception as e:
    print(f"❌ ThingsBoard test FAILED: {e}")
# ← SLUT TEST

# Initial Sunrise API (default København)
update_sun_times(55.6761, 12.5683)

lcd.clear()
lcd.putstr("SYSTEM READY!")
lcd.move_to(0, 1)
lcd.putstr("Smart Bicycle")
lcd.move_to(0, 2)
lcd.putstr("All systems GO")
time.sleep(2)

print("\n🚴 System running...\n")

last_mqtt_check = 0
last_connection_check = 0
MQTT_CHECK_INTERVAL = 50
CONNECTION_CHECK_INTERVAL = 30000

while True:
    now = time.ticks_ms()
    
    # MQTT
    if time.ticks_diff(now, last_mqtt_check) > MQTT_CHECK_INTERVAL:
        try:
            client.check_msg()
            last_mqtt_check = now
        except:
            pass
    
    if time.ticks_diff(now, last_connection_check) > CONNECTION_CHECK_INTERVAL:
        check_mqtt_connection()
        last_connection_check = now
    
    # LCD rotation
    if time.ticks_diff(now, last_lcd_rotation) > LCD_ROTATION_INTERVAL:
        lcd_screen = (lcd_screen + 1) % 3
        last_lcd_rotation = now
    
    # Alarm blink
    update_alarm_blink()
    
        # Debug: Check for ANY ESP-NOW messages
    host, test_msg = e.recv(0)
    if test_msg:
        host_str = ':'.join(['%02X' % b for b in host])
        print("[MAIN] ESP-NOW received", len(test_msg), "bytes from", host_str)

    # Receive GPS from baglygte
    if receive_gps_from_baglygte():
        print(f"[MAIN] GPS updated: {gps_lat}, {gps_lon}")
    
    # Receive GPS from baglygte
    if receive_gps_from_baglygte():
        print(f"[MAIN] GPS updated: {gps_lat}, {gps_lon}")
    
    # KRAV 16: Automatic lights
    update_automatic_lights()
    
    # ESP-NOW periodic send
    if time.ticks_diff(now, last_espnow) > ESPNOW_INTERVAL:
        ldr_value = ldr.read()
        pot_value = pot.read()
        brightness = int((pot_value / 4095) * 100)
        send_espnow(ldr_value, brightness, light_on)
        last_espnow = now
    
    # KRAV 17: Update Sunrise API
    if gps_lat and time.ticks_diff(now, last_api_update) > API_UPDATE:
        update_sun_times(gps_lat, gps_lon)
        last_api_update = now
    
    # Theft detection
    if not TEST_MODE and system_enabled and MPU_AVAILABLE:
        motion = detect_motion()
        
        if motion:
            
            last_motion = now
            print(f"*** DEBUG: last_motion nulstillet til {last_motion} ***")
            last_motion_detected = now
            
            if not alarm_active:
                #last_motion = now
                
                if auto_armed:
                    if motion_start == 0:
                        motion_start = now
                    else:
                        elapsed = time.ticks_diff(now, motion_start)
                        
                        if elapsed > MOTION_CONFIRM:
                            alarm_active = True
                            start_alarm()
                            send_telemetry(alarm=True)
                            last_telemetry = now
                else:
                    motion_start = 0
        else:
            if motion_start != 0:
                if time.ticks_diff(now, last_motion_detected) > MOTION_GRACE:
                    motion_start = 0
        
        # Auto-arm
        idle_time_ms = time.ticks_diff(now, last_motion)
        
        if not auto_armed and not alarm_active and idle_time_ms > IDLE_TIME:
            auto_armed = True
            set_neopixel_off()
            print("🟡 AUTO-ARMED")
    
    # Telemetry
    if alarm_active and time.ticks_diff(now, last_telemetry) > ALARM_TELEMETRY:
        send_telemetry(alarm=True)
        last_telemetry = now
        
    if not alarm_active and time.ticks_diff(now, last_telemetry) > TELEMETRY_INTERVAL:
        send_telemetry(alarm=False)
    
    if not alarm_active and time.ticks_diff(now, last_telemetry) > TELEMETRY_INTERVAL:
        send_telemetry(alarm=False)
        print("📤 Telemetry sent")  # Debug
        last_telemetry = now
