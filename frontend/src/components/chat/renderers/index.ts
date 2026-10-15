import { registerRenderer } from './registry'
import ImageRenderer from './ImageRenderer.vue'
import ImageLightbox from './ImageLightbox.vue'
import HtmlRenderer from './HtmlRenderer.vue'
import HtmlLightbox from './HtmlLightbox.vue'
import AudioRenderer from './AudioRenderer.vue'
import AudioLightbox from './AudioLightbox.vue'
import VideoRenderer from './VideoRenderer.vue'
import VideoLightbox from './VideoLightbox.vue'

registerRenderer('image', { thumb: ImageRenderer, lightbox: ImageLightbox, editable: false })
registerRenderer('html', { thumb: HtmlRenderer, lightbox: HtmlLightbox, editable: false })
registerRenderer('chart', { thumb: HtmlRenderer, lightbox: HtmlLightbox, editable: false })
registerRenderer('mindmap', { thumb: HtmlRenderer, lightbox: HtmlLightbox, editable: false })
registerRenderer('structured', { thumb: HtmlRenderer, lightbox: HtmlLightbox, editable: true })
registerRenderer('audio', { thumb: AudioRenderer, lightbox: AudioLightbox, editable: false })
registerRenderer('video', { thumb: VideoRenderer, lightbox: VideoLightbox, editable: false })

export { getRenderer, getAllRenderers } from './registry'