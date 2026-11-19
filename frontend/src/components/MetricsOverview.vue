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
    <!-- Card 1: Total Alerts -->
    <div class="p-5 rounded-lg bg-slate-900 border border-slate-800">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-slate-400">Total de Alertas</span>
        <div class="w-8 h-8 rounded bg-slate-800 flex items-center justify-center text-slate-400">
          <Layers class="w-4 h-4" />
        </div>
      </div>
      <div class="mt-2">
        <p class="text-2xl font-semibold text-slate-100">
          {{ props.metrics?.total_alerts || 0 }}
        </p>
        <p class="text-xs text-slate-400 mt-1">Fila Redis + PostgreSQL</p>
      </div>
    </div>

    <!-- Card 2: High RMA Risk -->
    <div class="p-5 rounded-lg bg-slate-900 border border-slate-800">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-slate-400">Risco Crítico de RMA</span>
        <div class="w-8 h-8 rounded bg-red-950/40 border border-red-800/40 flex items-center justify-center text-red-400">
          <AlertTriangle class="w-4 h-4" />
        </div>
      </div>
      <div class="mt-2">
        <p class="text-2xl font-semibold text-red-400">
          {{ props.metrics?.high_rma_alerts || 0 }}
        </p>
        <p class="text-xs text-slate-400 mt-1">Probabilidade &ge; 70% de troca física</p>
      </div>
    </div>

    <!-- Card 3: Pending Human Review -->
    <div class="p-5 rounded-lg bg-slate-900 border border-slate-800">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-slate-400">Revisão Humana Pendente</span>
        <div class="w-8 h-8 rounded bg-amber-950/40 border border-amber-800/40 flex items-center justify-center text-amber-400">
          <UserCheck class="w-4 h-4" />
        </div>
      </div>
      <div class="mt-2">
        <p class="text-2xl font-semibold text-amber-400">
          {{ props.metrics?.pending_human_review || 0 }}
        </p>
        <p class="text-xs text-slate-400 mt-1">Aguardando parecer do suporte N2</p>
      </div>
    </div>

    <!-- Card 4: Semantic Cache Hit Rate -->
    <div class="p-5 rounded-lg bg-slate-900 border border-slate-800">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-slate-400">Eficiência de Cache</span>
        <div class="w-8 h-8 rounded bg-emerald-950/40 border border-emerald-800/40 flex items-center justify-center text-emerald-400">
          <Zap class="w-4 h-4" />
        </div>
      </div>
      <div class="mt-2">
        <p class="text-2xl font-semibold text-emerald-400">
          {{ ((props.metrics?.semantic_cache_hit_rate || 0) * 100).toFixed(1) }}%
        </p>
        <p class="text-xs text-slate-400 mt-1">Cache semântico vetorial (pgvector)</p>
      </div>
    </div>
  </div>
</template>
