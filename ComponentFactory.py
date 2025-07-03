import RPi.GPIO as GPIO
import yaml
import logging
from Button import Button
from TemperatureSensor import TemperatureSensor
from Relay import Relay
from Fan import Fan
from MultiTempSensor import MultiTempSensor
from MQTTManager import MQTTManager

class ComponentFactory:
    """Factory to create components"""
    
    component_types = {
        'Button': Button,
        'Relay': Relay,
        'Fan': Fan,
        'TemperatureSensor': TemperatureSensor,
        'MultiTempSensor': MultiTempSensor
    }
    
    @classmethod
    def create_component(cls, component_type, name=None, device_name=None, **kwargs):
        if component_type not in cls.component_types:
            raise ValueError(f"Unknown component type: {component_type}")
        
        component_class = cls.component_types[component_type]
        # Pass the exact component name from YAML
        return component_class(name=name, device_name=device_name, **kwargs)

class CompositeDevice:
    """A device made up of multiple components with defined behaviors"""
    
    def __init__(self, name, components_config):
        self.name = name
        self.components = {}
        
        # Create all components
        for comp_name, comp_config in components_config.items():
            comp_type = comp_config.pop('type')
            component = ComponentFactory.create_component(
                comp_type, name=comp_name, device_name=name, **comp_config
            )
            self.components[comp_name] = component
            
            # Add this component's methods to the device
            self._add_component_methods(comp_name, component)
    
    def _add_component_methods(self, comp_name, component):
        """Dynamically add component methods to device"""
        # Add methods like led_on, led_off, button_is_pressed, etc.
        for method_name in dir(component):
            if not method_name.startswith('_') and callable(getattr(component, method_name)):
                device_method_name = f"{comp_name}_{method_name}"
                setattr(self, device_method_name, getattr(component, method_name))
    
    def get_component(self, name):
        """Get component by name"""
        return self.components.get(name)
    
    def cleanup(self):
        """Clean up all components"""
        for component in self.components.values():
            component.cleanup()

class DeviceManager:
    """Manages all composite devices from YAML config"""
    
    def __init__(self, config_file):
        self.devices = {}
        self.mqtt_manager = None
        self.load_config(config_file)
    
    def load_config(self, config_file):
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
        
        # Initialize MQTT manager with config
        mqtt_config = config.get('mqtt', {})
        if mqtt_config:
            print("Initializing MQTT with config:", {k: v if k != 'password' else '***' for k, v in mqtt_config.items()})
            self.mqtt_manager = MQTTManager(mqtt_config)
        else:
            print("No MQTT config found, using defaults")
            self.mqtt_manager = MQTTManager()
        
        # Create devices
        devices_config = config.get('devices', {})
        for device_name, device_config in devices_config.items():
            try:
                device = CompositeDevice(
                    name=device_name,
                    components_config=device_config['components']
                )
                self.devices[device_name] = device
                logging.info(f"Created device '{device_name}' with MQTT topics")
            except Exception as e:
                logging.error(f"Failed to create device '{device_name}': {e}")
    
    def get_device(self, name):
        return self.devices.get(name)
    
    def list_mqtt_topics(self):
        """List all MQTT command topics for debugging"""
        print("\n=== MQTT Command Topics ===")
        for device_name, device in self.devices.items():
            for comp_name, component in device.components.items():
                if hasattr(component, 'command_topics'):
                    for method_name, topic in component.command_topics.items():
                        print(f"{device_name}.{comp_name}.{method_name}: {topic}")
    
    def cleanup_all(self):
        for device in self.devices.values():
            device.cleanup()
        self.devices.clear()
        
        if self.mqtt_manager:
            self.mqtt_manager.disconnect()