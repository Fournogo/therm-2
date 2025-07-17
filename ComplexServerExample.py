#!/usr/bin/env python3
"""
Async example showing how to capture data from TemperatureSensor using server-side events
"""

import asyncio
from ConfigLoader import create_device_controller

async def temperature_monitor_example(controller):
    """Example of waiting for temperature sensor data"""
    
    # Assuming you have a temperature sensor device in your config
    # Replace 'hvac' with your actual device name
    temp_device = controller.get_device('hvac')  # Update this
    if not temp_device:
        print("❌ Device 'hvac' not found")
        return
        
    temp_sensor = temp_device.temp_sensor  # Assuming component name is 'temp_sensor'
    
    print("=== Temperature Sensor Data Capture Example ===\n")
    
    while True:
        try:
            print("Sending read command to temperature sensor...")
            
            # Send the read command (now async)
            await temp_sensor.read_temp(units="f")
            
            # Wait for the status response (with 10 second timeout)
            print("Waiting for temperature data...")
            if await temp_sensor.wait_for_status('temp_status', timeout=10):
                # Get the latest data
                status_data = temp_sensor.get_latest_status('temp_status')
                
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
                temp_sensor.clear_status_event('read_temp')
                
            else:
                print("⏰ Timeout waiting for temperature data")
            
            print("\n" + "-"*50 + "\n")
            await asyncio.sleep(5)  # Wait 5 seconds before next reading
            
        except KeyboardInterrupt:
            print("Temperature monitoring stopped")
            break
        except Exception as e:
            print(f"Error in temperature monitoring: {e}")
            await asyncio.sleep(2)

async def button_monitor_example(controller):
    """Example of waiting for button press events"""
    
    # Get the stink button from your config
    stink_button = controller.get_device('stink_button')
    if not stink_button:
        print("❌ Device 'stink_button' not found")
        return
        
    button_component = stink_button.button
    
    print("=== Button Press Monitor Example ===\n")
    print("Press the physical button to see events...")
    
    while True:
        try:
            # Wait for button press status (30 second timeout)
            if await button_component.wait_for_status('pressed_status', timeout=30):
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
                    
                    # Flash the light in response (now async)
                    print("   💡 Flashing light in response...")
                    await stink_button.light.on()
                    await asyncio.sleep(0.5)
                    await stink_button.light.off()
                
                # Clear the event
                button_component.clear_status_event('pressed_status')
                
            else:
                print("⏰ No button press in the last 30 seconds")
                
        except KeyboardInterrupt:
            print("Button monitoring stopped")
            break
        except Exception as e:
            print(f"Error in button monitoring: {e}")
            await asyncio.sleep(1)

async def any_device_monitor_example(controller):
    """Example of waiting for ANY status event from ANY device"""
    
    stink_button = controller.get_device('stink_button')
    if not stink_button:
        print("❌ Device 'stink_button' not found")
        return
    
    print("=== Any Device Event Monitor ===\n")
    print("Waiting for any status events from any component...")
    
    while True:
        try:
            # Wait for any status event from any component in stink_button device
            result = await stink_button.wait_for_any_status(timeout=10)
            
            if result:
                component_name, status_method, status_data = result
                print(f"📡 Event received from {component_name}.{status_method}")
                print(f"   Data: {status_data}")
                
                # Handle different types of events
                if status_method == 'pressed_status':
                    print("   🔘 Button was pressed!")
                elif status_method == 'read_status' and isinstance(status_data, dict) and 'temperature' in status_data:
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
            await asyncio.sleep(1)

async def simple_command_and_wait_example(controller):
    """Simple example: send command and wait for response"""
    
    print("=== Simple Command & Wait Example ===\n")
    
    # Example with button status check
    stink_button = controller.get_device('stink_button')
    if not stink_button:
        print("❌ Device 'stink_button' not found")
        return
        
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
        if await button.wait_for_status('pressed_status', timeout=10):
            press_data = button.get_latest_status('pressed_status')
            print(f"   Button pressed! Data: {press_data}")
        else:
            print("   No button press detected")
            
    except Exception as e:
        print(f"Error: {e}")

async def test_execute_and_wait_example(controller):
    """Test the execute_and_wait_for_status functionality"""
    
    print("=== Execute and Wait Example ===\n")
    
    # Test with temperature sensor if available
    hvac = controller.get_device('hvac')
    if hvac and hasattr(hvac, 'temp_sensor'):
        try:
            print("Testing execute_and_wait with temperature sensor...")
            
            # This should send the command and wait for the status response
            result = await hvac.temp_sensor.execute_and_wait_for_status(
                'read_temp',  # command method
                'read_status',  # status method to wait for
                timeout=15,
                units="f"  # parameter for read_temp
            )
            
            if result:
                print(f"✅ Got temperature data: {result}")
            else:
                print("⏰ Timeout waiting for temperature response")
                
        except Exception as e:
            print(f"❌ Error in execute_and_wait: {e}")
    
    # Test with valve if available
    if hvac and hasattr(hvac, 'avery_valve'):
        try:
            print("\nTesting valve commands...")
            
            print("Turning valve on...")
            await hvac.avery_valve.on()
            await asyncio.sleep(2)
            
            print("Turning valve off...")
            await hvac.avery_valve.off()
            
        except Exception as e:
            print(f"❌ Error controlling valve: {e}")

async def continuous_monitor_example(controller):
    """Example using continuous monitoring"""
    
    print("=== Continuous Monitor Example ===\n")
    
    stink_button = controller.get_device('stink_button')
    if not stink_button:
        print("❌ Device 'stink_button' not found")
        return
    
    button = stink_button.button
    
    def button_callback(status_data):
        """Callback for button press events"""
        if status_data:
            print(f"🔘 Continuous monitor: Button pressed! {status_data}")
        else:
            print("⏰ Continuous monitor: Timeout/error")
    
    try:
        # Start continuous monitoring
        print("Starting continuous button monitor...")
        wait_id = button.wait_for_continuous('pressed_status', button_callback)
        
        print(f"Monitor started (ID: {wait_id[:8]}). Press button or wait 30 seconds...")
        await asyncio.sleep(30)
        
        print("Stopping continuous monitor...")
        await button.stop_continuous_wait(wait_id)
        
    except Exception as e:
        print(f"Error in continuous monitoring: {e}")

async def run_concurrent_monitors(controller):
    """Run multiple monitors concurrently using asyncio.gather"""
    
    print("=== Running Concurrent Monitors ===\n")
    print("Starting multiple monitors concurrently...")
    print("Press Ctrl+C to stop all monitors\n")
    
    try:
        # Create tasks for different monitors
        tasks = []
        
        # Only add tasks for devices that exist
        if controller.get_device('stink_button'):
            tasks.append(asyncio.create_task(button_monitor_example(controller)))
            tasks.append(asyncio.create_task(any_device_monitor_example(controller)))
        
        if controller.get_device('hvac'):
            tasks.append(asyncio.create_task(temperature_monitor_example(controller)))
        
        if not tasks:
            print("❌ No compatible devices found for monitoring")
            return
        
        # Run all tasks concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping all monitors...")
        # Cancel all tasks
        for task in tasks:
            task.cancel()
        
        # Wait for tasks to finish canceling
        await asyncio.gather(*tasks, return_exceptions=True)
        print("✅ All monitors stopped")

async def main():
    """Main example runner"""
    print("Loading async device controller...")
    
    try:
        controller = await create_device_controller(
            '/home/scrumpi/containers/therm-2/configs', 
            component_path='/home/scrumpi/containers/therm-2'
        )
        
        print("\nAvailable devices:")
        controller.list_all_devices()
        
        print("\nChoose an example:")
        print("1. Temperature Sensor Monitor")
        print("2. Button Press Monitor") 
        print("3. Any Device Event Monitor")
        print("4. Simple Command & Wait")
        print("5. Execute and Wait Test")
        print("6. Continuous Monitor Example")
        print("7. Run Concurrent Monitors")
        
        # For automated testing, you can uncomment this:
        # choice = "5"  # Auto-run execute and wait test
        
        choice = input("\nEnter choice (1-7): ").strip()
        
        if choice == "1":
            await temperature_monitor_example(controller)
        elif choice == "2":
            await button_monitor_example(controller)
        elif choice == "3":
            await any_device_monitor_example(controller)
        elif choice == "4":
            await simple_command_and_wait_example(controller)
        elif choice == "5":
            await test_execute_and_wait_example(controller)
        elif choice == "6":
            await continuous_monitor_example(controller)
        elif choice == "7":
            await run_concurrent_monitors(controller)
        else:
            print("Invalid choice")
            
    except KeyboardInterrupt:
        print("\n🛑 Exiting...")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await controller.disconnect_all()
            print("✅ Disconnected from MQTT")
        except:
            print("⚠️  Error disconnecting (controller may not have been created)")

if __name__ == "__main__":
    asyncio.run(main())