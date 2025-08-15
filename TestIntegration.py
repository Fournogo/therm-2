#!/usr/bin/env python3
# test_integration.py - Test script to verify the new integration works

import asyncio
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_new_system():
    """Test the new integrated system"""
    
    print("=== Testing New Integration ===\n")
    
    try:
        # Import the new modules
        from ImprovedConfigLoader import create_device_controller
        from SimplifiedStateManager import create_simplified_state_manager
        
        # 1. Test controller creation
        print("1. Creating device controller...")
        controller = await create_device_controller(
            config_directory="configs",
            component_path="."
        )
        print("✅ Controller created successfully")
        
        # 2. List all devices
        print("\n2. Listing all devices:")
        controller.list_all_devices()
        
        # 3. Test MQTT component if available
        if hasattr(controller, 'hvac'):
            print("\n3. Testing MQTT component (hvac)...")
            
            # Test temperature sensor
            if hasattr(controller.hvac, 'temp_sensor'):
                print("   Reading temperature...")
                await controller.hvac.temp_sensor.read_temperature()
                await asyncio.sleep(2)  # Wait for response
                
                # Get status
                temp_status = await controller.hvac.temp_sensor.get_temp_status()
                print(f"   Temperature status: {temp_status}")
        
        # 4. Test ESPHome component if available
        if hasattr(controller, 'living_room_ac'):
            print("\n4. Testing ESPHome component (living_room_ac)...")
            
            if hasattr(controller.living_room_ac, 'ac'):
                # Get current status
                print("   Getting AC status...")
                temp_status = await controller.living_room_ac.ac.get_temp_status()
                print(f"   Current temperature: {temp_status}")
                
                mode_status = await controller.living_room_ac.ac.get_mode_status()
                print(f"   Current mode: {mode_status}")
        
        # 5. Test state manager
        print("\n5. Testing state manager...")
        state_config = {
            "internal_state": {
                "control_mode": "MANUAL",
                "target_temperature": 72
            },
            "config": {
                "poll_intervals": {
                    "temp_status": 5,
                    "mode_status": 10,
                    "power_status": 30
                }
            }
        }
        
        state_manager = await create_simplified_state_manager(controller, state_config)
        print("✅ State manager created")
        
        # Start state monitoring
        await state_manager.start_continuous_refresh()
        print("✅ State monitoring started")
        
        # Monitor for a few updates
        print("\n6. Monitoring state updates for 20 seconds...")
        
        async def monitor_states():
            count = 0
            async for state in state_manager.get_state_updates():
                count += 1
                print(f"\n   Update #{count}: {len(state)} total states")
                
                # Show some example states
                example_keys = [k for k in state.keys() if any(x in k for x in ['temp', 'mode', 'control'])]
                for key in example_keys[:5]:
                    print(f"     {key}: {state[key]}")
                
                if count >= 3:  # Stop after 3 updates
                    break
        
        # Run monitoring with timeout
        try:
            await asyncio.wait_for(monitor_states(), timeout=20)
        except asyncio.TimeoutError:
            print("   (Monitoring timeout reached)")
        
        # 7. Test command execution
        print("\n7. Testing command execution...")
        
        if hasattr(controller, 'hvac') and hasattr(controller.hvac, 'avery_valve'):
            print("   Testing valve control...")
            
            # Turn on
            print("   Turning valve ON...")
            result = await controller.hvac.avery_valve.execute_and_wait_for_status(
                'on', 'is_on', timeout=5
            )
            print(f"   Valve status: {result}")
            
            await asyncio.sleep(2)
            
            # Turn off
            print("   Turning valve OFF...")
            result = await controller.hvac.avery_valve.execute_and_wait_for_status(
                'off', 'is_on', timeout=5
            )
            print(f"   Valve status: {result}")
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        print("\n8. Cleaning up...")
        
        if 'state_manager' in locals():
            await state_manager.stop_continuous_refresh()
            print("   State manager stopped")
        
        if 'controller' in locals():
            await controller.disconnect_all()
            print("   Controller disconnected")
        
        print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_new_system())