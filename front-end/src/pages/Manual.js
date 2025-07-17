import "../css/Basic.css"
import "../css/Manual.css"
import React, { useState, useEffect } from 'react';
import { useSocket } from '../SocketContext';
import DarkModeToggle from "../components/ThemeSwitch";
import { isMobile } from 'react-device-detect';

// Import our new components
import { 
  BooleanDisplay, 
  NumberInput, 
  BooleanToggle, 
  DeviceStatus, 
  TemperatureDisplay, 
  ControlModeSelector 
} from '../components/DataDisplay';

function Manual({ onOpenSettings }) {
    const { socketData, sendCommand, isConnected } = useSocket();

    const mobileGrafanaLink = "http://temp.cfd/d/edubx296b5loge/thermostat?orgId=1&refresh=30s&kiosk";
    const desktopGrafanaLink = "http://temp.cfd/d/edubx296b5loge/thermostat?orgId=1&refresh=30s";

    // React state for all our values
    const [currentMode, setCurrentMode] = useState('MANUAL');
    const [livingRoomTemp, setLivingRoomTemp] = useState(75.0);
    const [averyRoomTemp, setAveryRoomTemp] = useState(75.0);
    const [radTemp, setRadTemp] = useState(75.0);
    const [ryanRoomTemp, setRyanRoomTemp] = useState(75.0);
    const [currentHumidity, setCurrentHumidity] = useState(null);
    const [tempTimestamp, setTempTimestamp] = useState(null);
    const [averyValve, setAveryValve] = useState(false);
    const [bathroomValve, setBathroomValve] = useState(false);

    const [ryanRoomHeartbeat, setRyanRoomHeartbeat] = useState(false);
    const [averyRoomHeartbeat, setAveryRoomHeartbeat] = useState(false);
    const [livingRoomHeartbeat, setLivingRoomHeartbeat] = useState(false);
    const [hvacHeartbeat, setHvacHeartbeat] = useState(false);
    const [fanPower, setFanPower] = useState(0);

    // useEffect to update state when socketData changes
    useEffect(() => {
        if (socketData) {
            // Update control mode
            if (socketData.control !== undefined) {
                setCurrentMode(socketData.control);
            }

            const hvacData = socketData['hvac.heartbeat_status'];
            if (hvacData) {
                if (hvacData.status == "alive") {
                    setHvacHeartbeat(true);
                } else {
                    setHvacHeartbeat(false);
                }
            }

            const ryanRoomHeartbeat = socketData['ryans_room.heartbeat_status'];
            if (ryanRoomHeartbeat) {
                if (ryanRoomHeartbeat.status == "alive") {
                    setRyanRoomHeartbeat(true);
                } else {
                    setRyanRoomHeartbeat(false);
                }
            }

            const averyRoomHeartbeat = socketData['averys_room.heartbeat_status'];
            if (averyRoomHeartbeat) {
                if (averyRoomHeartbeat.status == "alive") {
                    setAveryRoomHeartbeat(true);
                } else {
                    setAveryRoomHeartbeat(false);
                }
            }

            const livingRoomHeartbeat = socketData['living_room.heartbeat_status'];
            if (livingRoomHeartbeat) {
                if (livingRoomHeartbeat.status == "alive") {
                    setLivingRoomHeartbeat(true);
                } else {
                    setLivingRoomHeartbeat(false);
                }
            }

            // Update temperature data from living room sensor
            const livingRoomData = socketData['living_room.temp_sensor.temp_status'];
            if (livingRoomData) {
                if (livingRoomData.temperature !== undefined) {
                    setLivingRoomTemp(livingRoomData.temperature);
                }
                if (livingRoomData.humidity !== undefined) {
                    setCurrentHumidity(livingRoomData.humidity);
                }
                if (livingRoomData.timestamp !== undefined) {
                    setTempTimestamp(livingRoomData.timestamp);
                }
            }

                        // Update temperature data from living room sensor
            const averyRoomData = socketData['averys_room.temp_sensor.temp_status'];
            if (averyRoomData) {
                if (averyRoomData.sensor_0 !== undefined) {
                    setAveryRoomTemp(averyRoomData.sensor_0.temperature);
                }
                if (averyRoomData.sensor_1 !== undefined) {
                    setRadTemp(averyRoomData.sensor_1.temperature);
                }
            }

                                    // Update temperature data from living room sensor
            const ryanRoomData = socketData['ryans_room.temp_sensor.temp_status'];
            if (ryanRoomData) {
                if (ryanRoomData.temperature !== undefined) {
                    setRyanRoomTemp(ryanRoomData.temperature);
                }
            }

            // Update fan power
            const fanData = socketData['hvac.fan.fan_status'];
            if (fanData && fanData.power !== undefined) {
                setFanPower(fanData.power);
            }

            // Update Avery's valve
            const averyValveData = socketData['hvac.avery_valve.relay_status'];
            if (averyValveData && averyValveData.relay !== undefined) {
                setAveryValve(averyValveData.relay);
            }

            // Update bathroom valve
            const bathroomValveData = socketData['hvac.bathroom_valve.relay_status'];
            if (bathroomValveData && bathroomValveData.relay !== undefined) {
                setBathroomValve(bathroomValveData.relay);
            }

            // Debug logging
            console.log('State Update:', {
                control: socketData.control,
                temp: livingRoomData?.temperature,
                fanPower: fanData?.power,
                averyValve: averyValveData?.relay,
                bathroomValve: bathroomValveData?.relay,
                rawTempData: livingRoomData,
                rawFanData: fanData,
                rawAveryData: averyValveData,
                rawBathroomData: bathroomValveData
            });
        }
    }, [socketData]); // Re-run when socketData changes

    // Handle mode changes
    const handleModeChange = (newMode) => {
        sendCommand("CONTROL", newMode);
    };

    // Handle Avery's valve toggle
    const handleAveryValveToggle = (newState) => {
        const action = newState ? "controller.hvac.avery_valve.on()" : "controller.hvac.avery_valve.off()";
        sendCommand("DIRECT", action);
    };

    // Handle Bathroom valve toggle  
    const handleBathroomValveToggle = (newState) => {
        const action = newState ? "controller.hvac.bathroom_valve.on()" : "controller.hvac.bathroom_valve.off()";
        sendCommand("DIRECT", action);
    };

    // Handle fan power setting
    const handleFanPowerSet = (newPower) => {
        sendCommand("DIRECT", `controller.hvac.fan.set_power(power=${newPower})`);
    };

    // Send direct device commands (for testing)
    const sendDirectCommand = (command) => {
        sendCommand("DIRECT", command);
    };

    // Show loading or disconnected state
    if (!isConnected || !socketData) {
        return (
            <div className="HeaderContainer">
                <div className="Header">
                    Thermostat - {isConnected ? 'Loading...' : 'Disconnected'}
                </div>
            </div>
        );
    }

    return (
        <>
            <div className="HeaderContainer">
                <div className="Header">
                    Thermostat
                </div>
            </div>
            
            <div className="MainContainer">
                <div className="LeftContainer" id="ManualLeftContainer">
                    <div className="Left-Line-2">
                        <TemperatureDisplay
                            label="Living Room Temperature"
                            temperature={livingRoomTemp}
                        />
                    </div>
                    <div className="Left-Line-2">
                        <TemperatureDisplay
                            label="Avery's Room Temperature"
                            temperature={averyRoomTemp}
                        />
                    </div>
                    <div className="Left-Line-2">
                        <TemperatureDisplay
                            label="Ryan's Room Temperature"
                            temperature={ryanRoomTemp}
                        />
                    </div>
                    <div className="Left-Line-2 text-outline">
                        <TemperatureDisplay
                            label="Radiator Temperature"
                            temperature={radTemp}
                        />
                    </div>
                    
                    <div className="Pinkbox Left-Line-3" id="ManualLeftLine3">
                        <div className="Pink-Line-2">
                            <BooleanDisplay
                                label="Avery's Room Valve"
                                value={averyValve}
                                trueText="Open"
                                falseText="Closed"
                                trueColor="#11e743ff"
                                falseColor="#e80e0eff"
                            />
                        </div>
                        <div className="Pink-Line-2">
                            <BooleanDisplay
                                label="Bathroom Valve"
                                value={bathroomValve}
                                trueText="Open"
                                falseText="Closed"
                                trueColor="#11e743ff"
                                falseColor="#e80e0eff"
                            />
                        </div>
                        <div className="Pink-Line-3">
                            <NumberInput
                                label="Fan Power"
                                value={fanPower}
                                onSubmit={handleFanPowerSet}
                                min={0}
                                max={8}
                                step={1}
                                suffix=""
                                className="fan-power-input"
                            />
                        </div>
                    </div>
                </div>
                
                <div className="RightContainer" id="ManualRightContainer">
                    <div className="Right-Line-2">
                        <div className="Pink-Line-2" style={{width: "100%", marginTop: "20px"}}>
                    <span>Avery's Room Valve: </span>
                    <div className="">
                        <BooleanToggle
                            value={averyValve}
                            onChange={handleAveryValveToggle}
                            onText="Close Valve"
                            offText="Open Valve"
                            disabled={!isConnected}
                            variant="danger"
                            className="button"
                        />
                    </div>
                    </div>
                    <div className="Pink-Line-2" style={{width: "100%"}}>
                    <span>Bathroom Valve: </span>
                    <div className="">
                        <BooleanToggle
                            value={bathroomValve}
                            onChange={handleBathroomValveToggle}
                            onText="Close Valve"
                            offText="Open Valve"
                            disabled={!isConnected}
                            variant="danger"
                            className="button"
                        />
                    </div>
                    </div>
                    <div className="Right-Line-2">
                        <ControlModeSelector
                            currentMode={currentMode}
                            onModeChange={handleModeChange}
                            disabled={true}
                        />
                    </div>

                    </div>
                </div>
            </div>
            
            <div className="Left-Line-4" id="ManualLeftLine4">
                Available Equipment:
                <div className="Left-Line-2">
                    {/* Avery's Room Valve Control */}
                    <div className={`Grid-Item Bold ${hvacHeartbeat ? "Greenbox" : "Redbox"}`}>Therm</div>

                    <div className={`Grid-Item Bold ${livingRoomHeartbeat ? "Greenbox" : "Redbox"}`}>Scrumpi</div>

                    <div className={`Grid-Item Bold ${ryanRoomHeartbeat ? "Greenbox" : "Redbox"}`}>EMS 2</div>
                    
                    <div className={`Grid-Item Bold ${averyRoomHeartbeat ? "Greenbox" : "Redbox"}`}>EMS</div>
                
                </div>
                
                {/* Debug Section - Remove in production */}
                {/* <div style={{ marginTop: '20px', padding: '10px', background: '#494949ff', borderRadius: '4px' }}>
                    <h5>Debug Controls:</h5>
                    <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' }}>
                        <button 
                            onClick={() => sendDirectCommand('controller.hvac.avery_valve.on()')}
                            style={{ padding: '5px 10px', fontSize: '12px' }}
                        >
                            Avery Valve On
                        </button>
                        <button 
                            onClick={() => sendDirectCommand('controller.hvac.avery_valve.off()')}
                            style={{ padding: '5px 10px', fontSize: '12px' }}
                        >
                            Avery Valve Off
                        </button>
                        <button 
                            onClick={() => sendDirectCommand('controller.hvac.bathroom_valve.on()')}
                            style={{ padding: '5px 10px', fontSize: '12px' }}
                        >
                            Bathroom Valve On
                        </button>
                        <button 
                            onClick={() => sendDirectCommand('controller.hvac.bathroom_valve.off()')}
                            style={{ padding: '5px 10px', fontSize: '12px' }}
                        >
                            Bathroom Valve Off
                        </button>
                        <button 
                            onClick={() => sendDirectCommand('controller.hvac.fan.set_power(power=5)')}
                            style={{ padding: '5px 10px', fontSize: '12px' }}
                        >
                            Fan Power 5
                        </button>
                        <button 
                            onClick={() => sendDirectCommand('controller.hvac.fan.set_power(power=0)')}
                            style={{ padding: '5px 10px', fontSize: '12px' }}
                        >
                            Fan Off
                        </button>
                        <button 
                            onClick={() => sendDirectCommand('controller.hvac.temp_sensor.read_temp(units="f")')}
                            style={{ padding: '5px 10px', fontSize: '12px' }}
                        >
                            Read Temp
                        </button>
                    </div>
                    

                    <details style={{ marginTop: '10px' }}>
                        <summary style={{ cursor: 'pointer', fontWeight: 'bold' }}>Raw State Data</summary>
                        <pre style={{ 
                            background: 'rgb(65, 65, 65)', 
                            padding: '10px', 
                            borderRadius: '4px', 
                            fontSize: '10px',
                            maxHeight: '400px',
                            overflow: 'auto'
                        }}>
                            {JSON.stringify(socketData, null, 2)}
                        </pre>
                    </details>
                </div> */}
            </div>
            
            <div className="FooterContainer">
                <div className="Footer">
                    MANUAL
                </div>
                <div className="GrafanaLink">
                    <i className="bi bi-gear" onClick={onOpenSettings}></i>
                </div>
                <DarkModeToggle>
                    <div className="GrafanaLink">
                        <i className="bi bi-lightbulb"></i>
                    </div>
                </DarkModeToggle>
                <a 
                    style={{ color: 'inherit', textDecoration: 'none' }} 
                    href={isMobile ? mobileGrafanaLink : desktopGrafanaLink} 
                    target="_blank" 
                    rel="noopener noreferrer"
                >
                    <div className="GrafanaLink">
                        <i className="bi bi-database"></i>
                    </div>
                </a>
            </div>
        </>
    );
}

export default Manual;