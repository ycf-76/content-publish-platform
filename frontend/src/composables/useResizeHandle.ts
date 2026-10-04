import { ref, onUnmounted } from 'vue'

export interface ResizeHandleOptions {
  direction: 'left' | 'right'
  minWidth: number
  maxWidth: number
  storageKey: string
  defaultWidth?: () => number
}

export function useResizeHandle(options: ResizeHandleOptions) {
  const {
    direction,
    minWidth,
    maxWidth,
    storageKey,
    defaultWidth = () => Math.max(minWidth, Math.min(maxWidth, Math.floor(window.innerWidth / 3))),
  } = options

  const width = ref(Number(localStorage.getItem(storageKey)) || defaultWidth())
  const isResizing = ref(false)

  let rafId = 0
  let startX = 0
  let startWidth = 0

  function clamp(v: number) {
    return Math.max(minWidth, Math.min(v, maxWidth))
  }

  function startResize(e: MouseEvent) {
    e.preventDefault()
    startX = e.clientX
    startWidth = width.value
    isResizing.value = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.body.classList.add('is-panel-resizing')
    document.addEventListener('mousemove', onResizeMove)
    document.addEventListener('mouseup', onResizeEnd)
  }

  function onResizeMove(e: MouseEvent) {
    if (!isResizing.value) return
    const delta = direction === 'right'
      ? startX - e.clientX
      : e.clientX - startX
    cancelAnimationFrame(rafId)
    rafId = requestAnimationFrame(() => {
      width.value = clamp(startWidth + delta)
    })
  }

  function onResizeEnd() {
    cancelAnimationFrame(rafId)
    isResizing.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    document.body.classList.remove('is-panel-resizing')
    document.removeEventListener('mousemove', onResizeMove)
    document.removeEventListener('mouseup', onResizeEnd)
    localStorage.setItem(storageKey, String(width.value))
  }

  function resetWidth() {
    width.value = defaultWidth()
    localStorage.setItem(storageKey, String(width.value))
  }

  onUnmounted(() => {
    cancelAnimationFrame(rafId)
    if (isResizing.value) {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.body.classList.remove('is-panel-resizing')
      document.removeEventListener('mousemove', onResizeMove)
      document.removeEventListener('mouseup', onResizeEnd)
    }
  })

  return {
    width,
    isResizing,
    startResize,
    resetWidth,
  }
}