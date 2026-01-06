from machine import I2C, Pin
import time
import math

# I2C setup
i2c = I2C(0, scl=Pin(18), sda=Pin(19), freq=100000)
MPU_ADDR = 0x68

# Wake up MPU6050
i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
time.sleep(0.1)

def read_accel():
    """Læs accelerometer data"""
    data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
    
    # Convert til signed 16-bit
    x = (data[0] << 8) | data[1]
    y = (data[2] << 8) | data[3]
    z = (data[4] << 8) | data[5]
    
    # Konverter til signed
    if x > 32767: x -= 65536
    if y > 32767: y -= 65536
    if z > 32767: z -= 65536
    
    return x, y, z

def detect_movement(threshold=5000):
    """Detekter bevægelse baseret på acceleration"""
    x, y, z = read_accel()
    total = math.sqrt(x*x + y*y + z*z)
    return total > threshold, total

# Test loop
print("Ryst boardet for at teste bevægelse...")
print("CTRL+C for at stoppe\n")

while True:
    moving, accel = detect_movement()
    
    if moving:
        print(f"🔴 BEVÆGELSE! Accel: {accel:.0f}")
    else:
        print(f"⚪ Stillstand. Accel: {accel:.0f}")
    
    time.sleep(0.5)