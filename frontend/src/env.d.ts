/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// Lucide Icons 全局类型声明（用于 window.lucide.createIcons()）
interface Window {
  lucide?: {
    createIcons: () => void
  }
}

declare namespace chrome {
  namespace runtime {
    function sendMessage(extensionId: string, message: any): Promise<any>
  }
}