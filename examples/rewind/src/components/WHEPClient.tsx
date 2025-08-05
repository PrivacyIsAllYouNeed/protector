import { useEffect, useRef, useState, useCallback } from 'react';

// Video stats interface
interface VideoStats {
  resolution: {
    width: number | null;
    height: number | null;
  };
  fps: number | null;
  framesDecoded: number | null;
}

// WHEP client types
interface WHEPClientProps {
  whepEndpoint: string;
  onConnectionStateChange?: (state: RTCPeerConnectionState) => void;
  onError?: (error: Error) => void;
  onStatsUpdate?: (stats: VideoStats) => void;
  className?: string;
}

interface WHEPClientState {
  connectionState: RTCPeerConnectionState;
  isConnecting: boolean;
  error: string | null;
  stats: VideoStats;
}

/**
 * WHEP (WebRTC-HTTP Egress Protocol) Client Component
 * 
 * This component establishes a WebRTC connection to receive live video/audio
 * streams using the WHEP protocol. It handles the SDP offer/answer negotiation
 * via HTTP and manages the WebRTC peer connection lifecycle.
 */
export const WHEPClient: React.FC<WHEPClientProps> = ({
  whepEndpoint,
  onConnectionStateChange,
  onError,
  onStatsUpdate,
  className = ''
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const statsIntervalRef = useRef<number | null>(null);
  const [state, setState] = useState<WHEPClientState>({
    connectionState: 'new',
    isConnecting: false,
    error: null,
    stats: {
      resolution: { width: null, height: null },
      fps: null,
      framesDecoded: null
    }
  });

  // Handle connection state changes
  const handleConnectionStateChange = useCallback(() => {
    const pc = peerConnectionRef.current;
    if (pc) {
      const connectionState = pc.connectionState;
      setState(prev => ({ ...prev, connectionState }));
      onConnectionStateChange?.(connectionState);
      
      // Handle connection failures
      if (connectionState === 'failed' || connectionState === 'disconnected') {
        setState(prev => ({ 
          ...prev, 
          error: `Connection ${connectionState}`,
          isConnecting: false 
        }));
      }
    }
  }, [onConnectionStateChange]);

  // Handle incoming media streams
  const handleTrack = useCallback((event: RTCTrackEvent) => {
    console.log('Received track:', event.track.kind);
    if (videoRef.current && event.streams[0]) {
      videoRef.current.srcObject = event.streams[0];
    }
  }, []);

  // Collect video stats from PeerConnection
  const collectStats = useCallback(async () => {
    const pc = peerConnectionRef.current;
    if (!pc || pc.connectionState !== 'connected') return;

    try {
      const stats = await pc.getStats();
      for (const report of stats.values()) {
        if (report.type === 'track' && report.kind === 'video') {
          const newStats: VideoStats = {
            resolution: {
              width: report.frameWidth ?? null,
              height: report.frameHeight ?? null
            },
            fps: report.framesPerSecond ?? null,
            framesDecoded: report.framesDecoded ?? null
          };
          
          setState(prev => ({ ...prev, stats: newStats }));
          onStatsUpdate?.(newStats);
          break; // Only process first video track
        }
      }
    } catch (error) {
      console.error('Error collecting stats:', error);
    }
  }, [onStatsUpdate]);

  // Create WebRTC peer connection
  const createPeerConnection = useCallback(() => {
    // No STUN servers needed for local network as mentioned in requirements
    const pc = new RTCPeerConnection({
      iceServers: []
    });

    pc.addEventListener('connectionstatechange', handleConnectionStateChange);
    pc.addEventListener('track', handleTrack);
    
    pc.addEventListener('iceconnectionstatechange', () => {
      console.log('ICE connection state:', pc.iceConnectionState);
    });

    return pc;
  }, [handleConnectionStateChange, handleTrack]);

  // Perform WHEP negotiation
  const startWHEPConnection = useCallback(async () => {
    try {
      setState(prev => ({ ...prev, isConnecting: true, error: null }));

      const pc = createPeerConnection();
      peerConnectionRef.current = pc;

      // Add transceiver to receive video and audio
      pc.addTransceiver('video', { direction: 'recvonly' });
      pc.addTransceiver('audio', { direction: 'recvonly' });

      // Create offer
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      // Send offer to WHEP endpoint
      const response = await fetch(whepEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/sdp',
        },
        body: offer.sdp
      });

      if (!response.ok) {
        throw new Error(`WHEP request failed: ${response.status} ${response.statusText}`);
      }

      // Get answer from server
      const answerSdp = await response.text();
      const answer: RTCSessionDescriptionInit = {
        type: 'answer',
        sdp: answerSdp
      };

      await pc.setRemoteDescription(answer);

      setState(prev => ({ ...prev, isConnecting: false }));
      console.log('WHEP connection established');

      // Start collecting stats every second
      if (statsIntervalRef.current) {
        clearInterval(statsIntervalRef.current);
      }
      statsIntervalRef.current = setInterval(collectStats, 1000);

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setState(prev => ({ 
        ...prev, 
        error: errorMessage, 
        isConnecting: false 
      }));
      onError?.(error instanceof Error ? error : new Error(errorMessage));
      console.error('WHEP connection failed:', error);
    }
  }, [whepEndpoint, createPeerConnection, onError, collectStats]);

  // Cleanup function
  const cleanup = useCallback(() => {
    if (peerConnectionRef.current) {
      peerConnectionRef.current.close();
      peerConnectionRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    if (statsIntervalRef.current) {
      clearInterval(statsIntervalRef.current);
      statsIntervalRef.current = null;
    }
  }, []);

  // Effect to manage connection lifecycle
  useEffect(() => {
    startWHEPConnection();

    // Cleanup on unmount
    return cleanup;
  }, [startWHEPConnection, cleanup]);

  // Retry connection function
  const retryConnection = useCallback(() => {
    cleanup();
    startWHEPConnection();
  }, [cleanup, startWHEPConnection]);

  return (
    <div className={`whep-client ${className}`}>
      <div className="video-container">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="whep-video"
          style={{
            width: '100%',
            height: 'auto',
            backgroundColor: '#000',
            borderRadius: '8px'
          }}
        />
        
        {/* Connection status overlay */}
        {(state.isConnecting || state.error) && (
          <div className="connection-status">
            {state.isConnecting && (
              <div className="connecting">
                <div className="spinner" />
                <span>Connecting to live stream...</span>
              </div>
            )}
            
            {state.error && (
              <div className="error">
                <span>Connection failed: {state.error}</span>
                <button onClick={retryConnection} className="retry-button">
                  Retry
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Connection info */}
      <div className="connection-info">
        <span className={`status ${state.connectionState}`}>
          Status: {state.connectionState}
        </span>
      </div>

      {/* Video stats */}
      {state.connectionState === 'connected' && (
        <div className="video-stats">
          <div className="stat-item">
            <label>RES:</label>
            <span>{state.stats.resolution.width ?? '—'} × {state.stats.resolution.height ?? '—'}</span>
          </div>
          <div className="stat-item">
            <label>FPS:</label>
            <span>{state.stats.fps?.toFixed(1) ?? '—'}</span>
          </div>
          <div className="stat-item">
            <label>DECODED:</label>
            <span>{state.stats.framesDecoded ?? '—'} frames</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default WHEPClient;