from machine import UART, Pin
import time

# GPS på UART2
gps_uart = UART(2, baudrate=9600, tx=17, rx=16)

print("Læser GPS data... (tag board udenfor)\n")

while True:
    if gps_uart.any():
        line = gps_uart.readline()
        try:
            decoded = line.decode('ascii').strip()
            # Vis kun GPGGA (position) og GPRMC (hastighed)
            if decoded.startswith('$GPGGA') or decoded.startswith('$GPRMC'):
                print(decoded)
        except:
            pass
    time.sleep(0.1)