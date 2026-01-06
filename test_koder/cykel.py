import neopixel
from machine import Pin
import time
import urequests

n = 5
p = Pin(26, Pin.OUT)
np = neopixel.NeoPixel(p, n)
relay = Pin(15, Pin.OUT)

def set_led(led_num, r, g, b):
    np[led_num] = (r, g, b)
    np.write()

def check_green_energy():
    try:
        response = urequests.get("https://api.energidataservice.dk/dataset/CO2Emis?limit=1")
        data = response.json()
        co2 = data['records'][0]['CO2Emission']
        response.close()
        return co2 > 50
    except:
        return False

while True:
    if check_green_energy():
        set_led(4, 255, 0, 0)
        relay.on()
    else:
        set_led(4, 0, 255, 0)
        relay.off()
    
    time.sleep(5)