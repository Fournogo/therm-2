import paho.mqtt.client as mqtt
import json
import time
import logging
import importlib
import sys
import os
import threading
from typing import Dict, Any

class ComponentInspector:
    """Helper class to inspect component classes and discover decorated methods"""
    
    @staticmethod
    def add_component_path(path: str):
        """Add a path to sys.path for component imports"""
        if path not in sys.path:
            sys.path.insert(0, path)
    
    @staticmethod
    def discover_data_methods(component_type: str) -> list:
        """Discover all @command decorated methods in a component class with the data command tag and their respective status"""
        try:
            # Try to import the component module
            module = importlib.import_module(component_type)
            component_class = getattr(module, component_type)
            
            # Find all methods decorated with @command
            data_methods = []
            for method_name in dir(component_class):
                method = getattr(component_class, method_name)
                if callable(method) and getattr(method, '_is_data_command', False):
                    # Get the event name from the data command
                    event_names = getattr(method, '_events', None)
                    if event_names:
                        for event_name in event_names:
                            # Find the corresponding status method
                            status_method = None
                            for status_method_name in dir(component_class):
                                status_method_obj = getattr(component_class, status_method_name)
                                if (callable(status_method_obj) and 
                                    getattr(status_method_obj, '_is_mqtt_status', False)):
                                    # Check if this status method triggers on our event
                                    trigger_events = getattr(status_method_obj, '_trigger_events', [])
                                    if event_name in trigger_events:
                                        status_method = status_method_name
                                        break
                            
                            # Add the pairing to our results
                            data_methods.append({
                                'command_method_name': method_name,
                                'command_method': method,
                                'event': event_name,
                                'status_method_name': status_method,
                                'status_method': status_method_obj    # Will be None if not found
                            })
                    else:
                        # Data command without event - add without pairing
                        data_methods.append({
                                'command_method_name': method_name,
                                'command_method': method,
                                'event': None,
                                'status_method_name': None,
                                'status_method': None 
                        })
            
            return data_methods
            
        except ImportError as e:
            logging.warning(f"Could not import {component_type}: {e}")
            return []
        except AttributeError as e:
            logging.warning(f"Could not find class {component_type}: {e}")
            return []
        except Exception as e:
            logging.error(f"Error inspecting {component_type}: {e}")
            return []

    @staticmethod
    def discover_command_methods(component_type: str) -> list:
        """Discover all @command decorated methods in a component class"""
        try:
            # Try to import the component module
            module = importlib.import_module(component_type)
            component_class = getattr(module, component_type)
            
            # Find all methods decorated with @command
            command_methods = []
            for method_name in dir(component_class):
                method = getattr(component_class, method_name)
                if callable(method) and hasattr(method, '_is_mqtt_command'):
                    command_methods.append(method_name)
            
            return command_methods
            
        except ImportError as e:
            logging.warning(f"Could not import {component_type}: {e}")
            return []
        except AttributeError as e:
            logging.warning(f"Could not find class {component_type}: {e}")
            return []
        except Exception as e:
            logging.error(f"Error inspecting {component_type}: {e}")
            return []
    
    @staticmethod
    def discover_status_methods(component_type: str) -> list:
        """Discover all @status decorated methods in a component class"""
        try:
            module = importlib.import_module(component_type)
            component_class = getattr(module, component_type)
            
            status_methods = []
            for method_name in dir(component_class):
                method = getattr(component_class, method_name)
                if callable(method) and hasattr(method, '_is_mqtt_status'):
                    status_methods.append(method_name)
            
            return status_methods
            
        except Exception as e:
            logging.error(f"Error inspecting status methods for {component_type}: {e}")
            return []

class ComponentProxy:
    """Represents a component on the server side - creates methods that publish MQTT commands"""
    
    def __init__(self, device_name: str, component_name: str, component_config: dict, mqtt_client, device_prefix: str):
        self.device_name = device_name
        self.component_name = component_name
        self.component_config = component_config
        self.mqtt_client = mqtt_client
        self.device_prefix = device_prefix
        self.component_type = component_config.get('type')
        
        # Threading events for status methods
        self.status_events = {}
        self.latest_status_data = {}
        
        # Generate proxy methods based on component type
        self._create_proxy_methods()
        self._setup_status_subscriptions()
    
    def _create_proxy_methods(self):
        """Create proxy methods by inspecting the actual component class decorators"""
        # Discover command methods from the actual component class
        command_methods = ComponentInspector.discover_command_methods(self.component_type)
        
        if command_methods:
            print(f"Found @command methods in {self.component_type}: {command_methods}")
            
            # Create proxy methods for each command
            for method_name in command_methods:
                # Create a closure to capture the method name
                def make_method(method):
                    def proxy_method(**kwargs):
                        return self._publish_command(method, kwargs)
                    return proxy_method
                
                # Add the method to this instance
                setattr(self, method_name, make_method(method_name))
            
            print(f"Created {len(command_methods)} proxy methods for {self.component_type}")
        else:
            print(f"No @command methods found for {self.component_type} (or could not inspect class)")
    
    def _setup_status_subscriptions(self):
        """Setup MQTT subscriptions for status methods and create threading events"""
        # Discover status methods from the actual component class
        status_methods = ComponentInspector.discover_status_methods(self.component_type)
        
        if status_methods:
            print(f"Found @status methods in {self.component_type}: {status_methods}")
            
            for method_name in status_methods:
                # Create a threading event for this status method
                event = threading.Event()
                self.status_events[method_name] = event
                
                # Initialize latest status data
                self.latest_status_data[method_name] = None
                
                # Create status topic and subscribe
                status_topic = f"{self.device_prefix}/{self.device_name}/{self.component_name}/status/{method_name}"
                
                # Create callback for this specific status method
                def make_status_callback(status_method, status_event):
                    def status_callback(topic, payload):
                        print(f"Status update: {status_method} -> {payload}")
                        self.latest_status_data[status_method] = payload
                        status_event.set()  # Trigger the event
                    return status_callback
                
                callback = make_status_callback(method_name, event)
                self._subscribe_to_topic(status_topic, callback)
                
                print(f"Created event for status method: {method_name}")
    
    def _subscribe_to_topic(self, topic: str, callback):
        """Subscribe to a topic with callback (delegate to device manager)"""
        # We'll need to pass this up to the device manager
        if hasattr(self.mqtt_client, '_proxy_subscribe'):
            self.mqtt_client._proxy_subscribe(topic, callback)
    
    def execute_and_wait_for_status(self, command_method_name: str, status_method_name: str, timeout: float = 10, **kwargs):
        """Execute a command and wait for its corresponding status update
        
        Args:
            command_method_name: Name of the command method to call
            status_method_name: Name of the status method to wait for
            timeout: Maximum time to wait for status
            **kwargs: Arguments to pass to the command method
            
        Returns:
            Status data if received, None if timeout
        """
        if status_method_name not in self.status_events:
            raise ValueError(f"No status method '{status_method_name}' found")
        
        # Clear any previous event BEFORE executing command
        self.status_events[status_method_name].clear()
        
        # Execute the command
        command_method = getattr(self, command_method_name)
        command_result = command_method(**kwargs)
        
        # Now wait for the status
        if self.wait_for_status(status_method_name, timeout):
            return self.get_latest_status(status_method_name)
        else:
            return None
    
    def wait_for_status(self, status_method: str, timeout: float = None) -> bool:
        """Wait for a specific status event to occur
        
        Args:
            status_method: Name of the status method to wait for
            timeout: Maximum time to wait (None for indefinite)
            
        Returns:
            True if event occurred, False if timeout
        """
        if status_method not in self.status_events:
            raise ValueError(f"No status method '{status_method}' found for {self.component_type}")
        
        event = self.status_events[status_method]
        event.clear()  # Clear any previous event
        return event.wait(timeout)
    
    def get_latest_status(self, status_method: str):
        """Get the latest status data for a method"""
        return self.latest_status_data.get(status_method)
    
    def clear_status_event(self, status_method: str):
        """Manually clear a status event"""
        if status_method in self.status_events:
            self.status_events[status_method].clear()

    def wait_for(self, status_method: str, callback, timeout: float = None):
        """Wait for a status event and execute callback (single use, non-blocking)
        
        Args:
            status_method: Name of the status method to wait for (e.g., 'pressed_status')
            callback: Function to call when event occurs. Will receive (status_data) as argument
            timeout: Optional timeout in seconds. If exceeded, callback is called with None
            
        Returns:
            threading.Thread: The thread handling the wait (for reference)
        """
        if status_method not in self.status_events:
            raise ValueError(f"No status method '{status_method}' found for {self.component_type}")
        
        def wait_thread():
            try:
                # Clear any previous event
                self.status_events[status_method].clear()
                
                # Wait for the event
                if self.status_events[status_method].wait(timeout):
                    # Event occurred - get the data and call callback
                    status_data = self.get_latest_status(status_method)
                    callback(status_data)
                else:
                    # Timeout occurred
                    callback(None)
                    
            except Exception as e:
                print(f"Error in wait_for thread for {status_method}: {e}")
                callback(None)
        
        # Start the thread
        thread = threading.Thread(
            target=wait_thread,
            name=f"WaitFor-{self.component_name}-{status_method}",
            daemon=True
        )
        thread.start()
        
        print(f"Started wait_for thread for {self.component_name}.{status_method}")
        return thread

    def wait_for_continuous(self, status_method: str, callback, stop_condition=None):
        """Wait for a status event continuously and execute callback each time (non-blocking)
        
        Args:
            status_method: Name of the status method to wait for (e.g., 'pressed_status')
            callback: Function to call when event occurs. Will receive (status_data) as argument
            stop_condition: Optional function that returns True when waiting should stop.
                        If None, will run indefinitely until stop_continuous_wait() is called
            
        Returns:
            str: A unique ID for this continuous wait (use with stop_continuous_wait)
        """
        if status_method not in self.status_events:
            raise ValueError(f"No status method '{status_method}' found for {self.component_type}")
        
        # Create unique ID for this continuous wait
        import uuid
        wait_id = str(uuid.uuid4())
        
        # Initialize continuous waits dict if it doesn't exist
        if not hasattr(self, 'continuous_waits'):
            self.continuous_waits = {}
            self.continuous_wait_stop_flags = {}
        
        # Create stop flag for this wait
        self.continuous_wait_stop_flags[wait_id] = threading.Event()
        
        def continuous_wait_thread():
            try:
                while not self.continuous_wait_stop_flags[wait_id].is_set():
                    # Clear the event before waiting
                    self.status_events[status_method].clear()
                    
                    # Wait for the event (with short timeout to check stop condition)
                    if self.status_events[status_method].wait(timeout=1.0):
                        # Event occurred - get the data and call callback
                        status_data = self.get_latest_status(status_method)
                        
                        try:
                            callback(status_data)
                        except Exception as e:
                            print(f"Error in callback for {status_method}: {e}")
                    
                    # Check external stop condition if provided
                    if stop_condition and stop_condition():
                        break
                        
            except Exception as e:
                print(f"Error in continuous wait thread for {status_method}: {e}")
            finally:
                # Clean up
                if wait_id in self.continuous_waits:
                    del self.continuous_waits[wait_id]
                if wait_id in self.continuous_wait_stop_flags:
                    del self.continuous_wait_stop_flags[wait_id]
        
        # Start the thread
        thread = threading.Thread(
            target=continuous_wait_thread,
            name=f"ContinuousWait-{self.component_name}-{status_method}-{wait_id[:8]}",
            daemon=True
        )
        
        # Store thread reference
        self.continuous_waits[wait_id] = thread
        thread.start()
        
        print(f"Started continuous wait for {self.component_name}.{status_method} (ID: {wait_id[:8]})")
        return wait_id

    def stop_continuous_wait(self, wait_id: str):
        """Stop a specific continuous wait
        
        Args:
            wait_id: The ID returned by wait_for_continuous()
        """
        if not hasattr(self, 'continuous_wait_stop_flags') or wait_id not in self.continuous_wait_stop_flags:
            print(f"No continuous wait found with ID: {wait_id}")
            return
        
        # Signal the thread to stop
        self.continuous_wait_stop_flags[wait_id].set()
        
        # Wait for thread to finish
        if hasattr(self, 'continuous_waits') and wait_id in self.continuous_waits:
            thread = self.continuous_waits[wait_id]
            thread.join(timeout=2.0)
            if thread.is_alive():
                print(f"Warning: Continuous wait thread {wait_id} did not stop cleanly")
            else:
                print(f"Stopped continuous wait {wait_id[:8]}")

    def stop_all_continuous_waits(self):
        """Stop all continuous waits for this component"""
        if not hasattr(self, 'continuous_waits'):
            return
        
        wait_ids = list(self.continuous_waits.keys())
        for wait_id in wait_ids:
            self.stop_continuous_wait(wait_id)
        
        print(f"Stopped all continuous waits for {self.component_name}")

    def list_active_waits(self):
        """List all active continuous waits for this component"""
        if not hasattr(self, 'continuous_waits'):
            print(f"No active waits for {self.component_name}")
            return []
        
        active_waits = []
        for wait_id, thread in self.continuous_waits.items():
            if thread.is_alive():
                active_waits.append({
                    'id': wait_id,
                    'thread_name': thread.name,
                    'is_alive': thread.is_alive()
                })
        
        if active_waits:
            print(f"Active waits for {self.component_name}:")
            for wait in active_waits:
                print(f"  - {wait['id'][:8]}: {wait['thread_name']}")
        else:
            print(f"No active waits for {self.component_name}")
        
        return active_waits
    
    def _publish_command(self, command: str, params: dict = None):
        """Publish a command to the MQTT topic"""
        topic = f"{self.device_prefix}/{self.device_name}/{self.component_name}/{command}"
        
        payload = {}
        if params:
            payload['params'] = params
        
        try:
            if payload:
                message = json.dumps(payload)
            else:
                message = ""
            
            result = self.mqtt_client.publish(topic, message)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"Published command: {topic} -> {message}")
                return True
            else:
                print(f"Failed to publish command: {topic}")
                return False
                
        except Exception as e:
            logging.error(f"Error publishing command {command} to {topic}: {e}")
            return False

class DeviceProxy:
    """Represents a device on the server side - contains component proxies"""
    
    def __init__(self, device_name: str, device_config: dict, mqtt_client, device_prefix: str):
        self.device_name = device_name
        self.device_config = device_config
        self.mqtt_client = mqtt_client
        self.device_prefix = device_prefix
        
        # Create component proxies
        self._create_components()
    
    def _create_components(self):
        """Create proxy objects for each component"""
        components_config = self.device_config.get('components', {})
        
        for component_name, component_config in components_config.items():
            component_proxy = ComponentProxy(
                self.device_name,
                component_name, 
                component_config,
                self.mqtt_client,
                self.device_prefix
            )
            
            # Add component as attribute to this device
            setattr(self, component_name, component_proxy)
            print(f"Created component proxy: {self.device_name}.{component_name} ({component_config['type']})")
    
    def wait_for_any_status(self, timeout: float = None) -> tuple:
        """Wait for any status event from any component
        
        Returns:
            (component_name, status_method, status_data) if event occurs, None if timeout
        """
        # Collect all events from all components
        all_events = {}
        for comp_name in dir(self):
            comp = getattr(self, comp_name)
            if hasattr(comp, 'status_events'):
                for status_method, event in comp.status_events.items():
                    all_events[f"{comp_name}.{status_method}"] = (comp_name, status_method, event, comp)
        
        if not all_events:
            return None
        
        # Wait for any event to be set
        start_time = time.time()
        while True:
            for event_key, (comp_name, status_method, event, comp) in all_events.items():
                if event.is_set():
                    status_data = comp.get_latest_status(status_method)
                    return (comp_name, status_method, status_data)
            
            if timeout and (time.time() - start_time) > timeout:
                return None
            
            time.sleep(0.01)  # Small sleep to prevent busy waiting

class ServerDeviceManager:
    """Manages device proxies on the server side"""
    
    def __init__(self, mqtt_config: dict = None):
        self.devices = {}
        self.mqtt_client = None
        self.mqtt_config = mqtt_config or {}
        self.device_prefix = self.mqtt_config.get('device_prefix', 'devices')
        self.topic_callbacks = {}  # Store topic callbacks for status subscriptions
        
        self._setup_mqtt()
    
    def _setup_mqtt(self):
        """Setup MQTT client connection"""
        try:
            self.mqtt_client = mqtt.Client()
            
            # Add proxy subscribe method
            self.mqtt_client._proxy_subscribe = self._proxy_subscribe
            
            # Set authentication if provided
            username = self.mqtt_config.get('username')
            password = self.mqtt_config.get('password')
            if username and password:
                self.mqtt_client.username_pw_set(username, password)
            
            # Set callbacks
            self.mqtt_client.on_connect = self._on_connect
            self.mqtt_client.on_disconnect = self._on_disconnect
            self.mqtt_client.on_message = self._on_message
            
            # Connect to broker
            broker_host = self.mqtt_config.get('broker_host', 'localhost')
            broker_port = self.mqtt_config.get('broker_port', 1883)
            
            print(f"Connecting to MQTT broker: {broker_host}:{broker_port}")
            self.mqtt_client.connect(broker_host, broker_port, 60)
            
            # Start the network loop
            self.mqtt_client.loop_start()
            
        except Exception as e:
            print(f"Failed to setup MQTT: {e}")
            raise
    
    def _proxy_subscribe(self, topic: str, callback):
        """Subscribe to a topic with callback for component proxies"""
        if topic not in self.topic_callbacks:
            self.topic_callbacks[topic] = []
        
        self.topic_callbacks[topic].append(callback)
        
        if hasattr(self.mqtt_client, 'is_connected') and self.mqtt_client.is_connected():
            self.mqtt_client.subscribe(topic)
            print(f"Subscribed to status topic: {topic}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when MQTT client connects"""
        if rc == 0:
            print("Server MQTT connected successfully")
            
            # Subscribe to all pending topics
            for topic in self.topic_callbacks.keys():
                client.subscribe(topic)
                print(f"Subscribed to topic: {topic}")
        else:
            print(f"Server MQTT connection failed with code: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when MQTT client disconnects"""
        print("Server MQTT disconnected")
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages for status updates"""
        topic = msg.topic
        try:
            # Try to decode as JSON, fall back to string
            try:
                payload = json.loads(msg.payload.decode())
            except json.JSONDecodeError:
                payload = msg.payload.decode()
            
            print(f"Server MQTT received: {topic} -> {payload}")
            
            # Call all callbacks for this topic
            if topic in self.topic_callbacks:
                for callback in self.topic_callbacks[topic]:
                    try:
                        callback(topic, payload)
                    except Exception as e:
                        logging.error(f"Error in status callback for {topic}: {e}")
                        
        except Exception as e:
            logging.error(f"Error processing MQTT message: {e}")
    
    def load_device_config(self, config: dict):
        """Load devices from a single config dictionary"""
        device_prefix = config.get('mqtt', {}).get('device_prefix', self.device_prefix)
        devices_config = config.get('devices', {})
        
        for device_name, device_config in devices_config.items():
            try:
                device_proxy = DeviceProxy(
                    device_name,
                    device_config,
                    self.mqtt_client,
                    device_prefix
                )
                
                self.devices[device_name] = device_proxy
                
                # Also add as attribute to this manager for easy access
                setattr(self, device_name, device_proxy)
                
                print(f"Created device proxy: {device_name}")
                
            except Exception as e:
                logging.error(f"Failed to create device proxy '{device_name}': {e}")
    
    def get_device(self, name: str):
        """Get device proxy by name"""
        return self.devices.get(name)
    
    def list_devices(self):
        """List all available devices and their components"""
        print("\n=== Available Devices ===")
        for device_name, device in self.devices.items():
            print(f"Device: {device_name}")
            for attr_name in dir(device):
                if not attr_name.startswith('_') and hasattr(getattr(device, attr_name), 'component_type'):
                    component = getattr(device, attr_name)
                    methods = [method for method in dir(component) if not method.startswith('_') and callable(getattr(component, method)) and method not in ['component_name', 'device_name', 'component_config', 'mqtt_client', 'device_prefix', 'component_type']]
                    print(f"  - {attr_name} ({component.component_type}): {', '.join(methods)}")
    
    def disconnect(self):
        """Disconnect from MQTT"""
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()