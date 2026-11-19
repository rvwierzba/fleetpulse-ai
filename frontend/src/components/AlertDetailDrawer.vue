<script setup lang="ts">
import { defineProps, defineEmits, ref, watch } from 'vue'
import {
  X,
  CheckCircle,
  UserCheck,
  Brain,
  Share2,
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
  { key: 'ML_SCORED', label: 'Score ML + SHAP' },
  { key: 'CONTEXT_RETRIEVED', label: 'RAG Híbrido' },
  { key: 'AGENT_DIAGNOSED', label: 'Agente IA' },
  { key: 'SCHEMA_VALIDATED', label: 'Pydantic OK' },
  { key: 'HUMAN_REVIEW', label: 'Decisão HITL' },
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
  const note = presetNote || resolutionNote.value || 'Intervenção validada pelo engenheiro N2 com despacho efetuado.'
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
    class="fixed inset-y-0 right-0 w-full sm:w-[580px] lg:w-[680px] bg-cyber-900 border-l border-cyber-700 shadow-2xl z-50 flex flex-col overflow-hidden backdrop-blur-2xl animate-in slide-in-from-right duration-300"
  >
    <!-- Header -->
    <div class="px-6 py-4 border-b border-cyber-800 flex items-center justify-between bg-cyber-950/80">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg bg-cyber-850 border border-cyber-700 flex items-center justify-center text-neon-cyan shadow-neon-cyan">
          <Brain class="w-5 h-5" />
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h3 class="text-sm font-bold text-white font-mono">{{ props.alert.device_id }}</h3>
            <span class="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-cyan-950 text-neon-cyan border border-cyan-800/60">
              {{ props.alert.error_code }}
            </span>
          </div>
          <p class="text-[11px] text-slate-400 font-mono mt-0.5">
            {{ props.alert.device_type }} &bull; {{ props.alert.subsystem }} &bull; SLA: {{ props.alert.sla_tier }}
          </p>
        </div>
      </div>

      <button
        @click="emit('close')"
        class="w-8 h-8 rounded-md bg-cyber-850 hover:bg-cyber-800 text-slate-400 hover:text-white flex items-center justify-center border border-cyber-700 transition"
      >
        <X class="w-4 h-4" />
      </button>
    </div>

    <!-- Scrollable Body -->
    <div class="flex-1 overflow-y-auto p-6 space-y-6 divide-y divide-cyber-800/80 font-mono">
      <!-- 1. Real-Time State Machine Stepper -->
      <div>
        <div class="flex items-center justify-between mb-3">
          <h4 class="text-xs font-bold uppercase text-slate-300 tracking-wider flex items-center gap-2">
            <GitBranch class="w-4 h-4 text-neon-cyan" />
            <span>Máquina de Estados (SSE Ao Vivo)</span>
          </h4>
          <span class="text-[10px] font-mono px-2.5 py-0.5 rounded bg-cyan-950 text-neon-cyan border border-cyan-800/60 font-bold">
            {{ props.alert.current_status }}
          </span>
        </div>

        <div class="p-4 rounded-lg bg-cyber-950/80 border border-cyber-800">
          <div class="grid grid-cols-4 sm:grid-cols-8 gap-1 text-center">
            <div
              v-for="(step, idx) in orderedSteps"
              :key="step.key"
              class="flex flex-col items-center"
            >
              <div
                class="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold border transition mb-1"
                :class="[
                  idx <= getStepIndex(props.alert.current_status)
                    ? 'bg-cyan-500/20 text-neon-cyan border-cyan-400 shadow-neon-cyan'
                    : 'bg-cyber-850 text-slate-600 border-cyber-700'
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
          <h4 class="text-xs font-bold uppercase text-slate-300 tracking-wider flex items-center gap-2">
            <Cpu class="w-4 h-4 text-neon-rose" />
            <span>Explicabilidade do Modelo (SHAP TreeExplainer)</span>
          </h4>
          <span
            class="text-[10px] font-bold px-2 py-0.5 rounded border"
            :class="[
              (props.alert.rma_risk_score || 0) >= 0.70
                ? 'bg-rose-950 text-neon-rose border-rose-800'
                : 'bg-emerald-950 text-neon-emerald border-emerald-800'
            ]"
          >
            Risco RMA: {{ ((props.alert.rma_risk_score || 0) * 100).toFixed(0) }}%
          </span>
        </div>

        <!-- Diverging Waterfall Bars -->
        <div class="p-4 rounded-lg bg-cyber-950/80 border border-cyber-800 space-y-3">
          <p class="text-[11px] text-slate-400">
            Atribuição causal das features para predição de falha de hardware:
          </p>

          <div
            v-for="(factor, fIdx) in (props.alert.shap_factors || [])"
            :key="fIdx"
            class="space-y-1"
          >
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-slate-300">{{ factor.feature || factor.feature_name || factor.human_label }}</span>
              <span
                class="font-bold"
                :class="(factor.importance ?? factor.attribution_value ?? 0) >= 0 ? 'text-neon-rose' : 'text-neon-emerald'"
              >
                {{ (factor.importance ?? factor.attribution_value ?? 0) >= 0 ? '+' : '' }}{{ (((factor.importance ?? factor.attribution_value ?? 0)) * 100).toFixed(1) }}%
                <span v-if="factor.value !== undefined" class="text-slate-500 text-[10px] font-normal">(val: {{ factor.value }})</span>
              </span>
            </div>
            <!-- Progress bar -->
            <div class="w-full h-1.5 rounded-full bg-cyber-850 overflow-hidden">
              <div
                class="h-full rounded-full"
                :style="{ width: `${Math.min(100, Math.abs(factor.importance ?? factor.attribution_value ?? 0) * 200)}%` }"
                :class="(factor.importance ?? factor.attribution_value ?? 0) >= 0 ? 'bg-rose-500' : 'bg-emerald-500'"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 3. Neo4j Knowledge Graph Causal Lineage -->
      <div class="pt-6">
        <h4 class="text-xs font-bold uppercase text-slate-300 tracking-wider flex items-center gap-2 mb-3">
          <Share2 class="w-4 h-4 text-neon-cyan" />
          <span>Linhagem Causal no Grafo (Neo4j)</span>
        </h4>

        <div class="p-4 rounded-lg bg-cyber-950/80 border border-cyber-800">
          <div class="flex items-center flex-wrap gap-2 text-xs">
            <template
              v-for="(node, nIdx) in (props.alert.rag_context?.graph_lineage || [props.alert.device_id, props.alert.subsystem, props.alert.error_code, 'Runbook #01'])"
              :key="nIdx"
            >
              <span class="px-2.5 py-1 rounded bg-cyber-850 border border-cyber-700 text-slate-200 text-[11px] font-bold">
                {{ node }}
              </span>
              <ArrowRight
                v-if="nIdx < (props.alert.rag_context?.graph_lineage || []).length - 1"
                class="w-3 h-3 text-neon-cyan"
              />
            </template>
          </div>

          <div v-if="props.alert.matched_bulletin_id" class="mt-3 pt-3 border-t border-cyber-800 text-[11px] text-slate-400 flex items-center gap-2">
            <FileText class="w-3.5 h-3.5 text-neon-cyan" />
            <span>Boletim Técnico: <strong class="text-slate-200">{{ props.alert.matched_bulletin_id }}</strong></span>
            <span v-if="props.alert.semantic_cache_hit" class="text-[9px] px-1.5 py-0.2 rounded bg-emerald-950 text-neon-emerald border border-emerald-800">
              CACHE HIT L1
            </span>
          </div>
        </div>
      </div>

      <!-- 4. AI Triage Agent Diagnosis -->
      <div class="pt-6">
        <h4 class="text-xs font-bold uppercase text-slate-300 tracking-wider flex items-center gap-2 mb-3">
          <ShieldCheck class="w-4 h-4 text-neon-emerald" />
          <span>Diagnóstico do Agente IA (Pydantic Validado)</span>
        </h4>

        <div class="p-4 rounded-lg bg-cyber-950/80 border border-cyber-800 space-y-2 text-xs">
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-slate-400">Ação de Triagem:</span>
            <span class="text-neon-cyan font-bold">{{ props.alert.triage_action || 'DIAGNOSIS_PENDING' }}</span>
          </div>
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-slate-400">Confiança do Agente:</span>
            <span class="text-neon-emerald font-bold">{{ ((props.alert.agent_confidence || 0.90) * 100).toFixed(0) }}%</span>
          </div>
          <div class="mt-2 p-2.5 rounded bg-cyber-900 border border-cyber-800 text-[11px] text-slate-300 leading-relaxed">
            {{ props.alert.agent_diagnosis?.summary || props.alert.description || 'Alerta diagnosticado pelo modelo especialista de frota.' }}
          </div>
        </div>
      </div>

      <!-- 5. Human-in-the-Loop Operator Action -->
      <div class="pt-6">
        <div class="flex items-center justify-between mb-3">
          <h4 class="text-xs font-bold uppercase text-slate-300 tracking-wider flex items-center gap-2">
            <UserCheck class="w-4 h-4 text-neon-amber" />
            <span>Portão de Decisão Humana (Invariante #6)</span>
          </h4>
        </div>

        <div
          v-if="props.alert.current_status === 'HUMAN_REVIEW' || props.alert.requires_human_approval"
          class="p-4 rounded-lg bg-amber-950/30 border border-amber-700/60 space-y-3"
        >
          <p class="text-[11px] text-amber-200/90 leading-relaxed">
            Este alerta possui risco RMA &ge; 70% e exige aprovação expressa do operador para despacho.
          </p>

          <!-- Quick Presets -->
          <div class="flex items-center flex-wrap gap-2">
            <button
              @click="handleResolve('Substituição de hardware aprovada. Técnico de campo despachado.')"
              :disabled="isResolving"
              class="px-2.5 py-1 rounded bg-cyber-850 hover:bg-cyber-800 border border-cyber-700 text-slate-200 text-[10px] transition"
            >
              + Despachar Substituição
            </button>
            <button
              @click="handleResolve('Rollback de firmware executado remotamente.')"
              :disabled="isResolving"
              class="px-2.5 py-1 rounded bg-cyber-850 hover:bg-cyber-800 border border-cyber-700 text-slate-200 text-[10px] transition"
            >
              + Rollback Remoto
            </button>
          </div>

          <!-- Note Input -->
          <div>
            <textarea
              v-model="resolutionNote"
              placeholder="Notas de auditoria operacional do engenheiro N2..."
              rows="2"
              class="w-full p-2.5 rounded bg-cyber-900 border border-cyber-700 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-neon-amber transition"
            />
          </div>

          <div v-if="resolveError" class="text-rose-400 text-[11px]">
            {{ resolveError }}
          </div>

          <button
            @click="handleResolve()"
            :disabled="isResolving"
            class="w-full py-2 px-4 rounded bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-slate-950 font-bold text-xs tracking-wider uppercase transition shadow-neon-amber flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Loader2 v-if="isResolving" class="w-4 h-4 animate-spin" />
            <CheckCircle v-else class="w-4 h-4" />
            <span>Aprovar & Resolver Intervenção (Audit Event)</span>
          </button>
        </div>

        <div v-else class="p-4 rounded-lg bg-cyber-950/80 border border-cyber-800 text-center text-xs text-slate-400">
          <CheckCircle class="w-6 h-6 text-neon-emerald mx-auto mb-2" />
          <span>Este incidente já foi resolvido ou automatizado sem bloqueio humano.</span>
        </div>
      </div>
    </div>
  </div>
</template>
