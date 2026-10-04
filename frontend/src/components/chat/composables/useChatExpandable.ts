import { ref } from 'vue'

export function useChatExpandable() {
  const expandedThinking = ref<Set<number>>(new Set())
  const expandedExec = ref<Set<string>>(new Set())
  const expandedDiff = ref<Set<number>>(new Set())
  const expandedAgentId = ref<string | null>(null)

  function isThinkingExpanded(idx: number): boolean {
    return expandedThinking.value.has(idx)
  }

  function toggleThinking(idx: number) {
    const s = new Set(expandedThinking.value)
    if (s.has(idx)) s.delete(idx)
    else s.add(idx)
    expandedThinking.value = s
  }

  function isExecExpanded(msgIdx: number, tcIdx: number): boolean {
    return expandedExec.value.has(`${msgIdx}-${tcIdx}`)
  }

  function toggleExec(msgIdx: number, tcIdx: number) {
    const key = `${msgIdx}-${tcIdx}`
    const s = new Set(expandedExec.value)
    if (s.has(key)) s.delete(key)
    else s.add(key)
    expandedExec.value = s
  }

  function isDiffExpanded(idx: number): boolean {
    return expandedDiff.value.has(idx)
  }

  function toggleDiff(idx: number) {
    const s = new Set(expandedDiff.value)
    if (s.has(idx)) s.delete(idx)
    else s.add(idx)
    expandedDiff.value = s
  }

  function toggleAgentExpand(agentId: string) {
    expandedAgentId.value = expandedAgentId.value === agentId ? null : agentId
  }

  function resetAll() {
    expandedThinking.value = new Set()
    expandedExec.value = new Set()
    expandedDiff.value = new Set()
    expandedAgentId.value = null
  }

  return {
    expandedThinking,
    expandedExec,
    expandedDiff,
    expandedAgentId,
    isThinkingExpanded,
    toggleThinking,
    isExecExpanded,
    toggleExec,
    isDiffExpanded,
    toggleDiff,
    toggleAgentExpand,
    resetAll,
  }
}