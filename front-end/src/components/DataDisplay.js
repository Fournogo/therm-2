// components/DataDisplay.js
import React, { useState, useEffect } from 'react';

  const interpolateHSLColor = (value, min=60, max=80, startHue=360, endHue=0) => {
    // Clamp the value within the range
    const clampedValue = Math.min(Math.max(value, min), max);
    // Map the value to a hue (0 = red, 120 = green, 240 = blue, 360 = red)
    const hue = ((clampedValue - min) / (max - min)) * (endHue - startHue);
    return `hsl(${hue}, 100%, 50%)`;
  };

  // Convert HSL to RGB
const hslToRgb = (h, s, l) => {
  h /= 360;
  s /= 100;
  l /= 100;
  
  const hue2rgb = (p, q, t) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1/6) return p + (q - p) * 6 * t;
    if (t < 1/2) return q;
    if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
    return p;
  };
  
  if (s === 0) {
    return [l, l, l]; // achromatic
  }
  
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const r = hue2rgb(p, q, h + 1/3);
  const g = hue2rgb(p, q, h);
  const b = hue2rgb(p, q, h - 1/3);
  
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
};

// Calculate relative luminance using WCAG formula
const getLuminance = (r, g, b) => {
  const [rs, gs, bs] = [r, g, b].map(c => {
    c = c / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
};

// Get contrasting text color (black or white) based on background color
const getContrastingTextColor = (hslColor) => {
  // Parse HSL string like "hsl(120, 100%, 50%)"
  const hslMatch = hslColor.match(/hsl\((\d+),\s*(\d+)%,\s*(\d+)%\)/);
  if (!hslMatch) return '#222222ff'; // fallback to black
  
  const [, h, s, l] = hslMatch.map(Number);
  const [r, g, b] = hslToRgb(h, s, l);
  const luminance = getLuminance(r, g, b);
  
  // WCAG recommendation: use white text if luminance < 0.5, black if >= 0.5
  return luminance < 0.5 ? '#ffffff' : '#272727ff';
};
/**
 * Boolean Data Display - Shows a boolean value with color coding
 */
export const BooleanDisplay = ({ 
  label, 
  value, 
  trueText = "ON", 
  falseText = "OFF",
  trueColor = "green",
  falseColor = "red",
  className = ""
}) => {
  const displayValue = value ? trueText : falseText;
  const color = value ? trueColor : falseColor;
  
  return (
    <>
      <span className={`boolean-display ${className}`}>{label}:</span>
      <span 
        className="value" 
        style={{ 
          color: color, 
          fontWeight: 'bold',
          marginLeft: '8px'
        }}
      >
        {displayValue}
      </span>
    </>
  );
};

/**
 * Numerical Input Field - Shows current value, allows editing
 */
export const NumberInput = ({ 
  label, 
  value, 
  onChange, 
  onSubmit,
  suffix = "",
  min,
  max,
  step = 1,
  className = "",
  disabled = false
}) => {
  const [editValue, setEditValue] = React.useState(value);
  const [isEditing, setIsEditing] = React.useState(false);

    const interpolateHSLColor = (value, min=0, max=10, startHue=360, endHue=0) => {
    // Clamp the value within the range
    const clampedValue = Math.min(Math.max(value, min), max);
    // Map the value to a hue (0 = red, 120 = green, 240 = blue, 360 = red)
    const hue = ((clampedValue - min) / (max - min)) * (endHue - startHue);
    return `hsl(${hue}, 100%, 50%)`;
  };

  let currentBackgroundColor = interpolateHSLColor(value, min, max)
  let inverseColor = getContrastingTextColor(currentBackgroundColor)

  React.useEffect(() => {
    setEditValue(value);
  }, [value]);

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSubmit();
    }
  };

  const handleBlur = () => {
    handleSubmit();
  };

  const handleSubmit = () => {
    setIsEditing(false);
    const numValue = parseFloat(editValue);
    if (!isNaN(numValue) && numValue !== value) {
      if (onSubmit) {
        onSubmit(numValue);
      } else if (onChange) {
        onChange(numValue);
      }
    } else {
      setEditValue(value); // Reset if invalid
    }
  };

  const handleFocus = () => {
    setIsEditing(true);
  };

  return (
<>
      {label && <span className={`number-input ${className}`}>{label}:</span>}
      <input className="Box" 
        style={{ backgroundColor: currentBackgroundColor }}
        id="SetTemp" 
        type="number"
        value={editValue}
        min={min}
        max={max}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onChange={(e) => setEditValue(e.target.value)}
        onKeyDown={handleKeyPress}
        disabled={disabled}
        step={step}
        enterKeyHint="done"
        ></input>
</>
  );
};

/**
 * Boolean Toggle Button - Interactive button for boolean values
 */
export const BooleanToggle = ({ 
  label, 
  value, 
  onChange,
  onText = "Turn Off",
  offText = "Turn On",
  disabled = false,
  loading = false,
  className = "",
  variant = "default" // "default", "success", "danger"
}) => {
  const getButtonClass = () => {
    let baseClass = "boolean-toggle";
    
    if (disabled) {
      baseClass += " disabled";
    } else if (value) {
      baseClass += variant === "danger" ? " btn-danger" : " btn-success";
    } else {
      baseClass += " btn-primary";
    }
    
    return `${baseClass} ${className}`;
  };

  const handleClick = () => {
    if (!disabled && !loading && onChange) {
      onChange(!value);
    }
  };

  return (
    <div className="boolean-toggle-container">
      {label && <span className="toggle-label">{label}:</span>}
      <button
        onClick={handleClick}
        disabled={disabled || loading}
        className={getButtonClass()}
        style={{
          marginLeft: label ? '8px' : '0',
          padding: '8px 16px',
          borderRadius: '4px',
          border: 'none',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.6 : 1,
          width: '200px'
        }}
      >
        {loading ? 'Loading...' : (value ? onText : offText)}
      </button>
    </div>
  );
};

/**
 * Device Status Component - Shows device name, status, and control
 */
export const DeviceStatus = ({
  deviceName,
  status,
  onToggle,
  heartbeat = true,
  className = ""
}) => {
  const isOnline = heartbeat;
  const isRunning = status && status.relay !== false;

  const getStatusText = () => {
    if (!isOnline) return "Not Available";
    return isRunning ? "Running" : "Not Running";
  };

  const getStatusColor = () => {
    if (!isOnline) return "#999";
    return isRunning ? "#28a745" : "#6c757d";
  };

  const getButtonText = () => {
    if (!isOnline) return "Not Available";
    return isRunning ? "Turn Off" : "Turn On";
  };

  return (
    <div className={`device-status ${className}`}>
      <div className="device-header">
        <span className="device-name">{deviceName}</span>
        <span 
          className="device-status-text"
          style={{ color: getStatusColor(), fontWeight: 'bold' }}
        >
          {getStatusText()}
        </span>
      </div>
      <BooleanToggle
        value={isRunning}
        onChange={onToggle}
        onText={getButtonText()}
        offText={getButtonText()}
        disabled={!isOnline}
        variant={isRunning ? "danger" : "success"}
      />
    </div>
  );
};

/**
 * Temperature Display Component
 */

export const TemperatureDisplay = ({
  label = "Temperature",
  temperature,
  min,
  max,
  unit = "°F",
  className = ""
}) => {

  let currentTempBackgroundColor = interpolateHSLColor(temperature, min, max)
  let inverseColor = getContrastingTextColor(currentTempBackgroundColor)

return (
  <div className={`temperature-display ${className}`}>
    <span className="temp-label" style={{flexGrow: 1}}>{label}:</span>
    <div 
      style={{ 
        backgroundColor: currentTempBackgroundColor,
        position: 'relative'
      }} 
      className="Box" 
      id="CurrentTemp"
    >
      {/* Bottom layer with stroke */}
      <span style={{
        WebkitTextStroke: '4px black',
        WebkitTextFillColor: 'transparent',
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        {temperature ? ` ${temperature.toFixed(1)}${unit}` : "N/A"}
      </span>
      
      {/* Top layer with solid color */}
      <span style={{
        color: 'white',
        position: 'relative',
        zIndex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        {temperature ? ` ${temperature.toFixed(1)}${unit}` : "N/A"}
      </span>
    </div>
  </div>
);
};

/**
 * Control Mode Selector Component
 */
export const ControlModeSelector = ({
  currentMode,
  onModeChange,
  disabled = false,
  className = ""
}) => {
  const modes = [
    { value: "MANUAL", label: "Manual" },
    { value: "BASIC", label: "Basic" },
    { value: "AUTO", label: "Auto" }
  ];

  return (
    <div className={`control-mode-selector ${className}`}>
      <span className="mode-label">Control Scheme:</span>
      <div className="mode-buttons">
        {modes.map(mode => (
          <button
            key={mode.value}
            onClick={() => onModeChange(mode.value)}
            disabled={disabled || currentMode === mode.value}
            className={`Pinkbox ${currentMode === mode.value ? 'active' : ''}`}
            style={{
              margin: '10px',
              padding: '8px 16px',
              borderRadius: '4px',
              border: '1px solid #ccc',
              fontSize: '30px',
              width: '100%',
              background: currentMode === mode.value ? '#007bff' : '',
              cursor: disabled || currentMode === mode.value ? 'not-allowed' : 'pointer'
            }}
          >
            {mode.label}
          </button>
        ))}
      </div>
    </div>
  );
};