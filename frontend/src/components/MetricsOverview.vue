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
    <!-- Total Ingested Alerts -->
    <div class="p-5 rounded-xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Alertas Ingeridos</p>
          <p class="text-2xl font-bold text-white mt-1 font-mono">
            {{ props.metrics?.total_alerts || 0 }}
          </p>
        </div>
        <div class="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
          <Layers class="w-5 h-5" />
        </div>
      </div>
      <div class="mt-3 flex items-center gap-1.5 text-xs text-slate-400">
        <span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
        <span>Máquina de estados assíncrona</span>
      </div>
    </div>

    <!-- High RMA Risk Alerts -->
    <div class="p-5 rounded-xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Alto Risco RMA (&ge; 70%)</p>
          <p class="text-2xl font-bold text-rose-400 mt-1 font-mono">
            {{ props.metrics?.high_rma_alerts || 0 }}
          </p>
        </div>
        <div class="w-10 h-10 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
          <AlertTriangle class="w-5 h-5" />
        </div>
      </div>
      <div class="mt-3 flex items-center gap-1.5 text-xs text-rose-400/80 font-medium">
        <span>Previsto por Random Forest + SHAP</span>
      </div>
    </div>

    <!-- Pending Human Review -->
    <div class="p-5 rounded-xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Human-in-the-Loop</p>
          <p class="text-2xl font-bold text-amber-400 mt-1 font-mono">
            {{ props.metrics?.pending_human_review || 0 }}
          </p>
        </div>
        <div class="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
          <UserCheck class="w-5 h-5" />
        </div>
      </div>
      <div class="mt-3 flex items-center gap-1.5 text-xs text-slate-400">
        <span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
        <span>Aguardando revisão do operador</span>
      </div>
    </div>

    <!-- Semantic Cache Hit Rate -->
    <div class="p-5 rounded-xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Cache Semântico (L1+L2)</p>
          <p class="text-2xl font-bold text-emerald-400 mt-1 font-mono">
            {{ ((props.metrics?.semantic_cache_hit_rate || 0) * 100).toFixed(1) }}%
          </p>
        </div>
        <div class="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
          <Zap class="w-5 h-5" />
        </div>
      </div>
      <div class="mt-3 flex items-center gap-1.5 text-xs text-slate-400">
        <span class="text-emerald-400 font-medium">Redis + pgvector</span>
        <span>amortecendo rajadas</span>
      </div>
    </div>
  </div>
</template>
