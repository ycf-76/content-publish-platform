import type { Component } from 'vue'
import type { MediaPage } from '@/types/media-content'

export interface MediaRenderer {
  thumb: Component
  lightbox: Component
  editable: boolean
}

const _registry = new Map<string, MediaRenderer>()

export function registerRenderer(mediaType: string, renderer: MediaRenderer): void {
  _registry.set(mediaType, renderer)
}

export function getRenderer(mediaType: string): MediaRenderer | null {
  return _registry.get(mediaType) ?? null
}

export function getAllRenderers(): ReadonlyMap<string, MediaRenderer> {
  return _registry
}