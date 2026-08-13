import { ref, watch, onUnmounted } from 'vue'

/**
 * 图片预览模态框（lightbox）状态管理
 *
 * 从 WorkbenchView.vue 抽出的 lightbox 逻辑。
 * 接收图片列表的 getter 函数，返回响应式状态和操作方法。
 */
export function useImagePreview(
  imageGenImagesGetter: () => { dataUrl: string; bytes?: number }[],
  imageReviewImagesGetter: () => { dataUrl: string; bytes?: number; role?: string; description?: string }[],
) {
  const lightboxVisible = ref(false)
  const lightboxCurrentUrl = ref('')
  const lightboxCurrentIndex = ref(0)
  const lightboxList = ref<{ dataUrl: string }[]>([])

  /** 打开图片预览（支持列表，可左右切换） */
  function previewImage(img: { dataUrl: string; bytes?: number }) {
    const genList = imageGenImagesGetter()
    const reviewList = imageReviewImagesGetter()
    const list = genList.length > 0
      ? genList
      : reviewList.length > 0
        ? reviewList
        : [img]
    lightboxList.value = list.map(g => ({ dataUrl: g.dataUrl }))
    lightboxCurrentIndex.value = list.findIndex(g => g.dataUrl === img.dataUrl)
    if (lightboxCurrentIndex.value < 0) lightboxCurrentIndex.value = 0
    lightboxCurrentUrl.value = lightboxList.value[lightboxCurrentIndex.value]?.dataUrl || img.dataUrl
    lightboxVisible.value = true
  }

  function lightboxPrev() {
    if (lightboxList.value.length === 0) return
    lightboxCurrentIndex.value = (lightboxCurrentIndex.value - 1 + lightboxList.value.length) % lightboxList.value.length
    lightboxCurrentUrl.value = lightboxList.value[lightboxCurrentIndex.value].dataUrl
  }

  function lightboxNext() {
    if (lightboxList.value.length === 0) return
    lightboxCurrentIndex.value = (lightboxCurrentIndex.value + 1) % lightboxList.value.length
    lightboxCurrentUrl.value = lightboxList.value[lightboxCurrentIndex.value].dataUrl
  }

  function lightboxClose() {
    lightboxVisible.value = false
  }

  /** lightbox 键盘快捷键：ESC 关闭、← → 切换 */
  function onLightboxKeydown(e: KeyboardEvent) {
    if (!lightboxVisible.value) return
    if (e.key === 'Escape') lightboxClose()
    else if (e.key === 'ArrowLeft') lightboxPrev()
    else if (e.key === 'ArrowRight') lightboxNext()
  }

  watch(lightboxVisible, (v) => {
    if (v) {
      window.addEventListener('keydown', onLightboxKeydown)
      document.body.style.overflow = 'hidden'
    } else {
      window.removeEventListener('keydown', onLightboxKeydown)
      document.body.style.overflow = ''
    }
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', onLightboxKeydown)
    document.body.style.overflow = ''
  })

  return {
    lightboxVisible,
    lightboxCurrentUrl,
    lightboxCurrentIndex,
    lightboxList,
    previewImage,
    lightboxPrev,
    lightboxNext,
    lightboxClose,
  }
}