# MQTTComponentAdapter.py
from BaseComponent import BaseComponent
from Component import Component, command, status
from typing import List, Dict, Any, Optional
import asyncio
import logging
import inspect

class MQTTComponentAdapter(BaseComponent):
    """
    Adapter that wraps existing MQTT components to work with the new interface.
    This allows us to keep using the existing MQTT components unchanged.
    """
    
    def __init__(self, wrapped_component: Component, name: str, device_name: str):
        # Don't pass config to BaseComponent since MQTT components don't need it
        super().__init__(name, device_name)
        self.wrapped_component = wrapped_component
        self._discover_methods()
        
    async def initialize(self) -> bool:
        """MQTT components are initialized during construction"""
        # MQTT components setup their connections in __init__
        return True
    
    async def disconnect(self):
        """Cleanup MQTT component"""
        if hasattr(self.wrapped_component, 'cleanup'):
            self.wrapped_component.cleanup()
    
    def _discover_methods(self):
        """Discover command and status methods from the wrapped component"""
        self.command_methods = []
        self.status_methods = []
        self.data_commands = []
        
        for method_name in dir(self.wrapped_component):
            if method_name.startswith('_'):
                continue
                
            method = getattr(self.wrapped_component, method_name)
            if not callable(method):
                continue
            
            # Check for command decorator
            if hasattr(method, '_is_mqtt_command'):
                self.command_methods.append(method_name)
                
                # Check if it's a data command
                if hasattr(method, '_is_data_command') and method._is_data_command:
                    events = getattr(method, '_events', [])
                    
                    # Find associated status methods for each event
                    for event in events:
                        status_method = self._find_status_method_for_event(event)
                        if status_method:
                            self.data_commands.append({
                                'command': method_name,
                                'status': status_method,
                                'events': [event]
                            })
            
            # Check for status decorator
            if hasattr(method, '_is_mqtt_status'):
                self.status_methods.append(method_name)
    
    def _find_status_method_for_event(self, event_name: str) -> Optional[str]:
        """Find the status method that triggers on a given event"""
        for method_name in dir(self.wrapped_component):
            method = getattr(self.wrapped_component, method_name)
            if callable(method) and hasattr(method, '_is_mqtt_status'):
                trigger_events = getattr(method, '_trigger_events', [])
                if event_name in trigger_events:
                    return method_name
        return None
    
    def get_command_methods(self) -> List[str]:
        return self.command_methods
    
    def get_status_methods(self) -> List[str]:
        return self.status_methods
    
    def get_data_commands(self) -> List[Dict[str, Any]]:
        return self.data_commands
    
    async def execute_command(self, command_name: str, **kwargs) -> Any:
        """Execute a command on the wrapped component"""
        if hasattr(self.wrapped_component, command_name):
            method = getattr(self.wrapped_component, command_name)
            
            # Handle async vs sync methods
            if asyncio.iscoroutinefunction(method):
                return await method(**kwargs)
            else:
                # Convert sync method to async
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, method, **kwargs)
        else:
            raise AttributeError(f"Component {self.name} has no command {command_name}")
    
    async def get_status(self, status_name: str) -> Any:
        """Get a status value from the wrapped component"""
        # First check if we have a cached value from MQTT
        cached_value = self.get_cached_status(status_name)
        if cached_value is not None:
            return cached_value
            
        # Otherwise try to get it directly from the component
        if hasattr(self.wrapped_component, status_name):
            method = getattr(self.wrapped_component, status_name)
            
            # Handle async vs sync methods
            if asyncio.iscoroutinefunction(method):
                result = await method()
            else:
                # Convert sync method to async
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, method)
            
            # Cache the result
            self._status_cache[status_name] = result
            return result
        else:
            raise AttributeError(f"Component {self.name} has no status {status_name}")
    
    def supports_event_updates(self) -> bool:
        """MQTT components support event-driven updates through pub/sub"""
        return True
    
    def requires_polling(self) -> bool:
        """MQTT components don't require polling - they use pub/sub"""
        return False
    
    def trigger_event(self, event_name: str, *args, **kwargs):
        """Pass through event triggers to the wrapped component"""
        if hasattr(self.wrapped_component, 'trigger_event'):
            self.wrapped_component.trigger_event(event_name, *args, **kwargs)
    
    def auto_publish_on_event(self, event_name: str):
        """Pass through auto-publish to the wrapped component"""
        if hasattr(self.wrapped_component, 'auto_publish_on_event'):
            self.wrapped_component.auto_publish_on_event(event_name)