# test_controller.py
import asyncio
from ConfigLoader import create_device_controller

async def main():
    controller = await create_device_controller()
    
    # Test a command
    try:
        print("Testing valve on command...")
        result = await controller.hvac.avery_valve.on()
        print(f"✅ Success: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())