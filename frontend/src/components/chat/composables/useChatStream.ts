import { ref, onUnmounted } from 'vue'
import type { ChatMessage } from '../cell-types'

export function useChatStream() {
  const isStreaming = ref(false)
  const streamingHasContent = ref(false)
  const streamingThinking = ref(false)
  const streamingClock = ref(0)
  const streamingMsg = ref<ChatMessage | null>(null)

  let streamStartTs = 0
  let clockTimer: ReturnType<typeof setInterval> | null = null
  let abortController: AbortController | null = null

  let _onStreamComplete: (() => void) | null = null
  let _beforeFinish: (() => void) | null = null
  let _safetyTimeout: ReturnType<typeof setTimeout> | null = null
  let _agentDoneTimer: ReturnType<typeof setTimeout> | null = null
  let _sseDone = false
  let _idleMs = 180_000

  function startClock() {
    streamStartTs = Date.now()
    streamingClock.value = 0
    clockTimer = setInterval(() => {
      streamingClock.value = Math.floor((Date.now() - streamStartTs) / 1000)
    }, 500)
  }

  function stopClock() {
    if (clockTimer) {
      clearInterval(clockTimer)
      clockTimer = null
    }
  }

  function createAbortController(): AbortController {
    abortController = new AbortController()
    return abortController
  }

  function getAbortController(): AbortController | null {
    return abortController
  }

  function clearAbortController() {
    abortController = null
  }

  function abort() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
  }

  function resetStreamState() {
    isStreaming.value = false
    streamingHasContent.value = false
    streamingThinking.value = false
    streamingMsg.value = null
    abortController = null
    _onStreamComplete = null
    _sseDone = false
    if (_safetyTimeout) {
      clearTimeout(_safetyTimeout)
      _safetyTimeout = null
    }
    if (_agentDoneTimer) {
      clearTimeout(_agentDoneTimer)
      _agentDoneTimer = null
    }
  }

  function _armIdleTimer(idleMs: number) {
    if (_safetyTimeout) {
      clearTimeout(_safetyTimeout)
      _safetyTimeout = null
    }
    if (idleMs <= 0) return
    _safetyTimeout = setTimeout(() => {
      if (isStreaming.value && !_sseDone) {
        console.warn(`[ChatStream] idle timeout: no activity for ${idleMs}ms, forcing reset`)
        _finishStream()
      }
    }, idleMs)
  }

  /**
   * 空闲超时（idle timeout），而非发起后的绝对超时。
   * 旧实现是「发起 180s 后无条件结束」，但视频制作后端预算是 900s
   * （loop.py _VIDEO_TOTAL_TIMEOUT），成片没出来 UI 就先判定结束，
   * 表现为「还没做完就停了」。改为：只要有数据流就续期，
   * 只有长时间完全无数据才兜底收尾。
   */
  function beginStream(onComplete: () => void, idleMs = 300_000) {
    _onStreamComplete = onComplete
    _sseDone = false
    _idleMs = idleMs
    isStreaming.value = true
    _armIdleTimer(idleMs)
  }

  /** 收到任意流式数据（delta / 阶段事件）时续期，防止长任务被误杀。 */
  function touchStream() {
    if (!isStreaming.value || _sseDone) return
    _armIdleTimer(_idleMs)
  }

  /** 视频等长任务：放宽空闲阈值（渲染耗时数分钟且期间无增量文本）。 */
  function setIdleTimeout(idleMs: number) {
    _idleMs = idleMs
    if (isStreaming.value && !_sseDone) _armIdleTimer(idleMs)
  }

  function notifySseComplete() {
    _sseDone = true
    if (_safetyTimeout) {
      clearTimeout(_safetyTimeout)
      _safetyTimeout = null
    }
    if (_agentDoneTimer) {
      clearTimeout(_agentDoneTimer)
      _agentDoneTimer = null
    }
    _finishStream()
  }

  /**
   * Codex turn 生命周期原则：终态事件（SSE 关闭）才是唯一结束信号。
   * POST /api/v1/chat/agent 是非流式端点——后端把整个 agentic loop 跑完才返回，
   * 此时 SSE 播放器可能仍在追赶积压的 delta。所以在 agent loop 结束时
   * 不能立即收尾，而是：SSE 已结束 → 立即收尾；否则最多再等 graceMs 兜底，
   * 防止 SSE 永远不回来时 UI 卡在 streaming 状态。
   */
  function notifyAgentLoopDone(graceMs = 10_000) {
    if (_sseDone || !isStreaming.value) {
      _finishStream()
      return
    }
    if (_agentDoneTimer) clearTimeout(_agentDoneTimer)
    _agentDoneTimer = setTimeout(() => {
      _agentDoneTimer = null
      if (isStreaming.value && !_sseDone) {
        console.warn('[ChatStream] agent loop done but SSE did not finish, finishing after grace period')
        _finishStream()
      }
    }, graceMs)
  }

  function notifyImmediateComplete() {
    _sseDone = true
    if (_safetyTimeout) {
      clearTimeout(_safetyTimeout)
      _safetyTimeout = null
    }
    _finishStream()
  }

  /**
   * 暂停流式状态（等待用户确认高危操作）。
   * 与 notifyImmediateComplete 不同：isStreaming 保持 true，状态指示器继续显示，
   * 只是停止空闲超时计时器（确认等待可能很长，不应被 180s 超时杀掉）。
   * 确认后调用 resumeFromPause() 恢复。
   */
  function notifyPaused() {
    if (_safetyTimeout) {
      clearTimeout(_safetyTimeout)
      _safetyTimeout = null
    }
    if (_agentDoneTimer) {
      clearTimeout(_agentDoneTimer)
      _agentDoneTimer = null
    }
  }

  /**
   * 从确认暂停中恢复：重新启动空闲超时，续期流式状态。
   */
  function resumeFromPause() {
    _sseDone = false
    _armIdleTimer(_idleMs)
  }

  function _finishStream() {
    if (!isStreaming.value) return
    if (_beforeFinish) {
      _beforeFinish()
    }
    isStreaming.value = false
    if (_onStreamComplete) {
      const cb = _onStreamComplete
      _onStreamComplete = null
      cb()
    }
  }

  onUnmounted(() => {
    if (clockTimer) { clearInterval(clockTimer); clockTimer = null }
    if (abortController) { abortController.abort(); abortController = null }
    if (_safetyTimeout) { clearTimeout(_safetyTimeout); _safetyTimeout = null }
    if (_agentDoneTimer) { clearTimeout(_agentDoneTimer); _agentDoneTimer = null }
  })

  return {
    isStreaming,
    streamingHasContent,
    streamingThinking,
    streamingClock,
    streamingMsg,
    startClock,
    stopClock,
    createAbortController,
    getAbortController,
    clearAbortController,
    abort,
    resetStreamState,
    beginStream,
    touchStream,
    setIdleTimeout,
    setBeforeFinish: (fn: (() => void) | null) => { _beforeFinish = fn },
    notifySseComplete,
    notifyAgentLoopDone,
    notifyImmediateComplete,
    notifyPaused,
    resumeFromPause,
  }
}