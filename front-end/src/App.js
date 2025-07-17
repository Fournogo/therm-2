import React, { useState, useEffect  } from 'react';
import { SocketProvider, useSocket } from './SocketContext';
import Loading from './pages/Loading';
import Basic from './pages/Basic';
import Manual from './pages/Manual';
import Auto from './pages/Auto';
import Settings from './pages/Settings'; 
import Background from './components/Background';
import 'bootstrap-icons/font/bootstrap-icons.css';

// Main App component that uses the socket context
function AppContent() {

  const { socketData, currentComponent, isConnected } = useSocket();
  const [showSettings, setShowSettings] = useState(false);

  // Function to render the correct component based on state
  const renderComponent = () => {
    if (showSettings) {
      return (
        <Settings
          socketData={socketData}
          onBack={() => setShowSettings(false)}
        />
      );
    }

    if (!isConnected || !socketData) {
      return <Loading />;
    }

    switch (currentComponent) {
      case 'BASIC':
        return (
          <Basic
            socketData={socketData}
            onOpenSettings={() => setShowSettings(true)}
          />
        );
      case 'MANUAL':
        return (
          <Manual
            socketData={socketData}
            onOpenSettings={() => setShowSettings(true)}
          />
        );
      case 'AUTO':
        return (
          <Auto
            socketData={socketData}
            onOpenSettings={() => setShowSettings(true)}
          />
        );
      default:
        return <Loading />;
    }
  };

  return (
    <div>
      <Background socketData={socketData}>
        {renderComponent()}
      </Background>
    </div>
  );
}

// Root App component wrapped with SocketProvider
function App() {
  return (
    <SocketProvider>
      <AppContent />
    </SocketProvider>
  );
}

export default App;