from abc import ABC, abstractmethod
from MQTTManager import MQTTManager
import logging

def command(func):
    """Decorator to automatically register a method as an MQTT command"""
    func._is_mqtt_command = True
    return func

def status(auto_publish=False, trigger_on=None):
    """Decorator for status methods that server should monitor
    
    Args:
        auto_publish: If True, method will be auto-published on trigger events
        trigger_on: List of events that should trigger this status publish
    """
    def decorator(func):
        func._is_mqtt_status = True
        func._auto_publish = auto_publish
        func._trigger_events = trigger_on or []
        return func
    return decorator

class Component(ABC):
    def __init__(self, name=None, device_name=None):
        self.name = name  # This is the component name from YAML
        self.device_name = device_name
        self.callbacks = {}
        self.command_topics = {}

        # MQTT integration
        self.mqtt_manager = None

        if device_name and name:
            self._setup_mqtt()
    
    def _setup_mqtt(self):
        """Setup MQTT topics for this component"""
        try:
            self.mqtt_manager = MQTTManager()
            self._register_command_methods()
            self._register_status_methods()
        except Exception as e:
            logging.error(f"Failed to setup MQTT for {self.device_name}.{self.name}: {e}")
    
    def _register_command_methods(self):
        """Find all methods decorated with @command and register them"""
        for method_name in dir(self):
            method = getattr(self, method_name)
            if callable(method) and hasattr(method, '_is_mqtt_command'):
                topic = self.mqtt_manager.register_command(
                    self.device_name, 
                    self.name, 
                    method_name, 
                    method
                )
                self.command_topics[method_name] = topic
                print(f"Registered command: {method_name} -> {topic}")

    def _register_status_methods(self):
        """Register status methods that server should monitor"""
        self.status_topics = {}
        self.auto_publish_status = {}  # Track which status methods to auto-publish
        
        for method_name in dir(self):
            method = getattr(self, method_name)
            if callable(method) and hasattr(method, '_is_mqtt_status'):
                status_topic = f"{self.mqtt_manager.device_prefix}/{self.device_name}/{self.name}/status/{method_name}"
                self.status_topics[method_name] = status_topic
                
                # Check if this should be auto-published
                if hasattr(method, '_auto_publish') and method._auto_publish:
                    self.auto_publish_status[method_name] = method
                
                print(f"Registered status: {method_name} -> {status_topic}")

    def publish_status(self, status_method_name):
        """Publish status from a decorated method"""
        if hasattr(self, 'status_topics') and status_method_name in self.status_topics:
            method = getattr(self, status_method_name)
            status_data = method()
            topic = self.status_topics[status_method_name]
            self.mqtt_manager.publish(topic, status_data)
            print(f"Published status: {topic} -> {status_data}")

    def auto_publish_on_event(self, event_name):
        """Auto-publish any status methods that should be triggered by this event"""
        if hasattr(self, 'auto_publish_status'):
            for method_name, method in self.auto_publish_status.items():
                # Check if this method should be triggered by this event
                if hasattr(method, '_trigger_events'):
                    if event_name in method._trigger_events:
                        self.publish_status(method_name)

    def trigger_event(self, event, *args, **kwargs):
        """Trigger all callbacks for an event"""
        if event in self.callbacks:
            for callback in self.callbacks[event]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logging.error(f"Error in callback for {event}: {e}")