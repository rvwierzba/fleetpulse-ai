<script setup lang="ts">
import { defineProps, defineEmits, ref, computed } from 'vue'
import { Laptop, Smartphone, ArrowRight, Search, Play, Inbox } from 'lucide-vue-next'
import type { AlertDetail, AlertStatus } from '@/types/alert'

const props = defineProps<{
  alerts: AlertDetail[]
  selectedAlertId: string | null
}>()

const emit = defineEmits<{
  (e: 'select', alert: AlertDetail): void
  (e: 'filter-change', status: string): void
  (e: 'simulate'): void
}>()

const activeFilter = ref<string>('ALL')
const searchQuery = ref<string>('')

const filters = [
  { label: 'Todos', value: 'ALL' },
  { label: 'Revisão Humana', value: 'HUMAN_REVIEW' },
  { label: 'Auto-Recomendados', value: 'AUTO_RECOMMENDED' },
  { label: 'Resolvidos', value: 'RESOLVED' },
  { label: 'DLQ / Falhas', value: 'FAILED_DLQ' },
]

function selectFilter(val: string) {
  activeFilter.value = val
  emit('filter-change', val)
}

const filteredAlerts = computed(() => {
  let list = props.alerts
  if (activeFilter.value !== 'ALL') {
    list = list.filter((a) => a.current_status === activeFilter.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(
      (a) =>
        a.device_id.toLowerCase().includes(q) ||
        a.error_code.toLowerCase().includes(q) ||
        a.subsystem.toLowerCase().includes(q) ||
        a.device_type.toLowerCase().includes(q)
    )
  }
  return list
})

function getCount(status: string): number {
  if (status === 'ALL') return props.alerts.length
  return props.alerts.filter((a) => a.current_status === status).length
}

function getStatusBadge(status: AlertStatus) {
  switch (status) {
    case 'RECEIVED':
      return { label: 'Recebido', class: 'bg-slate-800 text-slate-300' }
    case 'DEDUPED':
      return { label: 'Deduplicado', class: 'bg-blue-950/60 text-blue-300 border border-blue-800/40' }
    case 'ML_SCORED':
      return { label: 'Score ML', class: 'bg-indigo-950/60 text-indigo-300 border border-indigo-800/40' }
    case 'CONTEXT_RETRIEVED':
      return { label: 'RAG Contexto', class: 'bg-cyan-950/60 text-cyan-300 border border-cyan-800/40' }
    case 'AGENT_DIAGNOSED':
      return { label: 'Agente Diagnosticou', class: 'bg-purple-950/60 text-purple-300 border border-purple-800/40' }
    case 'SCHEMA_VALIDATED':
      return { label: 'Validado', class: 'bg-teal-950/60 text-teal-300 border border-teal-800/40' }
    case 'HUMAN_REVIEW':
      return { label: 'Revisão Humana', class: 'bg-amber-500/10 text-amber-400 border border-amber-500/30 font-medium' }
    case 'AUTO_RECOMMENDED':
      return { label: 'Auto-Recomendado', class: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-medium' }
    case 'RESOLVED':
      return { label: 'Resolvido', class: 'bg-slate-800 text-slate-400' }
    case 'FAILED_DLQ':
      return { label: 'Falha / DLQ', class: 'bg-red-500/10 text-red-400 border border-red-500/30 font-medium' }
    default:
      return { label: status, class: 'bg-slate-800 text-slate-300' }
  }
}
</script>

<template>
  <div class="rounded-lg bg-slate-900 border border-slate-800 overflow-hidden">
    <!-- Filter Tabs & Search Header -->
    <div class="px-6 py-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4">
      <div>
        <h2 class="text-sm font-semibold text-slate-100">
          Incidentes de Frota
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">
          Lista de telemetrias processadas pelo pipeline de triagem
        </p>
      </div>

      <!-- Search Input -->
      <div class="relative w-full sm:w-64">
        <Search class="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Buscar dispositivo ou erro..."
          class="w-full pl-9 pr-3 py-1.5 rounded-md bg-slate-800 border border-slate-700 text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-blue-500 transition"
        />
      </div>

      <!-- Filter Tabs -->
      <div class="flex items-center flex-wrap gap-1 p-1 rounded-md bg-slate-950 border border-slate-800">
        <button
          v-for="f in filters"
          :key="f.value"
          @click="selectFilter(f.value)"
          :class="[
            'px-3 py-1 rounded text-xs transition flex items-center gap-1.5',
            activeFilter === f.value
              ? 'bg-slate-800 text-slate-100 font-medium'
              : 'text-slate-400 hover:text-slate-200'
          ]"
        >
          <span>{{ f.label }}</span>
          <span
            class="text-[10px] px-1.5 py-0.2 rounded-full"
            :class="activeFilter === f.value ? 'bg-slate-700 text-slate-200' : 'bg-slate-800 text-slate-400'"
          >
            {{ getCount(f.value) }}
          </span>
        </button>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="filteredAlerts.length === 0" class="p-12 text-center">
      <div class="w-12 h-12 mx-auto rounded-full bg-slate-800 flex items-center justify-center text-slate-400 mb-3">
        <Inbox class="w-6 h-6" />
      </div>
      <h3 class="text-sm font-medium text-slate-200">
        Nenhum alerta registrado
      </h3>
      <p class="text-xs text-slate-400 max-w-sm mx-auto mt-1">
        Não há incidentes na fila no momento. Clique no botão abaixo para gerar dados simulados de telemetria.
      </p>
      <div class="mt-4">
        <button
          @click="emit('simulate')"
          class="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition shadow-sm"
        >
          <Play class="w-3.5 h-3.5 fill-current" />
          <span>Gerar Alertas de Teste</span>
        </button>
      </div>
    </div>

    <!-- Table -->
    <div v-else class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-xs">
        <thead>
          <tr class="border-b border-slate-800 bg-slate-950/40 text-slate-400 font-medium text-[11px]">
            <th class="py-3 px-5">Dispositivo</th>
            <th class="py-3 px-4">Subsistema</th>
            <th class="py-3 px-4">Código de Erro</th>
            <th class="py-3 px-4">SLA</th>
            <th class="py-3 px-4">Risco de RMA</th>
            <th class="py-3 px-4">Status</th>
            <th class="py-3 px-4 text-right">Ação</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800/60">
          <tr
            v-for="alert in filteredAlerts"
            :key="alert.alert_id"
            @click="emit('select', alert)"
            :class="[
              'cursor-pointer transition hover:bg-slate-800/40',
              selectedAlertId === alert.alert_id ? 'bg-slate-800/60 border-l-2 border-l-blue-500' : ''
            ]"
          >
            <!-- Device -->
            <td class="py-3 px-5">
              <div class="flex items-center gap-2.5">
                <div class="w-6 h-6 rounded bg-slate-800 flex items-center justify-center text-slate-400">
                  <Laptop v-if="alert.device_type === 'NOTEBOOK'" class="w-3.5 h-3.5" />
                  <Smartphone v-else class="w-3.5 h-3.5" />
                </div>
                <div>
                  <p class="font-medium text-slate-100">{{ alert.device_id }}</p>
                  <p class="text-[11px] text-slate-400">{{ alert.device_type }}</p>
                </div>
              </div>
            </td>

            <!-- Subsystem -->
            <td class="py-3 px-4 text-slate-300">
              {{ alert.subsystem }}
            </td>

            <!-- Error Code -->
            <td class="py-3 px-4 font-mono text-[11px] text-slate-200">
              {{ alert.error_code }}
            </td>

            <!-- SLA -->
            <td class="py-3 px-4 text-slate-400">
              {{ alert.sla_tier }}
            </td>

            <!-- RMA Risk -->
            <td class="py-3 px-4">
              <div v-if="alert.rma_risk_score !== null && alert.rma_risk_score !== undefined" class="w-28">
                <div class="flex items-center justify-between text-[11px] mb-1">
                  <span
                    :class="alert.rma_risk_score >= 0.7 ? 'text-red-400 font-semibold' : 'text-slate-300'"
                  >
                    {{ (alert.rma_risk_score * 100).toFixed(0) }}%
                  </span>
                  <span v-if="alert.rma_risk_score >= 0.7" class="text-[10px] text-red-400 font-medium">
                    Alto
                  </span>
                </div>
                <div class="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    class="h-full rounded-full"
                    :style="{ width: `${alert.rma_risk_score * 100}%` }"
                    :class="[
                      alert.rma_risk_score >= 0.70
                        ? 'bg-red-500'
                        : alert.rma_risk_score >= 0.40
                        ? 'bg-amber-400'
                        : 'bg-emerald-400'
                    ]"
                  />
                </div>
              </div>
              <span v-else class="text-slate-500">&mdash;</span>
            </td>

            <!-- Status Badge -->
            <td class="py-3 px-4">
              <span
                class="inline-block text-[11px] px-2 py-0.5 rounded"
                :class="getStatusBadge(alert.current_status).class"
              >
                {{ getStatusBadge(alert.current_status).label }}
              </span>
            </td>

            <!-- Action -->
            <td class="py-3 px-4 text-right">
              <button
                class="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 font-medium transition"
              >
                <span>Detalhes</span>
                <ArrowRight class="w-3 h-3" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
