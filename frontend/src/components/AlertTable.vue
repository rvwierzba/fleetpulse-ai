<script setup lang="ts">
import { defineProps, defineEmits, ref, computed } from 'vue'
import { Laptop, Smartphone, ArrowRight, Search, Zap, AlertCircle } from 'lucide-vue-next'
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
  { label: 'Human-in-the-Loop', value: 'HUMAN_REVIEW' },
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

function getSubsystemBadge(sub: string) {
  switch (sub.toUpperCase()) {
    case 'BATTERY':
      return 'text-amber-400 bg-amber-950/40 border-amber-800/50'
    case 'STORAGE':
      return 'text-cyan-400 bg-cyan-950/40 border-cyan-800/50'
    case 'THERMAL':
      return 'text-rose-400 bg-rose-950/40 border-rose-800/50'
    case 'MEMORY':
      return 'text-purple-400 bg-purple-950/40 border-purple-800/50'
    case 'CONNECTIVITY':
      return 'text-blue-400 bg-blue-950/40 border-blue-800/50'
    default:
      return 'text-slate-400 bg-slate-900 border-slate-700'
  }
}

function getStatusBadge(status: AlertStatus) {
  switch (status) {
    case 'RECEIVED':
      return { label: 'Recebido', class: 'bg-cyber-850 text-slate-300 border-cyber-700' }
    case 'DEDUPED':
      return { label: 'Deduplicado', class: 'bg-blue-950/80 text-blue-300 border-blue-700/60' }
    case 'ML_SCORED':
      return { label: 'Score ML + SHAP', class: 'bg-indigo-950/80 text-indigo-300 border-indigo-700/60' }
    case 'CONTEXT_RETRIEVED':
      return { label: 'RAG Híbrido', class: 'bg-cyan-950/80 text-cyan-300 border-cyan-700/60' }
    case 'AGENT_DIAGNOSED':
      return { label: 'Agente IA', class: 'bg-purple-950/80 text-purple-300 border-purple-700/60' }
    case 'SCHEMA_VALIDATED':
      return { label: 'Pydantic OK', class: 'bg-teal-950/80 text-teal-300 border-teal-700/60' }
    case 'HUMAN_REVIEW':
      return { label: 'Revisão Humana (N2)', class: 'bg-amber-950 text-neon-amber border-amber-600 animate-pulse font-bold shadow-neon-amber' }
    case 'AUTO_RECOMMENDED':
      return { label: 'Auto-Recomendado', class: 'bg-emerald-950/80 text-neon-emerald border-emerald-700/60' }
    case 'RESOLVED':
      return { label: 'Resolvido', class: 'bg-cyber-800 text-slate-400 border-cyber-700' }
    case 'FAILED_DLQ':
      return { label: 'Dead Letter Queue', class: 'bg-rose-950 text-neon-rose border-rose-600 font-bold shadow-neon-rose' }
    default:
      return { label: status, class: 'bg-cyber-850 text-slate-300 border-cyber-700' }
  }
}
</script>

<template>
  <div class="hud-corner-card rounded-lg bg-cyber-900/90 border border-cyber-800 backdrop-blur-xl overflow-hidden shadow-cyber-card">
    <!-- Filter Tabs & Real-Time Search Header -->
    <div class="px-6 py-4 border-b border-cyber-800 flex flex-wrap items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-neon-cyan animate-ping"></span>
          <h2 class="text-sm font-bold text-white tracking-wider uppercase font-mono">
            Feed de Telemetria de Frota
          </h2>
        </div>
        <p class="text-xs text-slate-400 font-mono mt-0.5">
          Auditoria de esteira assíncrona, predições SHAP e intervenções de engenharia
        </p>
      </div>

      <!-- Search Input -->
      <div class="relative w-full sm:w-64">
        <Search class="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Buscar dispositivo ou erro..."
          class="w-full pl-9 pr-3 py-1.5 rounded-md bg-cyber-850 border border-cyber-700 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-neon-cyan transition"
        />
      </div>

      <!-- Filter Tabs -->
      <div class="flex items-center flex-wrap gap-1.5 p-1 rounded-md bg-cyber-950/80 border border-cyber-800">
        <button
          v-for="f in filters"
          :key="f.value"
          @click="selectFilter(f.value)"
          :class="[
            'px-2.5 py-1 rounded text-xs font-mono transition flex items-center gap-1.5',
            activeFilter === f.value
              ? 'bg-cyber-800 text-neon-cyan border border-cyan-500/30 font-bold shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-cyber-900/60'
          ]"
        >
          <span>{{ f.label }}</span>
          <span
            class="text-[10px] px-1.5 py-0.2 rounded-full font-bold"
            :class="activeFilter === f.value ? 'bg-cyan-950 text-cyan-300' : 'bg-cyber-850 text-slate-500'"
          >
            {{ getCount(f.value) }}
          </span>
        </button>
      </div>
    </div>

    <!-- Empty State Banner (When 0 alerts) -->
    <div v-if="filteredAlerts.length === 0" class="p-12 text-center">
      <div class="w-16 h-16 mx-auto rounded-full bg-cyber-850 border border-cyber-700 flex items-center justify-center text-neon-cyan mb-4 shadow-neon-cyan">
        <AlertCircle class="w-8 h-8 animate-pulse" />
      </div>
      <h3 class="text-base font-bold text-white font-mono uppercase tracking-wider">
        Nenhum Alerta Ativo Encontrado
      </h3>
      <p class="text-xs text-slate-400 max-w-md mx-auto mt-2 font-mono leading-relaxed">
        O pipeline de observabilidade está ativo e aguardando rajadas de telemetria. Injete uma carga de teste para visualizar o fluxo completo da máquina de estados.
      </p>
      <div class="mt-6">
        <button
          @click="emit('simulate')"
          class="inline-flex items-center gap-2 px-5 py-2.5 rounded-md bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-mono font-bold tracking-wider uppercase border border-cyan-400/40 shadow-neon-cyan transition"
        >
          <Zap class="w-4 h-4" />
          <span>Disparar Injeção de Telemetria (Simulação)</span>
        </button>
      </div>
    </div>

    <!-- Table -->
    <div v-else class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-xs">
        <thead>
          <tr class="border-b border-cyber-800 bg-cyber-950/60 text-slate-400 font-mono uppercase tracking-wider text-[11px]">
            <th class="py-3 px-5">Dispositivo</th>
            <th class="py-3 px-4">Subsistema / Erro</th>
            <th class="py-3 px-4">SLA</th>
            <th class="py-3 px-4">Risco RMA (ML)</th>
            <th class="py-3 px-4">Status da Máquina</th>
            <th class="py-3 px-4 text-right">Ação</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-cyber-800/60 font-mono">
          <tr
            v-for="alert in filteredAlerts"
            :key="alert.alert_id"
            @click="emit('select', alert)"
            :class="[
              'cursor-pointer transition group hover:bg-cyber-850/60',
              selectedAlertId === alert.alert_id ? 'bg-cyan-950/30 border-l-2 border-l-neon-cyan' : ''
            ]"
          >
            <!-- Device -->
            <td class="py-3.5 px-5">
              <div class="flex items-center gap-3">
                <div class="w-7 h-7 rounded bg-cyber-850 border border-cyber-700 flex items-center justify-center text-slate-300">
                  <Laptop v-if="alert.device_type === 'NOTEBOOK'" class="w-3.5 h-3.5 text-cyan-400" />
                  <Smartphone v-else class="w-3.5 h-3.5 text-neon-purple" />
                </div>
                <div>
                  <p class="font-bold text-white group-hover:text-neon-cyan transition">{{ alert.device_id }}</p>
                  <p class="text-[10px] text-slate-500">{{ alert.device_type }} &bull; {{ alert.sla_tier }}</p>
                </div>
              </div>
            </td>

            <!-- Subsystem & Error Code -->
            <td class="py-3.5 px-4">
              <div class="flex items-center gap-2">
                <span
                  class="text-[10px] font-bold px-2 py-0.5 rounded border uppercase"
                  :class="getSubsystemBadge(alert.subsystem)"
                >
                  {{ alert.subsystem }}
                </span>
                <span class="text-xs text-slate-200 font-bold tracking-tight">
                  {{ alert.error_code }}
                </span>
              </div>
            </td>

            <!-- SLA Tier -->
            <td class="py-3.5 px-4">
              <span class="text-[11px] text-slate-300">
                {{ alert.sla_tier }}
              </span>
            </td>

            <!-- RMA Risk Gauge Bar -->
            <td class="py-3.5 px-4">
              <div v-if="alert.rma_risk_score !== null && alert.rma_risk_score !== undefined" class="w-36">
                <div class="flex items-center justify-between text-[11px] mb-1">
                  <span
                    :class="alert.rma_risk_score >= 0.7 ? 'text-neon-rose font-bold' : 'text-slate-300'"
                  >
                    {{ (alert.rma_risk_score * 100).toFixed(0) }}%
                  </span>
                  <span v-if="alert.rma_risk_score >= 0.7" class="text-[9px] text-neon-rose uppercase font-bold tracking-wider">
                    CRÍTICO
                  </span>
                </div>
                <div class="w-full h-1.5 rounded-full bg-cyber-800 overflow-hidden border border-cyber-700">
                  <div
                    class="h-full transition-all"
                    :style="{ width: `${alert.rma_risk_score * 100}%` }"
                    :class="[
                      alert.rma_risk_score >= 0.70
                        ? 'bg-gradient-to-r from-amber-500 to-rose-500'
                        : alert.rma_risk_score >= 0.40
                        ? 'bg-amber-400'
                        : 'bg-emerald-400'
                    ]"
                  />
                </div>
              </div>
              <span v-else class="text-slate-600 text-[11px]">&mdash;</span>
            </td>

            <!-- Machine Status Badge -->
            <td class="py-3.5 px-4">
              <span
                class="inline-block text-[10px] font-mono font-semibold px-2.5 py-1 rounded border tracking-wide"
                :class="getStatusBadge(alert.current_status).class"
              >
                {{ getStatusBadge(alert.current_status).label }}
              </span>
            </td>

            <!-- Action -->
            <td class="py-3.5 px-4 text-right">
              <button
                class="inline-flex items-center gap-1 text-[11px] font-mono text-cyan-400 group-hover:text-neon-cyan transition font-semibold"
              >
                <span>Inspecionar</span>
                <ArrowRight class="w-3 h-3 group-hover:translate-x-1 transition" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
