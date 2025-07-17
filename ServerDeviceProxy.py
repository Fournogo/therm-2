import asyncio
import aiomqtt
import json
import time
import logging
import importlib
import sys
import os
from typing import Dict, Any, Optional, Callable, Tuple
import uuid

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

class AsyncComponentProxy:
    """Async version of ComponentProxy - represents a component on the server side"""
    
    def __init__(self, device_name: str, component_name: str, component_config: dict, mqtt_manager, device_prefix: str):
        self.device_name = device_name
        self.component_name = component_name
        self.component_config = component_config
        self.mqtt_manager = mqtt_manager
        self.device_prefix = device_prefix
        self.component_type = component_config.get('type')
        
        # Async events for status methods
        self.status_events: Dict[str, asyncio.Event] = {}
        self.latest_status_data: Dict[str, Any] = {}
        self.status_queues: Dict[str, asyncio.Queue] = {}
        
        # Continuous wait management
        self.continuous_waits: Dict[str, asyncio.Task] = {}
        self.continuous_wait_stop_flags: Dict[str, asyncio.Event] = {}
        
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
                    async def proxy_method(**kwargs):
                        return await self._publish_command(method, kwargs)
                    return proxy_method
                
                # Add the method to this instance
                setattr(self, method_name, make_method(method_name))
            
            print(f"Created {len(command_methods)} proxy methods for {self.component_type}")
        else:
            print(f"No @command methods found for {self.component_type} (or could not inspect class)")
    
    def _setup_status_subscriptions(self):
        """Setup MQTT subscriptions for status methods and create async events"""
        # Discover status methods from the actual component class
        status_methods = ComponentInspector.discover_status_methods(self.component_type)
        
        if status_methods:
            print(f"Found @status methods in {self.component_type}: {status_methods}")
            
            for method_name in status_methods:
                # Create async event and queue for this status method
                event = asyncio.Event()
                queue = asyncio.Queue()
                self.status_events[method_name] = event
                self.status_queues[method_name] = queue
                
                # Initialize latest status data
                self.latest_status_data[method_name] = None
                
                # Create status topic and subscribe
                status_topic = f"{self.device_prefix}/{self.device_name}/{self.component_name}/status/{method_name}"
                
                # Create callback for this specific status method
                def make_status_callback(status_method, status_event, status_queue):
                    async def status_callback(topic, payload):
                        print(f"Status update: {status_method} -> {payload}")
                        self.latest_status_data[status_method] = payload
                        
                        # Put in queue for continuous listeners
                        try:
                            status_queue.put_nowait(payload)
                        except asyncio.QueueFull:
                            # Remove oldest item and add new one
                            try:
                                status_queue.get_nowait()
                                status_queue.put_nowait(payload)
                            except asyncio.QueueEmpty:
                                pass
                        
                        # Set event for one-time waiters
                        status_event.set()
                    return status_callback
                
                callback = make_status_callback(method_name, event, queue)
                self._subscribe_to_topic(status_topic, callback)
                
                print(f"Created async event for status method: {method_name}")
    
    def _subscribe_to_topic(self, topic: str, callback):
        """Subscribe to a topic with callback (delegate to device manager)"""
        if hasattr(self.mqtt_manager, '_proxy_subscribe'):
            self.mqtt_manager._proxy_subscribe(topic, callback)
    
    async def execute_and_wait_for_status(self, command_method_name: str, status_method_name: str, timeout: float = 10, **kwargs):
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
        await command_method(**kwargs)
        
        # Now wait for the status
        try:
            await asyncio.wait_for(
                self.status_events[status_method_name].wait(), 
                timeout=timeout
            )
            return self.get_latest_status(status_method_name)
        except asyncio.TimeoutError:
            return None
    
    async def wait_for_status(self, status_method: str, timeout: float = None) -> bool:
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
        
        try:
            if timeout:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            else:
                await event.wait()
            return True
        except asyncio.TimeoutError:
            return False
    
    def get_latest_status(self, status_method: str):
        """Get the latest status data for a method"""
        return self.latest_status_data.get(status_method)
    
    def clear_status_event(self, status_method: str):
        """Manually clear a status event"""
        if status_method in self.status_events:
            self.status_events[status_method].clear()

    async def wait_for(self, status_method: str, callback: Callable, timeout: float = None):
        """Wait for a status event and execute callback (single use)
        
        Args:
            status_method: Name of the status method to wait for
            callback: Function to call when event occurs. Will receive (status_data) as argument
            timeout: Optional timeout in seconds. If exceeded, callback is called with None
            
        Returns:
            asyncio.Task: The task handling the wait (for reference)
        """
        if status_method not in self.status_events:
            raise ValueError(f"No status method '{status_method}' found for {self.component_type}")
        
        async def wait_task():
            try:
                # Clear any previous event
                self.status_events[status_method].clear()
                
                # Wait for the event
                try:
                    if timeout:
                        await asyncio.wait_for(
                            self.status_events[status_method].wait(), 
                            timeout=timeout
                        )
                    else:
                        await self.status_events[status_method].wait()
                    
                    # Event occurred - get the data and call callback
                    status_data = self.get_latest_status(status_method)
                    if asyncio.iscoroutinefunction(callback):
                        await callback(status_data)
                    else:
                        callback(status_data)
                except asyncio.TimeoutError:
                    # Timeout occurred
                    if asyncio.iscoroutinefunction(callback):
                        await callback(None)
                    else:
                        callback(None)
                        
            except Exception as e:
                print(f"Error in wait_for task for {status_method}: {e}")
                if asyncio.iscoroutinefunction(callback):
                    await callback(None)
                else:
                    callback(None)
        
        # Create and start the task
        task = asyncio.create_task(wait_task())
        print(f"Started wait_for task for {self.component_name}.{status_method}")
        return task

    def wait_for_continuous(self, status_method: str, callback: Callable, stop_condition: Callable = None):
        """Wait for a status event continuously and execute callback each time
        
        Args:
            status_method: Name of the status method to wait for
            callback: Function to call when event occurs. Will receive (status_data) as argument
            stop_condition: Optional function that returns True when waiting should stop
            
        Returns:
            str: A unique ID for this continuous wait (use with stop_continuous_wait)
        """
        if status_method not in self.status_queues:
            raise ValueError(f"No status method '{status_method}' found for {self.component_type}")
        
        # Create unique ID for this continuous wait
        wait_id = str(uuid.uuid4())
        
        # Create stop flag for this wait
        self.continuous_wait_stop_flags[wait_id] = asyncio.Event()
        
        async def continuous_wait_task():
            try:
                queue = self.status_queues[status_method]
                stop_flag = self.continuous_wait_stop_flags[wait_id]
                
                while not stop_flag.is_set():
                    try:
                        # Wait for new status data or stop signal
                        status_data = await asyncio.wait_for(
                            queue.get(), 
                            timeout=1.0  # Check stop condition periodically
                        )
                        
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(status_data)
                            else:
                                callback(status_data)
                        except Exception as e:
                            print(f"Error in callback for {status_method}: {e}")
                    
                    except asyncio.TimeoutError:
                        # Timeout is normal - just check stop condition
                        pass
                    
                    # Check external stop condition if provided
                    if stop_condition and stop_condition():
                        break
                        
            except Exception as e:
                print(f"Error in continuous wait task for {status_method}: {e}")
            finally:
                # Clean up
                if wait_id in self.continuous_waits:
                    del self.continuous_waits[wait_id]
                if wait_id in self.continuous_wait_stop_flags:
                    del self.continuous_wait_stop_flags[wait_id]
        
        # Create and start the task
        task = asyncio.create_task(continuous_wait_task())
        self.continuous_waits[wait_id] = task
        
        print(f"Started continuous wait for {self.component_name}.{status_method} (ID: {wait_id[:8]})")
        return wait_id

    async def stop_continuous_wait(self, wait_id: str):
        """Stop a specific continuous wait"""
        if wait_id not in self.continuous_wait_stop_flags:
            print(f"No continuous wait found with ID: {wait_id}")
            return
        
        # Signal the task to stop
        self.continuous_wait_stop_flags[wait_id].set()
        
        # Wait for task to finish
        if wait_id in self.continuous_waits:
            task = self.continuous_waits[wait_id]
            try:
                await asyncio.wait_for(task, timeout=2.0)
                print(f"Stopped continuous wait {wait_id[:8]}")
            except asyncio.TimeoutError:
                print(f"Warning: Continuous wait task {wait_id} did not stop cleanly")
                task.cancel()

    async def stop_all_continuous_waits(self):
        """Stop all continuous waits for this component"""
        wait_ids = list(self.continuous_waits.keys())
        tasks = [self.stop_continuous_wait(wait_id) for wait_id in wait_ids]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        print(f"Stopped all continuous waits for {self.component_name}")

    def list_active_waits(self):
        """List all active continuous waits for this component"""
        if not self.continuous_waits:
            print(f"No active waits for {self.component_name}")
            return []
        
        active_waits = []
        for wait_id, task in self.continuous_waits.items():
            if not task.done():
                active_waits.append({
                    'id': wait_id,
                    'task': task,
                    'is_done': task.done()
                })
        
        if active_waits:
            print(f"Active waits for {self.component_name}:")
            for wait in active_waits:
                print(f"  - {wait['id'][:8]}: Active task")
        else:
            print(f"No active waits for {self.component_name}")
        
        return active_waits
    
    async def _publish_command(self, command: str, params: dict = None):
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
            
            await self.mqtt_manager.publish(topic, message)
            print(f"Published command: {topic} -> {message}")
            return True
                
        except Exception as e:
            logging.error(f"Error publishing command {command} to {topic}: {e}")
            return False

class AsyncDeviceProxy:
    """Async version of DeviceProxy - represents a device on the server side"""
    
    def __init__(self, device_name: str, device_config: dict, mqtt_manager, device_prefix: str):
        self.device_name = device_name
        self.device_config = device_config
        self.mqtt_manager = mqtt_manager
        self.device_prefix = device_prefix
        
        # Create component proxies
        self._create_components()
    
    def _create_components(self):
        """Create proxy objects for each component"""
        components_config = self.device_config.get('components', {})
        
        for component_name, component_config in components_config.items():
            component_proxy = AsyncComponentProxy(
                self.device_name,
                component_name, 
                component_config,
                self.mqtt_manager,
                self.device_prefix
            )
            
            # Add component as attribute to this device
            setattr(self, component_name, component_proxy)
            print(f"Created async component proxy: {self.device_name}.{component_name} ({component_config['type']})")
    
    async def wait_for_any_status(self, timeout: float = None) -> Optional[Tuple[str, str, Any]]:
        """Wait for any status event from any component
        
        Returns:
            (component_name, status_method, status_data) if event occurs, None if timeout
        """
        # Collect all events from all components
        tasks = []
        component_info = {}
        
        for comp_name in dir(self):
            comp = getattr(self, comp_name)
            if hasattr(comp, 'status_events'):
                for status_method, event in comp.status_events.items():
                    task_name = f"{comp_name}.{status_method}"
                    task = asyncio.create_task(event.wait())
                    tasks.append(task)
                    component_info[task] = (comp_name, status_method, comp)
        
        if not tasks:
            return None
        
        try:
            # Wait for any event to be set
            done, pending = await asyncio.wait(
                tasks, 
                timeout=timeout, 
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
            
            if done:
                # Get the first completed task
                completed_task = next(iter(done))
                comp_name, status_method, comp = component_info[completed_task]
                status_data = comp.get_latest_status(status_method)
                return (comp_name, status_method, status_data)
            
            return None
            
        except asyncio.TimeoutError:
            # Cancel all tasks on timeout
            for task in tasks:
                task.cancel()
            return None

import asyncio
import aiomqtt
import json
import logging
from typing import Dict, Any, Optional, Callable, Tuple

class AsyncServerDeviceManager:
    """Async version of ServerDeviceManager - manages device proxies on the server side"""
    
    def __init__(self, mqtt_config: dict = None):
        self.devices = {}
        self.mqtt_config = mqtt_config or {}
        self.device_prefix = self.mqtt_config.get('device_prefix', 'devices')
        self.topic_callbacks = {}
        self.is_connected = False
        self._mqtt_task = None
        self._client_context = None
        
    async def initialize(self):
        """Initialize the MQTT connection"""
        await self._setup_mqtt()
    
    async def _setup_mqtt(self):
        """Setup async MQTT client connection"""
        try:
            broker_host = self.mqtt_config.get('broker_host', 'localhost')
            broker_port = self.mqtt_config.get('broker_port', 1883)
            username = self.mqtt_config.get('username')
            password = self.mqtt_config.get('password')
            
            print(f"Connecting to MQTT broker: {broker_host}:{broker_port}")
            
            # Create async MQTT client
            client_args = {
                'hostname': broker_host,
                'port': broker_port,
            }
            
            if username and password:
                client_args['username'] = username
                client_args['password'] = password
            
            self.mqtt_client = aiomqtt.Client(**client_args)
            
            # Add proxy subscribe method
            self.mqtt_client._proxy_subscribe = self._proxy_subscribe
            
            # Start the client context and message processing
            self._mqtt_task = asyncio.create_task(self._mqtt_context())
            
            # Wait a bit for connection to establish
            await asyncio.sleep(0.5)
            
            print("Async MQTT setup initiated")
            
        except Exception as e:
            print(f"Failed to setup async MQTT: {e}")
            raise
    
    async def _mqtt_context(self):
        """Handle the MQTT client context and message processing"""
        try:
            async with self.mqtt_client as client:
                self.is_connected = True
                print("MQTT client connected successfully")
                
                # Subscribe to all pending topics
                for topic in self.topic_callbacks.keys():
                    await client.subscribe(topic)
                    print(f"Subscribed to topic: {topic}")
                
                # Process messages
                async for message in client.messages:
                    await self._handle_message(message)
                    
        except Exception as e:
            print(f"Error in MQTT context: {e}")
            self.is_connected = False
        finally:
            self.is_connected = False
            print("MQTT client disconnected")
    
    def _proxy_subscribe(self, topic: str, callback):
        """Subscribe to a topic with callback for component proxies"""
        if topic not in self.topic_callbacks:
            self.topic_callbacks[topic] = []
        
        self.topic_callbacks[topic].append(callback)
        
        if self.is_connected:
            # Subscribe in background
            asyncio.create_task(self._subscribe_topic(topic))
    
    async def _subscribe_topic(self, topic: str):
        """Subscribe to a single topic"""
        try:
            await self.mqtt_client.subscribe(topic)
            print(f"Subscribed to status topic: {topic}")
        except Exception as e:
            print(f"Error subscribing to {topic}: {e}")
    
    async def _handle_message(self, message):
        """Handle incoming MQTT messages for status updates"""
        topic = message.topic.value
        try:
            # Try to decode as JSON, fall back to string
            try:
                payload = json.loads(message.payload.decode())
            except json.JSONDecodeError:
                payload = message.payload.decode()
            
            print(f"Async MQTT received: {topic} -> {payload}")
            
            # Call all callbacks for this topic
            if topic in self.topic_callbacks:
                tasks = []
                for callback in self.topic_callbacks[topic]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            tasks.append(callback(topic, payload))
                        else:
                            # For non-async callbacks, run in executor or call directly
                            callback(topic, payload)
                    except Exception as e:
                        logging.error(f"Error in status callback for {topic}: {e}")
                
                # Wait for all async callbacks
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                        
        except Exception as e:
            logging.error(f"Error processing MQTT message: {e}")
    
    async def publish(self, topic: str, message: str):
        """Publish a message to MQTT"""
        try:
            await self.mqtt_client.publish(topic, message)
            return True
        except Exception as e:
            logging.error(f"Error publishing to {topic}: {e}")
            return False
    
    def load_device_config(self, config: dict):
        """Load devices from a single config dictionary"""
        device_prefix = config.get('mqtt', {}).get('device_prefix', self.device_prefix)
        devices_config = config.get('devices', {})
        
        for device_name, device_config in devices_config.items():
            try:
                device_proxy = AsyncDeviceProxy(
                    device_name,
                    device_config,
                    self,  # Pass self as mqtt_manager
                    device_prefix
                )
                
                self.devices[device_name] = device_proxy
                
                # Also add as attribute to this manager for easy access
                setattr(self, device_name, device_proxy)
                
                print(f"Created async device proxy: {device_name}")
                
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
                    methods = [method for method in dir(component) if not method.startswith('_') and callable(getattr(component, method)) and method not in ['component_name', 'device_name', 'component_config', 'mqtt_manager', 'device_prefix', 'component_type']]
                    print(f"  - {attr_name} ({component.component_type}): {', '.join(methods)}")
    
    async def disconnect(self):
        """Disconnect from MQTT"""
        try:
            self.is_connected = False
            if self._mqtt_task and not self._mqtt_task.done():
                self._mqtt_task.cancel()
                try:
                    await self._mqtt_task
                except asyncio.CancelledError:
                    pass
            print("Async MQTT disconnected")
        except Exception as e:
            print(f"Error disconnecting MQTT: {e}")