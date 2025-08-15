#!/usr/bin/env python3
# test_clean_architecture.py - Test the clean MQTT architecture

import asyncio
import logging
import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_clean_system():
    """Test the clean architecture with proper MQTT proxies"""
    
    print("=== Testing Clean Architecture ===\n")
    
    try:
        from ConfigLoader import create_device_controller
        from State import create_state_manager
        
        # 1. Create controller
        print("1. Creating device controller...")
        controller = await create_device_controller(
            config_directory="configs",
            component_path="."
        )
        print("✅ Controller created")
        
        # 2. List all devices
        print("\n2. Loaded devices:")
        controller.list_all_devices()
        
        # Wait for MQTT connections to stabilize
        await asyncio.sleep(2)
        
        # 3. Test MQTT commands
        print("\n3. Testing MQTT device commands...")
        
        # Test hvac device (therm prefix)
        if hasattr(controller, 'hvac'):
            print("\n   Testing hvac device:")
            
            # Test temperature sensor
            if hasattr(controller.hvac, 'temp_sensor'):
                print("   - Sending read_temperature command...")
                await controller.hvac.temp_sensor.read_temperature()
                
                # Wait and check for status
                await asyncio.sleep(2)
                temp_status = controller.hvac.temp_sensor.get_latest_status('temp_status')
                print(f"   - Temperature status: {temp_status}")
            
            # Test valve
            if hasattr(controller.hvac, 'avery_valve'):
                print("   - Testing valve on/off...")
                await controller.hvac.avery_valve.on()
                await asyncio.sleep(1)
                await controller.hvac.avery_valve.off()
                print("   - Valve commands sent")
        
        # Test scrumpi device
        if hasattr(controller, 'living_room'):
            print("\n   Testing living_room device (scrumpi prefix):")
            
            if hasattr(controller.living_room, 'temp_sensor'):
                print("   - Testing ScrumpiTempSensor...")
                result = await controller.living_room.temp_sensor.execute_and_wait_for_status(
                    'read_temp', 'temp_status', timeout=5
                )
                print(f"   - Scrumpi temp result: {result}")
            
            if hasattr(controller.living_room, 'pressure_sensor'):
                print("   - Testing ScrumpiBaroSensor...")
                result = await controller.living_room.pressure_sensor.execute_and_wait_for_status(
                    'read_baro', 'baro_status', timeout=5
                )
                print(f"   - Scrumpi baro result: {result}")
        
        # 4. Test ESPHome devices
        if hasattr(controller, 'living_room_ac'):
            print("\n   Testing ESPHome AC:")
            
            if hasattr(controller.living_room_ac, 'ac'):
                # Get current temperature
                temp_status = await controller.living_room_ac.ac.get_temp_status()
                print(f"   - AC temperature: {temp_status}")
                
                # Get mode
                mode_status = await controller.living_room_ac.ac.get_mode_status()
                print(f"   - AC mode: {mode_status}")
        
        # 5. Test state manager
        print("\n4. Testing state manager...")
        
        # Load state config
        with open('config.yaml', 'r') as f:
            app_config = yaml.safe_load(f)
        
        state_config = app_config.get('state', {})
        state_manager = await create_state_manager(controller, state_config)
        
        # Start monitoring
        await state_manager.start_continuous_refresh()
        print("   State manager started")
        
        # Wait for initial states
        await asyncio.sleep(3)
        
        # Get all states
        all_states = state_manager.get_all_states()
        print(f"\n5. Current states ({len(all_states)} total):")
        
        # Group by device
        by_device = {}
        for key, value in all_states.items():
            if '.' in key:
                device = key.split('.')[0]
                if device not in by_device:
                    by_device[device] = {}
                by_device[device][key] = value
            else:
                # Internal state
                if '_internal' not in by_device:
                    by_device['_internal'] = {}
                by_device['_internal'][key] = value
        
        # Display organized
        for device, states in sorted(by_device.items()):
            print(f"\n   [{device}]")
            for key, value in states.items():
                if isinstance(value, dict) and 'temperature' in value:
                    temp = value.get('temperature', 'N/A')
                    print(f"     {key}: {temp}°F")
                elif isinstance(value, dict) and 'pressure' in value:
                    pressure = value.get('pressure', 'N/A')
                    print(f"     {key}: {pressure} hPa")
                else:
                    print(f"     {key}: {value}")
        
        # 6. Test live updates
        print("\n6. Monitoring live updates for 15 seconds...")
        
        update_count = 0
        start_time = asyncio.get_event_loop().time()
        
        async for state in state_manager.get_state_updates():
            update_count += 1
            elapsed = asyncio.get_event_loop().time() - start_time
            
            print(f"\n   Update #{update_count} at {elapsed:.1f}s")
            
            # Show temperature changes
            for key, value in state.items():
                if 'temp_status' in key and isinstance(value, dict):
                    temp = value.get('temperature', 'N/A')
                    print(f"     {key}: {temp}°F")
            
            if elapsed > 15:
                break
        
        print("\n✅ Clean architecture test completed!")
        
        # Cleanup
        await state_manager.stop_continuous_refresh()
        await controller.disconnect_all()
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


async def test_mqtt_topics():
    """Test MQTT topic structure"""
    print("\n\n=== Testing MQTT Topic Structure ===\n")
    
    # Show expected topic structure
    print("Expected MQTT topic structure:")
    print("  Commands: /{device_prefix}/{device_name}/{component_name}/{method_name}")
    print("  Status:   /{device_prefix}/{device_name}/{component_name}/status/{status_method}")
    print("\nExamples:")
    print("  /therm/hvac/fan/set_power")
    print("  /therm/hvac/temp_sensor/read_temperature")
    print("  /therm/hvac/temp_sensor/status/temp_status")
    print("  /scrumpi/living_room/temp_sensor/read_temp")
    print("  /scrumpi/living_room/temp_sensor/status/temp_status")


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_clean_system())
    asyncio.run(test_mqtt_topics())