import type { AlertDetail, SystemMetrics } from '@/types/alert'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export async function fetchAlerts(statusFilter?: string): Promise<AlertDetail[]> {
  const url = new URL(`${API_BASE}/v1/alerts`)
  if (statusFilter && statusFilter !== 'ALL') {
    url.searchParams.set('status_filter', statusFilter)
  }
  url.searchParams.set('limit', '100')
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch alerts`)
  return res.json()
}

export async function fetchAlertDetail(alertId: string): Promise<AlertDetail> {
  const res = await fetch(`${API_BASE}/v1/alerts/${alertId}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}: Alert not found`)
  return res.json()
}

export async function fetchSystemMetrics(): Promise<SystemMetrics> {
  const res = await fetch(`${API_BASE}/v1/alerts/metrics/summary`)
  if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch system metrics`)
  return res.json()
}

export async function resolveAlert(
  alertId: string,
  resolutionNote: string,
  actionTaken: string = 'OPERATOR_APPROVED_REMEDIATION'
): Promise<AlertDetail> {
  const res = await fetch(`${API_BASE}/v1/alerts/${alertId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      resolution_note: resolutionNote,
      action_taken: actionTaken,
      operator_id: 'engineer-n2',
    }),
  })
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}))
    throw new Error(errorBody.detail || `HTTP ${res.status}: Failed to resolve alert`)
  }
  return res.json()
}

export function subscribeAlertStream(
  alertId: string,
  onEvent: (event: any) => void,
  onError?: (err: any) => void
): () => void {
  const eventSource = new EventSource(`${API_BASE}/v1/alerts/${alertId}/stream`)

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      onEvent(data)
    } catch (err) {
      console.error('Failed to parse SSE event data', err)
    }
  }

  eventSource.onerror = (err) => {
    if (onError) onError(err)
    eventSource.close()
  }

  return () => {
    eventSource.close()
  }
}
