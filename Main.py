from adc_sub import ADC_substitute
import time
import network
from machine import UART, I2C, Pin, ADC
import math
import dht
import gc
from gpio_lcd import GpioLcd
from buzzer_music import music
from neopixel import NeoPixel

# ============================================================================
# CONFIGURATION
# ============================================================================
WIFI_SSID = "matt"
WIFI_PASS = "12345678"

TB_TOKEN = "Ctqwsp4GvIZWVD27u4eA"
TB_SERVER = "demo.thingsboard.io"

# Timing
IDLE_TIME = 180_000
MOTION_CONFIRM = 5_000
MOTION_GRACE = 1_000  # Grace period for motion confirmation
TELEMETRY_INTERVAL = 10_000
ALARM_TELEMETRY = 10_000
GPS_UPDATE = 1_000

# Hardware pins
GPS_TX = 17
GPS_RX = 16
MPU_SCL = 18
MPU_SDA = 19
DHT11_PIN = 26
BATTERY_PIN = 34
INA219_I2C_ADDR = 0x40

# Alarm hardware
ALARM_LED_PIN = 14      # Rød LED til alarm blink (backup)
ALARM_BUZZER_PIN = 15   # Passiv buzzer til alarm lyd
NEOPIXEL_PIN = 13       # NeoPixel ring (WS2812)
NEOPIXEL_COUNT = 12     # Antal LEDs i ring (juster efter din ring)
NEOPIXEL_FIRST_LED = 0  # Start LED index (0=normal, 1=skip første LED - ANBEFALET hvis kun 1 LED lyser!)

# Battery configuration
BATTERY_CAPACITY = 2000  # mAh

# ADC calibration for battery percentage
X1, Y1 = 1703, 0
X2, Y2 = 2449, 100
ADC_A = (Y2 - Y1) / (X2 - X1)
ADC_B = Y2 - ADC_A * X2

TEST_MODE = False

# ============================================================================
# CRITICAL: HARDWARE INIT FØRST - FØR UTHINGSBOARD IMPORT
# ============================================================================
print("\n" + "="*50)
print("SMART BICYCLE SYSTEM")
print("="*50)

print("\n1. Initializing hardware (before ThingsBoard)...")

# GPS
gps = UART(2, baudrate=9600, tx=GPS_TX, rx=GPS_RX)

# I2C bus - delt mellem MPU6050 og INA219
i2c = I2C(0, scl=Pin(MPU_SCL), sda=Pin(MPU_SDA), freq=50000)
time.sleep(0.5)

# MPU6050 address
MPU_ADDR = 0x68

# MPU6050 - KRITISK at dette sker før uthingsboard import

MPU_AVAILABLE = True

try:
    i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
    time.sleep(0.1)
    MPU_AVAILABLE = True
    print(f"   ✓ MPU6050 initialized")
except Exception as e:
    print(f"   ✗ MPU init failed: {e}")
    MPU_AVAILABLE = False

# INA219 - Current sensor (deler I2C bus med MPU)
INA219_AVAILABLE = True
try:
    from ina219_lib import INA219
    ina219 = INA219(i2c, INA219_I2C_ADDR)
    print("   ✓ INA219 initialized")
except Exception as e:
    print(f"   ✗ INA219 init failed: {e}")
    INA219_AVAILABLE = False

# DHT11
dht_sensor = dht.DHT11(Pin(DHT11_PIN))

# LCD - Fast pins på educaboard (kan ikke ændres)
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

# Alarm LED (blinker når alarm aktiv)
alarm_led = Pin(ALARM_LED_PIN, Pin.OUT)
alarm_led.value(0)  # Start slukket
print("   ✓ Alarm LED initialized")

# NeoPixel ring (grøn normal, rød blinkende alarm)
NEOPIXEL_AVAILABLE = False
try:
    from neopixel import NeoPixel
    np = NeoPixel(Pin(NEOPIXEL_PIN), NEOPIXEL_COUNT)
    
    # Start grøn (DISARMED)
    # Sluk defekte LEDs før første aktive
    for i in range(NEOPIXEL_FIRST_LED):
        np[i] = (0, 0, 0)
    # Tænd aktive LEDs grøn
    for i in range(NEOPIXEL_FIRST_LED, NEOPIXEL_COUNT):
        np[i] = (0, 20, 0)  # Svag grøn (R, G, B)
    np.write()
    
    NEOPIXEL_AVAILABLE = True
    active_leds = NEOPIXEL_COUNT - NEOPIXEL_FIRST_LED
    if NEOPIXEL_FIRST_LED > 0:
        print(f"   ✓ NeoPixel ring initialized (using LEDs {NEOPIXEL_FIRST_LED+1}-{NEOPIXEL_COUNT}, {active_leds} active)")
    else:
        print(f"   ✓ NeoPixel ring initialized ({NEOPIXEL_COUNT} LEDs)")
except Exception as e:
    print(f"   ⚠️ NeoPixel initialization failed: {e}")
    print("   System continues without NeoPixel (LED only)")
    NEOPIXEL_AVAILABLE = False

# Alarm buzzer (alarm melody) - HØJERE duty cycle for højere lyd!
# Simple alarm melody: alternating high-low tones
alarm_melody = "0 G5 2 0;2 E5 2 0;4 G5 2 0;6 E5 2 0;8 G5 2 0;10 E5 2 0;12 G5 2 0;14 E5 2 0"
alarm_sound = music(songString=alarm_melody, looping=True, tempo=2, duty=50000, pin=Pin(ALARM_BUZZER_PIN))  # duty 50000 (højere lyd!)
alarm_sound.stop()  # Start slukket
print("   ✓ Alarm buzzer initialized (high volume)")

battery_adc = ADC_substitute(BATTERY_PIN)
print("   ✓ Battery ADC initialized (calibrated)")

print("   ✓ All sensors initialized")

print("   Sensors ready - LCD disabled for test")
# ============================================================================
# MPU BASELINE - FØR UTHINGSBOARD
# ============================================================================
mpu_baseline = 0

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
            data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
            x = (data[0] << 8) | data[1]
            y = (data[2] << 8) | data[3]
            z = (data[4] << 8) | data[5]
            
            if x > 32767: x -= 65536
            if y > 32767: y -= 65536
            if z > 32767: z -= 65536
            
            readings.append(math.sqrt(x*x + y*y + z*z))
            
            # LCD progress
            lcd.move_to(0, 2)
            lcd.putstr(f"Sample {i+1}/10")
            
            time.sleep(0.05)
        except Exception as e:
            print(f"   ⚠️ Read failed: {e}")
    
    if readings:
        mpu_baseline = sum(readings) / len(readings)
        print(f"   ✓ MPU baseline: {mpu_baseline:.0f} ({len(readings)} samples)")
        lcd.move_to(0, 3)
        lcd.putstr("Calibration OK!")
        time.sleep(1)
    else:
        print("   ✗ MPU calibration failed")
        lcd.move_to(0, 3)
        lcd.putstr("Calibration FAILED!")
        time.sleep(2)

print("\n2. Calibrating MPU (before network)...")
init_mpu_baseline()

# ============================================================================
# NU FØRST IMPORTÉR UTHINGSBOARD (efter MPU er klar)
# ============================================================================
print("\n3. Importing ThingsBoard library...")
from uthingsboard.client import TBDeviceMqttClient

# ============================================================================
# STATE VARIABLES
# ============================================================================
# Krav ID: 4 - Automatisk armering efter 3 min idle
system_enabled = True    # System ON/OFF (ThingsBoard kontrol: ON=enabled, OFF=disabled)
auto_armed = False       # Automatisk armed efter 3 min ingen bevægelse
alarm_active = False     # Alarm aktiv ved bevægelse efter auto-arming

last_motion = time.ticks_ms()      # Sidste bevægelse timestamp (bruges til auto-arming)
last_telemetry = 0
last_gps_update = 0
motion_start = 0                   # Motion confirmation start (1 sekund delay)
last_motion_detected = 0           # Last detected motion timestamp
last_auto_arm_print = 0            # Printdebounce for auto-arm besked

# Alarm LED blink
last_alarm_blink = 0
alarm_led_state = False
ALARM_BLINK_RATE = 200  # Blink hvert 200ms (5 Hz)

latest_gps = None
latest_speed = None
latest_course = None
prev_gps = None
prev_fix_time = None

# Current monitoring
current_readings = []
MAX_CURRENT_READINGS = 10

# LCD rotation
lcd_screen = 0  # Nuværende skærm (0, 1, 2)
last_lcd_rotation = 0
LCD_ROTATION_INTERVAL = 3000  # Skift skærm hvert 3 sekund

# ============================================================================
# BATTERY & CURRENT FUNCTIONS
# ============================================================================

def read_current():
    """Read current from INA219 with error handling"""
    global current_readings
    
    if not INA219_AVAILABLE:
        return 0.0
    
    try:
        current = ina219.get_current()
        current = abs(current)
    except OSError as e:
        current = current_readings[-1] if current_readings else 0.0
    
    current_readings.append(current)
    if len(current_readings) > MAX_CURRENT_READINGS:
        current_readings.pop(0)
    
    return sum(current_readings) / len(current_readings)

def read_battery():
    """Read battery voltage with ACTUAL corrections from multimeter calibration"""
    voltage = battery_adc.read_voltage()  # ADC læser ~1.72V

    battery_voltage = voltage * 1.691
    
    # 3.0V = 0%, 4.2V = 100%
    battery_pct = ((battery_voltage - 3.3) / (4.2 - 3.3)) * 100
    battery_pct = max(0, min(100, int(battery_pct)))
    
    return battery_pct

def calculate_runtime(battery_pct, current_ma):
    """Calculate remaining runtime in hours"""
    if current_ma <= 1:
        return None
    
    remaining_capacity = BATTERY_CAPACITY * (battery_pct / 100)
    return remaining_capacity / current_ma

def calculate_runtime(battery_pct, current_ma):
    """Calculate remaining runtime in hours"""
    if current_ma <= 1:  # Current too low to calculate
        return None
    
    remaining_capacity = BATTERY_CAPACITY * (battery_pct / 100)
    return remaining_capacity / current_ma

# ============================================================================
# ALARM CONTROL (LED + BUZZER + NEOPIXEL)
# ============================================================================
def set_neopixel_color(r, g, b):
    """Set alle NeoPixels til samme farve (skipper defekte LEDs)"""
    if not NEOPIXEL_AVAILABLE:
        return
    
    # Sluk eventuelle defekte LEDs før første aktive LED
    for i in range(NEOPIXEL_FIRST_LED):
        np[i] = (0, 0, 0)
    
    # Set farve på aktive LEDs
    for i in range(NEOPIXEL_FIRST_LED, NEOPIXEL_COUNT):
        np[i] = (r, g, b)
    np.write()

def set_neopixel_green():
    """Grøn farve for normal drift (DISARMED eller ARMED)"""
    if NEOPIXEL_AVAILABLE:
        set_neopixel_color(0, 20, 0)  # Svag grøn

def set_neopixel_red():
    """Rød farve for alarm"""
    if NEOPIXEL_AVAILABLE:
        set_neopixel_color(50, 0, 0)  # Kraftig rød

def set_neopixel_off():
    """Sluk alle NeoPixels"""
    if NEOPIXEL_AVAILABLE:
        set_neopixel_color(0, 0, 0)

def start_alarm():
    """Start alarm: blink LED, NeoPixel rød og afspil buzzer lyd"""
    global alarm_led_state, last_alarm_blink
    alarm_led.value(1)  # Tænd LED
    set_neopixel_red()  # NeoPixel rød (hvis available)
    alarm_led_state = True
    last_alarm_blink = time.ticks_ms()
    alarm_sound.resume()  # Start buzzer melody
    np_status = "NeoPixel RED + " if NEOPIXEL_AVAILABLE else ""
    print(f"🚨 ALARM ACTIVATED: LED + {np_status}Buzzer")

def stop_alarm():
    """Stop alarm: sluk LED, NeoPixel grøn, stop buzzer"""
    alarm_led.value(0)  # Sluk LED
    set_neopixel_green()  # NeoPixel grøn (hvis available)
    alarm_sound.stop()  # Stop buzzer
    np_status = "NeoPixel GREEN + " if NEOPIXEL_AVAILABLE else ""
    print(f"🟢 ALARM DEACTIVATED: LED off + {np_status}Buzzer silent")

def update_alarm_blink():
    """Blink alarm LED og NeoPixel med fast rate når alarm aktiv"""
    global alarm_led_state, last_alarm_blink
    
    if alarm_active:
        now = time.ticks_ms()
        if time.ticks_diff(now, last_alarm_blink) > ALARM_BLINK_RATE:
            alarm_led_state = not alarm_led_state
            
            # LED blink
            alarm_led.value(1 if alarm_led_state else 0)
            
            # NeoPixel blink (hvis available)
            if NEOPIXEL_AVAILABLE:
                if alarm_led_state:
                    set_neopixel_red()  # Kraftig rød
                else:
                    set_neopixel_color(10, 0, 0)  # Svag rød (ikke helt slukket)
            
            last_alarm_blink = now
            
            # Tick buzzer for continuous sound
            alarm_sound.tick()


# ============================================================================
# WIFI & MQTT
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
    print(f"   ✓ WiFi connected: {ip}")
    lcd.move_to(0, 2)
    lcd.putstr("Connected!")
    lcd.move_to(0, 3)
    lcd.putstr(ip)
    time.sleep(2)


def on_server_side_rpc(req_id, method, params):
    """Handle ThingsBoard RPC commands for system enable/disable (Krav ID: 4)"""
    global system_enabled, auto_armed, alarm_active, last_motion
    
    try:
        print(f"\n📥 RPC RECEIVED: method={method}, params={params}, req_id={req_id}")
        
        reply_value = 'false' 
        
        if method == 'getState':
            reply_value = str(system_enabled).lower()
            print(f"   → Returning state: {reply_value}")
            
        elif method == 'setState':
            new_state = params if isinstance(params, bool) else (params == 'true')
            print(f"   → Changing state to: {new_state}")
            
            if new_state:
                # ENABLE system
                system_enabled = True
                last_motion = time.ticks_ms()
                
                lcd.clear()
                lcd.putstr("System ENABLED")
                lcd.move_to(0, 1)
                lcd.putstr("via ThingsBoard")
                
                print("🟢 System ENABLED via ThingsBoard")
                
            else:
                # DISABLE system - STOP EVERYTHING
                system_enabled = False
                
                # KRITISK: Stop alarm hvis aktiv
                if alarm_active:
                    alarm_active = False
                    stop_alarm()
                    print("🚨 Alarm STOPPED via ThingsBoard")
                
                # Reset auto-armed
                if auto_armed:
                    auto_armed = False
                    set_neopixel_green()
                    print("🟡 Auto-arm CLEARED via ThingsBoard")
                
                lcd.clear()
                lcd.putstr("System DISABLED")
                lcd.move_to(0, 1)
                lcd.putstr("via ThingsBoard")
                lcd.move_to(0, 2)
                lcd.putstr("Alarm: OFF")
                
                print("🔴 System DISABLED via ThingsBoard")
                
            reply_value = str(system_enabled).lower()
        
        # Send svar tilbage
        client.send_rpc_reply(req_id, reply_value)
        print(f"   ✅ RPC reply sent: {reply_value}\n")
        
    except Exception as e:
        print(f"   ❌ RPC ERROR: {e}")
        import sys
        sys.print_exception(e)
        try:
            client.send_rpc_reply(req_id, 'error')
        except:
            pass


def connect_thingsboard():
    lcd.clear()
    lcd.putstr("Connecting to")
    lcd.move_to(0, 1)
    lcd.putstr("ThingsBoard...")
    
    client = TBDeviceMqttClient(TB_SERVER, access_token=TB_TOKEN)
    client.connect()
    client.set_server_side_rpc_request_handler(on_server_side_rpc)
    print("   ✓ ThingsBoard connected")
    
    lcd.move_to(0, 2)
    lcd.putstr("Connected!")
    time.sleep(1)
    
    return client


def check_mqtt_connection():
    """Check og genopret MQTT forbindelse hvis nødvendigt"""
    global client
    
    try:
        # Prøv at sende en ping/dummy request
        client.send_telemetry({'ping': time.ticks_ms()})
        return True
    except Exception as e:
        print(f"⚠️ MQTT connection lost: {e}")
        print("   Attempting reconnect...")
        
        try:
            client.disconnect()
            time.sleep(2)
            client = connect_thingsboard()
            print("   ✅ MQTT reconnected")
            return True
        except Exception as e2:
            print(f"   ❌ Reconnect failed: {e2}")
            return False
# ============================================================================
# MPU MOTION DETECTION - FORBEDRET MED RETRY LOGIC
# ============================================================================
def detect_motion():
    global mpu_baseline
    
    if TEST_MODE:
        return True
    
    if not MPU_AVAILABLE:
        return False
    
    max_retries = 3
    retry_delay = 0.01  # 10ms mellem retries
    
    for attempt in range(max_retries):
        try:
            data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
            x = (data[0] << 8) | data[1]
            y = (data[2] << 8) | data[3]
            z = (data[4] << 8) | data[5]
            
            if x > 32767: x -= 65536
            if y > 32767: y -= 65536
            if z > 32767: z -= 65536
            
            current = math.sqrt(x*x + y*y + z*z)
            diff = abs(current - mpu_baseline)
            
            # Kun print når der faktisk er betydelig motion (reducer spam)
            if diff > 5000:
                print(f"✅ MOTION! diff={diff:.0f}, attempt={attempt+1}")
                return True
            
            return False  # Succesful read, ingen motion
            
        except OSError as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                # Kun print error ved sidste forsøg
                print(f"⚠️ MPU timeout after {max_retries} attempts")
                return False
        except Exception as e:
            print(f"❌ MPU unexpected error: {e}")
            return False
    
    return False


# ============================================================================
# GPS
# ============================================================================
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
    
    speed = 0.0  # ← ÆNDRET: Default til 0
    if parts[7]:
        try:
            speed_raw = float(parts[7]) * 1.852
            if 0 <= speed_raw <= 80:  # ← Max Hastighed(kan ændres)
                speed = speed_raw
            else:
                print(f"⚠️ GPS: Invalid speed {speed_raw:.0f} km/t ignored")
        except:
            pass
    
    course = None
    if parts[8]:
        try:
            course = float(parts[8])
        except:
            pass
    
    return lat, lon, speed, course

def update_gps():
    global latest_gps, latest_speed, latest_course, prev_gps, prev_fix_time
    
    if gps.any():
        line = gps.readline()
        try:
            sentence = line.decode('ascii').strip()
            if sentence.startswith('$GPRMC') or sentence.startswith('$GNRMC'):
                result = parse_gprmc(sentence)
                if result:
                    lat, lon, speed, course = result
                    now = time.ticks_ms()
                    
                    latest_gps = (lat, lon)
                    latest_course = course
                    latest_speed = speed if speed is not None else 0.0
                    
                    prev_gps = (lat, lon)
                    prev_fix_time = now
        except:
            pass


def wait_for_gps():
    global latest_gps
    print("   Waiting for GPS fix...")
    
    lcd.clear()
    lcd.putstr("Waiting for GPS...")
    
    timeout = 60
    while latest_gps is None and timeout > 0:
        update_gps()
        
        # Update LCD countdown
        lcd.move_to(0, 1)
        lcd.putstr(f"Timeout: {timeout}s    ")
        
        time.sleep(0.1)
        timeout -= 1
    
    if latest_gps:
        print(f"   ✓ GPS fix: {latest_gps}, speed: {latest_speed} km/h")
        lcd.move_to(0, 2)
        lcd.putstr("GPS Fix OK!")
        lcd.move_to(0, 3)
        lcd.putstr(f"{latest_gps[0]:.4f},{latest_gps[1]:.4f}")
        time.sleep(2)
    else:
        print("   ⚠️ GPS timeout (continuing without fix)")
        lcd.move_to(0, 2)
        lcd.putstr("GPS Timeout!")
        lcd.move_to(0, 3)
        lcd.putstr("Continuing...")
        time.sleep(2)


# ============================================================================
# SENSORS
# ============================================================================
def read_temperature_humidity():
    try:
        dht_sensor.measure()
        return dht_sensor.temperature(), dht_sensor.humidity()
    except:
        return None, None


# ============================================================================
# LCD DISPLAY
# ============================================================================
def update_lcd(speed, direction, lat, lon, battery, temp, humidity, runtime_str="N/A"):
    """Update LCD display with rotating screens (Krav ID: 2)"""
    global lcd_screen
    
    try:
        lcd.clear()
        
        # ALARM AKTIV: Vis altid alarm besked (ignorer rotation)
        if alarm_active:
            lcd.putstr("!!! ALARM AKTIV !!!")
            lcd.move_to(0, 1)
            lcd.putstr("THEFT DETECTED!")
            lcd.move_to(0, 2)
            if lat is not None and lon is not None:
                lcd.putstr(f"{lat:.4f},{lon:.4f}"[:20])
            else:
                lcd.putstr("GPS: NO FIX")
            lcd.move_to(0, 3)
            lcd.putstr("Stop via ThingsBoard")
            return
        
        # SKÆRM 0: Hastighed, Retning, GPS
        if lcd_screen == 0:
            lcd.putstr("=== GPS & MOVEMENT ===")
            lcd.move_to(0, 1)
            lcd.putstr(f"Speed:  {speed:5.1f} km/h")
            lcd.move_to(0, 2)
            lcd.putstr(f"Course: {direction:5.1f} deg")
            lcd.move_to(0, 3)
            if lat is not None and lon is not None:
                lcd.putstr(f"{lat:.4f},{lon:.4f}"[:20])
            else:
                lcd.putstr("GPS: NO FIX")
        
        # SKÆRM 1: Batteri, Temperatur, Fugtighed
        elif lcd_screen == 1:
            lcd.putstr("=== POWER & SENSORS ==")
            lcd.move_to(0, 1)
            lcd.putstr(f"Battery: {battery}%")
            lcd.move_to(0, 2)
            temp_str = f"{temp}C" if temp is not None else "N/A"
            humid_str = f"{humidity}%" if humidity is not None else "N/A"
            lcd.putstr(f"Temp: {temp_str} H: {humid_str}")
            lcd.move_to(0, 3)
            lcd.putstr(f"Runtime: {runtime_str}")
        
        # SKÆRM 2: System status
        elif lcd_screen == 2:
            lcd.putstr("=== SYSTEM STATUS ===")
            temp_str = f"{temp}C" if temp is not None else "N/A"
            humid_str = f"{humidity}%" if humidity is not None else "N/A"
            lcd.move_to(0, 1)
            lcd.move_to(0, 1)
            if not system_enabled:
                lcd.putstr("State: DISABLED")
            elif auto_armed:
                lcd.putstr("State: AUTO-ARMED")
            else:
                lcd.putstr("State: ENABLED")
            lcd.move_to(0, 2)
            lcd.putstr(f"Bat: {battery}% T: {temp_str}")
            lcd.move_to(0, 3)
            if lat is not None:
                lcd.putstr(f"{lat:.5f},{lon:.5f}"[:20])
            else:
                lcd.putstr("Waiting for GPS...")
        
    except Exception as e:
        print(f"LCD error: {e}")
        
# ============================================================================
# TELEMETRY
# ============================================================================
def send_telemetry(alarm=False):
    # Læs alle sensorer FØRST
    temp, humidity = read_temperature_humidity()
    battery = read_battery()
    current_ma = read_current()
    runtime = calculate_runtime(battery, current_ma)
    
    lat = latest_gps[0] if latest_gps else None
    lon = latest_gps[1] if latest_gps else None
    speed = latest_speed if latest_speed is not None else 0.0
    course = latest_course if latest_course is not None else 0.0
    
    # Build telemetry dict
    telemetry = {
        'temp_dht': temp,
        'humidity': humidity,
        'battery_pct': battery,
        'current_ma': current_ma,
        'theft_alarm': alarm,
        'system_enabled': system_enabled,
        'auto_armed': auto_armed,
        'free_memory': gc.mem_free()
    }
    
    if lat is not None and lon is not None:
        telemetry.update({
            'latitude': lat,
            'longitude': lon,
            'speed_kmh': speed,
            'direction_deg': course
        })
    
    if runtime is not None:
        telemetry['runtime_hours'] = runtime
    
    client.send_telemetry(telemetry)
    
    # Update LCD (runtime ER defineret nu)
    runtime_str = f"{runtime:.1f}h" if runtime else "N/A"
    update_lcd(speed, course, lat, lon, battery, temp, humidity, runtime_str)
    
    # Console output
    if alarm:
        status = "🚨 ALARM"
    elif auto_armed:
        status = "🟡 AUTO-ARMED"
    elif system_enabled:
        status = "🟢 ENABLED"
    else:
        status = "🔴 DISABLED"
    
    gps_str = f"GPS: ({lat:.5f}, {lon:.5f})" if lat else "GPS: NO FIX"
    print(f"{status} | {gps_str} | Speed: {speed:.1f} km/h")
    print(f"Temp: {temp}°C | Humidity: {humidity}% | Battery: {battery}%")
    print(f"Current: {current_ma:.1f} mA | Runtime: {runtime_str}")
    print("-" * 60)
    
# ============================================================================
# MAIN - Network init EFTER MPU calibration
# ============================================================================
print("\n4. Connecting to network...")
connect_wifi()
client = connect_thingsboard()

print("\n5. Waiting for GPS...")
wait_for_gps()

# System ready!
lcd.clear()
lcd.putstr("SYSTEM READY!")
lcd.move_to(0, 1)
lcd.putstr("Smart Bicycle")
lcd.move_to(0, 2)
lcd.putstr("Status: ENABLED")  # Start ENABLED (Krav ID: 4)
lcd.move_to(0, 3)
if NEOPIXEL_AVAILABLE:
    lcd.putstr("Auto-arm: 3 min")
else:
    lcd.putstr("LED: Standby")
time.sleep(3)

print("\n🚴 System running (ENABLED - Krav ID: 4)...\n")
print("ℹ️  System will AUTO-ARM after 3 minutes without motion")
print("ℹ️  Disable via ThingsBoard to prevent auto-arming")
if NEOPIXEL_AVAILABLE:
    print("🟢 NeoPixel: GREEN (enabled)")
else:
    print("⚠️  NeoPixel not available - using LED only")

# Tracking af sidste check_msg tid
last_mqtt_check = 0
MQTT_CHECK_INTERVAL = 50  # Check hvert 50ms (20 gange per sekund)

print("ℹ️  Disable via ThingsBoard to prevent auto-arming")
if NEOPIXEL_AVAILABLE:
    print("🟢 NeoPixel: GREEN (enabled)")
else:
    print("⚠️  NeoPixel not available - using LED only")

# Tracking af sidste check_msg tid
last_mqtt_check = 0
last_connection_check = 0  # ← TILFØJ DENNE LINJE
MQTT_CHECK_INTERVAL = 50  # Check hvert 50ms (20 gange per sekund)
CONNECTION_CHECK_INTERVAL = 30000  # ← TILFØJ DENNE LINJE

while True:
    now = time.ticks_ms()
    
    # Check MQTT beskeder hyppigt
    if time.ticks_diff(now, last_mqtt_check) > MQTT_CHECK_INTERVAL:
        try:
            client.check_msg()
            last_mqtt_check = now
        except Exception as e:
            print(f"⚠️ MQTT check_msg error: {e}")
    
    # Check MQTT forbindelse periodisk
    if time.ticks_diff(now, last_connection_check) > CONNECTION_CHECK_INTERVAL:
        check_mqtt_connection()
        last_connection_check = now
        
    # LCD rotation (hvert 3 sekund)
    if time.ticks_diff(now, last_lcd_rotation) > LCD_ROTATION_INTERVAL:
        lcd_screen = (lcd_screen + 1) % 3
        last_lcd_rotation = now
        temp, humidity = read_temperature_humidity()
        battery = read_battery()
        current_ma = read_current()
        runtime = calculate_runtime(battery, current_ma)
        runtime_str = f"{runtime:.1f}h" if runtime else "N/A"
        lat = latest_gps[0] if latest_gps else None
        lon = latest_gps[1] if latest_gps else None
        speed = latest_speed if latest_speed is not None else 0.0
        course = latest_course if latest_course is not None else 0.0
        update_lcd(speed, course, lat, lon, battery, temp, humidity, runtime_str)
    
    # Update alarm LED blink
    update_alarm_blink()
    
    # GPS update
    if time.ticks_diff(now, last_gps_update) > GPS_UPDATE:
        update_gps()
        last_gps_update = now

    # AUTO-ARMERING LOGIK
    if not TEST_MODE and system_enabled and MPU_AVAILABLE:
        motion = detect_motion()
        time.sleep(0.005)
        
        if motion:
            print(f"🔍 motion=True, auto_armed={auto_armed}, alarm_active={alarm_active}")
            last_motion_detected = now
            
            if not alarm_active:
                last_motion = now
                
                if auto_armed:
                    if motion_start == 0:
                        motion_start = now
                        print(f"⏱️ Motion confirmation started (need {MOTION_CONFIRM}ms)")
                    else:
                        elapsed = time.ticks_diff(now, motion_start)
                        print(f"⏱️ Progress: {elapsed}ms / {MOTION_CONFIRM}ms")
                        
                        if elapsed > MOTION_CONFIRM:
                            alarm_active = True
                            start_alarm()
                            send_telemetry(alarm=True)
                            last_telemetry = now
                            
                            print("="*60)
                            print("🚨 THEFT ALARM TRIGGERED!")
                            print(f"   GPS: {latest_gps if latest_gps else 'NO FIX'}")
                            if NEOPIXEL_AVAILABLE:
                                print("   🔴 NeoPixel: RED BLINKING")
                            print("="*60)
                else:
                    motion_start = 0
        else:
            if motion_start != 0:
                if time.ticks_diff(now, last_motion_detected) > MOTION_GRACE:
                    print(f"⏸️ Motion timeout - reset confirmation")
                    motion_start = 0
        
        # Check om idle time → AUTO-ARM
        idle_time_ms = time.ticks_diff(now, last_motion)
        
        if not auto_armed and not alarm_active and idle_time_ms > IDLE_TIME:
            auto_armed = True
            set_neopixel_green()
            
            if time.ticks_diff(now, last_auto_arm_print) > 5000:
                print("="*60)
                print("🟡 SYSTEM AUTO-ARMED (Krav ID: 4)")
                print(f"   No motion detected for {IDLE_TIME//1000} seconds")
                print("   Will trigger alarm on next motion detection")
                if NEOPIXEL_AVAILABLE:
                    print("   NeoPixel: GREEN (standby)")
                print("="*60)
                last_auto_arm_print = now
    
    # TELEMETRY - Alarm og Regular
    if alarm_active and time.ticks_diff(now, last_telemetry) > ALARM_TELEMETRY:
        send_telemetry(alarm=True)
        last_telemetry = now
        
    if not alarm_active and time.ticks_diff(now, last_telemetry) > TELEMETRY_INTERVAL:
        send_telemetry(alarm=False)
        last_telemetry = now