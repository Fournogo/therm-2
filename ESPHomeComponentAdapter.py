# ESPHomeComponentAdapter.py
from BaseComponent import BaseComponent
from ESPHomeACComponent import ESPHomeACComponent
from typing import List, Dict, Any, Optional, Callable
import asyncio
import logging
import time

class ESPHomeComponentAdapter(BaseComponent):
    """
    Adapter for ESPHome components that properly handles their direct API nature.
    This provides a clean integration without forcing MQTT patterns.
    """
    
    def __init__(self, name: str, device_name: str, **config):
        super().__init__(name, device_name, **config)
        
        # Create the ESPHome component
        esphome_config = {
            'host': config.get('host'),
            'port': config.get('port', 6053),
            'password': config.get('password'),
            'name': name,
            'device_name': device_name
        }
        self.esphome_component = ESPHomeACComponent(**esphome_config)
        
        # Track polling tasks
        self._polling_tasks = {}
        self._polling_intervals = {
            'temp_status': 10,      # Poll temperature every 10 seconds
            'mode_status': 5,       # Poll mode changes more frequently
            'preset_status': 5,     # Poll preset changes frequently
            'power_status': 30,     # Poll power less frequently
            'heartbeat_status': 30, # Poll heartbeat every 30 seconds
        }
        
        self._discover_methods()

        logging.info(f"ESPHome {device_name}.{name} discovered methods:")
        logging.info(f"  Command methods: {self.command_methods}")
        logging.info(f"  Status methods: {self.status_methods}")

        self._create_proxy_methods()
    
    async def initialize(self) -> bool:
        """Initialize the ESPHome connection"""
        success = await self.esphome_component.initialize()
        
        if success:
            # Start polling for status updates
            await self._start_polling()
            
        return success
    
    async def disconnect(self):
        """Disconnect from ESPHome device"""
        # Stop all polling tasks
        await self._stop_polling()
        
        # Disconnect the component
        await self.esphome_component.disconnect()
    
    def _discover_methods(self):
        """Discover available methods from ESPHomeACComponent"""
        self.command_methods = []
        self.status_methods = []
        self.data_commands = []
        
        for method_name in dir(ESPHomeACComponent):
            if method_name.startswith('_'):
                continue
                
            method = getattr(ESPHomeACComponent, method_name)
            if not callable(method):
                continue
            
            # Check for command decorator
            if hasattr(method, '_is_mqtt_command'):
                self.command_methods.append(method_name)
                logging.debug(f"Found command method: {method_name}")
            
            # Check for status decorator
            if hasattr(method, '_is_mqtt_status'):
                self.status_methods.append(method_name)
                logging.debug(f"Found status method: {method_name}")
    
    def _create_proxy_methods(self):
        """Create proxy methods for all ESPHome commands"""
        # Create proxy methods for all discovered command methods
        for method_name in self.command_methods:
            # Don't override existing methods
            if hasattr(self, method_name):
                continue
            
            # Create a closure to capture the method name
            def make_proxy_method(name):
                async def proxy_method(*args, **kwargs):
                    print(f"DEBUG: ESPHome proxy method '{name}' called with args={args}, kwargs={kwargs}")
                    print(f"DEBUG: Getting method '{name}' from component {type(self.esphome_component)}")
                    
                    method = getattr(self.esphome_component, name)
                    print(f"DEBUG: Got method: {method}, type: {type(method)}")
                    
                    if method is None:
                        raise AttributeError(f"ESPHome component method '{name}' returned None")
                    
                    print(f"DEBUG: About to call method {name}")
                    result = await method(*args, **kwargs)
                    print(f"DEBUG: Method {name} returned: {result}")
                    return result
                return proxy_method
            
            # Set the proxy method on this instance
            setattr(self, method_name, make_proxy_method(method_name))
            logging.debug(f"Created proxy method: {method_name}")
        
        # Also create proxy methods for status methods (keeping original non-async version)
        for method_name in self.status_methods:
            if hasattr(self, method_name):
                continue
                
            def make_status_proxy(name):
                def status_proxy(*args, **kwargs):
                    print(f"DEBUG: ESPHome status proxy '{name}' called with args={args}, kwargs={kwargs}")
                    method = getattr(self.esphome_component, name)
                    print(f"DEBUG: Got status method: {method}, type: {type(method)}")
                    
                    if method is None:
                        raise AttributeError(f"ESPHome component status method '{name}' returned None")
                    
                    result = method(*args, **kwargs)
                    print(f"DEBUG: Status method {name} returned: {result}")
                    return result
                return status_proxy
            
            setattr(self, method_name, make_status_proxy(method_name))
            logging.debug(f"Created status proxy method: {method_name}")
    
    def get_command_methods(self) -> List[str]:
        return self.command_methods
    
    def get_status_methods(self) -> List[str]:
        return self.status_methods
    
    def get_data_commands(self) -> List[Dict[str, Any]]:
        """Provide data commands for ESPHome components"""
        return [
            {
                'command': 'read_status',
                'status': 'temp_status',
                'events': ['temp_update']
            },
            {
                'command': 'read_status',
                'status': 'target_temp_status',
                'events': ['target_temp_update']
            },
            {
                'command': 'read_status',
                'status': 'mode_status',
                'events': ['mode_update']
            },
            {
                'command': 'read_status',
                'status': 'fan_mode_status',
                'events': ['fan_mode_update']
            },
            {
                'command': 'read_status',
                'status': 'preset_status',
                'events': ['preset_update']
            },
            {
                'command': 'heartbeat',
                'status': 'heartbeat_status',
                'events': ['heartbeat_update']
            }
        ]
    
    async def execute_command(self, command_name: str, **kwargs) -> Any:
        """Execute a command on the ESPHome component"""
        if hasattr(self, command_name):
            method = getattr(self, command_name)
            if asyncio.iscoroutinefunction(method):
                return await method(**kwargs)
            else:
                return method(**kwargs)
        else:
            raise AttributeError(f"ESPHome component has no command {command_name}")
    
    async def get_status(self, status_name: str) -> Any:
        """Get a status value from the ESPHome component"""
        if hasattr(self, status_name):
            method = getattr(self, status_name)
            
            # Call the status method
            result = method() if not asyncio.iscoroutinefunction(method) else await method()
            
            # Cache the result
            self._status_cache[status_name] = result
            
            return result
        else:
            # Return cached value if available
            if status_name in self._status_cache:
                return self._status_cache[status_name]
            
            raise AttributeError(f"ESPHome component has no status {status_name}")
    
    def supports_event_updates(self) -> bool:
        """ESPHome uses polling, not events"""
        return False
    
    def requires_polling(self) -> bool:
        """ESPHome requires periodic polling for updates"""
        return True
    
    async def _start_polling(self):
        """Start polling tasks for status updates"""
        # Poll all status methods that have intervals defined
        for status_method in self.status_methods:
            interval = self._polling_intervals.get(status_method, 10)  # Default 10 seconds
            task = asyncio.create_task(self._poll_status(status_method, interval))
            self._polling_tasks[status_method] = task
            logging.info(f"Started polling {status_method} every {interval}s")
    
    async def _stop_polling(self):
        """Stop all polling tasks"""
        for task in self._polling_tasks.values():
            task.cancel()
        
        # Wait for all tasks to complete
        if self._polling_tasks:
            await asyncio.gather(*self._polling_tasks.values(), return_exceptions=True)
        
        self._polling_tasks.clear()
    
    async def _poll_status(self, status_name: str, interval: float):
        """Poll a specific status method periodically"""
        while True:
            try:
                # Special handling for heartbeat
                if status_name == 'heartbeat_status':
                    # First send heartbeat command
                    if hasattr(self, 'heartbeat'):
                        await self.heartbeat()
                        await asyncio.sleep(0.5)  # Wait for response
                
                # Get the current status
                old_value = self._status_cache.get(status_name)
                new_value = await self.get_status(status_name)
                
                # If value changed, emit update
                if new_value != old_value:
                    self._emit_status_update(status_name, new_value)
                    logging.debug(f"ESPHome {self.device_name}.{self.name} {status_name} updated: {new_value}")
                
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error polling {status_name}: {e}")
                await asyncio.sleep(interval)
    
    async def execute_and_wait_for_status(self, command_name: str, status_name: str, timeout: float = 10) -> Any:
        """
        Execute a command and immediately get the status.
        For ESPHome, we can often get the status directly without waiting.
        """
        # Execute the command
        await self.execute_command(command_name)
        
        # For ESPHome, we can immediately query the status
        # Add a small delay to ensure the device has processed the command
        await asyncio.sleep(0.5)
        
        # Get the status
        return await self.get_status(status_name)