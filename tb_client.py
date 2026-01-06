
from uthingsboard.client import TBDeviceMqttClient
import time

class ThingsBoardClient:
    def __init__(self, server, token, rpc_handler=None):
        self.server = server
        self.token = token
        self.client = None
        self.connected = False
        
        try:
            print("   Creating TB client...")
            self.client = TBDeviceMqttClient(server, access_token=token)
            
            print("   Connecting to ThingsBoard...")
            self.client.connect()
            
            if rpc_handler:
                self.client.set_server_side_rpc_request_handler(rpc_handler)
            
            self.connected = True
            print("   ✓ ThingsBoard connected")
            
        except Exception as e:
            print(f"   ✗ TB connection failed: {e}")
            self.connected = False
    
    def send_telemetry(self, data):
        """Send telemetry data"""
        if not self.connected or self.client is None:
            return False
        
        try:
            self.client.send_telemetry(data)
            return True
        except Exception as e:
            print(f"⚠️ Telemetry send failed: {e}")
            return False
    
    def check_messages(self):
        """Check for incoming RPC commands"""
        if not self.connected or self.client is None:
            return
        
        try:
            self.client.check_msg()
        except:
            pass
    
    def reconnect(self):
        """Attempt to reconnect"""
        if self.client:
            try:
                self.client.disconnect()
            except:
                pass
        
        time.sleep(2)
        
        try:
            self.client = TBDeviceMqttClient(self.server, access_token=self.token)
            self.client.connect()
            self.connected = True
            return True
        except:
            self.connected = False
            return False