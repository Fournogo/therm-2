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
    using event-driven updates instead of polling.
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
        self.external_state_definitions = controller.list_data_commands()
        self.running = False
        self.refresh_task = None
        self.event_listeners = {}  # Track active event listeners
        self._initialized = True
        
        # Create nested attribute structure
        self._create_nested_attributes()
        
    @classmethod
    async def get_instance(cls, controller=None, config=None):
        """
        Get the singleton instance. If it doesn't exist, create it with the provided parameters.
        """
        async with cls._lock:
            if cls._instance is None:
                instance = cls(controller, config)
                await instance._setup_event_listeners()
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
        
    def _create_nested_attributes(self):
        """Create nested attribute structure to mirror controller"""
        for method_info in self.external_state_definitions:
            # Create nested attributes: self.hvac.temp_sensor.temp_status
            self._create_nested_path(method_info['status_path'])
    
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
        Setup event-driven listeners for all status methods.
        This replaces the need for constant polling.
        """
        print("Setting up event-driven state listeners...")
        
        for cmd_info in self.external_state_definitions:
            status_method_name = cmd_info['status_method_name']
            component_path = cmd_info['component_path']
            status_path = cmd_info['status_path']
            
            if not status_method_name:
                continue
                
            try:
                # Get the component proxy
                parts = component_path.split('.')
                component_proxy = self.controller
                for part in parts:
                    component_proxy = getattr(component_proxy, part)
                
                # Create a callback for this specific status update
                def make_status_callback(status_path_local, component_path_local):
                    async def status_callback(status_data):
                        if status_data is not None:
                            print(f"Event-driven update: {status_path_local} = {status_data}")
                            # Update nested attributes
                            self._set_nested_value(status_path_local, status_data)
                            # Update external states dictionary
                            new_states = {**self._external_states}
                            new_states[status_path_local] = status_data
                            self.external_states = new_states
                        else:
                            print(f"No data received for {status_path_local}")
                    return status_callback
                
                callback = make_status_callback(status_path, component_path)
                
                # Start continuous monitoring for this status method
                wait_id = component_proxy.wait_for_continuous(
                    status_method_name, 
                    callback
                )
                
                # Track the listener for cleanup
                self.event_listeners[status_path] = {
                    'component_proxy': component_proxy,
                    'wait_id': wait_id,
                    'status_method': status_method_name
                }
                
                print(f"Started event listener for {status_path}")
                
            except Exception as e:
                print(f"Error setting up listener for {status_path}: {e}")

    async def refresh_all_data(self):
        """
        Manually refresh all data by sending commands and waiting for responses.
        This is now used for initial state loading and manual refreshes only.
        """
        print("Manual refresh: requesting all device states...")
        new_external_states = {}
        
        # Group commands by device to send them concurrently per device
        device_commands = defaultdict(list)
        
        for cmd_info in self.external_state_definitions:
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
        
        # Update external states (this will trigger queue update if changed)
        if new_external_states:
            self.external_states = new_external_states
            print(f"Manual refresh completed: {len(new_external_states)} states updated")
    
    async def _refresh_device_data(self, device_name: str, commands: list, new_external_states: dict):
        """Refresh data for a specific device"""
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
        This runs much less frequently than the old polling approach.
        """
        while self.running:
            try:
                print("Periodic refresh check...")
                # Only refresh devices that haven't been updated recently
                await self._refresh_stale_data()
            except Exception as e:
                print(f"Error during periodic refresh: {e}")
            
            # Sleep for the refresh interval
            await asyncio.sleep(self.refresh_interval)
    
    async def _refresh_stale_data(self):
        """
        Refresh data that hasn't been updated recently.
        This is a fallback for devices that don't auto-publish.
        """
        current_time = time.time()
        stale_threshold = getattr(self, 'stale_threshold', 30)  # 30 seconds default
        
        stale_commands = []
        
        for cmd_info in self.external_state_definitions:
            status_path = cmd_info['status_path']
            
            # Check if this status path has been updated recently
            # You could track last_updated timestamps here
            # For now, we'll just do a lighter refresh cycle
            
            # Only refresh critical sensors or those marked as needing periodic refresh
            if self._needs_periodic_refresh(cmd_info):
                stale_commands.append(cmd_info)
        
        if stale_commands:
            print(f"Refreshing {len(stale_commands)} stale data points...")
            new_states = {}
            await self._refresh_device_data("periodic", stale_commands, new_states)
            
            if new_states:
                current_states = {**self._external_states}
                current_states.update(new_states)
                self.external_states = current_states
    
    def _needs_periodic_refresh(self, cmd_info: dict) -> bool:
        """
        Determine if a command needs periodic refresh.
        Override this method to customize which devices need polling.
        """
        # Example: refresh temperature sensors every cycle
        if 'temp' in cmd_info['status_path'].lower():
            return True
        
        # Example: refresh critical status indicators
        if 'heartbeat' in cmd_info['status_path'].lower():
            return True
            
        # Most other devices rely on event-driven updates
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
        
        # Start periodic refresh for devices that need it (much less frequent)
        if hasattr(self, 'refresh_interval') and self.refresh_interval > 0:
            self.refresh_task = asyncio.create_task(self._periodic_refresh_loop())
            print(f"Started periodic refresh task (interval: {self.refresh_interval}s)")
        
        print("Event-driven state management started")
    
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
        
        # Stop all event listeners
        print("Stopping event listeners...")
        for status_path, listener_info in self.event_listeners.items():
            try:
                component_proxy = listener_info['component_proxy']
                wait_id = listener_info['wait_id']
                await component_proxy.stop_continuous_wait(wait_id)
                print(f"Stopped listener for {status_path}")
            except Exception as e:
                print(f"Error stopping listener for {status_path}: {e}")
        
        self.event_listeners.clear()
        self.refresh_task = None
        print("State management stopped")
    
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
    """Example usage"""
    from ConfigLoader import create_device_controller
    
    controller = await create_device_controller(
        "/home/scrumpi/containers/therm-2/configs", 
        "/home/scrumpi/containers/therm-2"
    )
    
    config = {
        "internal_state": {"control": "MANUAL"},
        "config": {"refresh_interval": 30}  # Much longer interval now
    }
    
    # Create state manager
    state_manager = await create_async_state_manager(controller, config)
    
    # Start event-driven monitoring
    await state_manager.start_continuous_refresh()
    
    print("State manager running. Current states:")
    print(state_manager.get_all_states())
    
    # Monitor state changes
    async def monitor_changes():
        async for new_state in state_manager.get_state_updates():
            print(f"State update received: {len(new_state)} states")
    
    # Run for a while
    monitor_task = asyncio.create_task(monitor_changes())
    await asyncio.sleep(60)  # Run for 1 minute
    
    # Cleanup
    monitor_task.cancel()
    await state_manager.stop_continuous_refresh()
    await controller.disconnect_all()

if __name__ == "__main__":
    asyncio.run(main())