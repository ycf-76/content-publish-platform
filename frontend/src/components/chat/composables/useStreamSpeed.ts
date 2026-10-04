import { ref, watch } from 'vue'

const STORAGE_KEY = 'stream_speed_config'

const DEFAULTS = {
  targetLag: 0.15,
  minCps: 120,
  maxCps: 4800,
  frameMs: 16,
}

const BOUNDS = {
  targetLag: { min: 0.02, max: 2.0, step: 0.01 },
  minCps: { min: 20, max: 800, step: 10 },
  maxCps: { min: 500, max: 10000, step: 100 },
  frameMs: { min: 8, max: 64, step: 4 },
}

function _clamp(v: number, b: { min: number; max: number }): number {
  return Math.max(b.min, Math.min(b.max, v))
}

function _load(): typeof DEFAULTS {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        targetLag: _clamp(parsed.targetLag, BOUNDS.targetLag),
        minCps: _clamp(parsed.minCps, BOUNDS.minCps),
        maxCps: _clamp(parsed.maxCps, BOUNDS.maxCps),
        frameMs: _clamp(parsed.frameMs, BOUNDS.frameMs),
      }
    }
  } catch {}
  return { ...DEFAULTS }
}

function _save(vals: typeof DEFAULTS) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(vals))
  } catch {}
}

const saved = _load()

export const streamTargetLag = ref(saved.targetLag)
export const streamMinCps = ref(saved.minCps)
export const streamMaxCps = ref(saved.maxCps)
export const streamFrameMs = ref(saved.frameMs)

export const streamSpeedBounds = BOUNDS
export const streamSpeedDefaults = DEFAULTS

let _watchInstalled = false

function _syncToStorage() {
  _save({
    targetLag: streamTargetLag.value,
    minCps: streamMinCps.value,
    maxCps: streamMaxCps.value,
    frameMs: streamFrameMs.value,
  })
}

function _ensureWatch() {
  if (_watchInstalled) return
  _watchInstalled = true
  watch([streamTargetLag, streamMinCps, streamMaxCps, streamFrameMs], _syncToStorage)
}

export function useStreamSpeed() {
  _ensureWatch()
  return {
    targetLag: streamTargetLag,
    minCps: streamMinCps,
    maxCps: streamMaxCps,
    frameMs: streamFrameMs,
    bounds: BOUNDS,
    defaults: DEFAULTS,
    reset: resetStreamSpeed,
  }
}

export function resetStreamSpeed() {
  streamTargetLag.value = DEFAULTS.targetLag
  streamMinCps.value = DEFAULTS.minCps
  streamMaxCps.value = DEFAULTS.maxCps
  streamFrameMs.value = DEFAULTS.frameMs
  _syncToStorage()
}