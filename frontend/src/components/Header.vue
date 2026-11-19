<script setup lang="ts">
import { defineProps, defineEmits } from 'vue'
import { Activity, RefreshCw, ShieldAlert, Cpu } from 'lucide-vue-next'
import type { SystemMetrics } from '@/types/alert'

const props = defineProps<{
  metrics: SystemMetrics | null
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
}>()
</script>

<template>
  <header class="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-30 px-6 py-4">
    <div class="max-w-7xl mx-auto flex items-center justify-between">
      <!-- Brand & Identity -->
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <Activity class="w-5 h-5 text-white animate-pulse" />
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="font-bold text-lg text-white tracking-tight">FleetPulse <span class="text-cyan-400">AI</span></h1>
            <span class="text-[10px] uppercase font-mono tracking-widest bg-cyan-950/80 text-cyan-400 px-2 py-0.5 rounded border border-cyan-800/50">
              Sprint 5 Live
            </span>
          </div>
          <p class="text-xs text-slate-400">Telemetria Proativa, RAG Híbrido & Human-in-the-Loop</p>
        </div>
      </div>

      <!-- Live System & Circuit Health Indicators -->
      <div class="flex items-center gap-4">
        <!-- Circuit Breaker Pill -->
        <div class="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60 text-xs font-mono">
          <Cpu class="w-4 h-4 text-slate-400" />
          <span class="text-slate-400">Circuit Breaker:</span>
          <span
            :class="{
              'text-emerald-400 font-semibold flex items-center gap-1': props.metrics?.circuit_breaker_state === 'CLOSED',
              'text-rose-400 font-semibold flex items-center gap-1': props.metrics?.circuit_breaker_state === 'OPEN',
              'text-amber-400 font-semibold flex items-center gap-1': props.metrics?.circuit_breaker_state === 'HALF_OPEN'
            }"
          >
            <span class="w-2 h-2 rounded-full inline-block"
              :class="{
                'bg-emerald-400 animate-ping': props.metrics?.circuit_breaker_state === 'CLOSED',
                'bg-rose-400 animate-ping': props.metrics?.circuit_breaker_state === 'OPEN',
                'bg-amber-400 animate-ping': props.metrics?.circuit_breaker_state === 'HALF_OPEN',
              }"
            />
            {{ props.metrics?.circuit_breaker_state || 'CLOSED' }}
          </span>
        </div>

        <!-- DLQ indicator if items exist -->
        <div v-if="props.metrics && props.metrics.dlq_count > 0" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs font-mono">
          <ShieldAlert class="w-4 h-4 text-rose-400 animate-bounce" />
          <span>DLQ: {{ props.metrics.dlq_count }}</span>
        </div>

        <!-- Refresh Button -->
        <button
          @click="emit('refresh')"
          :disabled="props.loading"
          class="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition disabled:opacity-50"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin text-cyan-400': props.loading }" />
          <span>Atualizar</span>
        </button>
      </div>
    </div>
  </header>
</template>
