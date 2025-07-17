import yaml
import os
import glob
from ServerDeviceProxy import AsyncServerDeviceManager, ComponentInspector
import json
import asyncio

class AsyncConfigLoader:
    """Async version of ConfigLoader - loads multiple config files and creates device proxies"""
    
    def __init__(self, config_directory: str = "configs", component_path: str = "."):
        self.config_directory = config_directory
        self.device_managers = {}  # One per device_prefix
        self.all_devices = {}  # All devices accessible by name
        self._initialized = False
        
        # Add component path for imports
        ComponentInspector.add_component_path(component_path)
    
    async def initialize(self):
        """Initialize all device managers"""
        if self._initialized:
            return
        
        await self.load_all_configs()
        
        # Initialize all device managers
        for manager in self.device_managers.values():
            await manager.initialize()
        
        self._initialized = True
        print("AsyncConfigLoader initialized successfully")
    
    async def load_all_configs(self):
        """Load all YAML config files from the directory"""
        if not os.path.exists(self.config_directory):
            print(f"Config directory '{self.config_directory}' not found")
            return
        
        # Find all .yaml and .yml files
        config_files = glob.glob(os.path.join(self.config_directory, "*.yaml"))
        config_files.extend(glob.glob(os.path.join(self.config_directory, "*.yml")))
        
        print(f"Found {len(config_files)} config files")
        
        for config_file in config_files:
            try:
                await self.load_config_file(config_file)
            except Exception as e:
                print(f"Failed to load config file {config_file}: {e}")
    
    async def load_config_file(self, config_file: str):
        """Load a single config file"""
        print(f"Loading config: {config_file}")
        
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
        
        # Extract MQTT config
        mqtt_config = config.get('mqtt', {})
        device_prefix = mqtt_config.get('device_prefix', 'devices')
        
        # Create or get device manager for this prefix
        if device_prefix not in self.device_managers:
            # Add broker_host if not specified
            if 'broker_host' not in mqtt_config:
                mqtt_config['broker_host'] = 'localhost'
            
            self.device_managers[device_prefix] = AsyncServerDeviceManager(mqtt_config)
        
        # Load devices into the appropriate manager
        device_manager = self.device_managers[device_prefix]
        device_manager.load_device_config(config)
        
        # Add devices to global registry and as attributes
        for device_name, device_proxy in device_manager.devices.items():
            self.all_devices[device_name] = device_proxy
            # Add device as attribute to this loader for easy access
            setattr(self, device_name, device_proxy)
    
    def get_device(self, name: str):
        """Get any device by name regardless of prefix"""
        return self.all_devices.get(name)
    
    def list_all_devices(self):
        """List all devices from all config files"""
        print("\n=== All Loaded Devices ===")
        for prefix, manager in self.device_managers.items():
            print(f"\nDevice Prefix: {prefix}")
            manager.list_devices()
    
    async def disconnect_all(self):
        """Disconnect all MQTT connections"""
        tasks = []
        for manager in self.device_managers.values():
            tasks.append(manager.disconnect())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def list_data_commands(self):
        """
        Generate a list of all available data commands with their proxy methods
        
        Returns:
            List of data command info with proxy method references
        """
        commands = []
        
        # Iterate through all loaded devices
        for device_name, device_proxy in self.all_devices.items():
            # Get the device config to find component types
            device_config = self._get_device_config(device_name)
            if not device_config:
                continue
                
            components_config = device_config.get('components', {})
            
            for component_name, component_config in components_config.items():
                component_type = component_config.get('type')
                if not component_type:
                    continue
                    
                # Use ComponentInspector to discover methods
                data_methods = ComponentInspector.discover_data_methods(component_type)
                
                # Add data methods
                for data_method in data_methods:
                    command_method_name = data_method['command_method_name']
                    status_method_name = data_method['status_method_name']

                    # Get signatures from the component class
                    command_signature = self._get_method_signature(component_type, command_method_name)
                    status_signature = self._get_method_signature(component_type, status_method_name)

                    # Build the command/status strings
                    command_str = f"{device_name}.{component_name}.{command_method_name}{command_signature}"
                    status_str = f"{device_name}.{component_name}.{status_method_name}{status_signature}"
                    component_path = f"{device_name}.{component_name}"
                    status_path = f"{device_name}.{component_name}.{status_method_name}"

                    # Get the actual proxy methods from the loaded device
                    try:
                        # Get the component proxy from the device proxy
                        component_proxy = getattr(device_proxy, component_name)
                        
                        # Get the actual proxy methods
                        command_proxy_method = getattr(component_proxy, command_method_name)
                        
                        commands.append({
                            "command_str": command_str,
                            "status_str": status_str,
                            "command_method_name": command_method_name,
                            "command_method": command_proxy_method,  # Async proxy method
                            "status_method_name": status_method_name,
                            "status_path": status_path,
                            "component_path": component_path
                        })
                        
                    except AttributeError as e:
                        print(f"Warning: Could not get proxy methods for {device_name}.{component_name}: {e}")
                        continue
        
        return commands

    # ... rest of the methods remain the same since they're just for listing/inspection ...
    
    def list_all_commands(self, include_status=True):
        """Generate a list of all available commands using ComponentInspector"""
        commands = []
        
        for device_name, device_proxy in self.all_devices.items():
            device_config = self._get_device_config(device_name)
            if not device_config:
                continue
                
            components_config = device_config.get('components', {})
            
            for component_name, component_config in components_config.items():
                component_type = component_config.get('type')
                if not component_type:
                    continue
                    
                command_methods = ComponentInspector.discover_command_methods(component_type)
                status_methods = ComponentInspector.discover_status_methods(component_type) if include_status else []
                
                for method_name in command_methods:
                    signature = self._get_method_signature(component_type, method_name)
                    command_str = f"await {device_name}.{component_name}.{method_name}{signature}"  # Add await prefix
                    commands.append(command_str)
                
                for method_name in status_methods:
                    signature = self._get_method_signature(component_type, method_name)
                    command_str = f"await {device_name}.{component_name}.{method_name}{signature}"  # Add await prefix
                    commands.append(command_str)
        
        return sorted(commands)

    def _get_device_config(self, device_name: str):
        """Get the original config for a device"""
        for manager in self.device_managers.values():
            if hasattr(manager, 'devices') and device_name in manager.devices:
                device_proxy = manager.devices[device_name]
                if hasattr(device_proxy, 'device_config'):
                    return device_proxy.device_config
        return None

    def _get_method_signature(self, component_type: str, method_name: str):
        """Get the actual method signature by inspecting the component class"""
        try:
            import importlib
            import inspect
            
            module = importlib.import_module(component_type)
            component_class = getattr(module, component_type)
            method = getattr(component_class, method_name)
            
            sig = inspect.signature(method)
            
            params = []
            for name, param in sig.parameters.items():
                if name == 'self':
                    continue
                if param.kind == param.VAR_KEYWORD:
                    continue
                params.append(str(param))
            
            if params:
                return f"({', '.join(params)})"
            else:
                return "()"
                
        except Exception as e:
            return "()"

    def print_all_commands(self, include_status=True):
        """Print all available commands to the terminal"""
        commands = self.list_all_commands(include_status)
        
        print(f"\nAvailable Commands ({len(commands)} total):")
        print("=" * 50)
        print("Note: All commands are now async and must be awaited!")
        print("=" * 50)
        
        by_device = {}
        for cmd in commands:
            device = cmd.split('.')[0].replace('await ', '')  # Remove await for grouping
            if device not in by_device:
                by_device[device] = []
            by_device[device].append(cmd)
            
        for device, cmds in by_device.items():
            print(f"\n{device.upper()}:")
            for cmd in cmds:
                if self._is_status_method(cmd):
                    print(f"  {cmd} [STATUS]")
                else:
                    print(f"  {cmd}")

    def _is_status_method(self, command_str: str):
        """Check if a command string represents a status method"""
        try:
            # Remove 'await ' prefix for parsing
            clean_cmd = command_str.replace('await ', '')
            parts = clean_cmd.split('.')
            if len(parts) < 3:
                return False
                
            device_name = parts[0]
            component_name = parts[1]
            method_name = parts[2].split('(')[0]
            
            device_config = self._get_device_config(device_name)
            if not device_config:
                return False
                
            component_config = device_config.get('components', {}).get(component_name, {})
            component_type = component_config.get('type')
            
            if not component_type:
                return False
                
            status_methods = ComponentInspector.discover_status_methods(component_type)
            return method_name in status_methods
            
        except Exception:
            return False

    def get_commands_json(self, include_status=True):
        """Get all commands as JSON string for API endpoints"""
        import json
        return json.dumps(self.get_commands(include_status), indent=2)

    def get_commands(self, include_status=True):
        commands = self.list_all_commands(include_status)
        
        command_list = []
        status_list = []
        
        for cmd in commands:
            if self._is_status_method(cmd):
                status_list.append(cmd)
            else:
                command_list.append(cmd)

        return {
            "commands": command_list,
            "status_methods": status_list,
            "total": len(commands)
        }

# Updated factory function
async def create_device_controller(config_directory: str = "configs", component_path: str = "."):
    """Create and return a configured async device controller"""
    loader = AsyncConfigLoader(config_directory, component_path)
    await loader.initialize()
    return loader

# Convenience function for testing
async def test_controller():
    """Test function to create controller and show usage"""
    controller = await create_device_controller()
    
    print("\n=== Testing Controller ===")
    controller.print_all_commands()
    
    # Example usage:
    try:
        # This is how you call methods now:
        result = await controller.hvac.avery_valve.on()
        print(f"Command result: {result}")
    except AttributeError as e:
        print(f"Device/component not found: {e}")
    except Exception as e:
        print(f"Error executing command: {e}")
    
    return controller

# Test in async context
if __name__ == "__main__":
    async def main():
        controller = await test_controller()
        
        # Keep alive for testing
        print("\nController ready for testing. Use 'await controller.device.component.method()' syntax")
        
        # Example interactive session:
        # await controller.hvac.avery_valve.on()
        # await controller.hvac.temp_sensor.get_temperature()
        
    asyncio.run(main())