# InputThread Standalone Implementation Plan

## Rationale

InputThread is fundamentally different from other pipeline threads:
- It's the data source, not a processor
- It deals with external network I/O with unpredictable blocking
- It needs special handling for connection/disconnection cycles
- Its lifecycle doesn't fit the standard `process_iteration()` pattern

Making InputThread standalone (not inheriting from BaseThread) allows us to handle these unique requirements without complex workarounds.

## Current Problems with BaseThread Inheritance

1. **Forced Iteration Pattern**: BaseThread expects `process_iteration()` to return regularly, but demux operations are inherently blocking
2. **Heartbeat Impedance Mismatch**: Heartbeats assume regular iteration returns, incompatible with blocking I/O
3. **Unnecessary Abstraction**: InputThread doesn't benefit from BaseThread's patterns - it's forcing a square peg into a round hole

## Proposed Standalone Architecture

### Design Principles

1. **Embrace the Blocking Nature**: Instead of fighting blocking I/O, design around it
2. **Integrated Health Signaling**: Build heartbeats into the I/O operations
3. **Simplified State Machine**: Direct control over connection lifecycle

### Implementation Structure

```python
class InputThread(threading.Thread):
    """Standalone input thread with custom lifecycle management."""
    
    def __init__(self, state_manager, connection_state, queues...):
        super().__init__(name="InputDemuxer", daemon=False)
        self.state_manager = state_manager
        self.connection_state = connection_state
        # ... queues setup
        self._stop_event = threading.Event()
        
    def run(self):
        """Custom run loop designed for blocking I/O operations."""
        self._register_with_state_manager()
        
        while not self._should_stop():
            if not self.in_container:
                self._connection_loop()
            else:
                self._demux_loop()
                
        self._cleanup()
```

## Key Implementation Details

### 1. Connection Loop with Integrated Heartbeats

```python
def _connection_loop(self):
    """Handle connection attempts with proper health signaling."""
    while not self._should_stop():
        # Send heartbeat before connection attempt
        self._send_heartbeat()
        
        # Try connection with short timeout
        if self._try_connect(timeout=1.0):
            break
            
        # Check for shutdown between attempts
        if self._stop_event.wait(timeout=0.5):
            break
```

**Benefits:**
- Heartbeats sent between connection attempts
- Responsive to shutdown signals
- No long blocking periods

### 2. Demux Loop with Periodic Health Checks

```python
def _demux_loop(self):
    """Process packets with periodic health updates."""
    last_heartbeat = time.time()
    packets_since_heartbeat = 0
    
    try:
        for packet in self.in_container.demux():
            # Process packet
            self._process_packet(packet)
            packets_since_heartbeat += 1
            
            # Periodic health check
            if time.time() - last_heartbeat > 1.0:
                self._send_heartbeat()
                self._report_throughput(packets_since_heartbeat)
                last_heartbeat = time.time()
                packets_since_heartbeat = 0
            
            # Check for shutdown
            if self._should_stop():
                break
                
    except (FFmpegError, StopIteration):
        self._handle_disconnect()
```

**Benefits:**
- Regular heartbeats even during streaming
- Throughput metrics for monitoring
- Clean shutdown capability

### 3. Smart Connection with Timeout Chunking

```python
def _try_connect(self, timeout: float) -> bool:
    """Attempt connection with chunked timeout for responsiveness."""
    # Instead of one long timeout, use shorter chunks
    chunk_size = 0.5  # 500ms chunks
    chunks = int(timeout / chunk_size)
    
    for _ in range(chunks):
        try:
            # Try with short timeout
            self.in_container = av.open(
                IN_URL, 
                mode="r", 
                options={"listen": "1"}, 
                timeout=(chunk_size, chunk_size)
            )
            return True
            
        except TimeoutError:
            # Check if we should stop between chunks
            if self._should_stop():
                return False
            continue
            
        except FFmpegError as e:
            self.logger.error(f"Connection error: {e}")
            return False
            
    return False
```

**Benefits:**
- Responsive to shutdown during connection attempts
- Maintains heartbeat cadence
- No single long blocking operation

### 4. Direct State Management

```python
def _send_heartbeat(self):
    """Send heartbeat directly to state manager."""
    self.state_manager.heartbeat(self.name)
    
def _report_throughput(self, packet_count: int):
    """Report processing metrics."""
    self.state_manager.update_metrics(self.name, {
        'packets_processed': packet_count,
        'timestamp': time.time()
    })
```

**Benefits:**
- Direct control over when and what to report
- Can include context-specific metrics
- No abstraction overhead

## Advantages Over Current Implementation

### 1. Simplicity
- No complex workarounds for blocking operations
- Direct, purpose-built implementation
- Fewer layers of abstraction

### 2. Performance
- No unnecessary iteration overhead
- Direct packet processing without queue intermediaries
- Optimal for streaming data pattern

### 3. Maintainability
- Code matches the actual behavior (blocking I/O)
- Clear state transitions
- Easier to debug and understand

### 4. Flexibility
- Can implement input-specific features without affecting other threads
- Custom metrics and monitoring
- Specialized error handling for network issues

## Advantages Over Dual-Thread Approach

| Aspect | Dual-Thread | Standalone |
|--------|------------|------------|
| Complexity | High (2 threads, queues) | Low (single thread) |
| Latency | Added queue overhead | Direct processing |
| Memory | Queue buffers needed | No intermediary buffers |
| Debugging | Complex thread interaction | Straightforward flow |
| Code Lines | ~300+ | ~200 |

## Migration Path

### Step 1: Create Standalone Implementation
```python
# input_standalone.py
class InputThread(threading.Thread):
    # New implementation
```

### Step 2: Compatibility Layer
Keep the same external interface:
- Same constructor parameters
- Same queue interactions
- Same state manager integration

### Step 3: Drop-in Replacement
```python
# In pipeline.py
from threads.input_standalone import InputThread  # Just change import
```

### Step 4: Remove BaseThread Dependency
Once validated, remove BaseThread inheritance completely.

## Implementation Checklist

- [ ] Create standalone InputThread class
- [ ] Implement connection loop with heartbeats
- [ ] Implement demux loop with health checks
- [ ] Add chunked timeout for connection
- [ ] Integrate state manager directly
- [ ] Add comprehensive error handling
- [ ] Test connection/disconnection scenarios
- [ ] Test shutdown responsiveness
- [ ] Validate heartbeat continuity
- [ ] Performance benchmarking

## Code Example: Complete Minimal Implementation

```python
import threading
import time
import av
from typing import Optional

class InputThread(threading.Thread):
    def __init__(self, state_manager, connection_state, video_queue, audio_queue):
        super().__init__(name="InputDemuxer", daemon=False)
        self.state_manager = state_manager
        self.connection_state = connection_state
        self.video_queue = video_queue
        self.audio_queue = audio_queue
        self.in_container: Optional[av.InputContainer] = None
        self._stop_event = threading.Event()
        self.logger = ThreadLogger("InputDemuxer")
        
    def run(self):
        self.state_manager.register_thread(self.name)
        self.state_manager.update_state(self.name, ThreadState.RUNNING)
        
        try:
            while not self._should_stop():
                if not self.in_container:
                    if not self._connection_loop():
                        break
                else:
                    if not self._demux_loop():
                        self._disconnect()
        finally:
            self._cleanup()
            
    def _connection_loop(self) -> bool:
        """Returns False if should stop, True if connected."""
        while not self._should_stop():
            self._send_heartbeat()
            
            try:
                # Try connection with 1s timeout
                self.in_container = av.open(
                    IN_URL, 
                    mode="r", 
                    options={"listen": "1"}, 
                    timeout=(1.0, 1.0)
                )
                self._on_connected()
                return True
                
            except TimeoutError:
                # Wait 0.5s before retry, checking for stop
                if self._stop_event.wait(0.5):
                    return False
                    
        return False
        
    def _demux_loop(self) -> bool:
        """Returns False if stream ended, True if stopped."""
        last_heartbeat = time.time()
        
        try:
            for packet in self.in_container.demux():
                self._process_packet(packet)
                
                # Heartbeat every second
                if time.time() - last_heartbeat > 1.0:
                    self._send_heartbeat()
                    last_heartbeat = time.time()
                    
                if self._should_stop():
                    return True
                    
        except (StopIteration, av.FFmpegError):
            return False
            
        return False
        
    def stop(self):
        self.logger.info("Stop requested")
        self._stop_event.set()
        
    def _should_stop(self) -> bool:
        return self._stop_event.is_set() or is_shutting_down()
        
    def _send_heartbeat(self):
        self.state_manager.heartbeat(self.name)
```

## Conclusion

Making InputThread standalone is the **simpler, cleaner, and more maintainable** solution compared to both the current implementation and the dual-thread approach. It:

1. **Embraces** the blocking nature of streaming I/O instead of fighting it
2. **Simplifies** the codebase by removing unnecessary abstractions
3. **Improves** responsiveness through intelligent timeout management
4. **Maintains** compatibility with the existing pipeline

This approach recognizes that InputThread is special and deserves special treatment, resulting in better code that's easier to understand and maintain.