#!/usr/bin/env python3
"""
Example showing how to capture data from TemperatureSensor using server-side events
"""

from ConfigLoader import create_device_controller
import time
import threading

def temperature_monitor_example(controller):
    """Example of waiting for temperature sensor data"""
    
    # Assuming you have a temperature sensor device in your config
    # Replace 'temp_device' with your actual device name
    temp_device = controller.get_device('hvac')  # Update this
    temp_sensor = temp_device.temp_sensor  # Assuming component name is 'temperature_sensor'
    
    print("=== Temperature Sensor Data Capture Example ===\n")
    
    while True:
        try:
            print("Sending read command to temperature sensor...")
            
            # Send the read command
            temp_sensor.read_temp(units="f")
            
            # Wait for the status response (with 10 second timeout)
            print("Waiting for temperature data...")
            if temp_sensor.wait_for_status('read_status', timeout=10):
                # Get the latest data
                status_data = temp_sensor.get_latest_status('read_status')
                
                if status_data:
                    temperature = status_data.get('temperature', 0)
                    humidity = status_data.get('humidity', 0)
                    timestamp = status_data.get('timestamp', 0)
                    
                    print(f"✅ Temperature Reading Received!")
                    print(f"   Temperature: {temperature}°F")
                    print(f"   Humidity: {humidity}%")
                    print(f"   Timestamp: {timestamp}")
                    print(f"   Full data: {status_data}")
                else:
                    print("❌ No data in status response")
                    
                # Clear the event for next reading
                temp_sensor.clear_status_event('read_status')
                
            else:
                print("⏰ Timeout waiting for temperature data")
            
            print("\n" + "-"*50 + "\n")
            time.sleep(5)  # Wait 5 seconds before next reading
            
        except KeyboardInterrupt:
            print("Temperature monitoring stopped")
            break
        except Exception as e:
            print(f"Error in temperature monitoring: {e}")
            time.sleep(2)

def button_monitor_example(controller):
    """Example of waiting for button press events"""
    
    # Get the stink button from your config
    stink_button = controller.stink_button
    button_component = stink_button.button
    
    print("=== Button Press Monitor Example ===\n")
    print("Press the physical button to see events...")
    
    while True:
        try:
            # Wait for button press status (30 second timeout)
            if button_component.wait_for_status('pressed_status', timeout=30):
                # Get the button press data
                press_data = button_component.get_latest_status('pressed_status')
                
                if press_data:
                    press_count = press_data.get('press_count', 0)
                    timestamp = press_data.get('timestamp', 0)
                    pin = press_data.get('pin', 0)
                    
                    print(f"🔘 Button Pressed!")
                    print(f"   Press Count: {press_count}")
                    print(f"   Pin: {pin}")
                    print(f"   Timestamp: {timestamp}")
                    print(f"   Full data: {press_data}")
                    
                    # Flash the light in response
                    print("   💡 Flashing light in response...")
                    stink_button.light.on()
                    time.sleep(0.5)
                    stink_button.light.off()
                
                # Clear the event
                button_component.clear_status_event('pressed_status')
                
            else:
                print("⏰ No button press in the last 30 seconds")
                
        except KeyboardInterrupt:
            print("Button monitoring stopped")
            break
        except Exception as e:
            print(f"Error in button monitoring: {e}")
            time.sleep(1)

def any_device_monitor_example(controller):
    """Example of waiting for ANY status event from ANY device"""
    
    stink_button = controller.stink_button
    
    print("=== Any Device Event Monitor ===\n")
    print("Waiting for any status events from any component...")
    
    while True:
        try:
            # Wait for any status event from any component in stink_button device
            result = stink_button.wait_for_any_status(timeout=10)
            
            if result:
                component_name, status_method, status_data = result
                print(f"📡 Event received from {component_name}.{status_method}")
                print(f"   Data: {status_data}")
                
                # Handle different types of events
                if status_method == 'pressed_status':
                    print("   🔘 Button was pressed!")
                elif status_method == 'pressed_status' and 'temperature' in str(status_data):
                    print("   🌡️ Temperature reading received!")
                else:
                    print(f"   📋 Other status event: {status_method}")
                    
                print()
            else:
                print("⏰ No events in the last 10 seconds...")
                
        except KeyboardInterrupt:
            print("Device monitoring stopped")
            break
        except Exception as e:
            print(f"Error in device monitoring: {e}")
            time.sleep(1)

def simple_command_and_wait_example(controller):
    """Simple example: send command and wait for response"""
    
    print("=== Simple Command & Wait Example ===\n")
    
    # Example with button status check
    stink_button = controller.stink_button
    button = stink_button.button
    
    try:
        # Method 1: Just get latest status without waiting
        print("1. Getting current button state...")
        # Note: get_state is a @status method but not auto-published
        # You'd need to manually trigger it or check latest data
        latest_state = button.get_latest_status('get_state')
        print(f"   Latest state: {latest_state}")
        
        # Method 2: Wait for auto-published events (like button press)
        print("\n2. Waiting for button press (10 seconds)...")
        if button.wait_for_status('pressed_status', timeout=10):
            press_data = button.get_latest_status('pressed_status')
            print(f"   Button pressed! Data: {press_data}")
        else:
            print("   No button press detected")
            
    except Exception as e:
        print(f"Error: {e}")

def main():
    """Main example runner"""
    print("Loading device controller...")
    controller = create_device_controller('/home/scrumpi/containers/thermostat-dev/Device Files/configs', component_path='/home/scrumpi/containers/thermostat-dev/Device Files')
    
    print("\nAvailable devices:")
    controller.list_all_devices()
    
    print("\nChoose an example:")
    print("1. Temperature Sensor Monitor")
    print("2. Button Press Monitor") 
    print("3. Any Device Event Monitor")
    print("4. Simple Command & Wait")
    print("5. Run All (in threads)")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    try:
        if choice == "1":
            temperature_monitor_example(controller)
        elif choice == "2":
            button_monitor_example(controller)
        elif choice == "3":
            any_device_monitor_example(controller)
        elif choice == "4":
            simple_command_and_wait_example(controller)
        elif choice == "5":
            # Run multiple monitors in threads
            print("Starting all monitors in separate threads...")
            
            # Only run button monitor since we know stink_button exists
            button_thread = threading.Thread(target=button_monitor_example, args=(controller,))
            any_event_thread = threading.Thread(target=any_device_monitor_example, args=(controller,))
            
            button_thread.daemon = True
            any_event_thread.daemon = True
            
            button_thread.start()
            any_event_thread.start()
            
            print("Press Ctrl+C to stop all monitors")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping all monitors...")
        else:
            print("Invalid choice")
            
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        controller.disconnect_all()
        print("Disconnected from MQTT")

if __name__ == "__main__":
    main()