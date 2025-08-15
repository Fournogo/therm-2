import asyncio
import logging
import importlib
import inspect
from typing import Dict, Any, List, Optional, Callable
import uuid

class MQTTComponentProxy:
    """
    Proxy for a single MQTT component that forwards commands via MQTT
    and handles status updates.
    """
    
    def __init__(self, device_name: str, component_name: str, component_type: str, mqtt_manager):
        self.device_name = device_name
        self.component_name = component_name
        self.component_type = component_type
        self.mqtt_manager = mqtt_manager
        
        # Status tracking
        self._status_cache = {}
        self._status_events = {}
        self._status_callbacks = {}
        
        # Discover methods from the component class
        self._discover_methods()
        
        # Create proxy methods
        self._create_proxy_methods()
        
        # Setup status subscriptions
        self._setup_status_subscriptions()
    
    def _discover_methods(self):
        """Discover methods by inspecting the component class"""
        self.command_methods = []
        self.status_methods = []
        self.data_commands = {}
        
        try:
            # Import the component module for inspection only
            module = importlib.import_module(self.component_type)
            component_class = getattr(module, self.component_type)
            
            # Find all decorated methods
            for method_name in dir(component_class):
                if method_name.startswith('_'):
                    continue
                
                try:
                    method = getattr(component_class, method_name)
                    if not callable(method):
                        continue
                    
                    # Check for command decorator
                    if hasattr(method, '_is_mqtt_command'):
                        self.command_methods.append(method_name)
                        
                        # Check if it's a data command
                        if getattr(method, '_is_data_command', False):
                            events = getattr(method, '_events', [])
                            for event in events:
                                # Find the status method for this event
                                status_method = self._find_status_method_for_event(component_class, event)
                                if status_method:
                                    self.data_commands[method_name] = {
                                        'events': events,
                                        'status_method': status_method
                                    }
                    
                    # Check for status decorator
                    if hasattr(method, '_is_mqtt_status'):
                        self.status_methods.append(method_name)
                        
                except Exception as e:
                    logging.debug(f"Error inspecting method {method_name}: {e}")
            
            logging.info(f"Discovered {len(self.command_methods)} commands and {len(self.status_methods)} status methods for {component_class.__name__}")
            
        except Exception as e:
            logging.error(f"Error discovering methods for {self.component_type}: {e}")
    
    def _find_status_method_for_event(self, component_class, event_name: str) -> Optional[str]:
        """Find the status method that triggers on a given event"""
        for method_name in dir(component_class):
            try:
                method = getattr(component_class, method_name)
                if callable(method) and hasattr(method, '_is_mqtt_status'):
                    trigger_events = getattr(method, '_trigger_events', [])
                    if event_name in trigger_events:
                        return method_name
            except:
                pass
        return None
    
    def _create_proxy_methods(self):
        """Create proxy methods that forward commands via MQTT"""
        for method_name in self.command_methods:
            # Create a closure to capture the method name
            def make_proxy_method(name):
                async def proxy_method(**kwargs):
                    return await self.mqtt_manager.publish_command(
                        self.device_name,
                        self.component_name,
                        name,
                        kwargs if kwargs else None
                    )
                return proxy_method
            
            # Add the proxy method to this instance
            setattr(self, method_name, make_proxy_method(method_name))
    
    def _setup_status_subscriptions(self):
        """Setup MQTT subscriptions for all status methods"""
        for status_method in self.status_methods:
            # Create event for this status
            self._status_events[status_method] = asyncio.Event()
            
            # Subscribe to status updates
            def make_status_callback(method_name):
                def callback(payload):
                    self._handle_status_update(method_name, payload)
                return callback
            
            self.mqtt_manager.subscribe_to_status(
                self.device_name,
                self.component_name,
                status_method,
                make_status_callback(status_method)
            )
    
    def _handle_status_update(self, status_method: str, payload: Any):
        """Handle incoming status update"""
        # Cache the status
        self._status_cache[status_method] = payload
        
        # Set the event
        if status_method in self._status_events:
            self._status_events[status_method].set()
        
        # Call any registered callbacks
        if status_method in self._status_callbacks:
            for callback in self._status_callbacks[status_method]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(payload))
                    else:
                        callback(payload)
                except Exception as e:
                    logging.error(f"Error in status callback: {e}")
    
    async def execute_and_wait_for_status(self, command_name: str, status_name: str, timeout: float = 10) -> Any:
        """Execute a command and wait for the associated status update"""
        if status_name not in self._status_events:
            raise ValueError(f"Unknown status method: {status_name}")
        
        # Clear the event
        self._status_events[status_name].clear()
        
        # Execute the command
        command_method = getattr(self, command_name)
        await command_method()
        
        # Wait for status update
        try:
            await asyncio.wait_for(
                self._status_events[status_name].wait(),
                timeout=timeout
            )
            return self._status_cache.get(status_name)
        except asyncio.TimeoutError:
            logging.warning(f"Timeout waiting for {status_name} after {command_name}")
            return None
    
    def get_latest_status(self, status_name: str) -> Any:
        """Get the latest cached status value"""
        return self._status_cache.get(status_name)
    
    def subscribe_to_status_updates(self, status_name: str, callback: Callable):
        """Subscribe to continuous status updates"""
        if status_name not in self._status_callbacks:
            self._status_callbacks[status_name] = []
        self._status_callbacks[status_name].append(callback)
    
    async def wait_for_status(self, status_name: str, timeout: Optional[float] = None) -> bool:
        """Wait for a status update"""
        if status_name not in self._status_events:
            raise ValueError(f"Unknown status method: {status_name}")
        
        self._status_events[status_name].clear()
        
        try:
            if timeout:
                await asyncio.wait_for(self._status_events[status_name].wait(), timeout)
            else:
                await self._status_events[status_name].wait()
            return True
        except asyncio.TimeoutError:
            return False


class MQTTDeviceProxy:
    """
    Proxy for a complete device containing multiple components.
    This represents the abstract device from the config (e.g., 'hvac').
    """
    
    def __init__(self, device_name: str, components_config: Dict[str, Any], mqtt_manager):
        self.device_name = device_name
        self.components_config = components_config
        self.mqtt_manager = mqtt_manager
        self.components = {}
        
        # Create component proxies
        self._create_components()
    
    def _create_components(self):
        """Create proxy objects for each component"""
        for component_name, component_config in self.components_config.items():
            component_type = component_config.get('type')
            
            if not component_type:
                logging.warning(f"No type specified for {self.device_name}.{component_name}")
                continue
            
            # Create component proxy
            component_proxy = MQTTComponentProxy(
                device_name=self.device_name,
                component_name=component_name,
                component_type=component_type,
                mqtt_manager=self.mqtt_manager
            )
            
            self.components[component_name] = component_proxy
            
            # Add as attribute for easy access
            setattr(self, component_name, component_proxy)
            
            logging.info(f"Created component proxy: {self.device_name}.{component_name} ({component_type})")