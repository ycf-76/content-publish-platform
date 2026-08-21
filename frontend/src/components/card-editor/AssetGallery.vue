<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listAssets, uploadAssets, deleteAsset, type ImageAsset } from '@/api/assets'

const emit = defineEmits<{
  'set-as-page': [asset: ImageAsset]
  'set-as-background': [asset: ImageAsset]
}>()

const assets = ref<ImageAsset[]>([])
const loading = ref(false)
const uploading = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  await refresh()
})

async function refresh() {
  loading.value = true
  error.value = null
  try {
    assets.value = await listAssets()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '素材加载失败'
  } finally {
    loading.value = false
  }
}

async function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (!files.length) return

  uploading.value = true
  try {
    const uploaded = await uploadAssets(files)
    assets.value = [...assets.value, ...uploaded]
  } catch (e) {
    error.value = e instanceof Error ? e.message : '上传失败'
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function handleDelete(assetId: string) {
  try {
    await deleteAsset(assetId)
    assets.value = assets.value.filter(a => a.asset_id !== assetId)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '删除失败'
  }
}
</script>

<template>
  <div class="asset-gallery">
    <div class="asset-upload">
      <input id="asset-file-input" type="file" accept="image/*" multiple @change="handleUpload" />
      <label for="asset-file-input" class="upload-btn">
        {{ uploading ? '上传中...' : '+ 上传图片' }}
      </label>
    </div>

    <div v-if="loading" class="gallery-loading">加载中...</div>
    <div v-else-if="error" class="gallery-error">{{ error }}</div>
    <div v-else-if="assets.length === 0" class="gallery-empty">暂无素材，点击上方按钮上传</div>
    <div v-else class="asset-grid">
      <div v-for="asset in assets" :key="asset.asset_id" class="asset-card">
        <div class="asset-thumb">
          <img :src="asset.thumbnail_url" :alt="asset.filename" />
          <div class="asset-overlay">
            <button class="overlay-btn" @click="emit('set-as-page', asset)" title="设为图片页">图片页</button>
            <button class="overlay-btn" @click="emit('set-as-background', asset)" title="设为背景">背景</button>
          </div>
        </div>
        <div class="asset-info">
          <span class="asset-name">{{ asset.filename }}</span>
          <button class="asset-delete" @click="handleDelete(asset.asset_id)" title="删除">×</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.asset-gallery {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
}
.asset-upload { position: relative; }
.asset-upload input { display: none; }
.upload-btn {
  display: block;
  text-align: center;
  padding: 8px;
  border-radius: 6px;
  background: rgba(37,99,235,0.15);
  color: #93c5fd;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px dashed rgba(37,99,235,0.3);
  transition: all 0.15s;
}
.upload-btn:hover { background: rgba(37,99,235,0.25); }
.gallery-loading, .gallery-error, .gallery-empty {
  font-size: 12px;
  color: #64748b;
  text-align: center;
  padding: 20px 0;
}
.asset-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.asset-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.asset-thumb {
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  aspect-ratio: 3 / 4;
  background: rgba(255,255,255,0.04);
}
.asset-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.asset-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  gap: 4px;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.5);
  opacity: 0;
  transition: opacity 0.15s;
}
.asset-thumb:hover .asset-overlay { opacity: 1; }
.overlay-btn {
  padding: 4px 8px;
  border: none;
  border-radius: 4px;
  background: rgba(255,255,255,0.2);
  color: #fff;
  font-size: 10px;
  cursor: pointer;
  transition: background 0.12s;
}
.overlay-btn:hover { background: rgba(37,99,235,0.6); }
.asset-info {
  display: flex;
  align-items: center;
  gap: 4px;
}
.asset-name {
  flex: 1;
  font-size: 10px;
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asset-delete {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 3px;
  color: #64748b;
  cursor: pointer;
  font-size: 12px;
}
.asset-delete:hover { color: #f87171; background: rgba(239,68,68,0.15); }
</style>