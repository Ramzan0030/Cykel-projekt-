#LDR test eksempel
from machine import Pin, ADC
from time import sleep

ldr = ADC(Pin(4, Pin.IN))

while True:
    print(f"LDR value: {ldr.read()}")
    sleep(1)