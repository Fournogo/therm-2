from flask import Flask, request, jsonify, send_from_directory
import os
from SafeCommandDispatcher import SafeCommandDispatcher
from ConfigLoader import create_device_controller

app = Flask(__name__)

# Initialize the controller and dispatcher
controller = create_device_controller('/home/scrumpi/containers/therm-2/configs', 
                                    component_path='/home/scrumpi/containers/therm-2')
dispatcher = SafeCommandDispatcher()
dispatcher.register_controller('controller', controller)

# Serve the HTML file
@app.route('/')
def serve_html():
    return send_from_directory('./front-end', 'index.html')

# API endpoint to execute commands
@app.route('/api/command', methods=['PUT'])
def execute_command():
    try:
        # Get the command from the request JSON
        data = request.get_json()
        if not data or 'command' not in data:
            return jsonify({'error': 'No command provided'}), 400
        
        command = data['command']
        
        # Validate that the command is not empty
        if not command.strip():
            return jsonify({'error': 'Empty command'}), 400
        
        # Execute the command using SafeCommandDispatcher
        result = dispatcher.execute_command(command)
        
        # Return success response
        return jsonify({
            'success': True,
            'command': command,
            'result': result
        }), 200
        
    except Exception as e:
        # Return error response
        return jsonify({
            'success': False,
            'error': str(e),
            'command': command if 'command' in locals() else 'unknown'
        }), 500

# Optional: Add a health check endpoint
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    # Make sure the HTML file exists
    if not os.path.exists('./front-end/index.html'):
        print("Warning: index.html not found in current directory")
        print("Please save the HTML content to 'index.html' in the same directory as this script")
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)