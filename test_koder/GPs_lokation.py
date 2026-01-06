from machine import UART
import time

gps = UART(2, baudrate=9600, tx=17, rx=16)

def parse_gprmc(sentence):
    """Parse GPRMC for hastighed og position"""
    parts = sentence.split(',')
    if len(parts) < 8 or parts[2] != 'A':  # A = valid
        return None
    
    # Lat: DDMM.MMMMM
    lat_raw = parts[3]
    lat_deg = int(lat_raw[:2]) + float(lat_raw[2:]) / 60
    if parts[4] == 'S':
        lat_deg = -lat_deg
    
    # Lon: DDDMM.MMMMM
    lon_raw = parts[5]
    lon_deg = int(lon_raw[:3]) + float(lon_raw[3:]) / 60
    if parts[6] == 'W':
        lon_deg = -lon_deg
    
    # Hastighed i knob → km/h
    speed_knots = float(parts[7]) if parts[7] else 0
    speed_kmh = speed_knots * 1.852
    
    return lat_deg, lon_deg, speed_kmh

while True:
    if gps.any():
        line = gps.readline()
        try:
            decoded = line.decode('ascii').strip()
            if decoded.startswith('$GPRMC'):
                result = parse_gprmc(decoded)
                if result:
                    lat, lon, speed = result
                    print(f"Pos: {lat:.5f}°N, {lon:.5f}°E | Speed: {speed:.1f} km/h")
        except:
            pass
    time.sleep(1)
