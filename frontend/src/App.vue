<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import Header from '@/components/Header.vue'
import MetricsOverview from '@/components/MetricsOverview.vue'
import AlertTable from '@/components/AlertTable.vue'
import AlertDetailDrawer from '@/components/AlertDetailDrawer.vue'
import { fetchAlerts, fetchSystemMetrics, fetchAlertDetail, simulateAlerts } from '@/services/api'
import type { AlertDetail, SystemMetrics } from '@/types/alert'

const alerts = ref<AlertDetail[]>([])
const metrics = ref<SystemMetrics | null>(null)
const selectedAlert = ref<AlertDetail | null>(null)
const loading = ref(false)
const simulating = ref(false)
const currentFilter = ref<string>('ALL')

let pollTimer: any = null

async function loadData() {
  loading.value = true
  try {
    const [fetchedAlerts, fetchedMetrics] = await Promise.all([
      fetchAlerts(currentFilter.value),
      fetchSystemMetrics(),
    ])
    alerts.value = fetchedAlerts
    metrics.value = fetchedMetrics

    // Keep drawer in sync if an alert is selected
    if (selectedAlert.value) {
      const refreshed = fetchedAlerts.find((a) => a.alert_id === selectedAlert.value?.alert_id)
      if (refreshed) {
        selectedAlert.value = refreshed
      }
    }
  } catch (err) {
    console.error('Failed to load dashboard telemetry', err)
  } finally {
    loading.value = false
  }
}

async function handleSimulate() {
  simulating.value = true
  try {
    await simulateAlerts()
    await loadData()
  } catch (err) {
    console.error('Failed to simulate telemetry', err)
  } finally {
    simulating.value = false
  }
}

async function handleSelectAlert(alert: AlertDetail) {
  try {
    const fullDetail = await fetchAlertDetail(alert.alert_id)
    selectedAlert.value = fullDetail
  } catch (err) {
    selectedAlert.value = alert
  }
}

function handleCloseDrawer() {
  selectedAlert.value = null
}

function handleAlertResolved(updated: AlertDetail) {
  selectedAlert.value = updated
  loadData()
}

function handleFilterChange(status: string) {
  currentFilter.value = status
  loadData()
}

onMounted(async () => {
  await loadData()
  // Auto-seed on first boot if database is completely empty so dashboard never looks barren
  if (alerts.value.length === 0) {
    await handleSimulate()
  }
  // Auto-refresh every 5s for live dashboard experience
  pollTimer = setInterval(loadData, 5000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="min-h-screen bg-cyber-950 text-slate-100 flex flex-col font-sans selection:bg-neon-cyan/30 selection:text-neon-cyan">
    <!-- Header -->
    <Header
      :metrics="metrics"
      :loading="loading"
      :simulating="simulating"
      @refresh="loadData"
      @simulate="handleSimulate"
    />

    <!-- Main Content -->
    <main class="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6">
      <!-- 4 High-Tech KPI Cards -->
      <MetricsOverview :metrics="metrics" />

      <!-- Live Incident Feed Table -->
      <AlertTable
        :alerts="alerts"
        :selected-alert-id="selectedAlert?.alert_id || null"
        @select="handleSelectAlert"
        @filter-change="handleFilterChange"
        @simulate="handleSimulate"
      />
    </main>

    <!-- Side Inspection & Action Drawer -->
    <AlertDetailDrawer
      :alert="selectedAlert"
      @close="handleCloseDrawer"
      @resolved="handleAlertResolved"
    />
  </div>
</template>
