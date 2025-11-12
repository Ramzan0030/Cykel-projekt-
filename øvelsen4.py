"""
Øvelse 4 - Oplad el-cykel når der er billig og grøn energi
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

# LCD display
lcd = GpioLcd(rs_pin=Pin(27), enable_pin=Pin(25),
              d4_pin=Pin(33), d5_pin=Pin(32), d6_pin=Pin(21), d7_pin=Pin(22),
              num_lines=4, num_columns=20)

# Neopixel LED4 (typisk pin 26 på Educaboard med 5 LEDs)
np = NeoPixel(Pin(26), 5)

# Relæ (typisk pin 14 eller 15 på Educaboard)
relay = Pin(14, Pin.OUT)
relay.value(0)  # Start med relæ slukket

###########################################################
# WIFI FORBINDELSE

def connect_wifi():
    """Forbind til WiFi ved boot"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if not wlan.isconnected():
        print('Forbinder til WiFi...')
        lcd.clear()
        lcd.putstr("Forbinder WiFi...")
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
        
        while not wlan.isconnected():
            time.sleep(1)
    
    print('WiFi forbundet:', wlan.ifconfig())
    lcd.clear()
    lcd.putstr("WiFi OK!")
    time.sleep(1)

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
        return 999  # Høj værdi hvis fejl
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
            # Pris er i øre/kWh
            pris = data['records'][0].get('SpotPriceDKK', 999)
            return pris
        return 999  # Høj værdi hvis fejl
    except Exception as e:
        print(f"Pris fejl: {e}")
        return 999

###########################################################
# KONTROL LOGIK

# Tærskelværdier (du kan justere disse)
CO2_THRESHOLD = 80  # gram CO2 pr kWh
PRIS_THRESHOLD = 40  # øre pr kWh

def opdater_system(co2, pris):

    """Opdater LED, relæ og LCD baseret på data"""
    
    # Tjek om energien er grøn (lav CO2)
    green_energy = co2 < CO2_THRESHOLD
    
    # Tjek om prisen er lav
    low_price = pris < PRIS_THRESHOLD
    
    # LED4 (index 3): Grøn hvis grøn energi, rød hvis ikke
    if green_energy:
        np[3] = (0, 50, 0)  # Grøn
    else:
        np[3] = (50, 0, 0)  # Rød
    np.write()
    
    # Relæ: Tænd kun hvis BÅDE grøn energi OG lav pris
    if green_energy and low_price:
        relay.value(1)
        relay_status = "ON"
    else:
        relay.value(0)
        relay_status = "OFF"
    
    # Opdater LCD
    lcd.clear()
    lcd.putstr(f"CO2: {co2:.1f} g/kWh\n")
    lcd.putstr(f"Pris: {pris:.1f} ore\n")
    lcd.putstr(f"Relay: {relay_status}")
    
    # Print til console
    print(f"CO2: {co2:.1f} g/kWh | Pris: {pris:.1f} øre | Relæ: {relay_status}")

###########################################################
# MAIN PROGRAM

# Forbind WiFi ved start
connect_wifi()

# Sluk alle Neopixels først
for i in range(5):
    np[i] = (0, 0, 0)
np.write()

lcd.clear()
lcd.putstr("System klar\nHenter data...")

# Hovedloop
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
        print("Stop!")
        relay.value(0)
        for i in range(5):
            np[i] = (0, 0, 0)
        np.write()
        break
    except Exception as e:
        print(f"Fejl: {e}")
        time.sleep(5)