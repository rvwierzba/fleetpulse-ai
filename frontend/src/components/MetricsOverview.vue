<script setup lang="ts">
import { defineProps } from 'vue'
import { AlertTriangle, UserCheck, Zap, Layers } from 'lucide-vue-next'
import type { SystemMetrics } from '@/types/alert'

const props = defineProps<{
  metrics: SystemMetrics | null
}>()
</script>

<template>
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
    <!-- Card 1: Total Ingested Alerts -->
    <div class="hud-corner-card p-5 rounded-lg bg-cyber-900/90 border border-cyber-800 backdrop-blur-md shadow-cyber-card group hover:border-cyber-700 transition">
      <div class="flex items-center justify-between">
        <div>
          <span class="text-[10px] font-mono tracking-wider uppercase text-cyan-400 font-semibold">TELEMETRY // PIPELINE</span>
          <p class="text-xs font-medium text-slate-400 mt-0.5">Alertas Ingeridos</p>
          <p class="text-3xl font-extrabold text-white mt-1.5 font-mono tracking-tight">
            {{ props.metrics?.total_alerts || 0 }}
          </p>
        </div>
        <div class="w-11 h-11 rounded-lg bg-cyan-950/60 border border-cyan-800/60 flex items-center justify-center text-neon-cyan shadow-neon-cyan">
          <Layers class="w-5 h-5" />
        </div>
      </div>
      <div class="mt-4 pt-3 border-t border-cyber-800/80 flex items-center justify-between text-[11px] font-mono text-slate-400">
        <span class="flex items-center gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full bg-neon-cyan animate-pulse"></span>
          <span>Máquina Assíncrona</span>
        </span>
        <span class="text-slate-500">Redis Stream</span>
      </div>
    </div>

    <!-- Card 2: High RMA Risk Alerts -->
    <div class="hud-corner-card p-5 rounded-lg bg-cyber-900/90 border border-cyber-800 backdrop-blur-md shadow-cyber-card group hover:border-rose-900/40 transition">
      <div class="flex items-center justify-between">
        <div>
          <span class="text-[10px] font-mono tracking-wider uppercase text-neon-rose font-semibold">PREDICTIVE ML // SHAP</span>
          <p class="text-xs font-medium text-slate-400 mt-0.5">Alto Risco RMA (&ge; 70%)</p>
          <p class="text-3xl font-extrabold text-neon-rose mt-1.5 font-mono tracking-tight drop-shadow-[0_0_8px_rgba(244,63,94,0.3)]">
            {{ props.metrics?.high_rma_alerts || 0 }}
          </p>
        </div>
        <div class="w-11 h-11 rounded-lg bg-rose-950/60 border border-rose-800/60 flex items-center justify-center text-neon-rose shadow-neon-rose">
          <AlertTriangle class="w-5 h-5" />
        </div>
      </div>
      <div class="mt-4 pt-3 border-t border-cyber-800/80 flex items-center justify-between text-[11px] font-mono">
        <span class="text-rose-400/90 font-medium">Random Forest Classifier</span>
        <span class="text-slate-500">Invariante #6</span>
      </div>
    </div>

    <!-- Card 3: Pending Human Review (HITL) -->
    <div class="hud-corner-card p-5 rounded-lg bg-cyber-900/90 border border-cyber-800 backdrop-blur-md shadow-cyber-card group hover:border-amber-900/40 transition">
      <div class="flex items-center justify-between">
        <div>
          <span class="text-[10px] font-mono tracking-wider uppercase text-neon-amber font-semibold">GOVERNANCE // HITL</span>
          <p class="text-xs font-medium text-slate-400 mt-0.5">Revisão Humana</p>
          <p class="text-3xl font-extrabold text-neon-amber mt-1.5 font-mono tracking-tight drop-shadow-[0_0_8px_rgba(245,158,11,0.3)]">
            {{ props.metrics?.pending_human_review || 0 }}
          </p>
        </div>
        <div class="w-11 h-11 rounded-lg bg-amber-950/60 border border-amber-800/60 flex items-center justify-center text-neon-amber shadow-neon-amber">
          <UserCheck class="w-5 h-5" />
        </div>
      </div>
      <div class="mt-4 pt-3 border-t border-cyber-800/80 flex items-center justify-between text-[11px] font-mono">
        <span class="flex items-center gap-1.5 text-amber-300">
          <span class="w-1.5 h-1.5 rounded-full bg-neon-amber animate-ping"></span>
          <span>Aguardando Operador</span>
        </span>
        <span class="text-slate-500">Nível N2</span>
      </div>
    </div>

    <!-- Card 4: Semantic Cache Hit Rate -->
    <div class="hud-corner-card p-5 rounded-lg bg-cyber-900/90 border border-cyber-800 backdrop-blur-md shadow-cyber-card group hover:border-emerald-900/40 transition">
      <div class="flex items-center justify-between">
        <div>
          <span class="text-[10px] font-mono tracking-wider uppercase text-neon-emerald font-semibold">EFFICIENCY // L1 + L2</span>
          <p class="text-xs font-medium text-slate-400 mt-0.5">Cache Semântico</p>
          <p class="text-3xl font-extrabold text-neon-emerald mt-1.5 font-mono tracking-tight drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]">
            {{ ((props.metrics?.semantic_cache_hit_rate || 0) * 100).toFixed(1) }}%
          </p>
        </div>
        <div class="w-11 h-11 rounded-lg bg-emerald-950/60 border border-emerald-800/60 flex items-center justify-center text-neon-emerald">
          <Zap class="w-5 h-5" />
        </div>
      </div>
      <div class="mt-4 pt-3 border-t border-cyber-800/80 flex items-center justify-between text-[11px] font-mono text-slate-400">
        <span class="text-emerald-400 font-medium">pgvector + Redis</span>
        <span class="text-slate-500">Amortecedor</span>
      </div>
    </div>
  </div>
</template>
