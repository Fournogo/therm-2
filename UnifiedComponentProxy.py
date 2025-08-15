# UnifiedComponentProxy.py
from BaseComponent import BaseComponent
from typing import Dict, Any, Optional, Callable, List
import asyncio
import logging
import uuid

class UnifiedComponentProxy:
    """
    Unified proxy that provides consistent interface for both MQTT and ESPHome components.
    This replaces the separate AsyncComponentProxy and ESPHomeComponentProxy.
    """
    
    def __init__(self, device_name: str, component_name: str, base_component: BaseComponent):
        self.device_name = device_name
        self.component_name = component_name
        self.base_component = base_component
        
        # Event management for async waiting
        self.status_events: Dict[str, asyncio.Event] = {}
        self.status_queues: Dict[str, asyncio.Queue] = {}
        self.continuous_listeners: Dict[str, asyncio.Task] = {}
        
        # Create proxy methods
        self._create_proxy_methods()
        self._setup_status_monitoring()
    
    async def initialize(self) -> bool:
        """Initialize the underlying component"""
        return await self.base_component.initialize()
    
    async def disconnect(self):
        """Disconnect and cleanup"""
        # Stop all continuous listeners
        await self.stop_all_continuous_waits()
        
        # Disconnect the component
        await self.base_component.disconnect()
    
    def _create_proxy_methods(self):
        """Create proxy methods for all commands"""
        for command_name in self.base_component.get_command_methods():
            # Create a closure to capture the command name
            def make_method(cmd_name):
                async def proxy_method(**kwargs):
                    return await self.base_component.execute_command(cmd_name, **kwargs)
                return proxy_method
            
            # Add the method to this instance
            setattr(self, command_name, make_method(command_name))
        
        # Also create methods for status getters
        for status_name in self.base_component.get_status_methods():
            # Create async event and queue for this status
            self.status_events[status_name] = asyncio.Event()
            self.status_queues[status_name] = asyncio.Queue(maxsize=100)
            
            # Create getter method
            def make_status_getter(status):
                async def get_status():
                    return await self.base_component.get_status(status)
                return get_status
            
            # Add getter method (optional - for direct access)
            setattr(self, f"get_{status_name}", make_status_getter(status_name))
    
    def _setup_status_monitoring(self):
        """Setup monitoring for status updates"""
        if self.base_component.supports_event_updates():
            # For event-driven components (MQTT), subscribe to updates
            for status_name in self.base_component.get_status_methods():
                self.base_component.subscribe_to_status(
                    status_name,
                    lambda value, s=status_name: self._handle_status_update(s, value)
                )
        
        # Note: Polling is handled by the adapter itself for ESPHome components
    
    def _handle_status_update(self, status_name: str, value: Any):
        """Handle incoming status updates"""
        # Update queues and events
        if status_name in self.status_events:
            # Set the event
            self.status_events[status_name].set()
            
            # Add to queue
            try:
                self.status_queues[status_name].put_nowait(value)
            except asyncio.QueueFull:
                # Remove oldest and add new
                try:
                    self.status_queues[status_name].get_nowait()
                    self.status_queues[status_name].put_nowait(value)
                except:
                    pass
    
    async def execute_and_wait_for_status(self, command_name: str, status_name: str, timeout: float = 10) -> Any:
        """Execute a command and wait for the associated status update"""
        if status_name not in self.status_events:
            raise ValueError(f"No status method '{status_name}' found")
        
        # Clear the event before executing
        self.status_events[status_name].clear()
        
        # Execute the command
        await self.base_component.execute_command(command_name)
        
        # For components that support direct status query (like ESPHome)
        if self.base_component.requires_polling():
            # Wait a bit for command to process
            await asyncio.sleep(0.5)
            # Get status directly
            return await self.base_component.get_status(status_name)
        
        # For event-driven components (MQTT), wait for the event
        try:
            await asyncio.wait_for(
                self.status_events[status_name].wait(),
                timeout=timeout
            )
            return self.base_component.get_cached_status(status_name)
        except asyncio.TimeoutError:
            return None
    
    async def wait_for_status(self, status_name: str, timeout: float = None) -> bool:
        """Wait for a status update event"""
        if status_name not in self.status_events:
            raise ValueError(f"No status method '{status_name}' found")
        
        self.status_events[status_name].clear()
        
        try:
            if timeout:
                await asyncio.wait_for(self.status_events[status_name].wait(), timeout=timeout)
            else:
                await self.status_events[status_name].wait()
            return True
        except asyncio.TimeoutError:
            return False
    
    def wait_for_continuous(self, status_name: str, callback: Callable, stop_condition: Callable = None) -> str:
        """Setup continuous monitoring of a status with callback"""
        if status_name not in self.status_queues:
            raise ValueError(f"No status method '{status_name}' found")
        
        wait_id = str(uuid.uuid4())
        
        async def continuous_monitor():
            queue = self.status_queues[status_name]
            
            while True:
                try:
                    # For polling components, manually check for updates
                    if self.base_component.requires_polling():
                        old_value = self.base_component.get_cached_status(status_name)
                        new_value = await self.base_component.get_status(status_name)
                        
                        if new_value != old_value:
                            self._handle_status_update(status_name, new_value)
                            
                            if asyncio.iscoroutinefunction(callback):
                                await callback(new_value)
                            else:
                                callback(new_value)
                        
                        await asyncio.sleep(5)  # Poll interval
                    else:
                        # For event-driven components, wait for queue updates
                        value = await asyncio.wait_for(queue.get(), timeout=1.0)
                        
                        if asyncio.iscoroutinefunction(callback):
                            await callback(value)
                        else:
                            callback(value)
                    
                    # Check stop condition
                    if stop_condition and stop_condition():
                        break
                        
                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logging.error(f"Error in continuous monitor: {e}")
                    await asyncio.sleep(1)
        
        # Start monitoring task
        task = asyncio.create_task(continuous_monitor())
        self.continuous_listeners[wait_id] = task
        
        return wait_id
    
    async def stop_continuous_wait(self, wait_id: str):
        """Stop a continuous wait by ID"""
        if wait_id in self.continuous_listeners:
            task = self.continuous_listeners[wait_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.continuous_listeners[wait_id]
    
    async def stop_all_continuous_waits(self):
        """Stop all continuous waits"""
        tasks = list(self.continuous_listeners.values())
        for task in tasks:
            task.cancel()
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.continuous_listeners.clear()
    
    def get_latest_status(self, status_name: str) -> Any:
        """Get the latest cached status value"""
        return self.base_component.get_cached_status(status_name)