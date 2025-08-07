import { useState, useCallback } from 'react'
import WHEPClient from './components/WHEPClient'
import './components/WHEPClient.css'
import './App.css'

function App() {
  const [connectionState, setConnectionState] = useState<RTCPeerConnectionState>('new')
  const [error, setError] = useState<string | null>(null)

  // WHEP endpoint configuration (port 8889 as specified in requirements)
  const whepEndpoint = 'http://localhost:8889/filtered/whep'

  const handleConnectionStateChange = useCallback((state: RTCPeerConnectionState) => {
    setConnectionState(state)
    console.log('Connection state changed:', state)
  }, [])

  const handleError = useCallback((err: Error) => {
    setError(err.message)
    console.error('WHEP Client Error:', err)
  }, [])

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  return (
    <div className="app">
      <header className="app-header">
        <h1>Rewind - Privacy Video Stream</h1>
        <p className="subtitle">
          Real-time privacy-preserving video streaming with consent management
        </p>
      </header>

      <main className="main-content">
        <section className="video-section">
          <h2>Live Stream</h2>
          <p className="section-description">
            Processed video stream with privacy protection. Faces are blurred by default
            until explicit consent is given.
          </p>

          <WHEPClient
            whepEndpoint={whepEndpoint}
            onConnectionStateChange={handleConnectionStateChange}
            onError={handleError}
            className="main-video-player"
          />
        </section>

        <aside className="sidebar">
          <section className="connection-panel">
            <h3>Connection Status</h3>
            <div className="status-grid">
              <div className="status-item">
                <label>WebRTC State:</label>
                <span className={`status-badge ${connectionState}`}>
                  {connectionState}
                </span>
              </div>
              <div className="status-item">
                <label>Endpoint:</label>
                <code className="endpoint">{whepEndpoint}</code>
              </div>
            </div>

            {error && (
              <div className="error-panel">
                <h4>Error</h4>
                <p>{error}</p>
                <button onClick={clearError} className="clear-error-btn">
                  Clear
                </button>
              </div>
            )}
          </section>

          <section className="consent-panel">
            <h3>Consent Management</h3>
            <p className="panel-description">
              Manage individuals who have given consent to appear in recordings.
            </p>
            <div className="coming-soon">
              <span>Coming Soon</span>
            </div>
          </section>

          <section className="recordings-panel">
            <h3>Recordings</h3>
            <p className="panel-description">
              View and manage saved video recordings.
            </p>
            <div className="coming-soon">
              <span>Coming Soon</span>
            </div>
          </section>

          <section className="ai-chat-panel">
            <h3>AI Chat</h3>
            <p className="panel-description">
              Interact with AI assistant for video analysis and insights.
            </p>
            <div className="coming-soon">
              <span>Coming Soon</span>
            </div>
          </section>
        </aside>
      </main>

      <footer className="app-footer">
        <p>
          Privacy-first video streaming infrastructure •
          Built with React, WebRTC, and WHEP protocol
        </p>
      </footer>
    </div>
  )
}

export default App
