import "../css/Basic.css"
import React, { useState, useEffect } from 'react';
import DarkModeToggle from "../components/ThemeSwitch";
import { isMobile } from 'react-device-detect';
import Countdown from 'react-countdown';

function Auto({ socketData, socket, onOpenSettings }) {

    const HVAC_TIME_DELTA = 4

    const mobileGrafanaLink = "http://temp.cfd/d/edubx296b5loge/thermostat?orgId=1&refresh=30s";
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

    const [HVACStatusText, setHVACStatusText] = useState('Running'); // Used for setting text on the equipment HVAC enable button
    const [FanStatusText, setFanStatusText] = useState('Not Running'); // Used for setting text on the equipment Fan enable button

    // In this mode these buttons are mutually exclusive so one should always say disabled
    const [HVACStatus, setHVACStatus] = useState(false); // Used for setting  on the equipment HVAC enable button
    const [FanStatus, setFanStatus] = useState(false); // Used for setting text on the equipment Fan enable button

    const [outsideDewp, setOutsideDewp] = useState(null);
    const [insideDewp, setInsideDewp] = useState(null);

    const [outsideTemp, setOutsideTemp] = useState(null);

    const [dryTime, setDry] = useState(5);
    const [dryFinal, setDryFinal] = useState(5);
    const [dryModeAvail, setDryModeAvail] = useState(true);
    const [dryButtonText, setDryButtonText] = useState('STINK!')

    const [setTempBackgroundColor, setSetTempBackgroundColor] = useState(null);

    const [currentTempBackgroundColor, setCurrentTempBackgroundColor] = useState(null);
    const [outsideTempBackgroundColor, setOutsideTempBackgroundColor] = useState(null);
    const [insideDewpBackgroundColor, setInsideDewpBackgroundColor] = useState(null);
    const [outsideDewpBackgroundColor, setOutsideDewpBackgroundColor] = useState(null);
    const [hvacTempBackgroundColor, setHvacTempBackgroundColor] = useState(null);

    const [dryingStop, setDryingStop] = useState(Date.now());
    const [dryingStatus, setDryingStatus] = useState(null);

    const [pauseStop, setPauseStop] = useState(Date.now());
    const [pauseStatus, setPauseStatus] = useState(null);
    const [pauseButtonText, setPauseButtonText] = useState("PAUSE!")

    const [modeCheckDisabled, setModeCheckDisabled] = useState(false);

    const [hvacMode, setHvacMode] = useState('AC');
    const [hvacTemp, setHvacTemp] = useState(null);

    const [systemMode, setSystemMode] = useState('AC');

    const [modeChangeAvail, setModeChangeAvail] = useState(false);
    const [modeChangeText, setModeChangeText] = useState('Change Mode')

    const [currentTempText, setCurrentTempText] = useState('Inside Temperature:')

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

    const interpolateHSLColor = (value, min=20, max=100, startHue=360, endHue=0) => {
        // Clamp the value within the range
        const clampedValue = Math.min(Math.max(value, min), max);
        // Map the value to a hue (0 = red, 120 = green, 240 = blue, 360 = red)
        const hue = ((clampedValue - min) / (max - min)) * (endHue - startHue);
        return `hsl(${hue}, 100%, 50%)`;
    };

    const interpolateRGBColor = (value, min=20, max=100, colors=['blue','red'], ) => {
        const clampedValue = Math.min(Math.max(value, min), max);
        const ratio = (clampedValue - min) / (max - min);
        const interpolate = require('color-interpolate');
        let colormap = interpolate(colors);
        return colormap(ratio);
    }

    useEffect(() => {
        if (socketData) {
            let mode = socketData.mode
            if (mode == "AC") {
                setAcMode(true)
                setHeatMode(false)
                setOffMode(false)
                setSystemMode("AC")
                setModeChangeText("Change to Heat")              
            } else if (mode == "HEAT") {
                setAcMode(false)
                setHeatMode(true)
                setOffMode(false)
                setSystemMode("HEAT")
                setModeChangeText("Change to AC") 
            } else if (mode == "OFF") {
                setAcMode(false)
                setHeatMode(false)
                setOffMode(true)
                setSystemMode("OFF") 
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
            } else if (control == "AUTO") {
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

            // Current logic for enabling/disabling devices based on their latest heartbeat
            let thermostat_heartbeat = socketData.thermostat_heartbeat
            let fan_heartbeat = socketData.fan_heartbeat

            let hvac_ability = socketData.hvac_ability;
            let fan_ability = socketData.fan_ability;
            if (thermostat_heartbeat == false) {
                setHVACStatusText('OFFLINE')
            } else if (hvac_ability == false) {
                setHVACStatusText('Disabled')
            }
            if (fan_heartbeat == false) {
                setFanStatusText('OFFLINE')
            } else if (fan_ability == false) {
                setFanStatusText('Disabled')
            }

            let inside_dewp = socketData.inside_dewp
            let outside_dewp = socketData.outside_dewp

            setInsideDewp(inside_dewp.toFixed(1))
            setOutsideDewp(outside_dewp.toFixed(1))

            if (fan_heartbeat == false) {
                setDryModeAvail(false)
            } else {
                setDryModeAvail(true)
            }

            let current_temp = socketData.current_temp
            let outside_temp = socketData.outside_temp
            let set_temp = socketData.set_temp

            setCurrentTemp(current_temp.toFixed(1))
            setOutsideTemp(outside_temp.toFixed(1))

            setSetTempFinal(set_temp.toFixed(1))
            setSetTemp(set_temp.toFixed(1))

            setCurrentTempBackgroundColor(interpolateHSLColor(current_temp, 60, 80))
            setOutsideTempBackgroundColor(interpolateHSLColor(outside_temp, 20, 100))

            setOutsideDewpBackgroundColor(interpolateHSLColor(outside_dewp, 20, 80))
            setInsideDewpBackgroundColor(interpolateHSLColor(inside_dewp, 20, 80))

            setSetTempBackgroundColor(interpolateHSLColor(set_temp, 50, 80))

            let drying_end = new Date(socketData.drying_end)
            setDryingStop(drying_end)
            setDryingStatus(socketData.drying_status)

            let pause_end = new Date(socketData.pause_end)
            setPauseStop(pause_end)
            setPauseStatus(socketData.pause_mode)

            if (socketData.pause_mode == true) {
                setPauseButtonText('UNPAUSE...')
            } else if (socketData.drying_status == false) {
                setPauseButtonText('PAUSE!')
            }

            if (socketData.drying_status == true) {
                setDryButtonText('NO STINK...')
            } else if (socketData.drying_status == false) {
                setDryButtonText('STINK!')
            }

            let last_hvac_event = new Date(socketData.last_hvac_event)
            const currentTime = new Date();
            let timeDifference = currentTime - last_hvac_event;

            if (ac_status == true || heat_status == true) {
                setModeCheckDisabled(true);
            } else {
                setModeCheckDisabled(false);
            }

            let hvac_mode = socketData.hvac_mode;
            setHvacMode(hvac_mode);

            let hvac_temp = socketData.hvac_temp;
            setHvacTemp(hvac_temp.toFixed(1));
            setHvacTempBackgroundColor(interpolateHSLColor(hvac_temp, 50, 90))

            let active_therm = socketData.active_therm;
            if (active_therm == "avery_room") {
                setCurrentTempText("Avery's Room Temp:")
            } else if (active_therm == "ryan_room") {
                setCurrentTempText("Ryan's Room Temp:")
            } else if (active_therm == "living_room") {
                setCurrentTempText("Living Room Temp:")
            }

            let mode_change_avail = socketData.mode_change_avail;
                setModeChangeAvail(mode_change_avail)
        }
    }, [socketData]);

    function ManualButtonHandler() {
        setBasicControl(!BasicControl)
        setManualControl(!ManualControl)
    }

    function BasicControlHandler() {
        ManualButtonHandler()
        sendPostRequest("CONTROL", "BASIC")
    }

    function AutoControlHandler() {
        ManualButtonHandler()
        sendPostRequest("CONTROL", "AUTO")
    }

    function ManualControlHandler() {
        ManualButtonHandler()
        sendPostRequest("CONTROL", "MANUAL")
    }

    function handleSetTemp(event) {
        let value = event.target.value
        if (isValidTemperature(value)) {
            value = Number(value)

            setSetTemp(value.toFixed(1))
            setSetTempFinal(value.toFixed(1))

            sendPostRequest('SET', value);

            console.log('Set temp changed')
        } else {
            console.log('NaN value set as set temp')
            setSetTemp(setTempFinal)
        }
        event.target.blur();     
    }

    function handleDry(event) {
        let value = event.target.value
        if (isValidTime(value)) {
            value = Number(value)
            setDry(value)
            setDryFinal(value)
            console.log('Dry mode set')
        } else {
            console.log('NaN value set as dry time')
            setDry(dryFinal)
        }
        event.target.blur();     
    }

    const isValidTime = (value) => {
        const num = parseFloat(value);
        return !isNaN(num) && num >= 0 && num <= 480;
      };

    function ModeCheckHandler() {
        sendPostRequest('HVAC MODE CHECK', 0)
    }

    function DryingModeHandler() {
        if (dryingStatus == false) {
            sendPostRequest('DRY', dryFinal)
        } else if (dryingStatus == true) {
            sendPostRequest('DRY CLEAR', 0)
        }
    }

    function ModeChangeHandler() {
        sendPostRequest('AUTO MODE CHANGE', 0)
    }

    function PauseModeHandler() {
        if (pauseStatus == false) {
            sendPostRequest('PAUSE START', dryFinal)
        } else if (pauseStatus == true) {
            sendPostRequest('PAUSE CLEAR', 0)
        }
    }

    const isValidTemperature = (value) => {
        const num = parseFloat(value);
        return !isNaN(num) && num >= 40 && num <= 90;
      };

    const handleSetTempChange = (e) => {
        setSetTemp(e.target.value);
    };

    const handleDryChange = (e) => {
        setDry(e.target.value);
    };

    const handleSetFocus = () => {
        setSetTemp('');
    };

    const handleDryFocus = () => {
        setDry('');
      };
    
    const handleSetKeyDown = (e) => {
        if (e.key === 'Enter') {
          handleSetTemp(e);
        }
    };

    const handleDryKeyDown = (e) => {
        if (e.key === 'Enter') {
          handleDry(e);
        }
    };

    const CountdownTimer = ({ stop }) => {
        return (
            <Countdown
                date={stop}
                zeroPadTime={2}
                daysInHours={true}
            />
        );
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
                                <span>{currentTempText}</span> <div style={{ backgroundColor: currentTempBackgroundColor }} className="Box" id="CurrentTemp">{currentTemp}</div>
                            </div>
                            <div className="Left-Line-2">
                                Set Temperature: <input className="Box" 
                                style={{ backgroundColor: setTempBackgroundColor }}
                                                        id="SetTemp" 
                                                        type="number"
                                                        value={setTemp}
                                                        onFocus={handleSetFocus}
                                                        onBlur={handleSetTemp}
                                                        onChange={handleSetTempChange}
                                                        onKeyDown={handleSetKeyDown}
                                                        enterKeyHint="done"
                                                        step="0.1"></input>
                            </div>
                            <div className="Left-Line-2">
                                Inside Dew Point: <div style={{ backgroundColor: insideDewpBackgroundColor }} className="Box" id="CurrentTemp">{insideDewp}</div>
                            </div>
                            <div className="Left-Line-2">
                                Outside Temperature: <div style={{ backgroundColor: outsideTempBackgroundColor }} className="Box" id="CurrentTemp">{outsideTemp}</div>
                            </div>
                            <div className="Left-Line-2">
                                Outside Dew Point: <div style={{ backgroundColor: outsideDewpBackgroundColor }} className="Box" id="CurrentTemp">{outsideDewp}</div>
                            </div>
                            <div className="Left-Line-2">
                                HVAC Temperature: <div style={{ backgroundColor: hvacTempBackgroundColor }} className="Box" id="CurrentTemp">{hvacTemp}</div>
                            </div>
                            {/* <div className="Left-Line-2">
                                HVAC Mode: <div style={{ backgroundColor: hvacMode === "HEAT" ? "red" : hvacMode === "AC" ? "blue" : "gray"}} className="Box" id="CurrentTemp">{hvacMode}</div>
                            </div> */}
                            
                            <div className="Pinkbox Left-Line-3">
                                <div className="HVAC-Mode">
                                HVAC Mode: <div style={{ backgroundColor: hvacMode === "HEAT" ? "red" : hvacMode === "AC" ? "blue" : "gray"}} className="Box" id="CurrentTemp">{hvacMode}</div>
                                </div>
                                <div className="HVAC-Mode">
                                System Mode: <div style={{ backgroundColor: systemMode === "HEAT" ? "red" : systemMode === "AC" ? "blue" : "gray"}} className="Box" id="CurrentTemp">{systemMode}</div>
                                </div>
                                <div className="Pink-Line-1">
                                    <div>HVAC:</div>
                                    <div id="HVAC-Status">{HVACStatusText}</div>
                                </div>
                                <div className="Pink-Line-2">
                                    <div>Fan:</div>
                                    <div id="Fan-Status">{FanStatusText}</div>
                                </div>
                            </div>

                            <button onClick={() => ModeCheckHandler()} disabled={modeCheckDisabled} className="Pinkbox Bold" id="Mode-Check-Button">HVAC Mode Check</button>

                    </div>
                    <div className="RightContainer">
                        <div className="Right-Line-1-Auto">
                        <button onClick={() => ModeChangeHandler()} disabled={!modeChangeAvail} className="Pinkbox Bold" id="AC-Button">{modeChangeText}</button>
                            
                            <div className="Right-Mid">
                                <span>Delay Input:</span> <input className="Box" 
                                                        id="DryTime" 
                                                        type="number"
                                                        value={dryTime}
                                                        onFocus={handleDryFocus}
                                                        onBlur={handleDry}
                                                        onChange={handleDryChange}
                                                        onKeyDown={handleDryKeyDown}
                                                        enterKeyHint="done"
                                                        step="0.1"></input>
                            </div>
                            <div className="Countdown-Container">
                                <span>Stink: </span>
                                <CountdownTimer stop={dryingStop} />
                            </div>
                            <button onClick={() => DryingModeHandler()} disabled={!dryModeAvail} className="Pinkbox" id="Dry-Button">{dryButtonText}</button>
                            <button onClick={() => PauseModeHandler()} className="Pinkbox" id="Dry-Button">{pauseButtonText}</button>
                            <div className="Countdown-Container">
                                <span>Pause: </span>
                                <CountdownTimer stop={pauseStop} />
                            </div>
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
                        AUTO
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

export default Auto;