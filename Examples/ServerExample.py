from SafeCommandDispatcher import SafeCommandDispatcher
from ConfigLoader import create_device_controller

controller = create_device_controller('/home/scrumpi/containers/therm-2/configs', component_path='/home/scrumpi/containers/therm-2')

dispatcher = SafeCommandDispatcher()
dispatcher.register_controller('controller', controller)

cmd = "controller.hvac.avery_valve.off()"

try:
    result = dispatcher.execute_command(cmd)
    print(f"Command: {cmd} -> Result: {result}")
except Exception as e:
    print(f"Error executing '{cmd}': {e}")