import asyncio
import time
import logging
from typing import Type, TypeVar, Dict, Any, Optional
from collections import defaultdict

SM = TypeVar("SM", bound="AsyncStateManager")

async def clear_async_queue(queue: asyncio.Queue) -> None:
    """
    Simple function to clear an async queue
    """
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break

class AsyncStateManager:
    """
    Async StateManager class for managing device states.
    
    This class provides centralized state management for all devices
    using event-driven updates instead of polling. Now supports both
    MQTT and ESPHome components.
    """
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls: Type[SM], *args, **kwargs) -> SM:
        """
        Ensures a single instance of this object (singleton pattern).
        """
        if not cls._instance:
            cls._instance = super(AsyncStateManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, controller=None, config=None):
        # Only initialize once
        if config is None:
            raise ValueError("Config must be provided on first initialization")
        
        self.config = config

        if hasattr(self, '_initialized'):
            return
        
        if controller is None:
            raise ValueError("Controller must be provided on first initialization")
        
        for key, value in self.config.get("config", {}).items():
            setattr(self, key, value)

        self._internal_states = {}
        for key, value in self.config.get("internal_state", {}).items():
            self._internal_states[key] = value

        # Initialize external states as a watched dictionary
        self._external_states = {}

        self.state_queue = asyncio.Queue()
        self.controller = controller
        
        # Get both MQTT and ESPHome state definitions
        self.external_state_definitions = self._discover_all_state_definitions()
        print(self.external_state_definitions)
        self.running = False
        self.refresh_task = None
        self.event_listeners = {}  # Track active event listeners
        self.esphome_monitor_tasks = {}  # Track ESPHome monitoring tasks
        
        # Heartbeat management
        self.heartbeat_definitions = self._discover_heartbeat_devices()
        self.heartbeat_listeners = {}  # Track heartbeat listeners
        
        self._initialized = True
        
        # Create nested attribute structure
        self._create_nested_attributes()
    
    def _discover_all_state_definitions(self):
        """
        Discover state definitions from both MQTT and ESPHome components.
        This replaces the simple call to controller.list_data_commands().
        """
        state_definitions = []
        
        # Get MQTT component data commands (existing functionality)
        all_data_commands = self.controller.list_data_commands()
        
        # Separate MQTT and ESPHome data commands
        mqtt_data_commands = [cmd for cmd in all_data_commands if cmd.get('type') != 'ESPHomeACComponent']
        esphome_data_commands = [cmd for cmd in all_data_commands if cmd.get('type') == 'ESPHomeACComponent']
        
        print(f"Discovered {len(mqtt_data_commands)} MQTT data commands")
        print(f"Discovered {len(esphome_data_commands)} ESPHome data commands")
        
        # Add MQTT data commands (with proper status pairing)
        for cmd in mqtt_data_commands:
            if cmd.get('status_method_name') and cmd.get('status_path'):
                state_definitions.append(cmd)
            else:
                print(f"Skipping MQTT command without status: {cmd.get('command_str')}")
        
        # Add ESPHome data commands (with proper status pairing)
        for cmd in esphome_data_commands:
            if cmd.get('status_method_name') and cmd.get('status_path'):
                # Mark as ESPHome type for different handling
                cmd['type'] = 'ESPHomeACComponent'
                state_definitions.append(cmd)
                print(f"Added ESPHome data command: {cmd.get('command_str')} -> {cmd.get('status_str')}")
            else:
                print(f"Skipping ESPHome command without status: {cmd.get('command_str')}")
        
        print(f"Total state definitions: {len(state_definitions)}")
        return state_definitions
    
    def _discover_esphome_state_definitions(self):
        """
        Discover all ESPHome component status methods and create state definitions.
        """
        esphome_definitions = []
        
        print("DEBUG: Starting ESPHome state definition discovery")
        
        # Check if we have ESPHome components
        if not hasattr(self.controller, 'esphome_components'):
            print("DEBUG: No esphome_components attribute found on controller")
            return esphome_definitions
        
        print(f"DEBUG: Found esphome_components: {list(self.controller.esphome_components.keys())}")
        
        from ESPHomeACComponent import ESPHomeACComponent
        
        for component_key, esphome_component_proxy in self.controller.esphome_components.items():
            print(f"DEBUG: Processing component_key: '{component_key}' (type: {type(component_key)})")
            
            # Safely handle component_key parsing
            if not component_key:
                print(f"WARNING: Empty component_key found")
                continue
                
            if component_key is None:
                print(f"WARNING: None component_key found")
                continue
                
            if not isinstance(component_key, str):
                print(f"WARNING: component_key is not a string: {component_key} (type: {type(component_key)})")
                continue
                
            if '.' not in component_key:
                print(f"WARNING: component_key does not contain '.': '{component_key}'")
                continue
                
            try:
                device_name, component_name = component_key.split('.', 1)
                print(f"DEBUG: Split successful - device_name: '{device_name}', component_name: '{component_name}'")
            except (ValueError, AttributeError) as e:
                print(f"ERROR: Could not parse ESPHome component key '{component_key}': {e}")
                continue
            
            # Ensure we have valid names
            if not device_name or not component_name:
                print(f"WARNING: Invalid device/component names from key '{component_key}' - device_name: '{device_name}', component_name: '{component_name}'")
                continue
            
            print(f"DEBUG: Processing ESPHome component: {device_name}.{component_name}")
            
            # Find all status methods in the ESPHome component
            esphome_methods = [method for method in dir(ESPHomeACComponent) if not method.startswith('_')]
            print(f"DEBUG: ESPHomeACComponent methods: {esphome_methods}")
            
            for method_name in esphome_methods:
                if not method_name or method_name.startswith('_'):
                    continue
                    
                try:
                    method = getattr(ESPHomeACComponent, method_name)
                    if callable(method) and hasattr(method, '_is_mqtt_status'):
                        print(f"DEBUG: Found status method: {method_name}")
                        
                        # Create a state definition for this status method
                        status_path = f"{device_name}.{component_name}.{method_name}"
                        component_path = f"{device_name}.{component_name}"
                        
                        print(f"DEBUG: Creating status_path: '{status_path}', component_path: '{component_path}'")
                        
                        # Verify the proxy has this method
                        if not hasattr(esphome_component_proxy, method_name):
                            print(f"WARNING: ESPHome component proxy missing method {method_name}")
                            continue
                        
                        # Get the actual proxy method
                        status_proxy_method = getattr(esphome_component_proxy, method_name)
                        print(f"DEBUG: Got proxy method for {method_name}")
                        
                        esphome_definition = {
                            "type": "esphome",
                            "status_method_name": method_name,
                            "status_path": status_path,
                            "component_path": component_path,
                            "status_method": status_proxy_method,
                            "esphome_component_proxy": esphome_component_proxy,
                            "device_name": device_name,
                            "component_name": component_name
                        }
                        
                        esphome_definitions.append(esphome_definition)
                        print(f"DEBUG: Added ESPHome status method: {status_path}")
                        
                except Exception as e:
                    print(f"ERROR: Error processing ESPHome method {method_name} for {component_key}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        
        print(f"DEBUG: ESPHome discovery complete. Found {len(esphome_definitions)} definitions")
        return esphome_definitions
        
    @classmethod
    async def get_instance(cls, controller=None, config=None):
        """
        Get the singleton instance. If it doesn't exist, create it with the provided parameters.
        """
        async with cls._lock:
            if cls._instance is None:
                instance = cls(controller, config)
                await instance._setup_event_listeners()
                await instance._setup_heartbeat_listeners()
                return instance
            return cls._instance
    
    @classmethod
    async def reset_instance(cls):
        """
        Reset the singleton instance. Useful for testing or reinitialization.
        """
        async with cls._lock:
            if cls._instance and cls._instance.running:
                await cls._instance.stop_continuous_refresh()
            cls._instance = None
    
    def _discover_heartbeat_devices(self):
        """
        Discover all devices that have heartbeat functionality.
        Returns a list of heartbeat definitions similar to external_state_definitions.
        """
        heartbeat_definitions = []
        
        # Iterate through all devices in the controller
        for device_name, device_proxy in self.controller.all_devices.items():
            # Check if this device has heartbeat methods
            if hasattr(device_proxy, 'heartbeat') and callable(device_proxy.heartbeat):
                heartbeat_definitions.append({
                    'device_name': device_name,
                    'device_proxy': device_proxy,
                    'status_path': f"{device_name}.heartbeat_status",
                    'command_str': f"{device_name}.heartbeat()",
                    'command_method': device_proxy.heartbeat,
                    'execute_and_wait_method': device_proxy.execute_heartbeat_and_wait,
                    'get_latest_method': device_proxy.get_latest_heartbeat
                })
                print(f"Discovered heartbeat for device: {device_name}")
        
        return heartbeat_definitions
        
    def _create_nested_attributes(self):
        """Create nested attribute structure to mirror controller"""
        # Create component-level attributes
        for method_info in self.external_state_definitions:
            # Create nested attributes: self.hvac.temp_sensor.temp_status
            self._create_nested_path(method_info['status_path'])
        
        # Create device-level heartbeat attributes
        for heartbeat_info in self.heartbeat_definitions:
            # Create nested attributes: self.therm.heartbeat_status
            self._create_nested_path(heartbeat_info['status_path'])
    
    def _create_nested_path(self, path):
        """Create nested attributes dynamically"""
        parts = path.split('.')
        current = self
        
        for part in parts[:-1]:  # All but the last part
            if not hasattr(current, part):
                setattr(current, part, type('StateObject', (), {})())
            current = getattr(current, part)
        
        # Set the final attribute to None initially
        setattr(current, parts[-1], None)
    
    def _set_nested_value(self, path, value):
        """Set a value in the nested structure"""
        parts = path.split('.')
        current = self
        
        for part in parts[:-1]:
            current = getattr(current, part)
        
        setattr(current, parts[-1], value)
    
    async def _setup_event_listeners(self):
        """
        Setup event-driven listeners for all component status methods.
        This handles both MQTT and ESPHome components.
        """
        print("Setting up event-driven state listeners...")
        
        for cmd_info in self.external_state_definitions:
            print(f"DEBUG: Processing cmd_info: {cmd_info.get('command_str')} -> {cmd_info.get('status_str')}")
            
            # Skip entries without proper status methods
            if not cmd_info.get('status_method_name') or not cmd_info.get('status_path'):
                print(f"DEBUG: Skipping command without status: {cmd_info.get('command_str')}")
                continue
            
            if cmd_info.get('type') == 'esphome':
                await self._setup_esphome_listener(cmd_info)
            else:
                await self._setup_mqtt_listener(cmd_info)
    
    async def _setup_mqtt_listener(self, cmd_info):
        """Setup listener for MQTT component status method"""
        print(f"DEBUG: Setting up MQTT listener for cmd_info: {cmd_info}")
        
        status_method_name = cmd_info.get('status_method_name')
        component_path = cmd_info.get('component_path')
        status_path = cmd_info.get('status_path')
        
        print(f"DEBUG: MQTT listener - status_method_name: '{status_method_name}', component_path: '{component_path}', status_path: '{status_path}'")
        
        # Validate required fields
        if not status_method_name or not component_path or not status_path:
            print(f"WARNING: Invalid MQTT command info, skipping: {cmd_info}")
            return
            
        try:
            # Get the component proxy
            print(f"DEBUG: Splitting component_path: '{component_path}' (type: {type(component_path)})")
            
            if component_path is None:
                print(f"ERROR: component_path is None!")
                return
                
            if not isinstance(component_path, str):
                print(f"ERROR: component_path is not a string: {component_path} (type: {type(component_path)})")
                return
            
            parts = component_path.split('.')
            print(f"DEBUG: component_path parts: {parts}")
            
            component_proxy = self.controller
            for i, part in enumerate(parts):
                if not part:  # Skip empty parts
                    print(f"WARNING: Empty part at index {i} in component_path: {parts}")
                    continue
                print(f"DEBUG: Getting attribute '{part}' from {type(component_proxy)}")
                component_proxy = getattr(component_proxy, part)
                print(f"DEBUG: Got {type(component_proxy)}")
            
            # Verify the component proxy has the required methods
            if not hasattr(component_proxy, 'wait_for_continuous'):
                print(f"WARNING: Component {component_path} does not support continuous waiting")
                return
            
            # Create a callback for this specific status update
            def make_status_callback(status_path_local, component_path_local):
                async def status_callback(status_data):
                    if status_data is not None:
                        print(f"MQTT event-driven update: {status_path_local} = {status_data}")
                        # Update nested attributes
                        self._set_nested_value(status_path_local, status_data)
                        # Update external states dictionary
                        new_states = {**self._external_states}
                        new_states[status_path_local] = status_data
                        self.external_states = new_states
                    else:
                        print(f"No MQTT data received for {status_path_local}")
                return status_callback
            
            callback = make_status_callback(status_path, component_path)
            
            # Start continuous monitoring for this status method
            wait_id = component_proxy.wait_for_continuous(
                status_method_name, 
                callback
            )
            
            # Track the listener for cleanup
            self.event_listeners[status_path] = {
                'type': 'mqtt',
                'component_proxy': component_proxy,
                'wait_id': wait_id,
                'status_method': status_method_name
            }
            
            print(f"Started MQTT event listener for {status_path}")
            
        except Exception as e:
            print(f"ERROR: Error setting up MQTT listener for {status_path}: {e}")
            import traceback
            traceback.print_exc()
    
    async def _setup_esphome_listener(self, cmd_info):
        """Setup listener for ESPHome component status method"""
        print(f"DEBUG: Setting up ESPHome listener for: {cmd_info}")
        
        status_method_name = cmd_info.get('status_method_name')
        status_path = cmd_info.get('status_path')
        component_path = cmd_info.get('component_path')
        
        # Validate required fields
        if not status_method_name or not status_path or not component_path:
            print(f"WARNING: Invalid ESPHome command info, skipping: {cmd_info}")
            return
        
        try:
            # Get the ESPHome component proxy directly
            parts = component_path.split('.')
            if len(parts) != 2:
                print(f"WARNING: Invalid ESPHome component path: {component_path}")
                return
            
            device_name, component_name = parts
            
            # Get the component proxy from the controller
            device_proxy = getattr(self.controller, device_name, None)
            if not device_proxy:
                print(f"WARNING: ESPHome device not found: {device_name}")
                return
            
            component_proxy = getattr(device_proxy, component_name, None)
            if not component_proxy:
                print(f"WARNING: ESPHome component not found: {component_path}")
                return
            
            # Verify the status method exists
            status_method = getattr(component_proxy, status_method_name, None)
            if not status_method or not callable(status_method):
                print(f"WARNING: ESPHome status method {status_method_name} is not callable")
                return
            
            print(f"DEBUG: Setting up ESPHome polling for {status_path}")
            
            # Create a callback for ESPHome status updates
            def make_esphome_callback(status_path_local):
                async def esphome_callback():
                    """Periodically check ESPHome component status"""
                    while self.running:
                        try:
                            # Call the status method directly
                            status_data = await status_method()
                            
                            if status_data is not None:
                                print(f"ESPHome update: {status_path_local} = {status_data}")
                                # Update nested attributes
                                self._set_nested_value(status_path_local, status_data)
                                # Update external states dictionary
                                new_states = {**self._external_states}
                                new_states[status_path_local] = status_data
                                self.external_states = new_states
                            
                            # Wait before next check (ESPHome components are polled less frequently)
                            await asyncio.sleep(getattr(self, 'esphome_poll_interval', 10))
                            
                        except Exception as e:
                            print(f"Error polling ESPHome status {status_path_local}: {e}")
                            await asyncio.sleep(5)  # Wait before retry
                        
                return esphome_callback
            
            # Start monitoring task for this ESPHome status method
            callback_coro = make_esphome_callback(status_path)
            monitor_task = asyncio.create_task(callback_coro())
            
            # Track the listener for cleanup
            self.event_listeners[status_path] = {
                'type': 'esphome',
                'monitor_task': monitor_task,
                'status_method': status_method_name
            }
            
            # Also track in esphome_monitor_tasks for easier cleanup
            self.esphome_monitor_tasks[status_path] = monitor_task
            
            print(f"Started ESPHome polling listener for {status_path}")
            
        except Exception as e:
            print(f"ERROR: Error setting up ESPHome listener for {status_path}: {e}")
            import traceback
            traceback.print_exc()

    async def _setup_heartbeat_listeners(self):
        """
        Setup event-driven listeners for heartbeat responses.
        Each device manager has its own heartbeat response topic.
        """
        print("Setting up heartbeat listeners...")
        
        # Track device managers we've already set up listeners for
        setup_managers = set()
        
        for heartbeat_info in self.heartbeat_definitions:
            device_name = heartbeat_info['device_name']
            device_proxy = heartbeat_info['device_proxy']
            status_path = heartbeat_info['status_path']
            
            # Get the device manager (mqtt_manager)
            device_manager = device_proxy.mqtt_manager
            
            # Only setup one listener per device manager (since heartbeats are shared)
            manager_id = id(device_manager)
            if manager_id in setup_managers:
                continue
                
            try:
                # Create a callback for heartbeat updates
                def make_heartbeat_callback(device_name_local, status_path_local):
                    async def heartbeat_callback(heartbeat_data):
                        if heartbeat_data is not None:
                            print(f"Heartbeat update: {device_name_local} = {heartbeat_data}")
                            # Update nested attributes
                            self._set_nested_value(status_path_local, heartbeat_data)
                            # Update external states dictionary
                            new_states = {**self._external_states}
                            new_states[status_path_local] = heartbeat_data
                            self.external_states = new_states
                        else:
                            print(f"No heartbeat data received for {device_name_local}")
                    return heartbeat_callback
                
                callback = make_heartbeat_callback(device_name, status_path)
                
                # Use the device manager's heartbeat queue for continuous monitoring
                wait_id = self._setup_heartbeat_continuous_wait(device_manager, callback)
                
                # Track the listener for cleanup
                self.heartbeat_listeners[status_path] = {
                    'device_manager': device_manager,
                    'wait_id': wait_id,
                    'device_name': device_name
                }
                
                setup_managers.add(manager_id)
                print(f"Started heartbeat listener for {device_name}")
                
            except Exception as e:
                print(f"Error setting up heartbeat listener for {device_name}: {e}")
    
    def _setup_heartbeat_continuous_wait(self, device_manager, callback):
        """
        Setup continuous monitoring of heartbeat responses for a device manager.
        Returns a unique wait ID for cleanup.
        """
        import uuid
        wait_id = str(uuid.uuid4())
        
        async def heartbeat_monitor_task():
            try:
                while self.running:
                    try:
                        # Wait for heartbeat data from the device manager's queue
                        heartbeat_data = await asyncio.wait_for(
                            device_manager.heartbeat_queue.get(), 
                            timeout=1.0  # Check stop condition periodically
                        )
                        
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(heartbeat_data)
                            else:
                                callback(heartbeat_data)
                        except Exception as e:
                            print(f"Error in heartbeat callback: {e}")
                    
                    except asyncio.TimeoutError:
                        # Timeout is normal - just continue monitoring
                        pass
                        
            except Exception as e:
                print(f"Error in heartbeat monitor task: {e}")
        
        # Start the monitoring task
        task = asyncio.create_task(heartbeat_monitor_task())
        
        # Store the task for cleanup (we'll clean it up in stop_continuous_refresh)
        if not hasattr(self, '_heartbeat_monitor_tasks'):
            self._heartbeat_monitor_tasks = {}
        self._heartbeat_monitor_tasks[wait_id] = task
        
        return wait_id

    async def refresh_all_data(self):
        """
        Manually refresh all data by sending commands and waiting for responses.
        This now includes MQTT components, ESPHome components, and heartbeat data.
        """
        print("Manual refresh: requesting all device states...")
        new_external_states = {}
        
        # Refresh MQTT component data
        await self._refresh_mqtt_component_data(new_external_states)
        
        # Refresh ESPHome component data
        await self._refresh_esphome_component_data(new_external_states)
        
        # Refresh heartbeat data
        await self._refresh_heartbeat_data(new_external_states)
        
        # Update external states (this will trigger queue update if changed)
        if new_external_states:
            self.external_states = new_external_states
            print(f"Manual refresh completed: {len(new_external_states)} states updated")
    
    async def _refresh_mqtt_component_data(self, new_external_states):
        """Refresh MQTT component-level data"""
        # Filter for MQTT components only
        mqtt_commands = [cmd for cmd in self.external_state_definitions 
                        if cmd.get('type') != 'esphome']
        
        if not mqtt_commands:
            return
        
        print(f"Refreshing {len(mqtt_commands)} MQTT component states...")
        
        # Group commands by device to send them concurrently per device
        device_commands = defaultdict(list)
        
        for cmd_info in mqtt_commands:
            device_name = cmd_info['component_path'].split('.')[0]
            device_commands[device_name].append(cmd_info)
        
        # Process each device's commands concurrently
        tasks = []
        for device_name, commands in device_commands.items():
            task = asyncio.create_task(
                self._refresh_device_data(device_name, commands, new_external_states)
            )
            tasks.append(task)
        
        # Wait for all devices to complete
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _refresh_esphome_component_data(self, new_external_states):
        """Refresh ESPHome component data"""
        # Filter for ESPHome components only
        esphome_commands = [cmd for cmd in self.external_state_definitions 
                           if cmd.get('type') == 'esphome']
        
        if not esphome_commands:
            return
        
        print(f"Refreshing {len(esphome_commands)} ESPHome component states...")
        
        # Process ESPHome commands
        tasks = []
        for cmd_info in esphome_commands:
            task = asyncio.create_task(
                self._refresh_single_esphome_status(cmd_info, new_external_states)
            )
            tasks.append(task)
        
        # Wait for all ESPHome status calls to complete
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _refresh_single_esphome_status(self, cmd_info, new_external_states):
        """Refresh a single ESPHome status method"""
        status_path = cmd_info['status_path']
        status_method = cmd_info['status_method']
        
        try:
            print(f"Refreshing ESPHome status: {status_path}")
            
            # Call the status method directly
            status_data = await status_method()
            
            if status_data is not None:
                # Update nested attributes
                self._set_nested_value(status_path, status_data)
                # Store in external states
                new_external_states[status_path] = status_data
                print(f"ESPHome status updated {status_path} = {status_data}")
            else:
                print(f"ESPHome status returned None for {status_path}")
                new_external_states[status_path] = None
                
        except Exception as e:
            print(f"Error refreshing ESPHome status {status_path}: {e}")
            new_external_states[status_path] = None
    
    async def _refresh_heartbeat_data(self, new_external_states):
        """Refresh heartbeat data for all devices"""
        print("Refreshing heartbeat data...")
        
        # Create tasks for all heartbeat requests
        tasks = []
        for heartbeat_info in self.heartbeat_definitions:
            task = asyncio.create_task(
                self._refresh_single_heartbeat(heartbeat_info, new_external_states)
            )
            tasks.append(task)
        
        # Wait for all heartbeat requests to complete
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _refresh_single_heartbeat(self, heartbeat_info, new_external_states):
        """Refresh heartbeat data for a single device"""
        device_name = heartbeat_info['device_name']
        status_path = heartbeat_info['status_path']
        
        try:
            print(f"Requesting heartbeat for {device_name}...")
            
            # Send heartbeat and wait for response
            heartbeat_data = await heartbeat_info['execute_and_wait_method'](timeout=5)
            
            if heartbeat_data is not None:
                # Update nested attributes
                self._set_nested_value(status_path, heartbeat_data)
                # Store in external states
                new_external_states[status_path] = heartbeat_data
                print(f"Heartbeat updated {status_path} = {heartbeat_data}")
            else:
                print(f"Heartbeat timeout for {device_name}")
                # Store timeout/offline status
                offline_status = {
                    "status": "offline",
                    "timestamp": time.time(),
                    "request_id": "timeout"
                }
                new_external_states[status_path] = offline_status
                
        except Exception as e:
            print(f"Error refreshing heartbeat for {device_name}: {e}")
            # Store error status
            error_status = {
                "status": "error",
                "timestamp": time.time(),
                "error": str(e)
            }
            new_external_states[status_path] = error_status
    
    async def _refresh_device_data(self, device_name: str, commands: list, new_external_states: dict):
        """Refresh data for a specific MQTT device"""
        for cmd_info in commands:
            try:
                command_str = cmd_info['command_str']
                status_method_name = cmd_info['status_method_name']
                component_path = cmd_info['component_path']
                status_path = cmd_info['status_path']
                command_method_name = cmd_info['command_method_name']
                
                if not status_method_name:
                    # No status method, just execute command
                    print(f"Executing command (no status): {command_str}")
                    await cmd_info['command_method']()
                    continue
                
                # Get the component proxy
                parts = component_path.split('.')
                component_proxy = self.controller
                for part in parts:
                    component_proxy = getattr(component_proxy, part)
                
                print(f"Executing command with status wait: {command_str}")
                
                # Use the execute_and_wait method
                status_data = await component_proxy.execute_and_wait_for_status(
                    command_method_name, 
                    status_method_name, 
                    timeout=10
                )
                
                if status_data is not None:
                    # Update our nested attributes for backward compatibility
                    self._set_nested_value(status_path, status_data)
                    # Also store in the new external states dict
                    new_external_states[status_path] = status_data
                    print(f"Updated {status_path} = {status_data}")
                else:
                    print(f"Timeout waiting for {status_method_name}")
                    new_external_states[status_path] = None
                    
            except Exception as e:
                print(f"Error processing {cmd_info['command_str']}: {e}")
                new_external_states[status_path] = None
    
    async def _periodic_refresh_loop(self):
        """
        Optional periodic refresh loop for devices that don't auto-publish status.
        This now includes heartbeat monitoring and ESPHome polling.
        """
        while self.running:
            try:
                print("Periodic refresh check...")
                # Refresh stale component data
                await self._refresh_stale_data()
                # Refresh heartbeat data periodically
                await self._refresh_periodic_heartbeats()
            except Exception as e:
                print(f"Error during periodic refresh: {e}")
            
            # Sleep for the refresh interval
            await asyncio.sleep(self.refresh_interval)
    
    async def _refresh_stale_data(self):
        """
        Refresh component data that hasn't been updated recently.
        This is a fallback for devices that don't auto-publish.
        """
        current_time = time.time()
        stale_threshold = getattr(self, 'stale_threshold', 30)  # 30 seconds default
        
        stale_commands = []
        
        for cmd_info in self.external_state_definitions:
            status_path = cmd_info['status_path']
            
            # Only refresh critical sensors or those marked as needing periodic refresh
            if self._needs_periodic_refresh(cmd_info):
                stale_commands.append(cmd_info)
        
        if stale_commands:
            print(f"Refreshing {len(stale_commands)} stale data points...")
            new_states = {}
            
            # Separate MQTT and ESPHome commands
            mqtt_commands = [cmd for cmd in stale_commands if cmd.get('type') != 'esphome']
            esphome_commands = [cmd for cmd in stale_commands if cmd.get('type') == 'esphome']
            
            # Refresh MQTT commands
            if mqtt_commands:
                await self._refresh_device_data("periodic", mqtt_commands, new_states)
            
            # Refresh ESPHome commands
            if esphome_commands:
                for cmd_info in esphome_commands:
                    await self._refresh_single_esphome_status(cmd_info, new_states)
            
            if new_states:
                current_states = {**self._external_states}
                current_states.update(new_states)
                self.external_states = current_states
    
    async def _refresh_periodic_heartbeats(self):
        """
        Periodically refresh heartbeat data to check device connectivity.
        """
        heartbeat_refresh_interval = getattr(self, 'heartbeat_refresh_interval', 30)  # 30 seconds default
        
        # Check if it's time for heartbeat refresh
        current_time = time.time()
        if not hasattr(self, '_last_heartbeat_refresh'):
            self._last_heartbeat_refresh = 0
        
        if current_time - self._last_heartbeat_refresh >= heartbeat_refresh_interval:
            print("Refreshing heartbeat data...")
            new_states = {}
            await self._refresh_heartbeat_data(new_states)
            
            if new_states:
                current_states = {**self._external_states}
                current_states.update(new_states)
                self.external_states = current_states
                
            self._last_heartbeat_refresh = current_time
    
    def _needs_periodic_refresh(self, cmd_info: dict) -> bool:
        """
        Determine if a command needs periodic refresh.
        Override this method to customize which devices need polling.
        """
        # ESPHome components benefit from periodic refresh since they don't have event-driven updates
        if cmd_info.get('type') == 'esphome':
            return True
        
        # Example: refresh temperature sensors every cycle
        if 'temp' in cmd_info['status_path'].lower():
            return True
        
        # Example: refresh critical status indicators
        if 'heartbeat' in cmd_info['status_path'].lower():
            return True
            
        # Most other MQTT devices rely on event-driven updates
        return False
    
    async def start_continuous_refresh(self):
        """Start the event-driven state management"""
        if self.running:
            print("Continuous refresh is already running")
            return
        
        self.running = True
        
        # Start with an initial manual refresh to get current states
        print("Starting with initial state refresh...")
        await self.refresh_all_data()
        
        # Start periodic refresh for devices that need it (ESPHome components benefit from this)
        if hasattr(self, 'refresh_interval') and self.refresh_interval > 0:
            self.refresh_task = asyncio.create_task(self._periodic_refresh_loop())
            print(f"Started periodic refresh task (interval: {self.refresh_interval}s)")
        
        print("Event-driven state management started (MQTT + ESPHome)")
    
    async def stop_continuous_refresh(self):
        """Stop the continuous refresh"""
        if not self.running:
            print("Continuous refresh is not running")
            return
        
        print("Stopping state management...")
        self.running = False
        
        # Stop periodic refresh task
        if self.refresh_task and not self.refresh_task.done():
            self.refresh_task.cancel()
            try:
                await self.refresh_task
            except asyncio.CancelledError:
                pass
        
        # Stop all MQTT component event listeners
        print("Stopping MQTT component event listeners...")
        for status_path, listener_info in self.event_listeners.items():
            try:
                if listener_info.get('type') == 'mqtt':
                    component_proxy = listener_info['component_proxy']
                    wait_id = listener_info['wait_id']
                    await component_proxy.stop_continuous_wait(wait_id)
                    print(f"Stopped MQTT listener for {status_path}")
                elif listener_info.get('type') == 'esphome':
                    monitor_task = listener_info['monitor_task']
                    if not monitor_task.done():
                        monitor_task.cancel()
                        try:
                            await monitor_task
                        except asyncio.CancelledError:
                            pass
                    print(f"Stopped ESPHome listener for {status_path}")
            except Exception as e:
                print(f"Error stopping listener for {status_path}: {e}")
        
        # Stop ESPHome monitor tasks
        print("Stopping ESPHome monitor tasks...")
        for status_path, task in self.esphome_monitor_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self.esphome_monitor_tasks.clear()
        
        # Stop heartbeat monitor tasks
        if hasattr(self, '_heartbeat_monitor_tasks'):
            print("Stopping heartbeat monitor tasks...")
            for wait_id, task in self._heartbeat_monitor_tasks.items():
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            self._heartbeat_monitor_tasks.clear()
        
        self.event_listeners.clear()
        self.heartbeat_listeners.clear()
        self.refresh_task = None
        print("State management stopped (MQTT + ESPHome)")
    
    def is_refresh_running(self):
        """Check if continuous refresh is currently running"""
        return self.running
    
    def get_all_states(self):
        """Return a dictionary of all current states"""
        return {**self._external_states, **self._internal_states}

    async def update_state_queue(self):
        """Add current state to queue for websocket emission"""
        await self.state_queue.put(self.get_all_states())

    async def set_state(self, key, value):
        """Set an internal state value"""
        self.internal_states = {**self.internal_states, key: value}

    @property
    def internal_states(self):
        return self._internal_states
    
    @internal_states.setter
    def internal_states(self, value):
        if value != self._internal_states:
            self._internal_states = value
            # Schedule queue update
            asyncio.create_task(self.update_state_queue())

    @property
    def external_states(self):
        """Get external states dictionary"""
        return self._external_states
    
    @external_states.setter
    def external_states(self, value):
        """Set external states and trigger queue update if changed"""
        if value != self._external_states:
            print(f"External states changed, updating queue")
            self._external_states = value
            # Schedule queue update
            asyncio.create_task(self.update_state_queue())

    async def get_state_updates(self):
        """
        Async generator for state updates. Use this in your web layer.
        
        Usage:
            async for new_state in state_manager.get_state_updates():
                await socketio.emit('state_update', serialize_state(new_state))
        """
        while True:
            try:
                new_state = await self.state_queue.get()
                yield new_state
            except asyncio.CancelledError:
                break

# Factory function for compatibility
async def create_async_state_manager(controller, config):
    """Create and initialize an async state manager"""
    state_manager = await AsyncStateManager.get_instance(controller, config)
    return state_manager

# Usage example:
async def main():
    """Example usage with ESPHome support"""
    from ConfigLoader import create_device_controller
    
    controller = await create_device_controller(
        "/home/scrumpi/containers/therm-2/configs", 
        "/home/scrumpi/containers/therm-2"
    )
    
    config = {
        "internal_state": {"control": "MANUAL"},
        "config": {
            "refresh_interval": 30,  # Component refresh interval
            "heartbeat_refresh_interval": 15,  # Heartbeat refresh interval
            "esphome_poll_interval": 10  # ESPHome polling interval (for real-time monitoring)
        }
    }
    
    # Create state manager
    state_manager = await create_async_state_manager(controller, config)
    
    # Start event-driven monitoring
    await state_manager.start_continuous_refresh()
    
    print("State manager running with MQTT + ESPHome support. Current states:")
    print(state_manager.get_all_states())
    
    # Monitor state changes
    async def monitor_changes():
        async for new_state in state_manager.get_state_updates():
            print(f"State update received: {len(new_state)} states")
            
            # Check for heartbeat updates
            heartbeat_keys = [k for k in new_state.keys() if 'heartbeat_status' in k]
            if heartbeat_keys:
                print(f"Heartbeat states: {heartbeat_keys}")
            
            # Check for ESPHome updates
            esphome_keys = [k for k in new_state.keys() if any(ac_name in k for ac_name in ['living_room_ac', 'bedroom_ac'])]
            if esphome_keys:
                print(f"ESPHome AC states: {esphome_keys}")
    
    # Run for a while
    monitor_task = asyncio.create_task(monitor_changes())
    await asyncio.sleep(60)  # Run for 1 minute
    
    # Cleanup
    monitor_task.cancel()
    await state_manager.stop_continuous_refresh()
    await controller.disconnect_all()

if __name__ == "__main__":
    asyncio.run(main())