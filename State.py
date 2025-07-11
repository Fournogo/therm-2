import time
import threading

class StateManager:
    def __init__(self, controller, refresh_interval=5):
        self.controller = controller
        self.refresh_interval = refresh_interval
        self.data_methods = controller.list_data_commands()
        self.running = False
        self.refresh_thread = None
        
        # Create nested attribute structure
        self._create_nested_attributes()
        
    def _create_nested_attributes(self):
        """Create nested attribute structure to mirror controller"""
        for method_info in self.data_methods:
            # Create nested attributes: self.averys_room.temp_sensor.temp_status
            self._create_nested_path(method_info['status_path'])
    
    def _create_nested_path(self, path):
        """Create nested attributes dynamically"""
        parts = path.split('.')
        current = self
        
        for part in parts[:-1]:  # All but the last part
            if not hasattr(current, part):
                setattr(current, part, type('StateObject', (), {})())
            current = getattr(current, part)
        
        # Set the final attribute to None initially
        setattr(current, parts[-1], None)
    
    def _set_nested_value(self, path, value):
        """Set a value in the nested structure"""
        parts = path.split('.')
        current = self
        
        for part in parts[:-1]:
            current = getattr(current, part)
        
        setattr(current, parts[-1], value)
    
    def refresh_all_data(self):
        """Call all data commands and wait for their status updates individually"""
        
        for cmd_info in self.data_methods:
            try:
                command_str = cmd_info['command_str']
                status_method_name = cmd_info['status_method_name']
                component_path = cmd_info['component_path']
                status_path = cmd_info['status_path']
                
                if not status_method_name:
                    # No status method, just execute command
                    print(f"Executing command (no status): {command_str}")
                    cmd_info['command_method']()
                    continue
                
                # Get the component proxy
                parts = component_path.split('.')
                component_proxy = self.controller
                for part in parts:
                    component_proxy = getattr(component_proxy, part)
                
                # Extract command method name from the command_method
                command_method_name = cmd_info['command_method_name']
                
                print(f"Executing command with status wait: {command_str}")
                
                # Use the new execute_and_wait method
                status_data = component_proxy.execute_and_wait_for_status(
                    command_method_name, 
                    status_method_name, 
                    timeout=10
                )
                
                if status_data is not None:
                    # Update our state variable
                    self._set_nested_value(status_path, status_data)
                    print(f"Updated {status_path}")
                else:
                    print(f"Timeout waiting for {status_method_name}")
                    
            except Exception as e:
                print(f"Error processing {cmd_info['command_str']}: {e}")
    
    def _continuous_refresh_loop(self):
        """Internal method that runs the continuous refresh loop"""
        while self.running:
            try:
                print("Refreshing all data...")
                self.refresh_all_data()
            except Exception as e:
                print(f"Error during refresh cycle: {e}")
            
            # Sleep for the refresh interval, but check for stop condition periodically
            sleep_time = 0
            while sleep_time < self.refresh_interval and self.running:
                time.sleep(0.1)
                sleep_time += 0.1
    
    def start_continuous_refresh(self):
        """Start the continuous refresh loop in a background thread"""
        if self.running:
            print("Continuous refresh is already running")
            return
        
        self.running = True
        self.refresh_thread = threading.Thread(
            target=self._continuous_refresh_loop,
            name="StateManager-Refresh",
            daemon=True  # Thread will exit when main program exits
        )
        self.refresh_thread.start()
        print(f"Started continuous refresh thread (interval: {self.refresh_interval}s)")
    
    def stop_continuous_refresh(self):
        """Stop the continuous refresh thread"""
        if not self.running:
            print("Continuous refresh is not running")
            return
        
        print("Stopping continuous refresh...")
        self.running = False
        
        # Wait for thread to finish (with timeout)
        if self.refresh_thread and self.refresh_thread.is_alive():
            self.refresh_thread.join(timeout=5.0)
            if self.refresh_thread.is_alive():
                print("Warning: Refresh thread did not stop cleanly")
            else:
                print("Continuous refresh stopped")
        
        self.refresh_thread = None
    
    def is_refresh_running(self):
        """Check if continuous refresh is currently running"""
        return self.running and self.refresh_thread and self.refresh_thread.is_alive()
    
    def get_all_states(self):
        """Return a dictionary of all current states"""
        states = {}
        for method_info in self.data_methods:
            path = method_info['status_path']
            parts = path.split('.')
            current = self
            
            try:
                for part in parts:
                    current = getattr(current, part)
                states[path] = current
            except AttributeError:
                states[path] = None
                
        return states

# Usage example:
if __name__ == "__main__":
    from ConfigLoader import *
    
    c = create_device_controller("/home/scrumpi/containers/therm-2/configs", "/home/scrumpi/containers/therm-2")
    s = StateManager(c, refresh_interval=5)
    
    # Manual refresh
    s.refresh_all_data()
    print(s.get_all_states())
    print(s.ryans_room.temp_sensor.temp_status)
    
    # Start continuous refresh in background
    s.start_continuous_refresh()
    
    # Do other work while refresh runs in background
    time.sleep(20)  # Let it run for 20 seconds
    
    # Check status
    print(f"Refresh running: {s.is_refresh_running()}")
    print("Current states:", s.get_all_states())
    
    # Stop the background refresh
    s.stop_continuous_refresh()