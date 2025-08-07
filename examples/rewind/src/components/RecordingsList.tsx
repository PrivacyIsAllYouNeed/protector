import { useState, useEffect } from 'react'
import { recordingsService } from '../services/recordings'
import type { Recording } from '../services/recordings'
import './RecordingsList.css'

interface RecordingsListProps {
  onSelectRecording: (recording: Recording) => void
  selectedRecording: Recording | null
  isStreamActive: boolean
}

function RecordingsList({ onSelectRecording, selectedRecording, isStreamActive }: RecordingsListProps) {
  const [recordings, setRecordings] = useState<Recording[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const fetchRecordings = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await recordingsService.fetchRecordings()
      setRecordings(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch recordings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchRecordings()
    const interval = setInterval(fetchRecordings, 10000)
    return () => clearInterval(interval)
  }, [])

  const handleDelete = async (recording: Recording, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Are you sure you want to delete this recording?')) {
      return
    }

    setDeletingId(recording.start)
    try {
      await recordingsService.deleteRecording(recording.start)
      setRecordings(prev => prev.filter(r => r.start !== recording.start))
      if (selectedRecording?.start === recording.start) {
        onSelectRecording(recordings[0] || null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete recording')
    } finally {
      setDeletingId(null)
    }
  }

  const handleRefresh = () => {
    fetchRecordings()
  }

  // Filter out the last recording if stream is active (it's the current streaming session)
  const displayRecordings = isStreamActive && recordings.length > 0 
    ? recordings.slice(0, -1) 
    : recordings

  if (loading && recordings.length === 0) {
    return (
      <div className="recordings-list">
        <div className="loading">Loading recordings...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="recordings-list">
        <div className="error">
          <p>Error: {error}</p>
          <button onClick={handleRefresh} className="refresh-btn">
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (displayRecordings.length === 0) {
    return (
      <div className="recordings-list">
        <div className="empty-state">
          <p>{isStreamActive && recordings.length === 1 ? 'No completed recordings (current stream in progress)' : 'No recordings available'}</p>
          <button onClick={handleRefresh} className="refresh-btn">
            Refresh
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="recordings-list">
      <div className="recordings-header">
        <h4>Available Recordings ({displayRecordings.length})</h4>
        <button onClick={handleRefresh} className="refresh-btn" disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>
      <div className="recordings-items">
        {displayRecordings.map((recording) => (
          <div
            key={recording.start}
            className={`recording-item ${selectedRecording?.start === recording.start ? 'selected' : ''}`}
            onClick={() => onSelectRecording(recording)}
          >
            <div className="recording-info">
              <div className="recording-time">
                {recordingsService.formatTimestamp(recording.start)}
              </div>
              <div className="recording-duration">
                Duration: {recordingsService.formatDuration(recording.duration)}
              </div>
            </div>
            <button
              className="delete-btn"
              onClick={(e) => handleDelete(recording, e)}
              disabled={deletingId === recording.start}
              title="Delete recording"
            >
              {deletingId === recording.start ? '...' : '×'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

export default RecordingsList