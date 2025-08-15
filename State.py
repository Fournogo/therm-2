# CleanStateManager.py
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from MQTTDeviceProxy import MQTTComponentProxy

class StateManager:
    """
    State manager that works with the clean proxy architecture.
    Monitors both MQTT and ESPHome devices.
    """
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, controller, config: Dict[str, Any]):
        self.controller = controller
        self.config = config
        
        # Internal states (control system state)
        self._internal_states = config.get("internal_state", {})
        
        # External states (device states)
        self._external_states = {}
        
        # State update queue for websocket
        self.state_queue = asyncio.Queue()
        
        # Running flag
        self.running = False
        
        # Monitoring tasks
        self.monitoring_tasks = {}

        # Event-driven polling triggers
        self.state_update_events = {}
        
        # Discover all data commands
        self.data_commands = self.controller.list_data_commands()
        
        # Discover heartbeat devices
        self.heartbeat_definitions = self._discover_heartbeat_devices()
        
        # Create nested attributes for easy access
        self._create_nested_attributes()
        
        logging.info(f"CleanStateManager initialized with {len(self.data_commands)} data commands and {len(self.heartbeat_definitions)} heartbeat devices")
    
    def _discover_heartbeat_devices(self):
        """Discover all devices that have heartbeat functionality"""
        heartbeat_definitions = []
        
        # Check all MQTT managers for heartbeat support (device_prefix level)
        for device_prefix, mqtt_manager in self.controller.mqtt_managers.items():
            # Create heartbeat definition for this prefix
            heartbeat_def = {
                'device_prefix': device_prefix,
                'mqtt_manager': mqtt_manager,
                'status_path': f"{device_prefix}.heartbeat_status",
                'type': 'mqtt'
            }
            heartbeat_definitions.append(heartbeat_def)
            logging.info(f"Discovered MQTT heartbeat for device prefix: {device_prefix}")
        
        # Check ESPHome devices for heartbeat functionality
        for device_name, device in self.controller.all_devices.items():
            if not hasattr(device, 'components'):  # ESPHome device
                for attr_name in dir(device):
                    if not attr_name.startswith('_'):
                        component = getattr(device, attr_name)
                        if hasattr(component, 'get_command_methods'):
                            commands = component.get_command_methods()
                            status_methods = component.get_status_methods()
                            if 'heartbeat' in commands and 'heartbeat_status' in status_methods:
                                heartbeat_def = {
                                    'device_name': device_name,
                                    'component_name': attr_name,
                                    'component_proxy': component,
                                    'status_path': f"{device_name}.{attr_name}.heartbeat_status",
                                    'type': 'esphome'
                                }
                                heartbeat_definitions.append(heartbeat_def)
                                logging.info(f"Discovered ESPHome heartbeat: {device_name}.{attr_name}")
        
        return heartbeat_definitions
    
    def _create_nested_attributes(self):
        """Create nested attribute structure"""
        # Create attributes for data commands
        for cmd_info in self.data_commands:
            path = cmd_info['status_path']
            self._create_nested_path(path)
        
        # Create attributes for heartbeats
        for heartbeat_info in self.heartbeat_definitions:
            path = heartbeat_info['status_path']
            self._create_nested_path(path)
    
    def _create_nested_path(self, path: str):
        """Create nested attributes dynamically"""
        parts = path.split('.')
        current = self
        
        for part in parts[:-1]:
            if not hasattr(current, part):
                setattr(current, part, type('StateObject', (), {})())
            current = getattr(current, part)
        
        # Set final attribute to None initially
        setattr(current, parts[-1], None)
    
    def _set_nested_value(self, path: str, value: Any):
        """Set a value in the nested structure"""
        parts = path.split('.')
        current = self
        
        for part in parts[:-1]:
            current = getattr(current, part)
        
        setattr(current, parts[-1], value)
    
    async def start_continuous_refresh(self):
        """Start monitoring all states"""
        if self.running:
            logging.warning("State manager already running")
            return
        
        self.running = True
        
        # Initial refresh to get current states
        await self.refresh_all_states()
        
        # Setup continuous monitoring for each data command
        for cmd_info in self.data_commands:
            if cmd_info['type'] == 'mqtt':
                # Setup MQTT monitoring
                task = asyncio.create_task(self._monitor_mqtt_state(cmd_info))
                self.monitoring_tasks[cmd_info['status_path']] = task
            elif cmd_info['type'] == 'esphome':
                # Setup ESPHome polling
                task = asyncio.create_task(self._monitor_esphome_state(cmd_info))
                self.monitoring_tasks[cmd_info['status_path']] = task
        
        # Setup heartbeat monitoring
        for heartbeat_info in self.heartbeat_definitions:
            task = asyncio.create_task(self._monitor_heartbeat(heartbeat_info))
            self.monitoring_tasks[heartbeat_info['status_path']] = task
            logging.debug(f"Monitoring heartbeat info: {heartbeat_info}")

        # Start periodic refresh for data commands
        self.monitoring_tasks['_periodic_refresh'] = asyncio.create_task(self._periodic_refresh())

        # Start periodic heartbeat refresh
        self.monitoring_tasks['_heartbeat_refresh'] = asyncio.create_task(self._periodic_heartbeat_refresh())
        
        logging.info(f"Started monitoring {len(self.monitoring_tasks)} states")
    
    async def stop_continuous_refresh(self):
        """Stop all monitoring"""
        if not self.running:
            return
        
        self.running = False
        
        # Cancel all tasks
        for task in self.monitoring_tasks.values():
            task.cancel()
        
        # Wait for cancellation
        if self.monitoring_tasks:
            await asyncio.gather(*self.monitoring_tasks.values(), return_exceptions=True)
        
        self.monitoring_tasks.clear()
        self.state_update_events.clear()
        logging.info("State monitoring stopped and events cleaned up")
        logging.info("State monitoring stopped")
    
    async def _monitor_mqtt_state(self, cmd_info: Dict[str, Any]):
        """Monitor an MQTT component state"""
        component_proxy = cmd_info['component_proxy']
        status_method = cmd_info['status_method_name']
        status_path = cmd_info['status_path']
        
        # Subscribe to status updates
        def status_callback(payload):
            # Update state
            self._set_nested_value(status_path, payload)
            self._external_states[status_path] = payload
            
            # Queue update
            asyncio.create_task(self._queue_state_update())
            
            logging.debug(f"MQTT state update: {status_path} = {payload}")
        
        component_proxy.subscribe_to_status_updates(status_method, status_callback)
        
        # Keep task alive
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
    
    async def _monitor_esphome_state(self, cmd_info: Dict[str, Any]):
        """Monitor an ESPHome component state with event-driven polling"""
        component_proxy = cmd_info['component_proxy']
        status_method = cmd_info['status_method_name']
        status_path = cmd_info['status_path']
        
        # Create an event for this state path
        update_event = asyncio.Event()
        self.state_update_events[status_path] = update_event
        
        # Add listener to ESPHome component if it supports events
        if hasattr(component_proxy, 'add_state_change_listener'):
            async def on_state_change(state_type: str, value: Any):
                # Signal immediate polling when any state changes
                update_event.set()
            
            component_proxy.add_state_change_listener(on_state_change)
            logging.info(f"Added event trigger for ESPHome polling: {status_path}")
        
        # Special handling for ESPHome heartbeat
        if status_method == 'heartbeat_status':
            poll_interval = 15  # 15 seconds for heartbeat
        else:
            poll_interval = self.config.get('config', {}).get('poll_intervals', {}).get(
                status_method, 10  # Default 10 seconds
            )
        
        try:
            while self.running:
                try:
                    # For heartbeat, we need to call the command first
                    if status_method == 'heartbeat_status' and hasattr(component_proxy, 'heartbeat'):
                        await component_proxy.heartbeat()
                        await asyncio.sleep(0.5)
                    
                    # Get status
                    if hasattr(component_proxy, f'get_{status_method}'):
                        status_getter = getattr(component_proxy, f'get_{status_method}')
                        value = await status_getter()
                    else:
                        value = await component_proxy.get_status(status_method)
                    
                    if value != self._external_states.get(status_path):
                        self._set_nested_value(status_path, value)
                        self._external_states[status_path] = value
                        await self._queue_state_update()
                        logging.debug(f"ESPHome state update: {status_path} = {value}")
                    
                except Exception as e:
                    logging.error(f"Error polling ESPHome state {status_path}: {e}")
                
                # Wait for either the timeout OR an event trigger
                try:
                    await asyncio.wait_for(update_event.wait(), timeout=poll_interval)
                    # If we get here, event was triggered - clear it and poll immediately
                    update_event.clear()
                    logging.debug(f"Event-triggered poll for {status_path}")
                except asyncio.TimeoutError:
                    # Normal timeout - continue to next poll cycle
                    pass
                
        except asyncio.CancelledError:
            # Clean up
            if hasattr(component_proxy, 'remove_state_change_listener') and 'on_state_change' in locals():
                component_proxy.remove_state_change_listener(on_state_change)
            
            # Clean up event
            if status_path in self.state_update_events:
                del self.state_update_events[status_path]
    
    async def trigger_state_refresh(self, status_path: str):
        """Manually trigger immediate state refresh for a specific path"""
        if status_path in self.state_update_events:
            self.state_update_events[status_path].set()
            logging.debug(f"Triggered immediate refresh for {status_path}")

    async def _monitor_heartbeat(self, heartbeat_info: Dict[str, Any]):
        """Monitor heartbeat responses from devices"""
        if heartbeat_info['type'] == 'mqtt':
            # MQTT heartbeat monitoring at device_prefix level
            mqtt_manager = heartbeat_info['mqtt_manager']
            status_path = heartbeat_info['status_path']
            device_prefix = heartbeat_info['device_prefix']
            
            # Subscribe to heartbeat responses
            def heartbeat_callback(payload):
                # Update state
                self._set_nested_value(status_path, payload)
                self._external_states[status_path] = payload
                
                # Queue update
                asyncio.create_task(self._queue_state_update())
                
                logging.debug(f"MQTT Heartbeat update: {status_path} = {payload}")
            
            mqtt_manager.add_heartbeat_callback(heartbeat_callback)
            
            # Keep task alive
            try:
                while self.running:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                # Remove callback on cancellation
                mqtt_manager.remove_heartbeat_callback(heartbeat_callback)
        
        elif heartbeat_info['type'] == 'esphome':
            # ESPHome heartbeat monitoring via polling
            component_proxy = heartbeat_info['component_proxy']
            status_path = heartbeat_info['status_path']
            poll_interval = 30  # Poll ESPHome heartbeat every 30 seconds
            
            try:
                while self.running:
                    try:
                        # Send heartbeat command
                        if hasattr(component_proxy, 'heartbeat'):
                            await component_proxy.heartbeat()
                            # Wait a bit for response
                            await asyncio.sleep(0.5)
                        
                        # Get heartbeat status
                        value = await component_proxy.get_status('heartbeat_status')
                        
                        if value != self._external_states.get(status_path):
                            # Update state
                            self._set_nested_value(status_path, value)
                            self._external_states[status_path] = value
                            
                            # Queue update
                            await self._queue_state_update()
                            
                            logging.debug(f"ESPHome Heartbeat update: {status_path} = {value}")
                        
                    except Exception as e:
                        logging.error(f"Error polling ESPHome heartbeat {status_path}: {e}")
                    
                    await asyncio.sleep(poll_interval)
                    
            except asyncio.CancelledError:
                pass
    
    async def _periodic_heartbeat_refresh(self):
        """Periodically send heartbeat requests"""
        heartbeat_interval = self.config.get('config', {}).get('heartbeat_refresh_interval', 30)
        
        try:
            while self.running:
                await asyncio.sleep(heartbeat_interval)
                
                # Send heartbeat to all MQTT managers (device_prefix level)
                for heartbeat_info in self.heartbeat_definitions:
                    try:
                        if heartbeat_info['type'] == 'mqtt':
                            mqtt_manager = heartbeat_info['mqtt_manager']
                            await mqtt_manager.send_heartbeat()
                            logging.debug(f"Sent heartbeat request for prefix: {heartbeat_info['device_prefix']}")
                        
                        # ESPHome heartbeats are handled in their individual monitoring tasks
                        
                    except Exception as e:
                        logging.error(f"Error sending heartbeat: {e}")
            
        except asyncio.CancelledError:
            pass
    
    async def _periodic_refresh(self):
        """Periodically send data commands to ensure states are fresh"""
        refresh_interval = self.config.get('config', {}).get('refresh_interval', 30)
        
        try:
            while self.running:
                await asyncio.sleep(refresh_interval)
                
                # Send data commands for MQTT components
                for cmd_info in self.data_commands:
                    if cmd_info['type'] == 'mqtt':
                        try:
                            component_proxy = cmd_info['component_proxy']
                            command_method = getattr(component_proxy, cmd_info['command_method_name'])
                            await command_method()
                            logging.debug(f"Sent refresh command: {cmd_info['component_path']}.{cmd_info['command_method_name']}")
                        except Exception as e:
                            logging.error(f"Error sending refresh command: {e}")
                
        except asyncio.CancelledError:
            pass
    
    def _needs_periodic_refresh(self, cmd_info: dict) -> bool:
        """
        Determine if a command needs periodic refresh.
        Override this method to customize which devices need polling.
        """
        # ESPHome components benefit from periodic refresh since they don't have event-driven updates
        if cmd_info.get('type') == 'esphome':
            return True
        
        # Example: refresh temperature sensors every cycle
        if 'temp' in cmd_info.get('status_path', '').lower():
            return True
        
        # Example: refresh critical status indicators
        if 'heartbeat' in cmd_info.get('status_path', '').lower():
            return True
            
        # Most other MQTT devices rely on event-driven updates
        return False
    
    async def refresh_all_states(self):
        """Manually refresh all states"""
        logging.info("Refreshing all states...")
        
        # Send all data commands
        for cmd_info in self.data_commands:
            try:
                if cmd_info['type'] == 'mqtt':
                    # Send MQTT data command
                    component_proxy = cmd_info['component_proxy']
                    command_method = getattr(component_proxy, cmd_info['command_method_name'])
                    await command_method()
                    logging.debug(f"Sent data command: {cmd_info['component_path']}.{cmd_info['command_method_name']}")
                    
                elif cmd_info['type'] == 'esphome':
                    # Get ESPHome status directly
                    component_proxy = cmd_info['component_proxy']
                    status_method = cmd_info['status_method_name']
                    
                    if hasattr(component_proxy, f'get_{status_method}'):
                        status_getter = getattr(component_proxy, f'get_{status_method}')
                        value = await status_getter()
                    else:
                        value = await component_proxy.get_status(status_method)
                    
                    if value is not None:
                        self._set_nested_value(cmd_info['status_path'], value)
                        self._external_states[cmd_info['status_path']] = value
                    
            except Exception as e:
                logging.error(f"Error refreshing state {cmd_info['status_path']}: {e}")
        
        # Send heartbeat requests
        for heartbeat_info in self.heartbeat_definitions:
            try:
                if heartbeat_info['type'] == 'mqtt':
                    mqtt_manager = heartbeat_info['mqtt_manager']
                    await mqtt_manager.send_heartbeat()
                    logging.debug(f"Sent heartbeat for prefix: {heartbeat_info['device_prefix']}")
                # ESPHome heartbeats are handled by their monitoring tasks
            except Exception as e:
                logging.error(f"Error sending heartbeat: {e}")
        
        # Wait for MQTT responses
        if any(cmd['type'] == 'mqtt' for cmd in self.data_commands) or self.heartbeat_definitions:
            await asyncio.sleep(2)
            
            # Get cached values for MQTT states
            for cmd_info in self.data_commands:
                if cmd_info['type'] == 'mqtt':
                    component_proxy = cmd_info['component_proxy']
                    status_method = cmd_info['status_method_name']
                    value = component_proxy.get_latest_status(status_method)
                    
                    if value is not None:
                        self._set_nested_value(cmd_info['status_path'], value)
                        self._external_states[cmd_info['status_path']] = value
        
        # Queue update
        await self._queue_state_update()
        
        logging.info(f"State refresh complete: {len(self._external_states)} states")
    
    async def _queue_state_update(self):
        """Queue current state for websocket emission"""
        all_states = self.get_all_states()
        await self.state_queue.put(all_states)
    
    def get_all_states(self) -> Dict[str, Any]:
        """Get all current states"""
        return {
            **self._external_states,
            **self._internal_states
        }
    
    async def set_state(self, key: str, value: Any):
        """Set an internal state value"""
        self._internal_states[key] = value
        await self._queue_state_update()

    def get_state(self, key: str):
        """Get a state value (checks internal first, then external)"""
        # Check internal states first
        if key in self._internal_states:
            return self._internal_states[key]
        
        # Check external states
        if key in self._external_states:
            return self._external_states[key]
        
        # Not found in either
        logging.warning(f"State '{key}' not found in internal or external states")
        return None
    
    async def get_state_updates(self):
        """Async generator for state updates"""
        while True:
            try:
                new_state = await self.state_queue.get()
                yield new_state
            except asyncio.CancelledError:
                break


# Factory function
async def create_state_manager(controller, config: Dict[str, Any]):
    """Create and return a clean state manager"""
    return StateManager(controller, config)