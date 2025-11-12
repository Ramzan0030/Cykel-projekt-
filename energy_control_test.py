from machine import Pin
import time
import urequests
import network
from neopixel import NeoPixel
from gpio_lcd import GpioLcd

GRÆNSE = 50
LYSSTYRKE = 10

np = NeoPixel(Pin(26), 2)
relay = Pin(15, Pin.OUT)

try:
    lcd = GpioLcd(rs_pin=Pin(27), enable_pin=Pin(25),
                  d4_pin=Pin(33), d5_pin=Pin(32), 
                  d6_pin=Pin(21), d7_pin=Pin(22),
                  num_lines=4, num_columns=20)
    LCD_OK = True
except:
    LCD_OK = False

# WIFI
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect("IT-TEKNOLOG-2", "KeaTeknolog6!")

print("Forbinder WiFi...")
while not wlan.isconnected():
    time.sleep(1)

print("WiFi forbundet:", wlan.ifconfig())
time.sleep(2)  # Vent ekstra før API kald

while True:
    try:
        print("Henter CO2...")
        response = urequests.get('https://api.energidataservice.dk/dataset/CO2Emis?limit=1')
        co2 = response.json()['records'][0]['CO2Emission']
        response.close()
        print(f"CO2: {co2}")
    except:
        pass
    
    try:
        print("Henter pris...")
        response = urequests.get('https://api.energidataservice.dk/dataset/Elspotprices?limit=1')
        pris = response.json()['records'][0]['SpotPriceDKK']
        response.close()
        print(f"Pris: {pris}")
        
        if co2 < GRÆNSE:
            np[0] = (0, LYSSTYRKE, 0)
            relay.value(1)
            status = "OPLADER"
        else:
            np[0] = (LYSSTYRKE, 0, 0)
            relay.value(0)
            status = "STOPPER"
        
        np.write()
        
        if LCD_OK:
            lcd.clear()
            lcd.putstr(f"CO2: {co2:.1f} g/kWh\n")
            lcd.putstr(f"Pris: {pris:.1f} ore\n")
            lcd.putstr(f"\n{status}")
        
        print(f"→ {status}\n")
        
    except Exception as e:
        print(f"FEJL: {e}")
        import sys
        sys.print_exception(e)
    
    time.sleep(20)