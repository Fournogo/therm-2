from zeroconf import ServiceBrowser, Zeroconf
import paho.mqtt.client as mqtt
import socket
import time
import json
import logging
from typing import Dict, Callable, Any

class MQTTManager:
    _instance = None
    
    def __new__(cls, mqtt_config=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            
            # Use config or defaults
            if mqtt_config:
            # Check if broker_host is explicitly provided
                if 'broker_host' in mqtt_config:
                    cls._instance.broker_host = mqtt_config['broker_host']
                    print(f"Using explicit broker host: {cls._instance.broker_host}")
                else:
                    # Use zeroconf discovery
                    cls._instance.broker_host = cls._instance._get_ip()
                    if cls._instance.broker_host == None:
                        raise AttributeError('MQTT Broker IP Address not found. Check avahi mDns service status. (Service is called mosquitto.service on the broker)')
                
                cls._instance.broker_port = mqtt_config.get('broker_port', 1883)
                cls._instance.username = mqtt_config.get('username')
                cls._instance.password = mqtt_config.get('password')
                cls._instance.device_prefix = mqtt_config.get('device_prefix', 'devices')
            else:
                cls._instance.broker_host = 'localhost'
                cls._instance.broker_port = 1883
                cls._instance.username = None
                cls._instance.password = None
                cls._instance.device_prefix = 'devices'
        
        # Heartbeat topics using device name
            cls._instance.heartbeat_request_topic = f"{cls._instance.device_prefix}/heartbeat/request"
            cls._instance.heartbeat_response_topic = f"{cls._instance.device_prefix}/heartbeat/response"

            cls._instance.client = None
            cls._instance.is_connected = False
            cls._instance.topic_callbacks = {}
            cls._instance.component_topics = {}
            cls._instance._initialized = False
            
            # Connect to MQTT broker
            cls._instance._connect_mqtt()
        
        return cls._instance
    
    def _handle_heartbeat_request(self, payload):
        """Respond to heartbeat ping from broker"""
        try:
            response_data = {
                "status": "alive",
                "timestamp": time.time(),
                "request_id": payload.get("request_id", "unknown") if isinstance(payload, dict) else "unknown"
            }
            
            self.publish(self.heartbeat_response_topic, response_data)
            print(f"Heartbeat response sent")
            
        except Exception as e:
            logging.error(f"Error handling heartbeat request: {e}")

    def _connect_mqtt(self):
        """Internal method to establish MQTT connection"""
        if self._initialized:
            return
        
        try:
            print(f"Connecting to MQTT broker: {self.broker_host}:{self.broker_port}")
            if self.username:
                print(f"Using authentication for user: {self.username}")
            
            # Create MQTT client
            self.client = mqtt.Client()
            
            # Set authentication if provided
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            # Set up callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            # Connect to broker
            self.client.connect(self.broker_host, self.broker_port, 60)
            
            # Start the network loop in background
            self.client.loop_start()
            
            self._initialized = True
            print("MQTT connection initiated")
            
        except Exception as e:
            print(f"MQTT connection failed: {e}")
            raise

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when MQTT client connects"""
        if rc == 0:
            self.is_connected = True
            print("MQTT connected successfully")
            
            # Subscribe to heartbeat request topic
            client.subscribe(self.heartbeat_request_topic)
            print(f"Subscribed to heartbeat: {self.heartbeat_request_topic}")

            # Resubscribe to all topics
            for topic in self.topic_callbacks.keys():
                if topic != self.heartbeat_request_topic:
                    client.subscribe(topic)
                    print(f"Subscribed to: {topic}")
        else:
            print(f"MQTT connection failed with code: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when MQTT client disconnects"""
        self.is_connected = False
        print("MQTT disconnected")
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        topic = msg.topic
        try:
            # Try to decode as JSON, fall back to string
            try:
                payload = json.loads(msg.payload.decode())
            except json.JSONDecodeError:
                payload = msg.payload.decode()
            
            print(f"MQTT received: {topic} -> {payload}")
            
            if topic == self.heartbeat_request_topic:
                self._handle_heartbeat_request(payload)
                return

            # Call all callbacks for this topic
            if topic in self.topic_callbacks:
                for callback in self.topic_callbacks[topic]:
                    try:
                        callback(topic, payload)
                    except Exception as e:
                        logging.error(f"Error in MQTT callback for {topic}: {e}")
                        
        except Exception as e:
            logging.error(f"Error processing MQTT message: {e}")

    def register_command(self, device_name: str, component_name: str, function_name: str, method):
        """Register a single command method"""
        # Create topic: {device_prefix}/{device_name}/{component_name}/{function_name}
        command_topic = f"{self.device_prefix}/{device_name}/{component_name}/{function_name}"
        
        # Create a callback that executes the method
        def command_callback(topic, payload):
            try:
                # Handle parameters if provided
                if isinstance(payload, dict) and 'params' in payload:
                    method(**payload['params'])
                else:
                    method()
                print(f"Executed command: {function_name} on {device_name}.{component_name}")
            except Exception as e:
                logging.error(f"Error executing command {function_name}: {e}")
        
        # Subscribe to the command topic
        self.subscribe(command_topic, command_callback)
        
        return command_topic

    def _handle_component_command(self, component_id: str, payload):
        """Handle commands sent to components via MQTT"""
        if component_id not in self.component_topics:
            return
        
        component = self.component_topics[component_id]['component']
        
        try:
            # Handle different command formats
            if isinstance(payload, dict):
                command = payload.get('command')
                params = payload.get('params', {})
            else:
                command = str(payload)
                params = {}
            
            print(f"Executing command '{command}' on {component_id}")
            
            # Execute the command on the component
            if hasattr(component, command):
                method = getattr(component, command)
                if callable(method):
                    if params:
                        method(**params)
                    else:
                        method()
                    
                    # Publish status update
                    self._publish_component_status(component_id, f"{command}_executed")
                else:
                    print(f"'{command}' is not a callable method on {component_id}")
            else:
                print(f"Component {component_id} doesn't have method '{command}'")
                
        except Exception as e:
            logging.error(f"Error executing command on {component_id}: {e}")
    
    def _publish_component_status(self, component_id: str, status):
        """Publish component status"""
        if component_id in self.component_topics:
            status_topic = self.component_topics[component_id]['status']
            self.publish(status_topic, {"status": status, "timestamp": time.time()})
    
    def subscribe(self, topic: str, callback: Callable):
        """Subscribe to a topic with callback"""
        if topic not in self.topic_callbacks:
            self.topic_callbacks[topic] = []
        
        self.topic_callbacks[topic].append(callback)
        
        if self.is_connected:
            self.client.subscribe(topic)
            print(f"Subscribed to: {topic}")
    
    def publish(self, topic: str, payload: Any, retain: bool = False):
        """Publish a message to a topic"""
        if not self.is_connected:
            print("MQTT not connected, cannot publish")
            return False
        
        try:
            # Convert payload to JSON if it's a dict/list
            if isinstance(payload, (dict, list)):
                payload = json.dumps(payload)
            
            result = self.client.publish(topic, payload, retain=retain)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"MQTT published: {topic} -> {payload}")
                return True
            else:
                print(f"MQTT publish failed: {result.rc}")
                return False
                
        except Exception as e:
            logging.error(f"Error publishing to MQTT: {e}")
            return False
    
    def get_component_topics(self, device_name: str, component_name: str):
        """Get the MQTT topics for a specific component"""
        component_id = f"{device_name}_{component_name}"
        return self.component_topics.get(component_id, {})
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        self.is_connected = False

    def _get_ip(self):
        zeroconf = Zeroconf()
        listener = DNSListener()
        browser = ServiceBrowser(zeroconf, "_mqtt._tcp.local.", listener)

        # Wait for the broker to be discovered with a timeout
        timeout = 5  # seconds
        start_time = time.time()

        while listener.broker_ip is None and time.time() - start_time < timeout:
            time.sleep(0.1)  # Check more frequently

        if listener.broker_ip is not None:
            print("Discovered broker IP:", listener.broker_ip)
            zeroconf.close()
            return listener.broker_ip
        else:
            print("Broker discovery timed out after 5 seconds")
            zeroconf.close()
            return None

class DNSListener:
    def __init__(self):
        self.broker_ip = None

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        print(f"Service {name} added, service info: {info}")
        if info:
            self.broker_ip = socket.inet_ntoa(info.addresses[0])
            print(f"Service {name} added, IP address: {self.broker_ip}")

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"Service {name} updated")

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"Service {name} removed")