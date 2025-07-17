import "../css/Basic.css"
import "../css/Settings.css"
import React, { useState, useEffect } from 'react';
import DarkModeToggle from "../components/ThemeSwitch";
import { isMobile } from 'react-device-detect';
import Countdown from 'react-countdown';

const ThermDropdown = ({ options, currentValue, onChange }) => {
  
    const handleChange = (event) => {
      const newValue = event.target.value;
      onChange(newValue); 
    };
  
    return (
      <select className="therm-dropdown" value={currentValue} onChange={handleChange}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  };

const TimeSelector = ({ currentDate, onChange }) => {
    const formatTime = (date) => {
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        return `${hours}:${minutes}`;
    };

    const handleTimeChange = (event) => {
        const [hours, minutes] = event.target.value.split(':').map(Number);
        const newDate = new Date(currentDate);
        newDate.setHours(hours, minutes);
        onChange(newDate); // Pass the updated Date object back to the parent
    };

    return (
        <input
        className = "time-selector"
        type="time"
        value={formatTime(currentDate)} // Format the current date to a time string
        onChange={handleTimeChange}
        />
    );
};

const interpolateHSLColor = (value, min=20, max=100, startHue=360, endHue=0) => {
    // Clamp the value within the range
    const clampedValue = Math.min(Math.max(value, min), max);
    // Map the value to a hue (0 = red, 120 = green, 240 = blue, 360 = red)
    const hue = ((clampedValue - min) / (max - min)) * (endHue - startHue);
    return `hsl(${hue}, 100%, 50%)`;
};

function Settings({ socketData, onBack }) {

    const mobileGrafanaLink = "http://temp.cfd/d/edubx296b5loge/thermostat?orgId=1&refresh=30s";
    const desktopGrafanaLink = "http://temp.cfd/d/edubx296b5loge/thermostat?orgId=1&refresh=30s";

    const [fanAbility, setFanAbility] = useState(true);
    const [hvacAbility, setHvacAbility] = useState(true);
    const [emsAbility, setEmsAbility] = useState(true);
    const [ems2Ability, setEms2Ability] = useState(true);

    const [fanAbilityText, setFanAbilityText] = useState('Active');
    const [hvacAbilityText, setHvacAbilityText] = useState('Active');
    const [emsAbilityText, setEmsAbilityText] = useState('Active');
    const [ems2AbilityText, setEms2AbilityText] = useState('Active');

    const [fanAbilityButtonText, setFanAbilityButtonText] = useState('Disable HVAC');
    const [hvacAbilityButtonText, setHvacAbilityButtonText] = useState('Disable Fan');

    const [hvacTempBackgroundColor, setHvacTempBackgroundColor] = useState(null);
    const [hvacTemp, setHvacTemp] = useState(null);

    const [thermSetting, setThermSetting] = useState('living_room');

    const [phase1BackgroundColor, setPhase1BackgroundColor] = useState(null);
    const [phase2BackgroundColor, setPhase2BackgroundColor] = useState(null);

    let now = new Date();

    const [phase1Time, setPhase1Time] = useState(now);
    const [phase2Time, setPhase2Time] = useState(now);

    const [phase1Temp, setPhase1Temp] = useState(66);
    const [phase2Temp, setPhase2Temp] = useState(66);

    const [phase1TempFinal, setPhase1TempFinal] = useState(66);
    const [phase2TempFinal, setPhase2TempFinal] = useState(66);

    const [scheduleActive, setScheduleActive] = useState(false);
    const [scheduleButtonText, setScheduleButtonText] = useState('Enable Scheduler');

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
            let thermostat_heartbeat = socketData.thermostat_heartbeat;
            let fan_heartbeat = socketData.fan_heartbeat;
            let ems_heartbeat = socketData.ems_heartbeat;
            let ems2_heartbeat = socketData.ems2_heartbeat;

            let hvac_ability = socketData.hvac_ability;
            let fan_ability = socketData.fan_ability;

            if (thermostat_heartbeat == false) {
                setHvacAbility(false)
                setHvacAbilityText('OFFLINE')
                setHvacAbilityButtonText('HVAC OFFLINE')
            } else if (hvac_ability == false) {
                setHvacAbility(false)
                setHvacAbilityText('Disabled')
                setHvacAbilityButtonText('Enable HVAC')
            } else {
                setHvacAbility(true)
                setHvacAbilityText('Active')
                setHvacAbilityButtonText('Disable HVAC')
            }

            if (fan_heartbeat == false) {
                setFanAbility(false)
                setFanAbilityText('OFFLINE')
                setFanAbilityButtonText('FAN OFFLINE')
            } else if (fan_ability == false) {
                setFanAbility(false)
                setFanAbilityText('Disabled')
                setFanAbilityButtonText('Enable Fan')
            } else {
                setFanAbility(true)
                setFanAbilityText('Active')
                setFanAbilityButtonText('Disable Fan')
            }

            if (ems_heartbeat == false) {
                setEmsAbilityText('OFFLINE')
                setEmsAbility(false)
            } else if (ems_heartbeat == true) {
                setEmsAbilityText('Active')
                setEmsAbility(true)
            }


            if (ems2_heartbeat == false) {
                setEms2AbilityText('OFFLINE')
                setEms2Ability(false)
            } else if (ems2_heartbeat == true) {
                setEms2AbilityText('Active')
                setEms2Ability(true)
            }

            let hvac_temp = socketData.hvac_temp;
            setHvacTemp(hvac_temp.toFixed(1));
            setHvacTempBackgroundColor(interpolateHSLColor(hvac_temp, 50, 90))

            let therm_setting = socketData.active_therm;
            setThermSetting(therm_setting);

            let phase_times = socketData.phase_times;

            let phase_1_time = new Date(phase_times[0])
            let phase_2_time = new Date(phase_times[1])

            setPhase1Time(phase_1_time);
            setPhase2Time(phase_2_time);

            let phase_temps = socketData.phase_sets;

            let phase_1_temp = phase_temps[0]
            let phase_2_temp = phase_temps[1]

            setPhase1Temp(phase_1_temp);
            setPhase1TempFinal(phase_1_temp);

            setPhase2Temp(phase_2_temp);
            setPhase2TempFinal(phase_2_temp);

            setPhase1BackgroundColor(interpolateHSLColor(phase_1_temp, 50, 80))
            setPhase2BackgroundColor(interpolateHSLColor(phase_2_temp, 50, 80))

            let active_phases = socketData.active_phases;
            if (active_phases.length > 0) {
                setScheduleActive(true);
                setScheduleButtonText('Disable Scheduler')
            } else {
                setScheduleActive(false);
                setScheduleButtonText('Enable Scheduler')
            }
        }
    }, [socketData]);

    function HvacAbilityHandler() {
        hvacAbility ? sendPostRequest("HVAC ABILITY", "OFF") : sendPostRequest("HVAC ABILITY", "ON");
    }

    function FanAbilityHandler() {
        fanAbility ? sendPostRequest("FAN ABILITY", "OFF") : sendPostRequest("FAN ABILITY", "ON");
    }

    function thermHandler(newValue) {
        sendPostRequest("CHANGE THERM", newValue)
    }

    const handlePhase1Change = (newTime) => {
        setPhase1Time(newTime);
        sendPostRequest("UPDATE PHASE TIME", [0, newTime.toISOString()])
    };

    const handlePhase2Change = (newTime) => {
        setPhase2Time(newTime);
        sendPostRequest("UPDATE PHASE TIME", [1, newTime.toISOString()])
    };

    const handlePhase1Focus = () => {
        setPhase1Temp('');
    };

    const handlePhase2Focus = () => {
        setPhase2Temp('');
    };

    const handlePhase1KeyDown = (e) => {
        if (e.key === 'Enter') {
          handlePhase1TempChange(e);
        }
    };

    const handlePhase2KeyDown = (e) => {
        if (e.key === 'Enter') {
          handlePhase2TempChange(e);
        }
    };

    const handlePhase1TempChange = (e) => {
        setPhase1Temp(e.target.value);
    };

    const handlePhase2TempChange = (e) => {
        setPhase2Temp(e.target.value);
    };

    function handlePhase1Temp(event) {
        let value = event.target.value
        if (value) {
            value = Number(value)

            setPhase1Temp(value.toFixed(1))
            setPhase1TempFinal(value.toFixed(1))

            sendPostRequest('UPDATE PHASE TEMP', [0, value]);

            console.log('Set temp changed')
        } else {
            console.log('NaN value set as set temp')
            setPhase1Temp(phase1TempFinal.toFixed(1))
        }
        event.target.blur();     
    }

    function handlePhase2Temp(event) {
        let value = event.target.value
        if (value) {
            value = Number(value)

            setPhase2Temp(value.toFixed(1))
            setPhase2TempFinal(value.toFixed(1))

            sendPostRequest('UPDATE PHASE TEMP', [1, value]);

            console.log('Set temp changed')
        } else {
            console.log('NaN value set as set temp')
            setPhase2Temp(phase2TempFinal.toFixed(1))
        }
        event.target.blur();     
    }

    function EnablePhases() {
        sendPostRequest('START PHASES', [0,1])
        setScheduleActive(true);
        setScheduleButtonText('Disable Scheduler')
    }

    function CancelPhases() {
        sendPostRequest('CANCEL PHASES', [0,1])
        setScheduleActive(false);
        setScheduleButtonText('Enable Scheduler')
    }

    const thermDropdownOptions = [
        { value: 'living_room', label: 'Living Room' },
        { value: 'avery_room', label: "Avery's Room" },
        { value: 'ryan_room', label: "Ryan's Room"}
    ];

    return (
        <>
        <div className="HeaderContainer">
                    <div className="Header">
                        Thermostat
                    </div>
        </div>
        <div className="MainContainer">
            <div className="LeftContainer">
            <div className="Left-Line-1">
            HVAC Functionality: <div style={{ backgroundColor: hvacAbility === true ? "green" : hvacAbility === false ? "red" : "gray"}} className="Box" id="CurrentTemp">{hvacAbilityText}</div>
            </div>
            <div className="Left-Line-2">
            Fan Functionality: <div style={{ backgroundColor: fanAbility === true ? "green" : fanAbility === false ? "red" : "gray"}} className="Box" id="CurrentTemp">{fanAbilityText}</div>
            </div>
            <div className="Left-Line-2">
            EMS Functionality: <div style={{ backgroundColor: emsAbility === true ? "green" : emsAbility === false ? "red" : "gray"}} className="Box" id="CurrentTemp">{emsAbilityText}</div>
            </div>
            <div className="Left-Line-2">
            EMS 2 Functionality: <div style={{ backgroundColor: ems2Ability === true ? "green" : ems2Ability === false ? "red" : "gray"}} className="Box" id="CurrentTemp">{ems2AbilityText}</div>
            </div>
            <div className="Left-Line-2">
            HVAC Temperature: <div style={{ backgroundColor: hvacTempBackgroundColor }} className="Box" id="CurrentTemp">{hvacTemp}</div>
            </div>
            <div className="Left-Line-2" style={{ marginBottom: '20px'}}><></>
            Active Thermostat: <ThermDropdown options={thermDropdownOptions} currentValue={thermSetting} onChange={thermHandler}/>
            </div>
            <div className="Left-Line-1">
            Scheduler: <div style={{ backgroundColor: scheduleActive === true ? "green" : scheduleActive === false ? "red" : "gray"}} className="Box" id="CurrentTemp">{scheduleActive ? "Active" : "Disabled"}</div>
            </div>
            <div className="Left-Line-2"><></>
            Phase 1 Start Time: <TimeSelector currentDate={phase1Time} onChange={handlePhase1Change} />
            </div>
            <div className="Left-Line-2">
                Phase 1 Set Temp: <input className="Box" 
                style={{ backgroundColor: phase1BackgroundColor }}
                                        id="SetTemp" 
                                        type="number"
                                        value={phase1Temp}
                                        onFocus={handlePhase1Focus}
                                        onBlur={handlePhase1Temp}
                                        onChange={handlePhase1TempChange}
                                        onKeyDown={handlePhase1KeyDown}
                                        enterKeyHint="done"
                                        step="0.1"></input>
            </div>
            <div className="Left-Line-2"><></>
            Phase 2 Start Time: <TimeSelector currentDate={phase2Time} onChange={handlePhase2Change} />
            </div>
            <div className="Left-Line-2 Extra-Bottom">
                Phase 2 Set Temp: <input className="Box" 
                style={{ backgroundColor: phase2BackgroundColor}}
                                        id="SetTemp" 
                                        type="number"
                                        value={phase2Temp}
                                        onFocus={handlePhase2Focus}
                                        onBlur={handlePhase2Temp}
                                        onChange={handlePhase2TempChange}
                                        onKeyDown={handlePhase2KeyDown}
                                        enterKeyHint="done"
                                        step="0.1"></input>
            </div>
            </div>
            <div className="RightContainer">
                <div className="Right-Line-1">
                <button onClick={() => onBack()} className="Pinkbox Bold" id="Auto-Control">Back</button>
                <button onClick={() => HvacAbilityHandler()} className="Pinkbox Bold" id="AC-Button">{hvacAbilityButtonText}</button>
                <button onClick={() => FanAbilityHandler()} className="Pinkbox Bold" id="Heat-Button">{fanAbilityButtonText}</button>
                <button onClick={() => (scheduleActive ? CancelPhases() : EnablePhases())} className="Pinkbox Bold" id="Auto-Control">{scheduleButtonText}</button>
                </div>
            </div>
        </div>
      <div className="FooterContainer">
                    <div className="Footer">
                        SETTINGS
                    </div>
                    <div className="GrafanaLink">
                    <i className="bi bi-gear" onClick={onBack}></i>
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
  
  export default Settings;