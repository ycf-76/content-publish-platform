import { ref, onMounted, onUnmounted, type Ref } from 'vue'

const SK_STATE = 'mint_dialog_state'
const SK_X = 'mint_dialog_x'
const SK_Y = 'mint_dialog_y'

/**
 * 浮动对话框：状态管理 + 拖拽 + 位置持久化
 *
 * 从 WorkbenchView.vue 抽出的灵犀助手对话框逻辑。
 * dialogState: 'expanded' | 'collapsed' | 'closed'，持久化到 localStorage。
 * 拖拽位置也持久化，展开时恢复上次位置。
 */
export function useDialogDrag() {
  const dialogState = ref(localStorage.getItem(SK_STATE) || 'expanded')
  const dialogEl = ref<HTMLElement | null>(null)
  const dragHandle = ref<HTMLElement | null>(null)
  let isDragging = false
  let startX = 0, startY = 0
  let dialogStartLeft = 0, dialogStartTop = 0

  function collapseDialog() {
    dialogState.value = 'collapsed'
    localStorage.setItem(SK_STATE, 'collapsed')
  }

  function closeDialog() {
    dialogState.value = 'closed'
    localStorage.setItem(SK_STATE, 'closed')
  }

  function expandDialog() {
    dialogState.value = 'expanded'
    localStorage.setItem(SK_STATE, 'expanded')
    restoreDialogPosition()
  }

  function restoreDialogPosition() {
    const dialog = dialogEl.value
    if (!dialog) return
    const x = localStorage.getItem(SK_X)
    const y = localStorage.getItem(SK_Y)
    if (x !== null && y !== null) {
      dialog.style.left = x + 'px'
      dialog.style.top = y + 'px'
      dialog.style.right = 'auto'
      dialog.style.bottom = 'auto'
    } else {
      dialog.style.left = 'auto'
      dialog.style.top = 'auto'
      dialog.style.right = '20px'
      dialog.style.bottom = '20px'
    }
  }

  function onPointerDown(e: PointerEvent) {
    const dialog = dialogEl.value
    const handle = dragHandle.value
    if (!dialog || !handle) return
    if ((e.target as HTMLElement).closest('.mint-dialog-btn')) return
    isDragging = true
    const rect = dialog.getBoundingClientRect()
    dialog.style.left = rect.left + 'px'
    dialog.style.top = rect.top + 'px'
    dialog.style.right = 'auto'
    dialog.style.bottom = 'auto'
    startX = e.clientX
    startY = e.clientY
    dialogStartLeft = parseFloat(dialog.style.left) || 0
    dialogStartTop = parseFloat(dialog.style.top) || 0
    handle.setPointerCapture(e.pointerId)
    e.preventDefault()
  }

  function onPointerMove(e: PointerEvent) {
    const dialog = dialogEl.value
    if (!dialog || !isDragging) return
    const dx = e.clientX - startX
    const dy = e.clientY - startY
    let newLeft = dialogStartLeft + dx
    let newTop = dialogStartTop + dy
    const dialogRect = dialog.getBoundingClientRect()
    const maxLeft = window.innerWidth - dialogRect.width
    const maxTop = window.innerHeight - dialogRect.height
    newLeft = Math.max(0, Math.min(newLeft, maxLeft))
    newTop = Math.max(0, Math.min(newTop, maxTop))
    dialog.style.left = newLeft + 'px'
    dialog.style.top = newTop + 'px'
  }

  function onPointerUp(e: PointerEvent) {
    const dialog = dialogEl.value
    const handle = dragHandle.value
    if (!dialog || !handle || !isDragging) return
    isDragging = false
    handle.releasePointerCapture(e.pointerId)
    localStorage.setItem(SK_X, String(parseFloat(dialog.style.left) || 0))
    localStorage.setItem(SK_Y, String(parseFloat(dialog.style.top) || 0))
  }

  function setupDrag() {
    const handle = dragHandle.value
    if (!handle) return
    handle.addEventListener('pointerdown', onPointerDown)
    handle.addEventListener('pointermove', onPointerMove)
    handle.addEventListener('pointerup', onPointerUp)
  }

  function destroyDrag() {
    const handle = dragHandle.value
    if (!handle) return
    handle.removeEventListener('pointerdown', onPointerDown)
    handle.removeEventListener('pointermove', onPointerMove)
    handle.removeEventListener('pointerup', onPointerUp)
  }

  return {
    dialogState,
    dialogEl,
    dragHandle,
    collapseDialog,
    closeDialog,
    expandDialog,
    restoreDialogPosition,
    setupDrag,
    destroyDrag,
  }
}