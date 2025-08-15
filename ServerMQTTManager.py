# ServerMQTTManager.py
import asyncio
import aiomqtt
import json
import logging
import time
from typing import Dict, Any, Callable, Optional
import uuid

class ServerMQTTManager:
    """
    Server-side MQTT manager that connects to broker and manages subscriptions
    for all remote devices. This is NOT the device-side MQTTManager.
    """
    
    def __init__(self, mqtt_config: Dict[str, Any]):
        self.broker_host = mqtt_config.get('broker_host', 'localhost')
        self.broker_port = mqtt_config.get('broker_port', 1883)
        self.username = mqtt_config.get('username')
        self.password = mqtt_config.get('password')
        self.device_prefix = mqtt_config.get('device_prefix', 'devices')
        
        # Topic subscriptions
        self.topic_callbacks = {}
        self.status_callbacks = {}
        
        # Connection state
        self.is_connected = False
        self.client = None
        self._mqtt_task = None
        
        # Heartbeat management
        self.heartbeat_request_topic = f"{self.device_prefix}/heartbeat/request"
        self.heartbeat_response_topic = f"{self.device_prefix}/heartbeat/response"
        self.heartbeat_callbacks = []
        
        logging.info(f"ServerMQTTManager created for prefix '{self.device_prefix}'")
    
    async def connect(self):
        """Connect to MQTT broker"""
        try:
            client_args = {
                'hostname': self.broker_host,
                'port': self.broker_port,
            }
            
            if self.username and self.password:
                client_args['username'] = self.username
                client_args['password'] = self.password
            
            self.client = aiomqtt.Client(**client_args)
            
            # Start connection and message handling
            self._mqtt_task = asyncio.create_task(self._mqtt_loop())
            
            # Wait for connection
            await asyncio.sleep(0.5)
            
            if self.is_connected:
                logging.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}")
                return True
            else:
                logging.error("Failed to connect to MQTT broker")
                return False
                
        except Exception as e:
            logging.error(f"Error connecting to MQTT: {e}")
            return False
    
    async def _mqtt_loop(self):
        """Main MQTT message handling loop"""
        try:
            async with self.client as client:
                self.is_connected = True
                
                # Subscribe to heartbeat responses
                await client.subscribe(self.heartbeat_response_topic)
                logging.info(f"Subscribed to heartbeat: {self.heartbeat_response_topic}")
                
                # Subscribe to all registered topics
                for topic in self.topic_callbacks.keys():
                    await client.subscribe(topic)
                    logging.info(f"Subscribed to: {topic}")
                
                # Process messages
                async for message in client.messages:
                    await self._handle_message(message)
                    
        except Exception as e:
            logging.error(f"MQTT loop error: {e}")
        finally:
            self.is_connected = False
    
    async def _handle_message(self, message):
        """Handle incoming MQTT messages"""
        topic = str(message.topic)
        
        try:
            # Decode payload
            try:
                payload = json.loads(message.payload.decode())
            except json.JSONDecodeError:
                payload = message.payload.decode()
            
            logging.debug(f"MQTT received: {topic} -> {payload}")
            
            # Handle heartbeat responses
            if topic == self.heartbeat_response_topic:
                for callback in self.heartbeat_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(payload)
                        else:
                            callback(payload)
                    except Exception as e:
                        logging.error(f"Error in heartbeat callback: {e}")
                return
            
            # Handle status updates
            if '/status/' in topic:
                # Extract component info from topic
                # Format: device_prefix/device_name/component_name/status/method_name
                parts = topic.split('/')
                if len(parts) >= 5:
                    status_key = f"{parts[1]}.{parts[2]}.{parts[4]}"  # device.component.status_method
                    
                    if status_key in self.status_callbacks:
                        for callback in self.status_callbacks[status_key]:
                            try:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(payload)
                                else:
                                    callback(payload)
                            except Exception as e:
                                logging.error(f"Error in status callback for {status_key}: {e}")
            
            # Handle general topic callbacks
            if topic in self.topic_callbacks:
                for callback in self.topic_callbacks[topic]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(topic, payload)
                        else:
                            callback(topic, payload)
                    except Exception as e:
                        logging.error(f"Error in topic callback: {e}")
                        
        except Exception as e:
            logging.error(f"Error handling MQTT message: {e}")
    
    async def publish_command(self, device_name: str, component_name: str, method_name: str, params: Dict[str, Any] = None):
        """
        Publish a command to a device component.
        Topic format: device_prefix/device_name/component_name/method_name
        """
        topic = f"{self.device_prefix}/{device_name}/{component_name}/{method_name}"
        
        payload = {}
        if params:
            payload['params'] = params
        
        return await self.publish(topic, payload)
    
    async def publish(self, topic: str, payload: Any):
        """Publish a message to a topic"""
        if not self.is_connected or not self.client:
            logging.error("MQTT not connected")
            return False
        
        try:
            if isinstance(payload, (dict, list)):
                message = json.dumps(payload)
            else:
                message = str(payload)
            
            await self.client.publish(topic, message)
            logging.debug(f"Published to {topic}: {message}")
            return True
            
        except Exception as e:
            logging.error(f"Error publishing to {topic}: {e}")
            return False
    
    def subscribe_to_status(self, device_name: str, component_name: str, status_method: str, callback: Callable):
        """
        Subscribe to status updates from a specific component.
        Topic format: device_prefix/device_name/component_name/status/status_method
        """
        topic = f"{self.device_prefix}/{device_name}/{component_name}/status/{status_method}"
        status_key = f"{device_name}.{component_name}.{status_method}"
        
        # Add to status callbacks
        if status_key not in self.status_callbacks:
            self.status_callbacks[status_key] = []
        self.status_callbacks[status_key].append(callback)
        
        # Subscribe to topic if not already subscribed
        if topic not in self.topic_callbacks:
            self.topic_callbacks[topic] = []
            
            # Subscribe if connected
            if self.is_connected:
                asyncio.create_task(self._subscribe_single_topic(topic))
        
        logging.info(f"Registered status callback for {status_key}")
    
    async def _subscribe_single_topic(self, topic: str):
        """Subscribe to a single topic"""
        try:
            if self.client:
                await self.client.subscribe(topic)
                logging.info(f"Subscribed to: {topic}")
        except Exception as e:
            logging.error(f"Error subscribing to {topic}: {e}")
    
    async def send_heartbeat(self):
        """Send heartbeat request to all devices"""
        payload = {
            "request_id": str(uuid.uuid4()),
            "timestamp": time.time()
        }
        return await self.publish(self.heartbeat_request_topic, payload)
    
    def add_heartbeat_callback(self, callback: Callable):
        """Add a callback for heartbeat responses"""
        self.heartbeat_callbacks.append(callback)
    
    def remove_heartbeat_callback(self, callback: Callable):
        """Remove a heartbeat callback"""
        if callback in self.heartbeat_callbacks:
            self.heartbeat_callbacks.remove(callback)
    
    async def disconnect(self):
        """Disconnect from MQTT broker"""
        self.is_connected = False
        
        if self._mqtt_task and not self._mqtt_task.done():
            self._mqtt_task.cancel()
            try:
                await self._mqtt_task
            except asyncio.CancelledError:
                pass
        
        logging.info(f"Disconnected from MQTT (prefix: {self.device_prefix})")