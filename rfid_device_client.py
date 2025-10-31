import paho.mqtt.client as mqtt
import ssl
import time
import json
import random
import csv
import os
import warnings
from datetime import datetime
import logging

# ---------- CONFIGURATION ----------
warnings.filterwarnings("ignore", category=DeprecationWarning)

# AWS IoT Core Configuration
ENDPOINT = "a3s8ak1t33mfjz-ats.iot.ap-south-1.amazonaws.com"
CLIENT_ID = "RFID-Device-01"
TOPIC = f"smaket/iot/data/{CLIENT_ID}"

# ✅ Corrected paths
CA_PATH = r"D:\IOTCoreCert\AmazonRootCA1.pem"
CERT_PATH = r"D:\IOTCoreCert\069ea350def9675c00a739d5432d7a37b56cfcd5d8a72781156458a30028e8d7-certificate.pem.crt"
KEY_PATH = r"D:\IOTCoreCert\069ea350def9675c00a739d5432d7a37b56cfcd5d8a72781156458a30028e8d7-private.pem.key"



# Data files
CSV_FILE = r"D:\IOTCoreCert\temperature_log.csv"
LOG_FILE = r"D:\IOTCoreCert\iot_publisher.log"

# Sensor data ranges
TEMP_RANGE = (22.0, 30.0)
HUMIDITY_RANGE = (35.0, 65.0)
PUBLISH_INTERVAL = 5  # seconds

# ---------- LOGGING SETUP ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------- VALIDATION ----------
def validate_files():
    """Validate that all required files exist"""
    missing_files = []
    file_checks = [
        (CA_PATH, "Root CA certificate"),
        (CERT_PATH, "Device certificate"), 
        (KEY_PATH, "Private key")
    ]
    
    for path, desc in file_checks:
        if not os.path.exists(path):
            missing_files.append(f"{desc}: {path}")
        else:
            logger.info("Found: %s", path)
    
    if missing_files:
        error_msg = "MISSING FILES:\n" + "\n".join(missing_files)
        logger.error(error_msg)
        
        # List what files actually exist
        logger.info("Files in directory:")
        for file in os.listdir(r"D:\IOTCoreCert"):
            if file.endswith(('.pem', '.crt', '.key')):
                logger.info("  - %s", file)
                
        raise FileNotFoundError(error_msg)
    
    logger.info("All certificate files verified")

def setup_csv():
    """Initialize CSV file with headers if it doesn't exist"""
    if not os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, "w", newline="", encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "device_id", "temperature", "humidity"])
            logger.info("Created new CSV file: %s", CSV_FILE)
        except Exception as e:
            logger.error("Failed to create CSV file: %s", e)
            raise
    else:
        logger.info("CSV file already exists: %s", CSV_FILE)

# ---------- MQTT CLIENT ----------
class IoTClient:
    def __init__(self):
        self.client = None
        self.is_connected = False
        
    def on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback for when the client receives a CONNACK response from the server"""
        if rc == 0:
            self.is_connected = True
            logger.info("Connected to AWS IoT Core")
            logger.info("Publishing to topic: %s", TOPIC)
        else:
            self.is_connected = False
            error_codes = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier", 
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorised"
            }
            error_msg = error_codes.get(rc, f"Unknown error code: {rc}")
            logger.error("Connection failed: %s", error_msg)
    
    def on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker"""
        self.is_connected = False
        if rc != 0:
            logger.warning("Unexpected disconnection from AWS IoT Core")
        else:
            logger.info("Disconnected from AWS IoT Core")
    
    def on_publish(self, client, userdata, mid):
        """Callback when a message is published"""
        logger.debug("Message %s published successfully", mid)
    
    def on_message(self, client, userdata, msg):
        """Callback when a message is received"""
        logger.info("Received message from %s: %s", msg.topic, msg.payload.decode())
    
    def connect(self):
        """Connect to AWS IoT Core"""
        try:
            self.client = mqtt.Client(client_id=CLIENT_ID, protocol=mqtt.MQTTv5)
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_publish = self.on_publish
            self.client.on_message = self.on_message
            
            # Configure TLS/SSL
            logger.info("Configuring TLS with:")
            logger.info("  CA: %s", CA_PATH)
            logger.info("  Cert: %s", CERT_PATH)
            logger.info("  Key: %s", KEY_PATH)
            
            self.client.tls_set(
                ca_certs=CA_PATH,
                certfile=CERT_PATH,
                keyfile=KEY_PATH,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
                cert_reqs=ssl.CERT_REQUIRED
            )
            
            logger.info("Connecting to %s...", ENDPOINT)
            self.client.connect(ENDPOINT, port=8883, keepalive=60)
            self.client.loop_start()
            
            # Wait for connection
            timeout = 10
            start_time = time.time()
            while not self.is_connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if not self.is_connected:
                raise Exception("Connection timeout")
                
            return True
            
        except Exception as e:
            logger.error("Connection error: %s", e)
            return False
    
    def publish_message(self, topic, message):
        """Publish a message to the specified topic"""
        if not self.is_connected:
            logger.error("Not connected to AWS IoT Core")
            return False
        
        try:
            result = self.client.publish(topic, message, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                return True
            else:
                logger.error("Failed to publish message: MQTT error %s", result.rc)
                return False
        except Exception as e:
            logger.error("Publish error: %s", e)
            return False
    
    def disconnect(self):
        """Disconnect from AWS IoT Core"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT client disconnected")

# ---------- DATA MANAGEMENT ----------
def generate_sensor_data():
    """Generate simulated sensor data"""
    temperature = round(random.uniform(*TEMP_RANGE), 2)
    humidity = round(random.uniform(*HUMIDITY_RANGE), 1)
    
    return {
        "temperature": temperature,
        "humidity": humidity
    }

def save_to_csv(data):
    """Save data to CSV file"""
    try:
        with open(CSV_FILE, "a", newline="", encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                data["timestamp"],
                data["device_id"],
                data["temperature"],
                data["humidity"]
            ])
    except Exception as e:
        logger.error("Failed to write to CSV: %s", e)

def create_payload(device_id, sensor_data):
    """Create JSON payload for MQTT message"""
    return {
        "device_id": device_id,
        "temperature": sensor_data["temperature"],
        "humidity": sensor_data["humidity"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "message_id": f"msg_{int(time.time())}_{random.randint(1000, 9999)}"
    }

# ---------- MAIN EXECUTION ----------
def main():
    """Main function to run the IoT publisher"""
    logger.info("Starting AWS IoT Core Publisher")
    
    try:
        # Validate configuration
        validate_files()
        setup_csv()
        
        # Initialize and connect MQTT client
        iot_client = IoTClient()
        if not iot_client.connect():
            logger.error("Failed to connect to AWS IoT Core")
            return
        
        # Main publishing loop
        message_count = 0
        logger.info("Starting data publishing (interval: %ss)", PUBLISH_INTERVAL)
        
        while True:
            try:
                # Generate and prepare data
                sensor_data = generate_sensor_data()
                payload = create_payload(CLIENT_ID, sensor_data)
                message = json.dumps(payload)
                
                # Publish to AWS IoT Core
                if iot_client.publish_message(TOPIC, message):
                    message_count += 1
                    logger.info("[%s] Sent: %s", message_count, message)
                    
                    # Save to local CSV
                    save_to_csv(payload)
                else:
                    logger.warning("Failed to publish message")
                
                # Wait for next interval
                time.sleep(PUBLISH_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("Stopping publisher...")
                break
            except Exception as e:
                logger.error("Error in main loop: %s", e)
                time.sleep(PUBLISH_INTERVAL)
    
    except Exception as e:
        logger.error("Fatal error: %s", e)
    
    finally:
        # Cleanup
        if 'iot_client' in locals():
            iot_client.disconnect()
        logger.info("Publisher stopped")

if __name__ == "__main__":
    main()