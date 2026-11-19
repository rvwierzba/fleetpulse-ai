<script setup lang="ts">
import { defineProps, defineEmits, ref, watch } from 'vue'
import {
  X,
  CheckCircle,
  GitBranch,
  ShieldCheck,
  ArrowRight,
  Loader2,
  Cpu,
  FileText
} from 'lucide-vue-next'
import type { AlertDetail, AlertStatus } from '@/types/alert'
import { resolveAlert, subscribeAlertStream } from '@/services/api'

const props = defineProps<{
  alert: AlertDetail | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'resolved', updated: AlertDetail): void
}>()

const resolutionNote = ref('')
const isResolving = ref(false)
const resolveError = ref<string | null>(null)
const liveEvents = ref<any[]>([])

const orderedSteps: { key: AlertStatus; label: string }[] = [
  { key: 'RECEIVED', label: 'Recebido' },
  { key: 'DEDUPED', label: 'Deduplicado' },
  { key: 'ML_SCORED', label: 'Score ML' },
  { key: 'CONTEXT_RETRIEVED', label: 'RAG Contexto' },
  { key: 'AGENT_DIAGNOSED', label: 'Agente IA' },
  { key: 'SCHEMA_VALIDATED', label: 'Validado' },
  { key: 'HUMAN_REVIEW', label: 'Revisão' },
  { key: 'RESOLVED', label: 'Resolvido' },
]

function getStepIndex(status: AlertStatus): number {
  if (status === 'AUTO_RECOMMENDED') return 6
  const idx = orderedSteps.findIndex((s) => s.key === status)
  return idx >= 0 ? idx : 0
}

let unsubscribeStream: (() => void) | null = null

watch(
  () => props.alert?.alert_id,
  (newId) => {
    resolutionNote.value = ''
    resolveError.value = null
    if (unsubscribeStream) {
      unsubscribeStream()
      unsubscribeStream = null
    }

    if (newId && props.alert) {
      liveEvents.value = [...(props.alert.events || [])]
      unsubscribeStream = subscribeAlertStream(
        newId,
        (event) => {
          liveEvents.value.push(event)
          if (props.alert) {
            props.alert.current_status = event.to_status
          }
        },
        (err) => console.debug('SSE stream status', err)
      )
    }
  },
  { immediate: true }
)

async function handleResolve(presetNote?: string) {
  if (!props.alert) return
  isResolving.value = true
  resolveError.value = null
  const note = presetNote || resolutionNote.value || 'Intervenção aprovada pelo operador N2.'
  try {
    const updated = await resolveAlert(
      props.alert.alert_id,
      note,
      props.alert.triage_action || 'OPERATOR_DISPATCH_CONFIRMED'
    )
    emit('resolved', updated)
  } catch (err: any) {
    resolveError.value = err.message || 'Falha ao processar resolução'
  } finally {
    isResolving.value = false
  }
}
</script>

<template>
  <div
    v-if="props.alert"
    class="fixed inset-y-0 right-0 w-full sm:w-[540px] bg-slate-900 border-l border-slate-800 shadow-2xl z-50 flex flex-col overflow-hidden"
  >
    <!-- Header -->
    <div class="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
      <div>
        <div class="flex items-center gap-2">
          <h3 class="text-sm font-semibold text-slate-100">{{ props.alert.device_id }}</h3>
          <span class="text-xs px-2 py-0.5 rounded font-mono font-medium bg-slate-800 text-slate-200 border border-slate-700">
            {{ props.alert.error_code }}
          </span>
        </div>
        <p class="text-xs text-slate-400 mt-0.5">
          {{ props.alert.device_type }} &bull; {{ props.alert.subsystem }} &bull; SLA: {{ props.alert.sla_tier }}
        </p>
      </div>

      <button
        @click="emit('close')"
        class="w-8 h-8 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 flex items-center justify-center transition"
      >
        <X class="w-4 h-4" />
      </button>
    </div>

    <!-- Scrollable Body -->
    <div class="flex-1 overflow-y-auto p-6 space-y-6 divide-y divide-slate-800">
      <!-- 1. Real-Time State Machine Stepper -->
      <div>
        <div class="flex items-center justify-between mb-3">
          <h4 class="text-xs font-semibold uppercase text-slate-400 tracking-wider flex items-center gap-2">
            <GitBranch class="w-3.5 h-3.5 text-blue-400" />
            <span>Fluxo do Alerta (Tempo Real)</span>
          </h4>
          <span class="text-xs font-medium px-2 py-0.5 rounded bg-slate-800 text-slate-300">
            {{ props.alert.current_status }}
          </span>
        </div>

        <div class="p-4 rounded-lg bg-slate-950/60 border border-slate-800">
          <div class="grid grid-cols-4 sm:grid-cols-8 gap-1 text-center">
            <div
              v-for="(step, idx) in orderedSteps"
              :key="step.key"
              class="flex flex-col items-center"
            >
              <div
                class="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-medium border transition mb-1"
                :class="[
                  idx <= getStepIndex(props.alert.current_status)
                    ? 'bg-blue-600 text-white border-blue-500'
                    : 'bg-slate-800 text-slate-500 border-slate-700'
                ]"
              >
                {{ idx + 1 }}
              </div>
              <span class="text-[9px] text-slate-400 leading-tight">{{ step.label }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. SHAP Predictive Explanation -->
      <div class="pt-6">
        <div class="flex items-center justify-between mb-3">
          <h4 class="text-xs font-semibold uppercase text-slate-400 tracking-wider flex items-center gap-2">
            <Cpu class="w-3.5 h-3.5 text-slate-400" />
            <span>Fatores de Risco de Falha (SHAP)</span>
          </h4>
          <span
            class="text-xs font-medium px-2 py-0.5 rounded"
            :class="[
              (props.alert.rma_risk_score || 0) >= 0.70
                ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
            ]"
          >
            Risco RMA: {{ ((props.alert.rma_risk_score || 0) * 100).toFixed(0) }}%
          </span>
        </div>

        <div class="p-4 rounded-lg bg-slate-950/60 border border-slate-800 space-y-3">
          <p class="text-xs text-slate-400">
            Peso das variáveis na decisão do modelo preditivo:
          </p>

          <div
            v-for="(factor, fIdx) in (props.alert.shap_factors || [])"
            :key="fIdx"
            class="space-y-1"
          >
            <div class="flex items-center justify-between text-xs">
              <span class="text-slate-300">{{ factor.feature || factor.feature_name || factor.human_label }}</span>
              <span
                class="font-medium"
                :class="(factor.importance ?? factor.attribution_value ?? 0) >= 0 ? 'text-red-400' : 'text-emerald-400'"
              >
                {{ (factor.importance ?? factor.attribution_value ?? 0) >= 0 ? '+' : '' }}{{ (((factor.importance ?? factor.attribution_value ?? 0)) * 100).toFixed(1) }}%
                <span v-if="factor.value !== undefined" class="text-slate-500 text-[11px] font-normal">(val: {{ factor.value }})</span>
              </span>
            </div>
            <div class="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div
                class="h-full rounded-full"
                :style="{ width: `${Math.min(100, Math.abs(factor.importance ?? factor.attribution_value ?? 0) * 200)}%` }"
                :class="(factor.importance ?? factor.attribution_value ?? 0) >= 0 ? 'bg-red-500' : 'bg-emerald-500'"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 3. Neo4j Knowledge Graph Lineage -->
      <div class="pt-6">
        <h4 class="text-xs font-semibold uppercase text-slate-400 tracking-wider flex items-center gap-2 mb-3">
          <span>Linhagem Causal de Falhas</span>
        </h4>

        <div class="p-4 rounded-lg bg-slate-950/60 border border-slate-800">
          <div class="flex items-center flex-wrap gap-2 text-xs">
            <template
              v-for="(node, nIdx) in (props.alert.rag_context?.graph_lineage || [props.alert.device_id, props.alert.subsystem, props.alert.error_code, 'Runbook #01'])"
              :key="nIdx"
            >
              <span class="px-2.5 py-1 rounded bg-slate-800 text-slate-200 text-xs">
                {{ node }}
              </span>
              <ArrowRight
                v-if="nIdx < (props.alert.rag_context?.graph_lineage || []).length - 1"
                class="w-3 h-3 text-slate-500"
              />
            </template>
          </div>

          <div v-if="props.alert.matched_bulletin_id" class="mt-3 pt-3 border-t border-slate-800 text-xs text-slate-400 flex items-center gap-2">
            <FileText class="w-3.5 h-3.5 text-blue-400" />
            <span>Boletim Técnico: <strong class="text-slate-200">{{ props.alert.matched_bulletin_id }}</strong></span>
            <span v-if="props.alert.semantic_cache_hit" class="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              Cache Hit
            </span>
          </div>
        </div>
      </div>

      <!-- 4. AI Diagnosis -->
      <div class="pt-6">
        <h4 class="text-xs font-semibold uppercase text-slate-400 tracking-wider flex items-center gap-2 mb-3">
          <ShieldCheck class="w-3.5 h-3.5 text-emerald-400" />
          <span>Diagnóstico do Agente</span>
        </h4>

        <div class="p-4 rounded-lg bg-slate-950/60 border border-slate-800 space-y-2 text-xs">
          <div class="flex items-center justify-between">
            <span class="text-slate-400">Ação Sugerida:</span>
            <span class="text-slate-200 font-medium">{{ props.alert.triage_action || 'DIAGNOSIS_PENDING' }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-slate-400">Confiança do Modelo:</span>
            <span class="text-emerald-400 font-medium">{{ ((props.alert.agent_confidence || 0.90) * 100).toFixed(0) }}%</span>
          </div>
          <div class="mt-2 p-2.5 rounded bg-slate-900 text-slate-300 leading-relaxed text-xs">
            {{ props.alert.agent_diagnosis?.summary || props.alert.description || 'Alerta diagnosticado pelo modelo especialista de frota.' }}
          </div>
        </div>
      </div>

      <!-- 5. Human-in-the-Loop Operator Action -->
      <div class="pt-6">
        <h4 class="text-xs font-semibold uppercase text-slate-400 tracking-wider mb-3">
          Aprovação do Operador
        </h4>

        <div
          v-if="props.alert.current_status === 'HUMAN_REVIEW' || props.alert.requires_human_approval"
          class="p-4 rounded-lg bg-amber-500/5 border border-amber-500/20 space-y-3"
        >
          <p class="text-xs text-amber-300/90 leading-relaxed">
            Este alerta possui risco elevado de RMA e requer validação manual para liberação de ordem de serviço.
          </p>

          <!-- Quick Presets -->
          <div class="flex items-center flex-wrap gap-2">
            <button
              @click="handleResolve('Substituição de hardware aprovada. Técnico de campo despachado.')"
              :disabled="isResolving"
              class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs transition"
            >
              + Despachar Substituição
            </button>
            <button
              @click="handleResolve('Rollback de firmware executado remotamente.')"
              :disabled="isResolving"
              class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs transition"
            >
              + Rollback Remoto
            </button>
          </div>

          <!-- Note Input -->
          <div>
            <textarea
              v-model="resolutionNote"
              placeholder="Notas de auditoria do operador..."
              rows="2"
              class="w-full p-2.5 rounded bg-slate-900 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition"
            />
          </div>

          <div v-if="resolveError" class="text-red-400 text-xs">
            {{ resolveError }}
          </div>

          <button
            @click="handleResolve()"
            :disabled="isResolving"
            class="w-full py-2 px-4 rounded bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs transition flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Loader2 v-if="isResolving" class="w-4 h-4 animate-spin" />
            <CheckCircle v-else class="w-4 h-4" />
            <span>Aprovar Intervenção</span>
          </button>
        </div>

        <div v-else class="p-4 rounded-lg bg-slate-950/60 border border-slate-800 text-center text-xs text-slate-400">
          <CheckCircle class="w-5 h-5 text-emerald-400 mx-auto mb-1.5" />
          <span>Este incidente já foi resolvido ou automatizado sem bloqueio humano.</span>
        </div>
      </div>
    </div>
  </div>
</template>
