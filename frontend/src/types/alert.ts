export type AlertStatus =
  | 'RECEIVED'
  | 'DEDUPED'
  | 'IGNORED_DUPLICATE'
  | 'ML_SCORED'
  | 'CONTEXT_RETRIEVED'
  | 'AGENT_DIAGNOSED'
  | 'SCHEMA_VALIDATED'
  | 'HUMAN_REVIEW'
  | 'AUTO_RECOMMENDED'
  | 'RESOLVED'
  | 'FAILED_DLQ'

export type DeviceType = 'NOTEBOOK' | 'SMARTPHONE'
export type SLATier = 'PLATINUM' | 'GOLD' | 'STANDARD'
export type Subsystem =
  | 'BATTERY_POWER'
  | 'STORAGE_NVME'
  | 'THERMAL_BOARD'
  | 'FIRMWARE_OS'
  | 'DISPLAY_PERIPHERAL'

export interface SHAPFactor {
  feature_name: string
  attribution_value: number
  human_label: string
  risk_direction: 'increases_risk' | 'decreases_risk'
}

export interface AlertStreamEvent {
  event_id: string
  alert_id: string
  from_status: AlertStatus | null
  to_status: AlertStatus
  reason: string
  metadata: Record<string, any>
  created_at: string
}

export interface TriageDiagnosis {
  matched_runbook_id: string
  matched_bulletin_id?: string | null
  action_type: 'REMOTE_PATCH' | 'DISPATCH_TECH' | 'REPLACE_HARDWARE' | 'UPDATE_FIRMWARE' | 'ESCALATE_TIER2'
  confidence_score: number
  root_cause_analysis: string
  requires_human_approval: boolean
  suggested_action_plan?: string[]
  preventive_measures?: string[]
}

export interface AlertDetail {
  alert_id: string
  device_id: string
  device_type: DeviceType
  subsystem: Subsystem
  error_code: string
  sla_tier: SLATier
  current_status: AlertStatus
  rma_risk_score?: number | null
  sla_breach_risk?: number | null
  predicted_subsystem?: Subsystem | null
  shap_factors?: SHAPFactor[] | null
  rag_context?: Record<string, any> | null
  matched_runbook_id?: string | null
  matched_bulletin_id?: string | null
  semantic_cache_hit?: boolean | null
  agent_diagnosis?: TriageDiagnosis | null
  triage_action?: string | null
  agent_confidence?: number | null
  requires_human_approval?: boolean | null
  created_at: string
  updated_at: string
  events: AlertStreamEvent[]
}

export interface SystemMetrics {
  total_alerts: number
  alerts_by_status: Record<string, number>
  high_rma_alerts: number
  pending_human_review: number
  dlq_count: number
  circuit_breaker_state: string
  semantic_cache_hit_rate: number
  primary_model: string
  fallback_model: string
}
