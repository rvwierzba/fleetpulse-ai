<script setup lang="ts">
import { defineProps, defineEmits, ref, computed } from 'vue'
import { Laptop, Smartphone, ArrowRight } from 'lucide-vue-next'
import type { AlertDetail, AlertStatus } from '@/types/alert'

const props = defineProps<{
  alerts: AlertDetail[]
  selectedAlertId: string | null
}>()

const emit = defineEmits<{
  (e: 'select', alert: AlertDetail): void
  (e: 'filter-change', status: string): void
}>()

const activeFilter = ref<string>('ALL')

const filters = [
  { label: 'Todos', value: 'ALL' },
  { label: 'Human-in-the-Loop', value: 'HUMAN_REVIEW' },
  { label: 'Auto-Recomendados', value: 'AUTO_RECOMMENDED' },
  { label: 'Resolvidos', value: 'RESOLVED' },
  { label: 'Falhas / DLQ', value: 'FAILED_DLQ' },
]

function selectFilter(val: string) {
  activeFilter.value = val
  emit('filter-change', val)
}

const filteredAlerts = computed(() => {
  if (activeFilter.value === 'ALL') return props.alerts
  return props.alerts.filter((a) => a.current_status === activeFilter.value)
})

function getStatusBadge(status: AlertStatus) {
  switch (status) {
    case 'RECEIVED':
      return { label: 'Recebido', class: 'bg-slate-800 text-slate-300 border-slate-700' }
    case 'DEDUPED':
      return { label: 'Deduplicado', class: 'bg-blue-950/60 text-blue-300 border-blue-800/60' }
    case 'ML_SCORED':
      return { label: 'Score ML', class: 'bg-indigo-950/60 text-indigo-300 border-indigo-800/60' }
    case 'CONTEXT_RETRIEVED':
      return { label: 'RAG Contexto', class: 'bg-cyan-950/60 text-cyan-300 border-cyan-800/60' }
    case 'AGENT_DIAGNOSED':
      return { label: 'Agente Diagnosticou', class: 'bg-purple-950/60 text-purple-300 border-purple-800/60' }
    case 'SCHEMA_VALIDATED':
      return { label: 'Contrato Validado', class: 'bg-teal-950/60 text-teal-300 border-teal-800/60' }
    case 'HUMAN_REVIEW':
      return { label: 'Revisão Humana', class: 'bg-amber-950/80 text-amber-300 border-amber-600 animate-pulse font-semibold' }
    case 'AUTO_RECOMMENDED':
      return { label: 'Auto-Recomendado', class: 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60' }
    case 'RESOLVED':
      return { label: 'Resolvido', class: 'bg-slate-850 text-slate-400 border-slate-800' }
    case 'FAILED_DLQ':
      return { label: 'Dead Letter Queue', class: 'bg-rose-950/80 text-rose-300 border-rose-700 font-bold' }
    default:
      return { label: status, class: 'bg-slate-800 text-slate-300 border-slate-700' }
  }
}
</script>

<template>
  <div class="rounded-xl bg-slate-900/60 border border-slate-800 backdrop-blur-md overflow-hidden">
    <!-- Filter Tabs & Header -->
    <div class="px-6 py-4 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-4">
      <div>
        <h2 class="text-sm font-semibold text-white tracking-wide uppercase">Feed de Incidentes em Tempo Real</h2>
        <p class="text-xs text-slate-400 mt-0.5">Selecione um alerta para auditar o fluxo e a explicabilidade do modelo</p>
      </div>

      <!-- Filter Buttons -->
      <div class="flex items-center gap-1.5 p-1 rounded-lg bg-slate-950/60 border border-slate-800">
        <button
          v-for="f in filters"
          :key="f.value"
          @click="selectFilter(f.value)"
          :class="[
            'px-3 py-1.5 rounded-md text-xs font-medium transition',
            activeFilter === f.value
              ? 'bg-slate-800 text-cyan-400 shadow-sm border border-slate-700 font-semibold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
          ]"
        >
          {{ f.label }}
        </button>
      </div>
    </div>

    <!-- Table -->
    <div class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-xs">
        <thead>
          <tr class="border-b border-slate-800 bg-slate-950/40 text-slate-400 font-mono uppercase tracking-wider">
            <th class="py-3 px-5">Dispositivo</th>
            <th class="py-3 px-4">Subsistema & Erro</th>
            <th class="py-3 px-4">SLA</th>
            <th class="py-3 px-4">Risco RMA</th>
            <th class="py-3 px-4">Status da Máquina</th>
            <th class="py-3 px-4">Diagnóstico IA</th>
            <th class="py-3 px-4 text-right">Ação</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800/60">
          <tr
            v-for="alert in filteredAlerts"
            :key="alert.alert_id"
            @click="emit('select', alert)"
            :class="[
              'cursor-pointer transition hover:bg-slate-800/40 group',
              props.selectedAlertId === alert.alert_id ? 'bg-cyan-950/20 border-l-2 border-l-cyan-400' : ''
            ]"
          >
            <!-- Device & Model -->
            <td class="py-3.5 px-5">
              <div class="flex items-center gap-2.5">
                <div class="w-7 h-7 rounded-lg bg-slate-800 flex items-center justify-center text-slate-300">
                  <Laptop v-if="alert.device_type === 'NOTEBOOK'" class="w-4 h-4 text-cyan-400" />
                  <Smartphone v-else class="w-4 h-4 text-purple-400" />
                </div>
                <div>
                  <p class="font-mono font-medium text-slate-200 group-hover:text-white">{{ alert.device_id }}</p>
                  <p class="text-[10px] text-slate-500 font-mono">{{ alert.device_type }}</p>
                </div>
              </div>
            </td>

            <!-- Subsystem & Error -->
            <td class="py-3.5 px-4">
              <p class="font-mono text-slate-300 font-medium">{{ alert.error_code }}</p>
              <p class="text-[10px] text-slate-400">{{ alert.subsystem }}</p>
            </td>

            <!-- SLA Tier -->
            <td class="py-3.5 px-4 font-mono">
              <span
                :class="[
                  'px-2 py-0.5 rounded text-[10px] font-semibold border',
                  alert.sla_tier === 'PLATINUM' ? 'bg-amber-950/40 text-amber-300 border-amber-800/50' :
                  alert.sla_tier === 'GOLD' ? 'bg-yellow-950/40 text-yellow-300 border-yellow-800/50' :
                  'bg-slate-800 text-slate-400 border-slate-700'
                ]"
              >
                {{ alert.sla_tier }}
              </span>
            </td>

            <!-- RMA Risk Score -->
            <td class="py-3.5 px-4">
              <div v-if="alert.rma_risk_score !== null && alert.rma_risk_score !== undefined" class="w-24">
                <div class="flex items-center justify-between text-[10px] font-mono mb-1">
                  <span :class="alert.rma_risk_score >= 0.70 ? 'text-rose-400 font-bold' : 'text-slate-300'">
                    {{ (alert.rma_risk_score * 100).toFixed(0) }}%
                  </span>
                  <span v-if="alert.rma_risk_score >= 0.70" class="text-[9px] text-rose-400 font-semibold">Crítico</span>
                </div>
                <div class="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all duration-500"
                    :class="alert.rma_risk_score >= 0.70 ? 'bg-rose-500' : alert.rma_risk_score >= 0.40 ? 'bg-amber-500' : 'bg-emerald-500'"
                    :style="{ width: `${alert.rma_risk_score * 100}%` }"
                  />
                </div>
              </div>
              <span v-else class="text-slate-500 font-mono text-[10px]">Aguardando ML</span>
            </td>

            <!-- Machine Status Badge -->
            <td class="py-3.5 px-4">
              <span
                :class="[
                  'px-2.5 py-1 rounded-full text-[10px] border whitespace-nowrap inline-flex items-center gap-1',
                  getStatusBadge(alert.current_status).class
                ]"
              >
                {{ getStatusBadge(alert.current_status).label }}
              </span>
            </td>

            <!-- AI Diagnosis Summary -->
            <td class="py-3.5 px-4">
              <div v-if="alert.triage_action" class="flex flex-col">
                <span class="font-mono text-[11px] text-cyan-300 font-semibold">
                  {{ alert.triage_action }}
                </span>
                <span v-if="alert.matched_runbook_id" class="text-[10px] text-slate-400 font-mono">
                  {{ alert.matched_runbook_id }}
                </span>
              </div>
              <span v-else class="text-slate-500 font-mono text-[10px]">Pendente</span>
            </td>

            <!-- Action Button -->
            <td class="py-3.5 px-4 text-right">
              <button
                class="px-2.5 py-1 rounded bg-slate-800 hover:bg-cyan-950/60 hover:text-cyan-400 text-slate-400 text-xs border border-slate-700/80 transition inline-flex items-center gap-1"
              >
                <span>Inspecionar</span>
                <ArrowRight class="w-3 h-3" />
              </button>
            </td>
          </tr>

          <tr v-if="filteredAlerts.length === 0">
            <td colspan="7" class="py-12 text-center text-slate-500">
              Nenhum alerta encontrado para o filtro selecionado.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
