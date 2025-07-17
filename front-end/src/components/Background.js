import "../css/Basic.css"
import React, { useState, useEffect } from 'react';

function Background({ children, socketData }) {

    const [AlertMode, setAlertMode] = useState(false);

    useEffect(() => {
        if (socketData) {
            setAlertMode(socketData.drying_status)
        }
    }, [socketData]);

    return (
        <>
        <div className={`Background ${AlertMode ? "Red-Alert" : ""}`}>
            <div className="Redbox" id="Left-Accent-1"></div>
            <div className="Greenbox" id="Left-Accent-2"></div>
            <div className="Bluebox" id="Right-Accent-1"></div>
            <div className="Orangebox" id="Right-Accent-2"></div>
            <div className="Redbox" id="Right-Accent-3"></div>
            <div className="Page">
                {children}
            </div>
        </div>
        </>
    )
}

export default Background;