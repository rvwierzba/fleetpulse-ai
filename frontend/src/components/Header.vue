<script setup lang="ts">
import { defineProps, defineEmits, ref, onMounted, onUnmounted } from 'vue'
import { Activity, RefreshCw, ShieldAlert, Cpu, Zap, Radio, Clock } from 'lucide-vue-next'
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

const currentTime = ref('')

function updateClock() {
  const now = new Date()
  currentTime.value = now.toTimeString().split(' ')[0] + ' UTC' + (now.getTimezoneOffset() > 0 ? '-' : '+') + Math.abs(now.getTimezoneOffset() / 60)
}

let clockTimer: any = null
onMounted(() => {
  updateClock()
  clockTimer = setInterval(updateClock, 1000)
})

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
})
</script>

<template>
  <header class="relative border-b border-cyber-800 bg-cyber-900/80 backdrop-blur-xl sticky top-0 z-30">
    <!-- Top hairline cyan glow -->
    <div class="h-[1px] w-full bg-gradient-to-r from-transparent via-neon-cyan/60 to-transparent"></div>

    <div class="max-w-7xl mx-auto px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
      <!-- Left: Brand & Telemetry Mission Control -->
      <div class="flex items-center gap-3.5">
        <div class="relative w-10 h-10 rounded-lg bg-cyber-850 border border-cyber-700 flex items-center justify-center shadow-neon-cyan">
          <Activity class="w-5 h-5 text-neon-cyan animate-pulse" />
          <span class="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-neon-emerald animate-ping" />
          <span class="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-neon-emerald" />
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="font-bold text-base tracking-wider uppercase text-white font-mono">
              FleetPulse <span class="text-neon-cyan drop-shadow-[0_0_8px_rgba(0,240,255,0.6)]">AI</span>
            </h1>
            <span class="text-[9px] uppercase font-mono tracking-widest bg-cyber-800 text-neon-cyan px-2 py-0.5 rounded border border-cyan-500/30">
              MISSION CONTROL
            </span>
          </div>
          <p class="text-[11px] text-slate-400 font-mono tracking-tight flex items-center gap-1.5 mt-0.5">
            <Radio class="w-3 h-3 text-neon-emerald" />
            <span>Autonomous Triage & Human-in-the-Loop Gateway</span>
          </p>
        </div>
      </div>

      <!-- Right: Real-Time Telemetry HUD & Controls -->
      <div class="flex items-center flex-wrap gap-3">
        <!-- Live Clock -->
        <div class="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-cyber-850 border border-cyber-700 text-[11px] font-mono text-slate-300">
          <Clock class="w-3.5 h-3.5 text-slate-400" />
          <span>{{ currentTime }}</span>
        </div>

        <!-- Circuit Breaker Status Pill -->
        <div class="flex items-center gap-2 px-3 py-1.5 rounded-md bg-cyber-850 border border-cyber-700 text-xs font-mono">
          <Cpu class="w-3.5 h-3.5 text-slate-400" />
          <span class="text-slate-400 text-[11px] uppercase">Circuit:</span>
          <span
            :class="{
              'text-neon-emerald font-bold flex items-center gap-1.5': props.metrics?.circuit_breaker_state === 'CLOSED',
              'text-neon-rose font-bold flex items-center gap-1.5': props.metrics?.circuit_breaker_state === 'OPEN',
              'text-neon-amber font-bold flex items-center gap-1.5': props.metrics?.circuit_breaker_state === 'HALF_OPEN'
            }"
          >
            <span
              class="w-2 h-2 rounded-full inline-block"
              :class="{
                'bg-neon-emerald': props.metrics?.circuit_breaker_state === 'CLOSED',
                'bg-neon-rose animate-pulse': props.metrics?.circuit_breaker_state === 'OPEN',
                'bg-neon-amber animate-pulse': props.metrics?.circuit_breaker_state === 'HALF_OPEN',
              }"
            />
            {{ props.metrics?.circuit_breaker_state || 'CLOSED' }}
          </span>
        </div>

        <!-- DLQ indicator if active -->
        <div v-if="props.metrics && props.metrics.dlq_count > 0" class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-rose-950/80 border border-rose-700/80 text-rose-300 text-xs font-mono shadow-neon-rose">
          <ShieldAlert class="w-3.5 h-3.5 text-neon-rose animate-bounce" />
          <span>DLQ: {{ props.metrics.dlq_count }}</span>
        </div>

        <!-- Simulator Injection Button -->
        <button
          @click="emit('simulate')"
          :disabled="props.simulating"
          class="flex items-center gap-2 px-3.5 py-1.5 rounded-md bg-gradient-to-r from-cyan-600/90 to-blue-600/90 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-mono font-semibold tracking-wide border border-cyan-400/40 shadow-neon-cyan transition disabled:opacity-50"
        >
          <Zap class="w-3.5 h-3.5" :class="{ 'animate-spin': props.simulating }" />
          <span>{{ props.simulating ? 'Injetando...' : 'Injetar Telemetria' }}</span>
        </button>

        <!-- Refresh Button -->
        <button
          @click="emit('refresh')"
          :disabled="props.loading"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-cyber-850 hover:bg-cyber-800 text-slate-300 text-xs font-mono border border-cyber-700 transition disabled:opacity-50"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin text-neon-cyan': props.loading }" />
          <span class="hidden sm:inline">Sincronizar</span>
        </button>
      </div>
    </div>
  </header>
</template>
