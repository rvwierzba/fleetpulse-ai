<script setup lang="ts">
import { defineProps, defineEmits } from 'vue'
import { RefreshCw, ShieldAlert, Cpu, Play } from 'lucide-vue-next'
import type { SystemMetrics } from '@/types/alert'

const props = defineProps<{
  metrics: SystemMetrics | null
  loading: boolean
  simulating: boolean
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
  (e: 'simulate'): void
}>()
</script>

<template>
  <header class="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-30">
    <div class="max-w-7xl mx-auto px-6 py-3.5 flex items-center justify-between">
      <!-- Brand -->
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-sm shadow-sm">
          FP
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="font-semibold text-sm text-slate-100 tracking-tight">FleetPulse</h1>
            <span class="text-[11px] font-medium px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
              Produção
            </span>
          </div>
          <p class="text-xs text-slate-400">Monitoramento e Triagem Preditiva de Hardware</p>
        </div>
      </div>

      <!-- Controls & Health Indicators -->
      <div class="flex items-center gap-3">
        <!-- Circuit Breaker Status -->
        <div class="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-800/80 border border-slate-700/80 text-xs">
          <Cpu class="w-3.5 h-3.5 text-slate-400" />
          <span class="text-slate-400">Circuit Breaker:</span>
          <span
            :class="{
              'text-emerald-400 font-medium flex items-center gap-1.5': props.metrics?.circuit_breaker_state === 'CLOSED',
              'text-red-400 font-medium flex items-center gap-1.5': props.metrics?.circuit_breaker_state === 'OPEN',
              'text-amber-400 font-medium flex items-center gap-1.5': props.metrics?.circuit_breaker_state === 'HALF_OPEN'
            }"
          >
            <span
              class="w-2 h-2 rounded-full inline-block"
              :class="{
                'bg-emerald-400': props.metrics?.circuit_breaker_state === 'CLOSED',
                'bg-red-400': props.metrics?.circuit_breaker_state === 'OPEN',
                'bg-amber-400': props.metrics?.circuit_breaker_state === 'HALF_OPEN',
              }"
            />
            {{ props.metrics?.circuit_breaker_state || 'CLOSED' }}
          </span>
        </div>

        <!-- DLQ indicator if items exist -->
        <div v-if="props.metrics && props.metrics.dlq_count > 0" class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-red-950/40 border border-red-800/60 text-red-300 text-xs">
          <ShieldAlert class="w-3.5 h-3.5 text-red-400" />
          <span>DLQ: {{ props.metrics.dlq_count }}</span>
        </div>

        <!-- Simulator Injection Button -->
        <button
          @click="emit('simulate')"
          :disabled="props.simulating"
          class="flex items-center gap-2 px-3.5 py-1.5 rounded-md bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition shadow-sm disabled:opacity-50"
        >
          <Play class="w-3 h-3 fill-current" :class="{ 'animate-spin': props.simulating }" />
          <span>{{ props.simulating ? 'Gerando dados...' : 'Simular Telemetria' }}</span>
        </button>

        <!-- Refresh Button -->
        <button
          @click="emit('refresh')"
          :disabled="props.loading"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs border border-slate-700 transition disabled:opacity-50"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin text-blue-400': props.loading }" />
          <span>Atualizar</span>
        </button>
      </div>
    </div>
  </header>
</template>
