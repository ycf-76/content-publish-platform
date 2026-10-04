import { reactive } from 'vue'

export interface ConfirmOptions {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}

// 模块级单例状态：同一时刻只会有一个确认框，组件间共享即可，避免每视图重复样板。
const state = reactive({
  visible: false,
  title: '',
  message: '',
  confirmText: '确定',
  cancelText: '取消',
  danger: false,
})

let resolver: ((value: boolean) => void) | null = null

export function useConfirm() {
  function confirm(opts: ConfirmOptions): Promise<boolean> {
    state.title = opts.title ?? '确认操作'
    state.message = opts.message
    state.confirmText = opts.confirmText ?? '确定'
    state.cancelText = opts.cancelText ?? '取消'
    state.danger = opts.danger ?? false
    state.visible = true
    return new Promise<boolean>((resolve) => {
      resolver = resolve
    })
  }

  function onConfirm() {
    state.visible = false
    resolver?.(true)
    resolver = null
  }

  function onCancel() {
    state.visible = false
    resolver?.(false)
    resolver = null
  }

  return { state, confirm, onConfirm, onCancel }
}
