import { ref, watch, onUnmounted, type Ref } from 'vue'

/**
 * 打字机效果：目标文本变化时，displayed 逐字追赶，实现"每个字打印"的视觉效果。
 *
 * - 目标是当前显示的延续（前缀匹配）→ 每 tick 追加 1~N 字，落后越多打越快
 * - 目标被重置（非延续或清空）→ 立即同步，从新起点继续打
 * - 组件卸载自动清理定时器
 */
export function useTypewriter(
  target: Ref<string>,
  opts?: { intervalMs?: number; charsPerTick?: number },
) {
  const intervalMs = opts?.intervalMs ?? 35
  const charsPerTick = opts?.charsPerTick ?? 1

  const displayed = ref('')
  let timer: ReturnType<typeof setInterval> | null = null

  function stopTimer() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function tick() {
    const t = target.value
    const d = displayed.value

    // 目标清空（节点重跑）：立即清空显示
    if (t.length === 0) {
      displayed.value = ''
      stopTimer()
      return
    }

    // 目标非延续（覆盖式更新或重置）：从头重打
    if (!t.startsWith(d)) {
      displayed.value = ''
      return
    }

    if (d.length >= t.length) {
      stopTimer()
      return
    }

    // 自适应速度：落后越多单次打的字越多，避免落后于推送速度
    const behind = t.length - d.length
    const n = behind > 40 ? Math.ceil(behind / 8)
            : behind > 15 ? 3
            : charsPerTick
    displayed.value = t.slice(0, d.length + n)
  }

  watch(target, (t) => {
    if (t === displayed.value) return
    if (!timer) timer = setInterval(tick, intervalMs)
  }, { immediate: true })

  onUnmounted(stopTimer)

  return { displayed }
}
