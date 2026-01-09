from uthingsboard.client import TBDeviceMqttClient
import time

class ThingsBoardClient:
    def __init__(self, server, token, rpc_handler=None):
        self.server = server
        self.token = token
        self.rpc_handler = rpc_handler
        self.client = None
        self.connected = False
        self.last_connect_attempt = 0
        self.reconnect_delay = 5000  # 5 sek mellem forsøg
    
    def connect(self):
        """Forbind til ThingsBoard med error handling"""
        try:
            print("Connecting TB...")
            self.client = TBDeviceMqttClient(self.server, access_token=self.token)
            self.client.connect()
            
            if self.rpc_handler:
                self.client.set_server_side_rpc_request_handler(self.rpc_handler)
            
            self.connected = True
            print("✓ TB Connected")
            return True
        except Exception as e:
            print(f"TB connect failed: {e}")
            self.connected = False
            self.client = None
            return False
    
    def send_telemetry(self, data):
        """Send telemetry med auto-reconnect"""
        if not self.connected:
            now = time.ticks_ms()
            if time.ticks_diff(now, self.last_connect_attempt) > self.reconnect_delay:
                print("Attempting TB reconnect...")
                self.connect()
                self.last_connect_attempt = now
            return False
        
        try:
            self.client.send_telemetry(data)
            return True
        except Exception as e:
            print(f"Telemetry failed: {e}")
            self.connected = False
            return False
    
    def check_messages(self):
        """Check RPC commands med error handling"""
        if self.connected and self.client:
            try:
                self.client.check_msg()
            except Exception as e:
                print(f"RPC check failed: {e}")
                self.connected = False