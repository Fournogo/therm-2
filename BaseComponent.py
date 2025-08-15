# BaseComponent.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, List
import asyncio
import logging

class BaseComponent(ABC):
    """
    Abstract base class that defines the common interface for all components.
    This allows MQTT and ESPHome components to be used interchangeably.
    """
    
    def __init__(self, name: str, device_name: str, **config):
        self.name = name
        self.device_name = device_name
        self.config = config
        self.callbacks = {}
        self._status_cache = {}
        self._status_update_callbacks = {}
        
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the component connection"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from the component"""
        pass
    
    @abstractmethod
    def get_command_methods(self) -> List[str]:
        """Return list of available command methods"""
        pass
    
    @abstractmethod
    def get_status_methods(self) -> List[str]:
        """Return list of available status methods"""
        pass
    
    @abstractmethod
    def get_data_commands(self) -> List[Dict[str, Any]]:
        """
        Return list of data commands with their associated status methods.
        Format: [{'command': 'read_temp', 'status': 'temp_status', 'events': ['temp_update']}]
        """
        pass
    
    async def execute_command(self, command_name: str, **kwargs) -> Any:
        """Execute a command on the component"""
        if hasattr(self, command_name):
            method = getattr(self, command_name)
            if asyncio.iscoroutinefunction(method):
                return await method(**kwargs)
            else:
                return method(**kwargs)
        else:
            raise AttributeError(f"Component {self.name} has no command {command_name}")
    
    async def get_status(self, status_name: str) -> Any:
        """Get a status value from the component"""
        if hasattr(self, status_name):
            method = getattr(self, status_name)
            if asyncio.iscoroutinefunction(method):
                return await method()
            else:
                return method()
        else:
            raise AttributeError(f"Component {self.name} has no status {status_name}")
    
    def subscribe_to_status(self, status_name: str, callback: Callable):
        """Subscribe to status updates (for event-driven components)"""
        if status_name not in self._status_update_callbacks:
            self._status_update_callbacks[status_name] = []
        self._status_update_callbacks[status_name].append(callback)
    
    def unsubscribe_from_status(self, status_name: str, callback: Callable):
        """Unsubscribe from status updates"""
        if status_name in self._status_update_callbacks:
            self._status_update_callbacks[status_name].remove(callback)
    
    def _emit_status_update(self, status_name: str, value: Any):
        """Emit a status update to all subscribers"""
        self._status_cache[status_name] = value
        if status_name in self._status_update_callbacks:
            for callback in self._status_update_callbacks[status_name]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(value))
                    else:
                        callback(value)
                except Exception as e:
                    logging.error(f"Error in status callback for {status_name}: {e}")
    
    def get_cached_status(self, status_name: str) -> Optional[Any]:
        """Get the last cached status value"""
        return self._status_cache.get(status_name)
    
    @abstractmethod
    def supports_event_updates(self) -> bool:
        """Return True if this component supports event-driven updates"""
        pass
    
    @abstractmethod
    def requires_polling(self) -> bool:
        """Return True if this component requires periodic polling"""
        pass