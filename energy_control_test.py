"""
Kombineret energistyringssystem med CO2 og pris
Styrer relæ baseret på grøn energi og lave priser
"""
from machine import Pin
import time
import urequests
import network
from neopixel import NeoPixel
from gpio_lcd import GpioLcd
import secrets

###########################################################
# HARDWARE OPSÆTNING

# LCD display (valgfrit - kan fjernes hvis ikke tilgængelig)
try:
    lcd = GpioLcd(rs_pin=Pin(27), enable_pin=Pin(25),
                  d4_pin=Pin(33), d5_pin=Pin(32), d6_pin=Pin(21), d7_pin=Pin(22),
                  num_lines=4, num_columns=20)
    LCD_AVAILABLE = True
except:
    LCD_AVAILABLE = False
    print("LCD ikke tilgængelig - fortsætter uden")

# Neopixel LEDs
n = 5
np = NeoPixel(Pin(26), n)

# Relæ (kan bruge pin 14 eller 15)
relay = Pin(15, Pin.OUT)
relay.value(0)

###########################################################
# WIFI FORBINDELSE

def connect_wifi():
    """Forbind til WiFi ved boot"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if not wlan.isconnected():
        print('Forbinder til WiFi...')
        if LCD_AVAILABLE:
            lcd.clear()
            lcd.putstr("Forbinder WiFi...")
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
        
        timeout = 0
        while not wlan.isconnected() and timeout < 30:
            time.sleep(1)
            timeout += 1
        
        if not wlan.isconnected():
            print("WiFi fejl - tjek credentials")
            return False
    
    print('WiFi forbundet:', wlan.ifconfig())
    if LCD_AVAILABLE:
        lcd.clear()
        lcd.putstr("WiFi OK!")
        time.sleep(1)
    return True

###########################################################
# LED FUNKTIONER

def set_led(led_num, r, g, b):
    """Sæt en enkelt LED til RGB farve"""
    if 0 <= led_num < n:
        np[led_num] = (r, g, b)
        np.write()

def clear_all_leds():
    """Sluk alle LEDs"""
    for i in range(n):
        np[i] = (0, 0, 0)
    np.write()

###########################################################
# API FUNKTIONER

def hent_co2_data():
    """Hent seneste CO2 data (g CO2/kWh)"""
    url = 'https://api.energidataservice.dk/dataset/CO2Emis?limit=1'
    try:
        response = urequests.get(url)
        data = response.json()
        response.close()
        
        if data.get('records'):
            co2 = data['records'][0].get('CO2Emission', 999)
            return co2
        return 999
    except Exception as e:
        print(f"CO2 fejl: {e}")
        return 999

def hent_spotpris():
    """Hent seneste elpris (øre/kWh)"""
    url = 'https://api.energidataservice.dk/dataset/Elspotprices?limit=1'
    try:
        response = urequests.get(url)
        data = response.json()
        response.close()
        
        if data.get('records'):
            pris = data['records'][0].get('SpotPriceDKK', 999)
            return pris
        return 999
    except Exception as e:
        print(f"Pris fejl: {e}")
        return 999

###########################################################
# KONTROL LOGIK

# Tærskelværdier (juster efter behov)
CO2_THRESHOLD = 80   # gram CO2 pr kWh
PRIS_THRESHOLD = 40  # øre pr kWh

def opdater_system(co2, pris):
    """Opdater LED, relæ og LCD baseret på data"""
    
    # Tjek betingelser
    green_energy = co2 < CO2_THRESHOLD
    low_price = pris < PRIS_THRESHOLD
    
    # LED 4 (index 4): Grøn hvis grøn energi, rød hvis ikke
    if green_energy:
        set_led(4, 0, 255, 0)  # Grøn
    else:
        set_led(4, 255, 0, 0)  # Rød
    
    # Relæ: Tænd kun hvis BÅDE grøn energi OG lav pris
    # (eller kun grøn energi hvis du vil ignorere pris)
    if green_energy and low_price:
        relay.value(1)
        relay_status = "ON - Lader"
    else:
        relay.value(0)
        relay_status = "OFF"
    
    # Opdater LCD hvis tilgængelig
    if LCD_AVAILABLE:
        lcd.clear()
        lcd.putstr(f"CO2: {co2:.1f} g/kWh\n")
        lcd.putstr(f"Pris: {pris:.1f} ore\n")
        lcd.putstr(f"Status: {relay_status}")
    
    # Print til console
    print(f"CO2: {co2:.1f} g/kWh | Pris: {pris:.1f} øre | {relay_status}")

###########################################################
# MAIN PROGRAM

print("Starter energistyring...")

# Forbind WiFi
if not connect_wifi():
    print("Kan ikke fortsætte uden WiFi")
    if LCD_AVAILABLE:
        lcd.clear()
        lcd.putstr("WiFi fejl!")
    # Blink rødt 3 gange
    for _ in range(3):
        set_led(4, 255, 0, 0)
        time.sleep(0.5)
        set_led(4, 0, 0, 0)
        time.sleep(0.5)
    raise Exception("WiFi fejl")

# Sluk alle LEDs ved start
clear_all_leds()

if LCD_AVAILABLE:
    lcd.clear()
    lcd.putstr("System klar\nHenter data...")

# Hovedloop
print("Starter overvågning...")
while True:
    try:
        # Hent data fra API
        co2 = hent_co2_data()
        pris = hent_spotpris()
        
        # Opdater system
        opdater_system(co2, pris)
        
        # Vent 5 sekunder før næste tjek
        time.sleep(5)
        
    except KeyboardInterrupt:
        print("\nStopper program...")
        relay.value(0)
        clear_all_leds()
        if LCD_AVAILABLE:
            lcd.clear()
            lcd.putstr("System stoppet")
        break
        
    except Exception as e:
        print(f"Fejl i hovedloop: {e}")
        # Blink gul ved fejl
        set_led(4, 255, 255, 0)
        time.sleep(1)
        set_led(4, 0, 0, 0)
        time.sleep(4)