import re
import asyncio
import inspect
from typing import Dict, Callable, Any

class SafeCommandDispatcher:
    """
    Safe command dispatcher that executes predefined commands without eval().
    Supports dot notation like: controller.stink_button.light.on()
    Now supports both sync and async operations.
    """
    
    def __init__(self):
        self.controllers = {}
        self.command_pattern = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_.]*)\(([^)]*)\)$')
        
    def register_controller(self, name: str, controller_obj):
        """Register a controller object"""
        self.controllers[name] = controller_obj
        
    def execute_command(self, command_string: str) -> Any:
        """
        Execute a command string safely (synchronous version)
        
        Args:
            command_string: String like "controller.stink_button.light.on()" or "dac.set_voltage(3.3, 0)"
            
        Returns:
            Result of the command execution
            
        Raises:
            ValueError: If command format is invalid
            AttributeError: If object/method doesn't exist
        """
        # Parse the command
        match = self.command_pattern.match(command_string.strip())
        if not match:
            raise ValueError(f"Invalid command format: {command_string}")
            
        method_path = match.group(1)
        args_string = match.group(2).strip()
        
        # Parse arguments
        args, kwargs = self._parse_arguments(args_string) if args_string else ([], {})
        
        # Navigate to the method
        method = self._get_method_from_path(method_path)
        
        # Execute the method (sync only)
        if asyncio.iscoroutinefunction(method):
            raise ValueError(f"Method '{method_path}' is async - use execute_command_async() instead")
        
        return method(*args, **kwargs)
    
    async def execute_command_async(self, command_string: str) -> Any:
        """
        Execute a command string safely (asynchronous version)
        
        Args:
            command_string: String like "controller.stink_button.light.on()" or "dac.set_voltage(3.3, 0)"
            
        Returns:
            Result of the command execution
            
        Raises:
            ValueError: If command format is invalid
            AttributeError: If object/method doesn't exist
        """
        # Parse the command
        match = self.command_pattern.match(command_string.strip())
        if not match:
            raise ValueError(f"Invalid command format: {command_string}")
            
        method_path = match.group(1)
        args_string = match.group(2).strip()
        
        # Parse arguments
        args, kwargs = self._parse_arguments(args_string) if args_string else ([], {})
        
        # Navigate to the method
        method = self._get_method_from_path(method_path)
        
        # Execute the method (async-aware)
        if asyncio.iscoroutinefunction(method):
            print(f"Executing async command: {command_string}")
            result = await method(*args, **kwargs)
        else:
            print(f"Executing sync command: {command_string}")
            # Run sync method in executor to avoid blocking
            result = await asyncio.get_event_loop().run_in_executor(None, lambda: method(*args, **kwargs))
        
        return result
    
    async def execute_command_auto(self, command_string: str) -> Any:
        """
        Execute a command string safely, automatically detecting sync vs async
        
        Args:
            command_string: String like "controller.stink_button.light.on()" or "dac.set_voltage(3.3, 0)"
            
        Returns:
            Result of the command execution
        """
        # Parse the command to get the method
        match = self.command_pattern.match(command_string.strip())
        if not match:
            raise ValueError(f"Invalid command format: {command_string}")
            
        method_path = match.group(1)
        method = self._get_method_from_path(method_path)
        
        # Choose appropriate execution method
        if asyncio.iscoroutinefunction(method):
            return await self.execute_command_async(command_string)
        else:
            return self.execute_command(command_string)
        
    def _get_method_from_path(self, path: str) -> Callable:
        """Navigate through dot notation to find the method"""
        parts = path.split('.')
        
        if not parts:
            raise ValueError("Empty method path")
            
        # Start with registered controller
        if parts[0] not in self.controllers:
            raise AttributeError(f"Controller '{parts[0]}' not registered")
            
        current_obj = self.controllers[parts[0]]
        
        # Navigate through the path
        for part in parts[1:]:
            if not hasattr(current_obj, part):
                raise AttributeError(f"'{type(current_obj).__name__}' has no attribute '{part}'")
            current_obj = getattr(current_obj, part)
            
        # Ensure it's callable
        if not callable(current_obj):
            raise AttributeError(f"'{path}' is not callable")
            
        return current_obj
        
    def _parse_arguments(self, args_string: str) -> tuple:
        """Parse argument string into Python values, returns (args, kwargs)"""
        if not args_string:
            return [], {}
            
        args = []
        kwargs = {}
        
        # Split by comma, but be careful with nested quotes
        arg_parts = self._split_arguments(args_string)
        
        for arg in arg_parts:
            arg = arg.strip()
            if not arg:
                continue
                
            # Check if it's a keyword argument (contains '=')
            if '=' in arg and not (arg.startswith('"') or arg.startswith("'")):
                key, value = arg.split('=', 1)
                key = key.strip()
                value = value.strip()
                kwargs[key] = self._parse_single_value(value)
            else:
                # Positional argument
                args.append(self._parse_single_value(arg))
                
        return args, kwargs
    
    def _split_arguments(self, args_string: str) -> list:
        """Split arguments by comma, respecting quotes"""
        parts = []
        current = ""
        in_quotes = False
        quote_char = None
        
        for char in args_string:
            if char in ['"', "'"] and not in_quotes:
                in_quotes = True
                quote_char = char
                current += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current += char
            elif char == ',' and not in_quotes:
                parts.append(current)
                current = ""
            else:
                current += char
                
        if current:
            parts.append(current)
            
        return parts
    
    def _parse_single_value(self, value: str):
        """Parse a single value string into appropriate Python type"""
        value = value.strip()
        
        # Boolean values
        if value.lower() == 'true':
            return True
        elif value.lower() == 'false':
            return False
        elif value.lower() == 'none':
            return None
        # String values
        elif value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            return value[1:-1]
        # Numeric values
        else:
            try:
                if '.' in value:
                    return float(value)
                else:
                    return int(value)
            except ValueError:
                # Treat as string if can't parse as number
                return value
    
    def is_method_async(self, command_string: str) -> bool:
        """
        Check if a command string would execute an async method
        
        Args:
            command_string: Command string to check
            
        Returns:
            True if the method is async, False if sync
        """
        try:
            match = self.command_pattern.match(command_string.strip())
            if not match:
                return False
                
            method_path = match.group(1)
            method = self._get_method_from_path(method_path)
            return asyncio.iscoroutinefunction(method)
        except:
            return False
    
    def get_method_info(self, command_string: str) -> dict:
        """
        Get information about a method from a command string
        
        Args:
            command_string: Command string to analyze
            
        Returns:
            Dictionary with method information
        """
        try:
            match = self.command_pattern.match(command_string.strip())
            if not match:
                return {"error": "Invalid command format"}
                
            method_path = match.group(1)
            method = self._get_method_from_path(method_path)
            
            return {
                "path": method_path,
                "is_async": asyncio.iscoroutinefunction(method),
                "signature": str(inspect.signature(method)),
                "callable": True,
                "type": type(method).__name__
            }
        except Exception as e:
            return {"error": str(e)}

# Example usage and testing
if __name__ == "__main__":
    # Example test with mock objects
    class MockDevice:
        def sync_method(self, value):
            return f"Sync result: {value}"
        
        async def async_method(self, value):
            await asyncio.sleep(0.1)  # Simulate async work
            return f"Async result: {value}"
    
    class MockController:
        def __init__(self):
            self.device = MockDevice()
    
    async def test_dispatcher():
        dispatcher = SafeCommandDispatcher()
        controller = MockController()
        dispatcher.register_controller('controller', controller)
        
        # Test sync command
        result1 = dispatcher.execute_command('controller.device.sync_method("test")')
        print(f"Sync command result: {result1}")
        
        # Test async command
        result2 = await dispatcher.execute_command_async('controller.device.async_method("test")')
        print(f"Async command result: {result2}")
        
        # Test auto detection
        result3 = await dispatcher.execute_command_auto('controller.device.sync_method("auto")')
        result4 = await dispatcher.execute_command_auto('controller.device.async_method("auto")')
        print(f"Auto sync result: {result3}")
        print(f"Auto async result: {result4}")
        
        # Test method info
        info = dispatcher.get_method_info('controller.device.async_method("test")')
        print(f"Method info: {info}")
    
    # Uncomment to run test
    # asyncio.run(test_dispatcher())