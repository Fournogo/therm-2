// SocketContext.js
import React, { createContext, useContext, useEffect, useState, useRef } from 'react';
import io from 'socket.io-client';

const SocketContext = createContext();

const SERVER_IP = `${window.location.hostname}`;
const SERVER_PORT = '5023';

export const SocketProvider = ({ children }) => {
  const [socketData, setSocketData] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [currentComponent, setCurrentComponent] = useState('MANUAL');
  const socketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

    // Function to send commands
  const sendCommand = (command, data) => {
    if (socketRef.current && isConnected) {
      fetch(`${window.location.protocol}//${SERVER_IP}:${SERVER_PORT}/data`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ command, data }),
      })
      .then(response => response.json())
      .then(result => console.log('Command sent:', result))
      .catch(error => console.error('Error sending command:', error));
    } else {
      console.warn('Socket not connected, cannot send command');
    }
  };

  // Make sendCommand available globally for console access
  useEffect(() => {
    window.sendCommand = sendCommand;
    
    // Cleanup on unmount
    return () => {
      delete window.sendCommand;
    };
  }, [isConnected]);

  useEffect(() => {
    const connectSocket = () => {
      // Clear any existing connection
      if (socketRef.current) {
        socketRef.current.removeAllListeners();
        socketRef.current.disconnect();
      }

      const protocol = window.location.protocol === 'https:' ? 'https' : 'http';
      const socket = io(`${protocol}://${SERVER_IP}:${SERVER_PORT}`, {
        forceNew: true,
        autoConnect: true,
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionAttempts: 5,
        timeout: 20000,
      });

      socketRef.current = socket;

      socket.on('connect', () => {
        console.log('Socket connected successfully');
        setIsConnected(true);
        // Clear any pending reconnect attempts
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
        // Request initial state
        // socket.emit('request_state');
      });

      socket.on('disconnect', (reason) => {
        console.log('Socket disconnected:', reason);
        setIsConnected(false);
        
        // Only attempt reconnect if it wasn't a manual disconnect
        if (reason !== 'io client disconnect') {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('Attempting to reconnect...');
            connectSocket();
          }, 2000);
        }
      });

      socket.on('connect_error', (error) => {
        console.error('Socket connection error:', error);
        setIsConnected(false);
      });

      socket.on('state_update', (data) => {
        console.log('Received state update:', data);
        setSocketData(prevData => {
          // Update current component if control mode changed
          if (data.control && data.control !== prevData?.control) {
            setCurrentComponent(data.control);
          }
          return data;
        });
      });
    };

    // Initial connection
    connectSocket();

    // Cleanup function
    return () => {
      console.log('Cleaning up socket connection');
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (socketRef.current) {
        socketRef.current.removeAllListeners();
        socketRef.current.disconnect();
        socketRef.current = null;
      }
    };
  }, []); // Empty dependency array - only run once

  const value = {
    socketData,
    isConnected,
    currentComponent,
    setCurrentComponent,
    sendCommand,
    socket: socketRef.current
  };

  return (
    <SocketContext.Provider value={value}>
      {children}
    </SocketContext.Provider>
  );
};

// Custom hook to use the socket context
export const useSocket = () => {
  const context = useContext(SocketContext);
  if (!context) {
    throw new Error('useSocket must be used within a SocketProvider');
  }
  return context;
};

export default SocketContext;