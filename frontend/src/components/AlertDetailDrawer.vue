<script setup lang="ts">
import { defineProps, defineEmits, ref, watch } from 'vue'
import {
  X,
  CheckCircle,
  AlertTriangle,
  UserCheck,
  Brain,
  Share2,
  GitBranch,
  ShieldCheck,
  Zap,
  ArrowRight,
  Send,
  Loader2,
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

// State machine steps ordered
const orderedSteps: { key: AlertStatus; label: string }[] = [
  { key: 'RECEIVED', label: 'Recebido' },
  { key: 'DEDUPED', label: 'Deduplicado' },
  { key: 'ML_SCORED', label: 'Score ML + SHAP' },
  { key: 'CONTEXT_RETRIEVED', label: 'RAG Híbrido' },
  { key: 'AGENT_DIAGNOSED', label: 'Agente IA' },
  { key: 'SCHEMA_VALIDATED', label: 'Pydantic OK' },
  { key: 'HUMAN_REVIEW', label: 'Decisão' },
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
      // Subscribe live SSE updates
      unsubscribeStream = subscribeAlertStream(
        newId,
        (event) => {
          liveEvents.value.push(event)
          if (props.alert) {
            props.alert.current_status = event.to_status
          }
        },
        (err) => console.debug('SSE disconnected or closed', err)
      )
    }
  },
  { immediate: true }
)

async function handleResolve() {
  if (!props.alert) return
  isResolving.value = true
  resolveError.value = null
  try {
    const updated = await resolveAlert(
      props.alert.alert_id,
      resolutionNote.value || 'Intervenção operacional validada pelo engenheiro de suporte N2.',
      props.alert.triage_action || 'OPERATOR_DISPATCH_CONFIRMED'
    )
    emit('resolved', updated)
  } catch (err: any) {
    resolveError.value = err.message || 'Falha ao resolver alerta'
  } finally {
    isResolving.value = false
  }
}
</script>

<template>
  <div
    v-if="props.alert"
    class="fixed inset-y-0 right-0 w-full sm:w-[540px] lg:w-[620px] bg-slate-900 border-l border-slate-800 shadow-2xl z-50 flex flex-col overflow-hidden backdrop-blur-xl animate-in slide-in-from-right duration-300"
  >
    <!-- Drawer Header -->
    <div class="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
          <Brain class="w-4 h-4" />
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h3 class="text-sm font-bold text-white font-mono">{{ props.alert.device_id }}</h3>
            <span class="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-slate-800 text-cyan-300 border border-slate-700">
              {{ props.alert.error_code }}
            </span>
          </div>
          <p class="text-xs text-slate-400 font-mono text-[11px]">ID: {{ props.alert.alert_id }}</p>
        </div>
      </div>

      <button
        @click="emit('close')"
        class="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition"
      >
        <X class="w-4 h-4" />
      </button>
    </div>

    <!-- Scrollable Body -->
    <div class="flex-1 overflow-y-auto p-6 space-y-6 divide-y divide-slate-800/80">
      <!-- 1. Real-Time State Machine Stepper -->
      <div>
        <div class="flex items-center justify-between mb-3">
          <h4 class="text-xs font-semibold uppercase text-slate-300 tracking-wider flex items-center gap-2">
            <GitBranch class="w-3.5 h-3.5 text-cyan-400" />
            <span>Máquina de Estados (SSE Ao Vivo)</span>
          </h4>
          <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/60">
            {{ props.alert.current_status }}
          </span>
        </div>

        <div class="p-4 rounded-xl bg-slate-950/60 border border-slate-800">
          <div class="relative flex items-center justify-between">
            <div
              v-for="(step, idx) in orderedSteps"
              :key="step.key"
              class="flex flex-col items-center z-10"
            >
              <div
                class="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-mono font-bold transition-all"
                :class="[
                  idx <= getStepIndex(props.alert.current_status)
                    ? 'bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/30'
                    : 'bg-slate-800 text-slate-500 border border-slate-700'
                ]"
              >
                {{ idx + 1 }}
              </div>
              <span class="text-[9px] text-slate-400 mt-1 font-mono text-center">
                {{ step.label }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. Machine Learning & SHAP Attribution -->
      <div class="pt-6">
        <h4 class="text-xs font-semibold uppercase text-slate-300 tracking-wider mb-3 flex items-center gap-2">
          <Zap class="w-3.5 h-3.5 text-amber-400" />
          <span>Explicabilidade SHAP (TreeExplainer)</span>
        </h4>

        <div class="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
          <div class="flex items-center justify-between pb-2 border-b border-slate-800/60">
            <span class="text-xs text-slate-400">Probabilidade de Risco RMA:</span>
            <span class="text-sm font-bold font-mono" :class="(props.alert.rma_risk_score || 0) >= 0.70 ? 'text-rose-400' : 'text-emerald-400'">
              {{ ((props.alert.rma_risk_score || 0) * 100).toFixed(1) }}%
            </span>
          </div>

          <div v-if="props.alert.shap_factors && props.alert.shap_factors.length > 0" class="space-y-2">
            <p class="text-[11px] text-slate-400 font-medium">Fatores de Maior Impacto na Falha:</p>
            <div
              v-for="factor in props.alert.shap_factors"
              :key="factor.feature_name"
              class="p-2.5 rounded-lg bg-slate-900 border border-slate-800/80 flex items-center justify-between"
            >
              <div class="flex items-center gap-2">
                <span
                  class="w-1.5 h-1.5 rounded-full"
                  :class="factor.risk_direction === 'increases_risk' ? 'bg-rose-400' : 'bg-emerald-400'"
                />
                <span class="text-xs text-slate-200 font-medium">{{ factor.human_label }}</span>
              </div>
              <span
                class="font-mono text-xs font-bold"
                :class="factor.risk_direction === 'increases_risk' ? 'text-rose-400' : 'text-emerald-400'"
              >
                {{ factor.attribution_value > 0 ? `+${factor.attribution_value.toFixed(2)}` : factor.attribution_value.toFixed(2) }}
              </span>
            </div>
          </div>
          <div v-else class="text-xs text-slate-500 py-2">
            Aguardando atribuição de explicabilidade SHAP.
          </div>
        </div>
      </div>

      <!-- 3. Neo4j Knowledge Graph Lineage -->
      <div class="pt-6">
        <h4 class="text-xs font-semibold uppercase text-slate-300 tracking-wider mb-3 flex items-center gap-2">
          <Share2 class="w-3.5 h-3.5 text-indigo-400" />
          <span>Linhagem no Grafo Neo4j (Invariante #3)</span>
        </h4>

        <div class="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2.5 font-mono text-xs">
          <div class="flex items-center gap-2 text-slate-300 flex-wrap">
            <span class="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-cyan-400">{{ props.alert.device_type }}</span>
            <ArrowRight class="w-3 h-3 text-slate-600" />
            <span class="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-indigo-400">{{ props.alert.subsystem }}</span>
            <ArrowRight class="w-3 h-3 text-slate-600" />
            <span class="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-amber-400">{{ props.alert.error_code }}</span>
          </div>

          <div v-if="props.alert.matched_runbook_id" class="p-2.5 rounded-lg bg-indigo-950/30 border border-indigo-800/40 text-indigo-200 flex items-center justify-between">
            <span>Runbook Validado no Grafo:</span>
            <span class="font-bold text-indigo-300">{{ props.alert.matched_runbook_id }}</span>
          </div>

          <div v-if="props.alert.semantic_cache_hit" class="flex items-center gap-1.5 text-emerald-400 text-[11px]">
            <CheckCircle class="w-3.5 h-3.5" />
            <span>Resposta recuperada via Cache Semântico (evitou chamada redundante de LLM)</span>
          </div>
        </div>
      </div>

      <!-- 4. AI Triage Agent Card & Pydantic Diagnosis -->
      <div class="pt-6">
        <h4 class="text-xs font-semibold uppercase text-slate-300 tracking-wider mb-3 flex items-center gap-2">
          <ShieldCheck class="w-3.5 h-3.5 text-teal-400" />
          <span>Diagnóstico do Agente de Triagem</span>
        </h4>

        <div class="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
          <div class="flex items-center justify-between text-xs font-mono">
            <span class="text-slate-400">Ação Prescrita:</span>
            <span class="px-2.5 py-0.5 rounded font-bold bg-cyan-950/80 text-cyan-300 border border-cyan-800">
              {{ props.alert.triage_action || 'ANÁLISE_PENDENTE' }}
            </span>
          </div>

          <div v-if="props.alert.agent_confidence" class="flex items-center justify-between text-xs font-mono">
            <span class="text-slate-400">Certeza do Modelo:</span>
            <span class="text-slate-200 font-bold">{{ ((props.alert.agent_confidence || 0) * 100).toFixed(0) }}%</span>
          </div>

          <div v-if="props.alert.agent_diagnosis?.root_cause_analysis" class="p-3 rounded-lg bg-slate-900 border border-slate-800">
            <p class="text-[11px] font-semibold text-slate-300 uppercase tracking-wider mb-1">Causa Raiz:</p>
            <p class="text-xs text-slate-300 leading-relaxed font-sans">
              {{ props.alert.agent_diagnosis.root_cause_analysis }}
            </p>
          </div>
        </div>
      </div>

      <!-- 5. Human-in-the-Loop Operational Approval (Invariante #6) -->
      <div class="pt-6">
        <h4 class="text-xs font-semibold uppercase text-slate-300 tracking-wider mb-3 flex items-center gap-2">
          <UserCheck class="w-3.5 h-3.5 text-amber-400" />
          <span>Aprovação Human-in-the-Loop (Invariante #6)</span>
        </h4>

        <div v-if="props.alert.current_status === 'RESOLVED'" class="p-4 rounded-xl bg-emerald-950/40 border border-emerald-800/60 flex items-center gap-3 text-emerald-300">
          <CheckCircle class="w-5 h-5 text-emerald-400 shrink-0" />
          <div>
            <p class="text-xs font-bold">Incidente Finalizado e Resolvido</p>
            <p class="text-[11px] text-emerald-400/80">A intervenção operacional foi auditada e registrada na máquina de estados.</p>
          </div>
        </div>

        <div v-else class="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
          <div v-if="props.alert.current_status === 'HUMAN_REVIEW'" class="p-3 rounded-lg bg-amber-950/40 border border-amber-800/60 text-amber-300 text-xs flex items-center gap-2">
            <AlertTriangle class="w-4 h-4 shrink-0" />
            <span>Este alerta exige validação manual obrigatória antes da execução técnica.</span>
          </div>

          <div>
            <label class="block text-[11px] font-medium text-slate-400 mb-1">Nota de Resolução do Operador:</label>
            <textarea
              v-model="resolutionNote"
              placeholder="Descreva a confirmação do procedimento ou observações técnicas..."
              rows="3"
              class="w-full rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 p-3 focus:outline-none focus:border-cyan-500 font-sans resize-none"
            ></textarea>
          </div>

          <div v-if="resolveError" class="text-xs text-rose-400">
            {{ resolveError }}
          </div>

          <div class="flex items-center gap-3 pt-2">
            <button
              @click="handleResolve"
              :disabled="isResolving"
              class="flex-1 py-2.5 px-4 rounded-lg bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white text-xs font-bold transition flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/20 disabled:opacity-50"
            >
              <Loader2 v-if="isResolving" class="w-3.5 h-3.5 animate-spin" />
              <Send v-else class="w-3.5 h-3.5" />
              <span>Aprovar Ação & Resolver Incidente</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
