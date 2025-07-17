import asyncio
import logging
from typing import Type, TypeVar
from SafeCommandDispatcher import SafeCommandDispatcher

async def clear_async_queue(queue: asyncio.Queue) -> None:
    """
    Simple function to clear an async queue
    """
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break

CP = TypeVar("CP", bound="AsyncCommandProcessor")

class AsyncCommandProcessor:
    """
    Async command processor class for processing commands/events and divvying up tasks 

    Attributes:
        command_queue (asyncio.Queue): Queue for user commands with priority processing
        controller: Device controller instance
        state_manager: State manager instance

    Methods:
        add_command(self, command, data): Public method to add commands to the queue
        start_processing(self): Start the command processing loop
        stop_processing(self): Stop the command processing loop
    """
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls: Type[CP], *args, **kwargs) -> CP:
        """
        Ensures a single instance of this object (singleton pattern).
        Note: In async context, singleton is less critical since we control instantiation
        """
        if not cls._instance:
            cls._instance = super(AsyncCommandProcessor, cls).__new__(cls)
        return cls._instance
    
    def __init__(self: CP, controller=None, state_manager=None, config=None) -> None:
        """
        Run when initializing the object. Initialize queues and state.
        Only initializes once due to singleton pattern.
        """
        if hasattr(self, '_initialized'):
            return
            
        if controller is None:
            raise ValueError("Controller must be provided on initialization")
        
        if config is None:
            raise ValueError("Config must be provided on first initialization")

        self.config = config
        
        for key, value in config.items():
            setattr(self, key, value)

        self.command_queue = asyncio.Queue()
        self.running = False
        self.processor_task = None
        self.controller = controller
        self.state_manager = state_manager
        self._initialized = True
        
        # Initialize dispatcher
        self.dispatcher = SafeCommandDispatcher()
        self.dispatcher.register_controller('controller', self.controller)
    
    @classmethod
    def get_instance(cls, controller=None, state_manager=None, config=None):
        """Get the singleton instance"""
        if cls._instance is None:
            return cls(controller, state_manager, config)
        return cls._instance
    
    async def add_command(self, command: str, data) -> None:
        """
        Public method to add a command to the command queue
        
        Args:
            command (str): Command string
            data: Command data
        """
        await self.command_queue.put((command, data))
        print(f"Added command to queue: {command} with data: {data}")
    
    async def start_processing(self) -> None:
        """
        Start the command processing loop as an async task.
        
        Returns: None
        """
        if self.running:
            print("AsyncCommandProcessor is already running")
            return
        
        self.running = True
        self.processor_task = asyncio.create_task(
            self._run_loop(),
            name="AsyncCommandProcessor"
        )

        print("AsyncCommandProcessor started successfully")
    
    async def stop_processing(self) -> None:
        """
        Stop the command processing loop.
        
        Returns: None
        """
        if not self.running:
            print("AsyncCommandProcessor is not running")
            return
        
        print("Stopping AsyncCommandProcessor...")
        self.running = False
        
        # Cancel the processor task
        if self.processor_task and not self.processor_task.done():
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                print("AsyncCommandProcessor stopped")
            except Exception as e:
                print(f"Error stopping AsyncCommandProcessor: {e}")
        
        self.processor_task = None
    
    def is_running(self) -> bool:
        """
        Check if the command processor is currently running.
        
        Returns: bool - True if running, False otherwise
        """
        return self.running and self.processor_task and not self.processor_task.done()

    async def _run_loop(self: CP) -> None:
        """
        Internal method that runs the main command processing loop.
        Processes command queue continuously.
        
        Returns: None
        """
        print("AsyncCommandProcessor loop started")
        
        while self.running:
            try:
                # Wait for commands with a timeout to check running status
                try:
                    command, data = await asyncio.wait_for(
                        self.command_queue.get(), 
                        timeout=getattr(self, 'command_loop_delay', 0.1)
                    )
                except asyncio.TimeoutError:
                    # No command received, continue loop
                    continue

                print(f"Processing command: {command} with data: {data}")

                # Handle DIRECT commands using the dispatcher
                if command == "DIRECT":
                    try:
                        # The SafeCommandDispatcher will need to handle async commands
                        result = await self.dispatcher.execute_command_async(data)
                        print(f"Direct command executed successfully: {result}")
                    except Exception as e:
                        logging.error(f"Error executing direct command {data}: {e}")
                        print(f"Error executing direct command {data}: {e}")

                # Handle mode changes
                elif command == "CONTROL":
                    try:
                        await self._handle_control_mode_change(data)
                    except Exception as e:
                        logging.error(f"Error changing control mode to {data}: {e}")
                        print(f"Error changing control mode to {data}: {e}")

                # Handle manual HVAC commands
                elif command.startswith("MANUAL "):
                    try:
                        await self._handle_manual_command(command, data)
                    except Exception as e:
                        logging.error(f"Error executing manual command {command}: {e}")
                        print(f"Error executing manual command {command}: {e}")

                # Add more command handling here as needed
                elif command == "SET_TEMPERATURE":
                    try:
                        await self._handle_set_temperature(data)
                    except Exception as e:
                        logging.error(f"Error setting temperature to {data}: {e}")

                elif command == "PLACEHOLDER":
                    # Placeholder for additional commands
                    print(f"Placeholder command received: {data}")

                else:
                    print(f"Unknown command: {command}")
                    logging.warning(f"Unknown command received: {command}")

                # Mark task as done
                self.command_queue.task_done()

            except asyncio.CancelledError:
                print("Command processing loop cancelled")
                break
            except Exception as e:
                logging.error(f"Unexpected error in command processing loop: {e}")
                print(f"Unexpected error in command processing loop: {e}")
                # Continue processing despite errors
                await asyncio.sleep(0.1)

        print("AsyncCommandProcessor loop ended")

    async def _handle_control_mode_change(self, mode: str):
        """Handle control mode changes (MANUAL, AUTO, BASIC)"""
        valid_modes = ["MANUAL", "AUTO", "BASIC"]
        
        if mode not in valid_modes:
            raise ValueError(f"Invalid control mode: {mode}. Valid modes: {valid_modes}")
        
        print(f"Changing control mode to: {mode}")
        
        # Update internal state
        if self.state_manager:
            await self.state_manager.set_state("control", mode)
        
        print(f"Control mode changed to: {mode}")

    async def _handle_manual_command(self, command: str, data: str):
        """Handle manual HVAC and Fan commands"""
        # Parse command like "MANUAL AC" or "MANUAL FAN"
        parts = command.split()
        if len(parts) != 2:
            raise ValueError(f"Invalid manual command format: {command}")
        
        device_type = parts[1]  # "AC" or "FAN"
        action = data.upper()   # "ON" or "OFF"
        
        if device_type == "AC":
            if action == "ON":
                # Turn on HVAC - you might want to customize this based on your setup
                await self.controller.hvac.avery_valve.on()
                print("HVAC turned ON via manual command")
            elif action == "OFF":
                await self.controller.hvac.avery_valve.off()
                print("HVAC turned OFF via manual command")
            else:
                raise ValueError(f"Invalid HVAC action: {action}")
                
        elif device_type == "FAN":
            if action == "ON":
                # Turn on fan - customize based on your setup
                if hasattr(self.controller, 'fan') and hasattr(self.controller.fan, 'fan'):
                    await self.controller.fan.fan.on()
                    print("Fan turned ON via manual command")
                else:
                    print("Fan device not found or not configured")
            elif action == "OFF":
                if hasattr(self.controller, 'fan') and hasattr(self.controller.fan, 'fan'):
                    await self.controller.fan.fan.off()
                    print("Fan turned OFF via manual command")
                else:
                    print("Fan device not found or not configured")
            else:
                raise ValueError(f"Invalid fan action: {action}")
        else:
            raise ValueError(f"Unknown device type: {device_type}")

    async def _handle_set_temperature(self, temperature: float):
        """Handle temperature set commands"""
        try:
            temperature = float(temperature)
            print(f"Setting target temperature to: {temperature}°F")
            
            # Update internal state
            if self.state_manager:
                await self.state_manager.set_state("target_temperature", temperature)
            
            # You might want to send this to a thermostat device
            # await self.controller.thermostat.set_target_temp(temperature)
            
            print(f"Target temperature set to: {temperature}°F")
            
        except (ValueError, TypeError):
            raise ValueError(f"Invalid temperature value: {temperature}")

    async def get_queue_size(self) -> int:
        """Get the current size of the command queue"""
        return self.command_queue.qsize()

    async def clear_queue(self) -> int:
        """Clear all pending commands from the queue"""
        cleared_count = 0
        while not self.command_queue.empty():
            try:
                self.command_queue.get_nowait()
                cleared_count += 1
            except asyncio.QueueEmpty:
                break
        
        print(f"Cleared {cleared_count} commands from queue")
        return cleared_count

# Factory function for easy creation
def create_async_command_processor(controller, state_manager, config):
    """Create an async command processor instance"""
    return AsyncCommandProcessor(controller, state_manager, config)

if __name__ == "__main__":
    # Example usage - normally this would be done from AsyncApp.py
    print("AsyncCommandProcessor module loaded. Use from AsyncApp.py to initialize.")
    
    # Example test
    async def test_command_processor():
        # This would normally be done with real controller and state manager
        processor = AsyncCommandProcessor(None, None, {"command_loop_delay": 0.1})
        
        await processor.start_processing()
        
        # Add some test commands
        await processor.add_command("PLACEHOLDER", "test data")
        await processor.add_command("CONTROL", "MANUAL")
        
        # Let it process for a bit
        await asyncio.sleep(1)
        
        await processor.stop_processing()
        print("Test completed")
    
    # Uncomment to run test
    # asyncio.run(test_command_processor())