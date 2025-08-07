# Input Thread Improvement Plan

## Current Issues

### 1. Connection Timeout Blocking
- `av.open()` with `timeout=CONNECTION_TIMEOUT` (5s, 1s) blocks the entire thread
- During this block, no heartbeats are sent, making the thread appear unhealthy
- After timeout, there's a 1s sleep before retry, creating dead time
- The thread cannot respond to shutdown signals during the blocking period

### 2. Demux Blocking
- `in_container.demux()` is a blocking generator that waits for packets
- While waiting for packets, `process_iteration()` doesn't return
- This prevents heartbeat updates from being sent
- The thread appears frozen even though it's actually waiting for data

### 3. Lack of Responsiveness
- Cannot cleanly shutdown during connection attempts
- Cannot send health signals while waiting for data
- No way to interrupt blocking operations without killing the thread

## Proposed Architecture

### Solution: Dual-Thread Design with Queue Communication

```
┌─────────────────────────────────────────────────────────┐
│                    InputThread (Main)                    │
│  - Manages lifecycle and health                          │
│  - Handles connection state                              │
│  - Monitors internal worker thread                       │
│  - Sends regular heartbeats                              │
└─────────────────────────────────────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │  Control Queue  │
                    │  (commands)     │
                    └───────┬────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│              DemuxWorkerThread (Internal)                │
│  - Handles blocking av.open() calls                      │
│  - Performs blocking demux() operations                  │
│  - Pushes frames to output queues                        │
│  - Reports status back to main thread                    │
└─────────────────────────────────────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │  Status Queue   │
                    │  (feedback)     │
                    └────────────────┘
```

## Implementation Details

### 1. Main InputThread Responsibilities

- **Non-blocking event loop**: Check queues with timeout, never block indefinitely
- **Health monitoring**: Send heartbeats every second regardless of worker state
- **State management**: Track connection state and worker health
- **Graceful shutdown**: Can interrupt worker thread and clean up resources
- **Queue management**: Clear output queues on disconnect

### 2. DemuxWorkerThread Responsibilities

- **Connection handling**: Perform blocking `av.open()` with timeout
- **Packet processing**: Execute blocking `demux()` operations
- **Frame distribution**: Push video/audio frames to respective queues
- **Status reporting**: Send periodic status updates to main thread
- **Error handling**: Report errors to main thread for proper handling

### 3. Communication Protocol

#### Control Commands (Main → Worker)
```python
class WorkerCommand(Enum):
    CONNECT = "connect"       # Start connection attempt
    DISCONNECT = "disconnect"  # Close current connection
    STOP = "stop"             # Shutdown worker thread
```

#### Status Updates (Worker → Main)
```python
class WorkerStatus:
    type: StatusType  # CONNECTING, CONNECTED, DISCONNECTED, ERROR, PACKET_PROCESSED
    metadata: Optional[Dict]  # Connection metadata, error details, etc.
    timestamp: float
```

### 4. Key Improvements

#### Non-Blocking Connection
```python
# Main thread
def process_iteration(self):
    # Check for worker status (non-blocking)
    status = self._check_worker_status(timeout=0.01)
    
    # Handle status if received
    if status:
        self._handle_worker_status(status)
    
    # Check if we need to initiate connection
    if not self.connected and not self.connecting:
        self._send_command(WorkerCommand.CONNECT)
        self.connecting = True
    
    # Always returns quickly for heartbeat
    return True
```

#### Interruptible Demux
```python
# Worker thread
def _demux_with_timeout(self):
    # Use threading.Event for interruptibility
    while not self.stop_event.is_set():
        try:
            # Set a reasonable timeout for demux operations
            packet = next(self.demux_iter, timeout=0.1)
            if packet:
                self._process_packet(packet)
                self._report_status(StatusType.PACKET_PROCESSED)
        except TimeoutError:
            # Check if we should stop
            continue
        except StopIteration:
            # Stream ended
            self._report_status(StatusType.DISCONNECTED)
            break
```

### 5. Benefits

1. **Continuous Heartbeats**: Main thread never blocks, always sends health signals
2. **Responsive Shutdown**: Can interrupt blocking operations cleanly
3. **Better Error Recovery**: Main thread can restart worker if it fails
4. **Improved Monitoring**: Clear visibility into connection and processing states
5. **Decoupled Concerns**: Blocking I/O separated from health/lifecycle management

### 6. Migration Strategy

#### Phase 1: Internal Refactor
- Create `DemuxWorkerThread` class within `input.py`
- Implement queue-based communication
- Maintain existing external interface

#### Phase 2: Testing & Validation
- Test connection/disconnection scenarios
- Verify heartbeat continuity
- Validate shutdown behavior
- Measure latency impact (should be minimal)

#### Phase 3: Optimization
- Fine-tune queue sizes and timeouts
- Add metrics for queue depths
- Implement backpressure handling

### 7. Alternative Approaches Considered

#### AsyncIO Approach
- **Pros**: Single-threaded, potentially cleaner code
- **Cons**: Requires rewriting entire pipeline, PyAV has limited async support

#### Subprocess Approach
- **Pros**: Complete isolation, can kill if hung
- **Cons**: IPC overhead for video frames, complex serialization

#### Polling with Short Timeouts
- **Pros**: Simple to implement
- **Cons**: High CPU usage, increased latency, still has blocking periods

### 8. Implementation Timeline

1. **Day 1**: Implement basic worker thread structure
2. **Day 2**: Add queue communication and state management
3. **Day 3**: Integrate with existing pipeline, test edge cases
4. **Day 4**: Performance testing and optimization
5. **Day 5**: Documentation and code review

## Conclusion

The dual-thread design with queue communication provides the best balance of:
- **Reliability**: Continuous health monitoring and graceful shutdown
- **Performance**: Minimal overhead, no busy-waiting
- **Maintainability**: Clear separation of concerns
- **Compatibility**: Works with existing PyAV blocking operations

This approach solves both the connection timeout and demux blocking issues while maintaining the existing external interface, making it a drop-in improvement to the current implementation.