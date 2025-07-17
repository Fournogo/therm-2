import asyncio
import logging
import os
import sys
import yaml
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import socketio

# Import your async components
from ConfigLoader import create_device_controller
from State import create_async_state_manager
from ControlLoop import AsyncCommandProcessor

class AsyncThermostatApp:
    """Async thermostat application using FastAPI and SocketIO"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.app_config = config.get('app', {})
        self.flask_config = self.app_config.get('flask', {})
        self.state_config = config.get('state', {})
        self.control_config = config.get('control', {})
        
        # Initialize FastAPI
        self.app = FastAPI(title="Async Thermostat API")
        
        # Add CORS middleware to FastAPI
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # In production, be more specific
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Initialize SocketIO
        self.sio = socketio.AsyncServer(
            async_mode='asgi',
            cors_allowed_origins=self._get_cors_origins(),
            logger=True,
            engineio_logger=False
        )
        
        # Combine FastAPI and SocketIO
        self.combined_app = socketio.ASGIApp(self.sio, self.app)
        
        # Application components (will be initialized in setup)
        self.controller = None
        self.state_manager = None
        self.command_processor = None
        
        # Background tasks
        self.state_emission_task = None
        self.running = False
        
        # Setup logging
        self._setup_logging()
        
        # Setup routes and socket handlers
        self._setup_routes()
        self._setup_socketio()
    
    def _get_cors_origins(self):
        """Get CORS origins from config"""
        socketio_config = self.flask_config.get('socketio', {})
        return socketio_config.get('cors_allowed_origins', [
            "*",
            "https://therm.cfd:5023",
            "http://therm.cfd:5023", 
            "http://therm.cfd",
            "https://therm.cfd",
            "http://localhost:3001",
            "http://10.1.1.11:3001"
        ])
    
    def _setup_logging(self):
        """Setup logging configuration"""
        log_config = self.app_config.get('logging', {})
        logging.basicConfig(
            level=getattr(logging, log_config.get('level', 'INFO')),
            format=log_config.get('format', '%(asctime)s - %(levelname)s - %(message)s'),
            filename=log_config.get('filename', 'app.log'),
            filemode=log_config.get('filemode', 'a')
        )
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get("/")
        async def index():
            """Serve the main HTML file"""
            static_folder = self.flask_config.get('static_folder', './front-end/build')
            html_path = os.path.join(static_folder, 'index.html')
            
            if os.path.exists(html_path):
                return FileResponse(html_path)
            else:
                raise HTTPException(status_code=404, detail="Frontend not found")
        
        @self.app.get("/state")
        async def get_state():
            """Get current system state"""
            if not self.state_manager:
                raise HTTPException(status_code=503, detail="State manager not initialized")
            
            state = self.state_manager.get_all_states()
            return JSONResponse(self.serialize_state(state))
        
        @self.app.post("/data")
        async def receive_data(request: Request):
            """Receive commands from the frontend"""
            if not self.command_processor:
                raise HTTPException(status_code=503, detail="Command processor not initialized")
            
            try:
                data = await request.json()
                command = data.get('command')
                command_data = data.get('data')
                
                if not command:
                    raise HTTPException(status_code=400, detail="Missing command")
                
                # Add command to processor queue
                await self.command_processor.add_command(command, command_data)
                
                return JSONResponse({
                    'status': 'success', 
                    'command': command, 
                    'data': command_data
                })
                
            except Exception as e:
                logging.error(f"Error processing command: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # Mount static files for React build
        static_folder = self.flask_config.get('static_folder', './front-end/build')
        if os.path.exists(static_folder):
            # Check if there's a static subfolder (typical React build structure)
            static_subfolder = os.path.join(static_folder, "static")
            if os.path.exists(static_subfolder):
                # Mount the static subfolder to /static
                self.app.mount("/static", StaticFiles(directory=static_subfolder), name="static")
                print(f"Mounted static files from: {static_subfolder}")
            else:
                # Fallback: mount the entire build directory
                self.app.mount("/static", StaticFiles(directory=static_folder), name="static")
                print(f"Mounted static files from: {static_folder}")
            
            # Also serve other assets like manifest.json, favicon.ico, etc.
            try:
                self.app.mount("/", StaticFiles(directory=static_folder, html=True), name="frontend")
                print(f"Mounted frontend files from: {static_folder}")
            except Exception as e:
                print(f"Could not mount frontend files: {e}")
    
    def _setup_socketio(self):
        """Setup SocketIO event handlers"""
        
        @self.sio.event
        async def connect(sid, environ):
            """Handle client connection"""
            print(f'Client {sid} connected')
            
            # Send initial state to new client
            if self.state_manager:
                try:
                    current_state = self.state_manager.get_all_states()
                    await self.sio.emit('state_update', self.serialize_state(current_state), room=sid)
                    print(f"Sent initial state to client {sid}")
                except Exception as e:
                    logging.error(f"Error sending initial state to {sid}: {e}")
        
        @self.sio.event
        async def disconnect(sid):
            """Handle client disconnection"""
            print(f'Client {sid} disconnected')
        
        @self.sio.event
        async def request_state(sid):
            """Handle state request from client"""
            if self.state_manager:
                try:
                    current_state = self.state_manager.get_all_states()
                    await self.sio.emit('state_update', self.serialize_state(current_state), room=sid)
                    print(f"Sent requested state to client {sid}")
                except Exception as e:
                    logging.error(f"Error sending state to {sid}: {e}")
    
    async def initialize(self):
        """Initialize all application components"""
        print("Initializing async thermostat application...")
        
        try:
            # Initialize controller
            print("Creating device controller...")
            paths_config = self.config.get('paths', {})
            self.controller = await create_device_controller(
                paths_config.get('config_dir', '/home/scrumpi/containers/therm-2/configs'),
                component_path=paths_config.get('component_path', '/home/scrumpi/containers/therm-2')
            )
            print("✅ Device controller initialized")
            
            # Initialize state manager
            print("Creating async state manager...")
            self.state_manager = await create_async_state_manager(self.controller, self.state_config)
            print("✅ State manager initialized")
            
            # Initialize command processor
            print("Creating async command processor...")
            self.command_processor = AsyncCommandProcessor(
                self.controller, 
                self.state_manager, 
                self.control_config
            )
            print("✅ Command processor initialized")
            
            print("🚀 All components initialized successfully!")
            
        except Exception as e:
            logging.error(f"Failed to initialize application: {e}")
            raise
    
    async def start_background_tasks(self):
        """Start all background tasks"""
        print("Starting background tasks...")
        
        try:
            # Start state manager
            await self.state_manager.start_continuous_refresh()
            print("✅ State manager started")
            
            # Start command processor
            await self.command_processor.start_processing()
            print("✅ Command processor started")
            
            # Start state emission task
            self.state_emission_task = asyncio.create_task(self._state_emission_loop())
            print("✅ State emission loop started")
            
            self.running = True
            print("🚀 All background tasks started!")
            
        except Exception as e:
            logging.error(f"Failed to start background tasks: {e}")
            raise
    
    async def _state_emission_loop(self):
        """Emit state changes to all connected WebSocket clients"""
        try:
            print("State emission loop started")
            async for new_state in self.state_manager.get_state_updates():
                try:
                    serialized_state = self.serialize_state(new_state)
                    await self.sio.emit('state_update', serialized_state)
                    print(f"📡 Emitted state update to all clients ({len(new_state)} states)")
                    logging.info('State update emitted via WebSocket')
                except Exception as e:
                    logging.error(f"Error emitting state update: {e}")
        except asyncio.CancelledError:
            print("State emission loop cancelled")
        except Exception as e:
            logging.error(f"Error in state emission loop: {e}")
    
    async def shutdown(self):
        """Shutdown the application gracefully"""
        print("🛑 Shutting down application...")
        self.running = False
        
        try:
            # Cancel state emission task
            if self.state_emission_task and not self.state_emission_task.done():
                self.state_emission_task.cancel()
                try:
                    await self.state_emission_task
                except asyncio.CancelledError:
                    pass
            
            # Stop command processor
            if self.command_processor:
                await self.command_processor.stop_processing()
                print("✅ Command processor stopped")
            
            # Stop state manager
            if self.state_manager:
                await self.state_manager.stop_continuous_refresh()
                print("✅ State manager stopped")
            
            # Disconnect controller
            if self.controller:
                await self.controller.disconnect_all()
                print("✅ Controller disconnected")
            
            print("✅ Application shutdown complete")
            
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")
    
    def serialize_state(self, state):
        """Serialize state for JSON transmission"""
        def convert_value(value):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: convert_value(v) for k, v in value.items()}
            if isinstance(value, list):
                return [convert_value(i) for i in value]
            return value
        return convert_value(state)


def load_config(config_path='config.yaml'):
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        print(f"Config file {config_path} not found, using defaults")
        return {}
    except yaml.YAMLError as e:
        print(f"Error parsing config file: {e}")
        return {}


def main():
    """Main application entry point"""
    # Parse command line arguments
    if len(sys.argv) != 2:
        print("Usage: python3 App.py <config.yaml>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    
    # Load configuration
    config = load_config(config_path)
    if not config:
        print("❌ Failed to load configuration")
        sys.exit(1)
    
    # Create application
    app = AsyncThermostatApp(config)
    
    async def run_app():
        try:
            # Initialize components
            await app.initialize()
            
            # Start background tasks
            await app.start_background_tasks()
            
            # Get server configuration
            server_config = app.flask_config.get('server', {})
            host = server_config.get('host', '0.0.0.0')
            port = server_config.get('port', 5023)
            debug = server_config.get('debug', False)
            
            print(f"🌐 Starting server on {host}:{port}")
            print(f"🔧 Debug mode: {debug}")
            
            # Check if HTML file exists
            html_path = app.flask_config.get('html_path', './front-end/index.html')
            if not os.path.exists(html_path):
                print(f"⚠️  Warning: index.html not found at {html_path}")
            
            # Run the server using uvicorn.Server for async compatibility
            import uvicorn
            config = uvicorn.Config(
                app.combined_app,
                host=host,
                port=port,
                log_level="info" if debug else "warning"
            )
            server = uvicorn.Server(config)
            await server.serve()
            
        except KeyboardInterrupt:
            print("\n🛑 Received interrupt signal")
        except Exception as e:
            logging.error(f"❌ Application error: {e}")
            print(f"❌ Application error: {e}")
        finally:
            # Cleanup
            await app.shutdown()
    
    # Run the async application
    asyncio.run(run_app())


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)