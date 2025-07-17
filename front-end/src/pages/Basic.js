import "../css/Basic.css"
import React, { useState, useEffect } from 'react';
import DarkModeToggle from "../components/ThemeSwitch";
import { isMobile } from 'react-device-detect';

function Basic({ socketData, socket, onOpenSettings }) {

    const mobileGrafanaLink = "http://temp.cfd/d/edubx296b5loge/thermostat?orgId=1&refresh=30s&kiosk";
    const desktopGrafanaLink = "http://temp.cfd/d/edubx296b5loge/thermostat?orgId=1&refresh=30s";

    const initialTemp = 75.0
    const initialSetTemp = 72.0

    const [AcMode, setAcMode] = useState(true); // Used for setting AC mode switch disabled/enabled 
    const [HeatMode, setHeatMode] = useState(false); // Used for setting Heat mode switch disabled/enabled 
    const [OffMode, setOffMode] = useState(false); // Used for setting Off mode switch disabled/enabled 

    const [HVACDisabled, setHVACDisabled] = useState(false); // Used for setting HVAC as the currently enabled equipment
    const [FanDisabled, setFanDisabled] = useState(false); // Used for setting Fan as the currently enabled equipment

    const [BasicControl, setBasicControl] = useState(true); // Used for Basic control button enable/disable
    const [ManualControl, setManualControl] = useState(false); // Used for Manual control button enable/disable
    const [AutoControl, setAutoControl] = useState(false)

    const [currentTemp, setCurrentTemp] = useState(initialTemp); // Used for setting the current temperature in the UI
    const [setTemp, setSetTemp] = useState(initialSetTemp); // Used for setting the set temperature in the UI

    const [setTempFinal, setSetTempFinal] = useState(initialSetTemp); // Value actually sent to the API. Used for keeping track of current

    // In this mode these buttons are mutually exclusive so one should always say enabled while the other says enable
    const [HVACButtonText, setHVACButtonText] = useState('Enabled'); // Used for setting text on the equipment HVAC enable button
    const [FanButtonText, setFanButtonText] = useState('Not Available'); // Used for setting text on the equipment Fan enable button

    const [HVACStatusText, setHVACStatusText] = useState('Running'); // Used for setting text on the equipment HVAC enable button
    const [FanStatusText, setFanStatusText] = useState('Not Running'); // Used for setting text on the equipment Fan enable button

    // In this mode these buttons are mutually exclusive so one should always say disabled
    const [HVACStatus, setHVACStatus] = useState(false); // Used for setting  on the equipment HVAC enable button
    const [FanStatus, setFanStatus] = useState(false); // Used for setting text on the equipment Fan enable button

    const [activeDevice, setActiveDevice] = useState("HVAC");

    const [HVACSuperDisabled, setHVACSuperDisabled] = useState(false);
    // This is currently set to true to disable the fan button
    const [FanSuperDisabled, setFanSuperDisabled] = useState(false);

    // Permanently disabled for now since manual mode doesn't exist yet
    const [ManualSuperDisabled, setManualSuperDisabled] = useState(false);

    // Unused right now since the settings page with the super disable stuff isn't ready yet
    const toggleHVACSuperDisable = () => setHVACSuperDisabled(!HVACSuperDisabled);
    const toggleFanSuperDisable = () => setFanSuperDisabled(!FanSuperDisabled);

    function sendPostRequest(command, data) {
        fetch('/data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ command: command, data: data })
        })
        .then(response => response.json())
        .then(data => {
            console.log('Success:', data);
        })
        .catch((error) => {
            console.error('Error:', error);
        });
    }

    useEffect(() => {
        if (socketData) {
            let mode = socketData.mode
            if (mode == "AC") {
                setAcMode(true)
                setHeatMode(false)
                setOffMode(false)             
            } else if (mode == "HEAT") {
                setAcMode(false)
                setHeatMode(true)
                setOffMode(false)
            } else if (mode == "OFF") {
                setAcMode(false)
                setHeatMode(false)
                setOffMode(true)
            }

            let control = socketData.control
            if (control == "BASIC") {
                setBasicControl(true)
                setManualControl(false)
                setAutoControl(false)
            } else if (control == "MANUAL") {
                setBasicControl(false)
                setManualControl(true)
                setAutoControl(false)
            }   else if (control == "AUTO") {
                setBasicControl(false)
                setManualControl(false)
                setAutoControl(true)
            }

            let ac_status = socketData.ac_status
            let heat_status = socketData.heat_status
            let fan_status = socketData.fan_status
            if (ac_status == true || heat_status == true) {
                setHVACStatusText('Running')
                setHVACStatus(true)
            } else {
                setHVACStatusText('Not Running')
                setHVACStatus(false)
            }

            if (fan_status == true) {
                setFanStatusText('Running')
                setFanStatus(true)
            } else {
                setFanStatusText('Not Running')
                setFanStatus(false)
            }

            let active_device = socketData.active_device
            if (active_device == "HVAC") {
                setFanDisabled(false)
                setHVACButtonText("Enabled")
                setFanButtonText("Switch to Fan")
                setHVACDisabled(true)
            } else if (active_device == "FAN") {
                setFanDisabled(true)
                setFanButtonText("Enabled")
                setHVACButtonText("Switch to HVAC")
                setHVACDisabled(false)
            }

            // Current logic for enabling/disabling devices based on their latest heartbeat
            let thermostat_heartbeat = socketData.thermostat_heartbeat
            let fan_heartbeat = socketData.fan_heartbeat
            setHVACSuperDisabled(!thermostat_heartbeat)
            setFanSuperDisabled(!fan_heartbeat)
            if (thermostat_heartbeat == false) {
                setHVACSuperDisabled(true)
                setHVACButtonText('Not Available')
                setHVACStatusText('Not Available')
            } else if (thermostat_heartbeat == true) {
                setHVACSuperDisabled(false)
            }
            if (fan_heartbeat == false) {
                setFanSuperDisabled(true)
                setFanButtonText('Not Available')
                setFanStatusText('Not Available')
            } else if (fan_heartbeat == true) {
                setFanSuperDisabled(false)
            }

            setCurrentTemp(socketData.current_temp.toFixed(1))
            setSetTempFinal(socketData.set_temp.toFixed(1))
            setSetTemp(socketData.set_temp.toFixed(1))

        }
    }, [socketData]);

    // Enable button logic is commented out for now since the Fan system is not set up
    function HVACEnableButtonHandler() {
        if (activeDevice == "HVAC") {
            setHVACButtonText('Switch to HVAC')
            setFanButtonText('Enabled')
            setActiveDevice("FAN")
            setFanDisabled(true)
            setHVACDisabled(false)
            sendPostRequest("DEVICE", "FAN")
        } else if (activeDevice == "FAN") {
            setHVACButtonText('Enabled')
            setFanButtonText('Switch to Fan')
            setActiveDevice("HVAC")
            setFanDisabled(false)
            setHVACDisabled(true)
            sendPostRequest("DEVICE", "HVAC")
        }
    }

    function ModeButtonHandler(value) {
        if (value == 'AC') {
            setAcMode(true)
            setHeatMode(false)
            setOffMode(false)
            sendPostRequest('MODE', value);
        } else if (value == 'HEAT') {
            setAcMode(false)
            setHeatMode(true)
            setOffMode(false)
            sendPostRequest('MODE', value);
        } else if (value == 'OFF') {
            setAcMode(false)
            setHeatMode(false)
            setOffMode(true)
            sendPostRequest('MODE', value);
        }
    }

    function ManualButtonHandler() {
        setBasicControl(!BasicControl)
        setManualControl(!ManualControl)
    }

    function BasicControlHandler() {
        ManualButtonHandler()
        sendPostRequest("CONTROL", "BASIC")
    }

    function ManualControlHandler() {
        ManualButtonHandler()
        sendPostRequest("CONTROL", "MANUAL")
    }

    function AutoControlHandler() {
        ManualButtonHandler()
        sendPostRequest("CONTROL", "AUTO")
    }

    function handleSetTemp(event) {
        let value = event.target.value
        if (isValidTemperature(value)) {
            value = Number(value)
            sendPostRequest('SET', value);
            setSetTemp(value)
            setSetTempFinal(value)
            console.log('Set temp changed')
        } else {
            console.log('NaN value set as set temp')
            setSetTemp(setTempFinal)
        }
        event.target.blur();     
    }

    const isValidTemperature = (value) => {
        const num = parseFloat(value);
        return !isNaN(num) && num >= 40 && num <= 90;
      };

    const handleSetTempChange = (e) => {
        setSetTemp(e.target.value);
    };

    const handleFocus = () => {
        setSetTemp('');
      };
    
    const handleKeyDown = (e) => {
        if (e.key === 'Enter') {
          handleSetTemp(e);
        }
    };

    return (
        <>
                <div className="HeaderContainer">
                    <div className="Header">
                        Thermostat
                    </div>
                </div>
                {socketData && (
                <div className="MainContainer">
                    <div className="LeftContainer">

                            <div className="Left-Line-1">
                                Set Temperature: <input className="Box" 
                                                        id="SetTemp" 
                                                        type="number"
                                                        value={setTemp}
                                                        onFocus={handleFocus}
                                                        onBlur={handleSetTemp}
                                                        onChange={handleSetTempChange}
                                                        onKeyDown={handleKeyDown}
                                                        enterKeyHint="done"
                                                        step="0.1"></input>
                            </div>
                            <div className="Left-Line-2">
                                Current Temperature: <div className="Box" id="CurrentTemp">{currentTemp}</div>
                            </div>
                            <div className="Pinkbox Left-Line-3">
                                <div className="Pink-Line-1">
                                    <div>HVAC:</div>
                                    <div id="HVAC-Status">{HVACStatusText}</div>
                                </div>
                                <div className="Pink-Line-2">
                                    <div>Fan:</div>
                                    <div id="Fan-Status">{FanStatusText}</div>
                                </div>
                            </div>
                            <div className="Left-Line-4">
                                Available Equipment:
                                <div className="Equip-Grid">
                                    <div className={`Grid-Item ${HVACSuperDisabled ? 'Redbox' : 'Greenbox'}`}>HVAC</div>
                                    <button onClick={() => HVACEnableButtonHandler()} disabled={HVACDisabled || HVACSuperDisabled} className="Pinkbox Grid-Item" data-super-disabled={HVACSuperDisabled ? "true" : undefined} id="HVAC-Enable">{HVACButtonText}</button>
                                    <div className={`Grid-Item ${FanSuperDisabled ? 'Redbox' : 'Greenbox'}`}>Fan</div>
                                    <button onClick={() => HVACEnableButtonHandler()} disabled={FanDisabled || FanSuperDisabled} className="Pinkbox Grid-Item" data-super-disabled={FanSuperDisabled ? "true" : undefined} id="Fan-Enable">{FanButtonText}</button>
                                </div>
                            </div>

                    </div>
                    <div className="RightContainer">
                        <div className="Right-Line-1">
                            System Mode:
                            <button onClick={() => ModeButtonHandler('AC')} disabled={AcMode} className="Bluebox" id="AC-Button">AC</button>
                            <button onClick={() => ModeButtonHandler('HEAT')} disabled={HeatMode} className="Orangebox" id="Heat-Button">Heat</button>
                            <button onClick={() => ModeButtonHandler('OFF')} disabled={OffMode} className="Redbox" id="OFF-Button">OFF</button>
                        </div>
                        <div className="Right-Line-2">
                            Control Scheme:
                            <button onClick={() => AutoControlHandler()} disabled={AutoControl} className="Pinkbox" id="Auto-Control">Auto</button>
                            <button onClick={() => BasicControlHandler()} disabled={BasicControl} className="Pinkbox" id="Basic-Control">Basic</button>
                            <button onClick={() => ManualControlHandler()} disabled={ManualControl} className="Pinkbox" id="Manual-Control">Manual</button>
                        </div>
                    </div>
                </div>
                )}
                <div className="FooterContainer">
                    <div className="Footer">
                        BASIC
                    </div>
                    <div className="GrafanaLink">
                    <i className="bi bi-gear" onClick={onOpenSettings}></i>
                    </div>
                    <DarkModeToggle>
                        <div className="GrafanaLink">
                        <i className="bi bi-lightbulb"></i>
                        </div>
                    </DarkModeToggle>
                    <a style={{ color: 'inherit', textDecoration: 'none' }} href={isMobile ? mobileGrafanaLink : desktopGrafanaLink} target="_blank" rel="noopener noreferrer">
                    <div className="GrafanaLink">
                        <i className="bi bi-database"></i>
                    </div>
                    </a>
                </div>

        </>
    );

}

export default Basic;