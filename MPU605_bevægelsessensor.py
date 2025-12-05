from machine import I2C, Pin
import time
import math

i2c = I2C(0, scl=Pin(18), sda=Pin(19), freq=100000)
MPU_ADDR = 0x68
i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
time.sleep(0.1)

def read_accel():
    data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
    x = (data[0] << 8) | data[1]
    y = (data[2] << 8) | data[3]
    z = (data[4] << 8) | data[5]
    
    if x > 32767: x -= 65536
    if y > 32767: y -= 65536
    if z > 32767: z -= 65536
    
    return math.sqrt(x*x + y*y + z*z)

# Baseline - gennemsnit af første 10 målinger
baseline = sum(read_accel() for _ in range(10)) / 10
print(f"Baseline: {baseline:.0f}\n")

while True:
    current = read_accel()
    diff = abs(current - baseline)
    
    if diff > 2000:  # Ændring threshold
        print(f"🔴 BEVÆGELSE! Diff: {diff:.0f}")
        baseline = current  # Opdater baseline
    else:
        print(f"⚪ Stille     Diff: {diff:.0f}")
    
    time.sleep(0.3)