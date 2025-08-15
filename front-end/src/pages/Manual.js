import "../css/Basic.css"
import "../css/Manual.css"
import React, { useState, useEffect, useRef } from 'react';
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
    const [ac1Heartbeat, setac1Heartbeat] = useState(false);
    const [ac2Heartbeat, setac2Heartbeat] = useState(false);

    const [fanPower, setFanPower] = useState(0);

    const [ac1Mode, setac1Mode] = useState(false);
    const [ac2Mode, setac2Mode] = useState(false);

    const [ac1Preset, setac1Preset] = useState(false);
    const [ac2Preset, setac2Preset] = useState(false);

    const [ac1SetTemp, setac1SetTemp] = useState(60.0);
    const [ac2SetTemp, setac2SetTemp] = useState(60.0);

    const delayUpdate = useRef(false);
    const delayTimeoutId = useRef(null);

    async function handleDelayUpdate(delay = 10000) {
        if (delayTimeoutId.current) {
            clearTimeout(delayTimeoutId.current);
        }

        delayUpdate.current = true;

        delayTimeoutId.current = setTimeout(() => {
            delayUpdate.current = false;
            delayTimeoutId.current = null;
        }, delay);
    }

    // useEffect to update state when socketData changes
    useEffect(() => {
        if (socketData) {
            // Update control mode
            if (socketData.control !== undefined) {
                setCurrentMode(socketData.control);
            }

            const ac1HeartbeatData = socketData['living_room_ac.ac.heartbeat_status'];
            if (ac1HeartbeatData) {
                if (ac1HeartbeatData.status == "online") {
                    setac1Heartbeat(true);
                } else {
                    setac1Heartbeat(false);
                }
            }

            const ac2HeartbeatData = socketData['avery_room_ac.ac.heartbeat_status'];
            if (ac2HeartbeatData) {
                if (ac2HeartbeatData.status == "online") {
                    setac2Heartbeat(true);
                } else {
                    setac2Heartbeat(false);
                }
            }

            const hvacData = socketData['therm.heartbeat_status'];
            if (hvacData) {
                if (hvacData.status == "alive") {
                    setHvacHeartbeat(true);
                } else {
                    setHvacHeartbeat(false);
                }
            }

            const ryanRoomHeartbeat = socketData['ems2.heartbeat_status'];
            if (ryanRoomHeartbeat) {
                if (ryanRoomHeartbeat.status == "alive") {
                    setRyanRoomHeartbeat(true);
                } else {
                    setRyanRoomHeartbeat(false);
                }
            }

            const averyRoomHeartbeat = socketData['ems.heartbeat_status'];
            if (averyRoomHeartbeat) {
                if (averyRoomHeartbeat.status == "alive") {
                    setAveryRoomHeartbeat(true);
                } else {
                    setAveryRoomHeartbeat(false);
                }
            }

            const livingRoomHeartbeat = socketData['scrumpi.heartbeat_status'];
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

            // Update temperature data from avery room sensor
            const averyRoomData = socketData['averys_room.temp_sensor.temp_status'];
            if (averyRoomData) {
                if (averyRoomData.sensor_0 !== undefined) {
                    setAveryRoomTemp(averyRoomData.sensor_0.temperature);
                }
                if (averyRoomData.sensor_1 !== undefined) {
                    setRadTemp(averyRoomData.sensor_1.temperature);
                }
            }

            // Update temperature data from ryan room sensor
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

            // Only update AC states if we're not currently polling for changes
            const ac1ModeData = socketData['living_room_ac.ac.mode_status'];
            if (ac1ModeData && ac1ModeData.mode !== undefined && delayUpdate.current === false) {
                const newAc1Mode = ac1ModeData.mode !== 'off';
                setac1Mode(newAc1Mode);
            }

            const ac2ModeData = socketData['avery_room_ac.ac.mode_status'];
            if (ac2ModeData && ac2ModeData.mode !== undefined && delayUpdate.current === false) {
                const newAc2Mode = ac2ModeData.mode !== 'off';
                setac2Mode(newAc2Mode);
            }

            const ac1PresetData = socketData['living_room_ac.ac.preset_status'];
            if (ac1PresetData && ac1PresetData.preset !== undefined && delayUpdate.current === false) {
                const newAc1Preset = ac1PresetData.preset === 'boost';
                setac1Preset(newAc1Preset);
            }

            const ac2PresetData = socketData['avery_room_ac.ac.preset_status'];
            if (ac2PresetData && ac2PresetData.preset !== undefined && delayUpdate.current === false) {
                const newAc2Preset = ac2PresetData.preset === 'boost';
                setac2Preset(newAc2Preset);
            }

            const ac1SetTempData = socketData['living_room_ac.ac.target_temp_status'];
            if (ac1SetTempData && ac1SetTempData.target_temperature !== undefined) {
                setac1SetTemp((ac1SetTempData.target_temperature * 1.8 + 32).toFixed(0));
            }

            const ac2SetTempData = socketData['avery_room_ac.ac.target_temp_status'];
             if (ac2SetTempData && ac2SetTempData.target_temperature !== undefined) {
                setac2SetTemp((ac2SetTempData.target_temperature * 1.8 + 32).toFixed(0));
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

    const handleAC1TempSet = (newTemp) => {
        newTemp = (newTemp -32) / 1.8
        sendCommand("DIRECT", `controller.living_room_ac.ac.set_temp(${newTemp})`);
    };

    const handleAC2TempSet = (newTemp) => {
        newTemp = (newTemp -32) / 1.8
        sendCommand("DIRECT", `controller.avery_room_ac.ac.set_temp(${newTemp})`);
    };

    // Updated AC1 Mode handler with immediate state change and polling
    const handleAC1Mode = (newMode) => {
        handleDelayUpdate();

        // Immediately update the UI state
        setac1Mode(newMode);      

        // Send the command
        const toggle = newMode ? "on" : "off";
        sendCommand("DIRECT", `controller.living_room_ac.ac.turn_${toggle}()`);
    
    };

    // Updated AC2 Mode handler with immediate state change and polling
    const handleAC2Mode = (newMode) => {
        handleDelayUpdate();

        // Immediately update the UI state
        setac2Mode(newMode);

        // Send the command
        const toggle = newMode ? "on" : "off";
        sendCommand("DIRECT", `controller.avery_room_ac.ac.turn_${toggle}()`);
    };

    // Updated AC1 Preset handler with immediate state change and polling
    const handleAC1Preset = (newPreset) => {
        handleDelayUpdate();

        // Immediately update the UI state
        setac1Preset(newPreset);

        // Send the command
        sendCommand("DIRECT", `controller.living_room_ac.ac.set_boost_mode(${newPreset})`);
        
    };

    // Updated AC2 Preset handler with immediate state change and polling
    const handleAC2Preset = (newPreset) => {
        handleDelayUpdate();

        // Immediately update the UI state
        setac2Preset(newPreset);

        // Send the command
        sendCommand("DIRECT", `controller.avery_room_ac.ac.set_boost_mode(${newPreset})`);
    
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
                    <div className="Left-Line-2 text-outline" style={{display: "flex", alignItems: "center", justifyContent: "space-between"}}>
                        <NumberInput
                                label="Living Room Set Temp"
                                value={ac1SetTemp}
                                onSubmit={handleAC1TempSet}
                                min={60}
                                max={86}
                                step={1}
                                suffix=""
                                className=""
                            />
                    </div>
                    <div className="Left-Line-2 text-outline" style={{display: "flex", alignItems: "center", justifyContent: "space-between"}}>
                        <NumberInput
                                label="Avery's Room Set Temp"
                                value={ac2SetTemp}
                                onSubmit={handleAC2TempSet}
                                min={60}
                                max={86}
                                step={1}
                                suffix=""
                                className=""
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
                        <div className="Pink-Line-2">
                            <BooleanDisplay
                                label="Living Room AC Boost"
                                value={ac1Preset}
                                trueText="On"
                                falseText="Off"
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
                    <div className="Right-Line-2" style={{width: "100%"}}>
                        <div className="Pink-Line-2 sel-text" style={{width: "100%", marginTop: "20px"}}>
                    <span style={{marginLeft: "12px"}}>Avery's Room Valve: </span>
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
                    <div className="Pink-Line-2 sel-text" style={{width: "100%"}}>
                    <span style={{marginLeft: "12px"}}>Bathroom Valve: </span>
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
                    <div className="Pink-Line-2 sel-text" style={{width: "100%"}}>
                    <span style={{marginLeft: "12px"}}>Living Room AC: </span>
                    <div className="">
                        <BooleanToggle
                            value={ac1Mode}
                            onChange={handleAC1Mode}
                            onText="Turn Off"
                            offText="Turn On"
                            disabled={!isConnected}
                            variant="danger"
                            className="button"
                        />
                    </div>
                    </div>
                    <div className="Pink-Line-2 sel-text" style={{width: "100%"}}>
                    <span style={{marginLeft: "12px"}}>Living Room AC Boost: </span>
                    <div className="">
                        <BooleanToggle
                            value={ac1Preset}
                            onChange={handleAC1Preset}
                            onText="Disable"
                            offText="Enable"
                            disabled={!isConnected}
                            variant="danger"
                            className="button"
                        />
                    </div>
                    </div>
                    <div className="Pink-Line-2 sel-text" style={{width: "100%"}}>
                    <span style={{marginLeft: "12px"}}>Avery's Room AC: </span>
                    <div className="">
                        <BooleanToggle
                            value={ac2Mode}
                            onChange={handleAC2Mode}
                            onText="Turn Off"
                            offText="Turn On"
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

                    <div className={`Grid-Item Bold ${ac1Heartbeat ? "Greenbox" : "Redbox"}`}>Living Room AC</div>

                    <div className={`Grid-Item Bold ${ac2Heartbeat ? "Greenbox" : "Redbox"}`}>Avery's Room AC</div>                
                </div>
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