import "../css/Basic.css"
import "../css/Manual.css"
import React, { useState, useEffect } from 'react';
import { useSocket } from '../SocketContext';
import DarkModeToggle from "../components/ThemeSwitch";
import { isMobile } from 'react-device-detect';

function Manual({ onOpenSettings }) {
    const { socketData, sendCommand, isConnected } = useSocket();

    const mobileGrafanaLink = "http://temp.cfd/d/edubx296b5loge/thermostat?orgId=1&refresh=30s&kiosk";
    const desktopGrafanaLink = "http://temp.cfd/d/edubx296b5loge/thermostat?orgId=1&refresh=30s";

    const initialTemp = 75.0
    const initialSetTemp = 72.0

    const [HVACEnable, setHVACEnable] = useState(false); // Used for setting HVAC as the currently enabled equipment
    const [FanEnable, setFanEnable] = useState(false); // Used for setting Fan as the currently enabled equipment

    const [BasicControl, setBasicControl] = useState(false); // Used for Basic control button enable/disable. True means disable
    const [ManualControl, setManualControl] = useState(true); // Used for Manual control button enable/disable. True means disable
    const [AutoControl, setAutoControl] = useState(false)

    const [currentTemp, setCurrentTemp] = useState(initialTemp); // Used for setting the current temperature in the UI

    // In this mode these buttons are mutually exclusive so one should always say enabled while the other says enable
    const [HVACButtonText, setHVACButtonText] = useState('Enabled'); // Used for setting text on the equipment HVAC enable button
    const [FanButtonText, setFanButtonText] = useState('Disabled'); // Used for setting text on the equipment Fan enable button

    const [HVACStatusText, setHVACStatusText] = useState('Running'); // Used for setting text on the equipment HVAC enable button
    const [FanStatusText, setFanStatusText] = useState('Disabled'); // Used for setting text on the equipment Fan enable button

    const [HVACStatus, setHVACStatus] = useState(false); // true if ac is running, false otherwise
    const [FanStatus, setFanStatus] = useState(false); // true if fan is running, false otherwise

    const [HVACSuperDisabled, setHVACSuperDisabled] = useState(false);
    // This is currently set to true to disable the fan button
    const [FanSuperDisabled, setFanSuperDisabled] = useState(true);

    // Unused right now since the settings page with the super disable stuff isn't ready yet
    const toggleHVACSuperDisable = () => setHVACSuperDisabled(!HVACSuperDisabled);
    const toggleFanSuperDisable = () => setFanSuperDisabled(!FanSuperDisabled);

    useEffect(() => {
        if (socketData) {

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
                setHVACButtonText("Turn Off")
                setHVACStatus(true)
            } else {
                setHVACStatusText('Not Running')
                setHVACButtonText("Turn On")
                setHVACStatus(false)
            }

            if (fan_status == true) {
                setFanStatusText('Running')
                setFanButtonText("Turn Off")
                setFanStatus(true)
            } else {
                setFanStatusText('Not Running')
                setFanButtonText("Turn On")
                setFanStatus(false)
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

            //setCurrentTemp(socketData.current_temp.toFixed(1))
        }
    }, [socketData]);

    function ManualButtonHandler() {
        setBasicControl(!BasicControl)
        setManualControl(!ManualControl)
    }

    function BasicControlHandler() {
        ManualButtonHandler()
        sendCommand("CONTROL", "BASIC")
    }

    function ManualControlHandler() {
        ManualButtonHandler()
        sendCommand("CONTROL", "MANUAL")
    }

    function AutoControlHandler() {
        ManualButtonHandler()
        sendCommand("CONTROL", "AUTO")
    }

    function EnableHVAC() {
        if (HVACStatus == true) {
            sendCommand("MANUAL AC", "OFF")
            setHVACButtonText("Turn On")
        } else if (HVACStatus == false) {
            sendCommand("MANUAL AC", "ON")
            setHVACButtonText("Turn Off")
        }
    }

    function EnableFan() {
        if (FanStatus == true) {
            sendCommand("MANUAL FAN", "OFF")
            setFanButtonText("Turn On")
        } else if (FanStatus == false) {
            sendCommand("MANUAL FAN", "ON")
            setFanButtonText("Turn Off")
        }
    }

    // Show loading or disconnected state if no socket data
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
                            Current Temperature: <div className="Box" id="CurrentTemp">{currentTemp}</div>
                        </div>
                        <div className="Pinkbox Left-Line-3" id="ManualLeftLine3">
                            <div className="Pink-Line-1">
                                <div>HVAC:</div>
                                <div id="HVAC-Status">{HVACStatusText}</div>
                            </div>
                            <div className="Pink-Line-2">
                                <div>Fan:</div>
                                <div id="Fan-Status">{FanStatusText}</div>
                            </div>
                        </div>
                </div>
                <div className="RightContainer" id="ManualRightContainer">
                    <div className="Right-Line-2">
                        Control Scheme:
                        <button onClick={() => AutoControlHandler()} disabled={AutoControl} className="Pinkbox" id="Auto-Control">Auto</button>
                        <button onClick={() => BasicControlHandler()} disabled={BasicControl} className="Pinkbox" id="Basic-Control">Basic</button>
                        <button onClick={() => ManualControlHandler()} disabled={ManualControl} className="Pinkbox" id="Manual-Control">Manual</button>
                    </div>
                </div>
            </div>
            <div className="Left-Line-4" id="ManualLeftLine4">
            Available Equipment:
            <div className="Equip-Grid">
                <div className={`Grid-Item ${HVACSuperDisabled ? 'Redbox' : 'Greenbox'}`}>HVAC</div>
                <button onClick={() => EnableHVAC()} disabled={HVACEnable} className={HVACSuperDisabled ? "Redbox Grid-Item" : "Greenbox Grid-Item"} data-super-disabled={HVACSuperDisabled ? "true" : undefined} id="HVAC-Enable">{HVACButtonText}</button>
                <div className={`Grid-Item ${FanSuperDisabled ? 'Redbox' : 'Greenbox'}`}>Fan</div>
                <button onClick={() => EnableFan()} disabled={FanEnable} className={FanSuperDisabled ? "Redbox Grid-Item" : "Greenbox Grid-Item"} data-super-disabled={FanSuperDisabled ? "true" : undefined} id="Fan-Enable">{FanButtonText}</button>
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
                <a style={{ color: 'inherit', textDecoration: 'none' }} href={isMobile ? mobileGrafanaLink : desktopGrafanaLink} target="_blank" rel="noopener noreferrer">
                <div className="GrafanaLink">
                    <i className="bi bi-database"></i>
                </div>
                </a>
            </div>
        </>
    );

}

export default Manual;