from machine import Pin, ADC
from neopixel import NeoPixel
from time import sleep

LDR = ADC(Pin(32, Pin.IN))
LDR.atten(ADC.ATTN_11DB)
np = NeoPixel(Pin(26), 12)

while True:
    ldr_value = LDR.read()
    
    if ldr_value > 1600:  # Mørkt
        np.fill((255, 0, 0))  # Rød
    else:  # Lyst
        np.fill((0, 0, 0))  # Slukket
    
    np.write()
    sleep(0.5)