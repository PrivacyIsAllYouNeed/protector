import { useEffect, useState, useCallback } from 'react'
import { ConsentsService, type ConsentInfo } from '../services/consents'
import './ConsentList.css'

function ConsentList() {
  const [consents, setConsents] = useState<ConsentInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set())

  const fetchConsents = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await ConsentsService.listConsents()
      setConsents(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch consents')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConsents()
    
    // Auto-refresh every 5 seconds
    const interval = setInterval(fetchConsents, 5000)
    
    return () => clearInterval(interval)
  }, [fetchConsents])

  const handleDelete = useCallback(async (consentId: string, name: string) => {
    if (!confirm(`Are you sure you want to revoke consent for ${name}?`)) {
      return
    }

    setDeletingIds(prev => new Set(prev).add(consentId))
    
    try {
      await ConsentsService.revokeConsent(consentId)
      // Refresh the list after successful deletion
      await fetchConsents()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke consent')
    } finally {
      setDeletingIds(prev => {
        const next = new Set(prev)
        next.delete(consentId)
        return next
      })
    }
  }, [fetchConsents])

  const formatDate = (timestamp: number) => {
    const date = new Date(timestamp * 1000)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  if (loading && consents.length === 0) {
    return (
      <div className="consent-list">
        <div className="loading">Loading consents...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="consent-list">
        <div className="error-message">
          <span>Error: {error}</span>
          <button onClick={fetchConsents} className="retry-btn">
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (consents.length === 0) {
    return (
      <div className="consent-list">
        <div className="empty-state">
          <p>No consents yet</p>
        </div>
      </div>
    )
  }

  return (
    <div className="consent-list">
      <div className="consent-header">
        <span className="consent-count">{consents.length} person{consents.length !== 1 ? 's' : ''}</span>
        <button onClick={fetchConsents} className="refresh-btn" disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>
      
      <div className="consent-items">
        {consents.map((consent) => (
          <div key={consent.id} className="consent-item">
            <div className="consent-image-container">
              <img 
                src={ConsentsService.getImageUrl(consent.id)} 
                alt={`${consent.name}'s face`}
                className="consent-image"
                loading="lazy"
              />
            </div>
            <div className="consent-info">
              <div className="consent-name">{consent.name}</div>
              <div className="consent-time">{formatDate(consent.time)}</div>
            </div>
            <button 
              className="delete-btn"
              onClick={() => handleDelete(consent.id, consent.name)}
              disabled={deletingIds.has(consent.id)}
              title="Revoke consent"
            >
              {deletingIds.has(consent.id) ? '...' : '×'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

export default ConsentList