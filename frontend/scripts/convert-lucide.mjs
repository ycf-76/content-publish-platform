import { readFileSync, writeFileSync } from 'fs'
import { resolve } from 'path'

const BASE = resolve(import.meta.dirname, '../src')

const LUCIDE_ICON_MAP = {
  'log-out': 'LogOut', 'arrow-left': 'ArrowLeft', 'arrow-right': 'ArrowRight',
  'git-branch': 'GitBranch', 'refresh-cw': 'RefreshCw', 'plus': 'Plus',
  'star': 'Star', 'layers': 'Layers', 'play': 'Play', 'folder': 'Folder',
  'inbox': 'Inbox', 'edit-2': 'Edit2', 'edit-3': 'Edit3', 'edit': 'Edit',
  'trash-2': 'Trash2', 'cpu': 'Cpu', 'x': 'X', 'chevron-right': 'ChevronRight',
  'chevron-left': 'ChevronLeft', 'chevron-up': 'ChevronUp', 'chevron-down': 'ChevronDown',
  'search': 'Search', 'save': 'Save', 'circle-dot': 'CircleDot',
  'layout-grid': 'LayoutGrid', 'check-circle': 'CheckCircle', 'download': 'Download',
  'upload': 'Upload', 'maximize-2': 'Maximize2', 'check': 'Check',
  'alert-circle': 'AlertCircle', 'layout-template': 'LayoutTemplate',
  'image': 'Image', 'palette': 'Palette', 'droplets': 'Droplets',
  'sparkles': 'Sparkles', 'clock': 'Clock', 'zap': 'Zap',
  'pen-tool': 'PenTool', 'eye': 'Eye', 'eye-off': 'EyeOff',
  'message-square-warning': 'MessageSquareWarning', 'trending-up': 'TrendingUp',
  'info': 'Info', 'heart': 'Heart', 'message-circle': 'MessageCircle',
  'minus-circle': 'MinusCircle', 'hash': 'Hash', 'layout-list': 'LayoutList',
  'quote': 'Quote', 'mouse-pointer-click': 'MousePointerClick',
  'smartphone': 'Smartphone', 'shield-check': 'ShieldCheck',
  'x-circle': 'XCircle', 'alert-triangle': 'AlertTriangle', 'lightbulb': 'Lightbulb',
  'send': 'Send', 'link': 'Link', 'rotate-ccw': 'RotateCcw',
  'image-off': 'ImageOff', 'sliders-horizontal': 'SlidersHorizontal',
  'rocket': 'Rocket', 'file-edit': 'FileEdit', 'external-link': 'ExternalLink',
  'radar': 'Radar', 'globe': 'Globe', 'user': 'User',
  'package-open': 'PackageOpen', 'puzzle': 'Puzzle', 'power': 'Power',
  'power-off': 'PowerOff', 'settings': 'Settings', 'loader': 'Loader',
  'help-circle': 'HelpCircle', 'activity': 'Activity', 'minimize-2': 'Minimize2',
  'play-circle': 'PlayCircle', 'pause': 'Pause', 'square': 'Square',
  'scan-search': 'ScanSearch', 'box': 'Box', 'bookmark': 'Bookmark',
  'pencil': 'Pencil', 'wrench': 'Wrench',
}

function kebabToPascal(kebab) {
  return LUCIDE_ICON_MAP[kebab] || kebab.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join('')
}

const FILES = [
  'components/workbench/SearchCard.vue',
  'components/workbench/CopywriteCard.vue',
  'components/workbench/AnalyzeCard.vue',
  'components/workbench/FinalReviewCard.vue',
  'components/workbench/ImagePlanCard.vue',
  'components/workbench/ImageGenCard.vue',
  'components/workbench/ImageReviewCard.vue',
  'components/workbench/ConfigPage.vue',
  'components/workbench/RightPanel.vue',
  'components/workbench/HistoryPage.vue',
  'components/workbench/HotCarousel.vue',
  'components/workbench/RecommendedCard.vue',
  'components/workbench/PublishCard.vue',
  'components/workbench/AuditCard.vue',
  'components/workflow/WorkflowEditor.vue',
  'views/WorkflowTemplatesView.vue',
  'views/TopicPoolView.vue',
  'views/TopicPoolDetailView.vue',
  'components/settings/PluginManagerInline.vue',
  'components/settings/PluginDetailView.vue',
]

for (const relPath of FILES) {
  const filePath = resolve(BASE, relPath)
  let content
  try {
    content = readFileSync(filePath, 'utf-8')
  } catch {
    console.log(`SKIP (not found): ${relPath}`)
    continue
  }

  const usedIcons = new Set()
  const dynamicIconExprs = []

  // Find all static data-lucide="xxx"
  const staticRe = /data-lucide="([^"]+)"/g
  let m
  while ((m = staticRe.exec(content)) !== null) {
    usedIcons.add(m[1])
  }

  // Find all dynamic :data-lucide="expr"
  const dynRe = /:data-lucide="([^"]+)"/g
  while ((m = dynRe.exec(content)) !== null) {
    dynamicIconExprs.push(m[1])
    // Extract icon names from ternary expressions like: showX ? 'eye-off' : 'eye'
    const iconNames = m[1].match(/'([a-z0-9-]+)'/g)
    if (iconNames) {
      iconNames.forEach(n => usedIcons.add(n.replace(/'/g, '')))
    }
    // Extract from variable references like: publishIcon, reviewIcon
    const varRefs = m[1].match(/\b([a-zA-Z_]\w*)\b/g)
    if (varRefs) {
      // We'll handle these manually - just note them
    }
  }

  // Generate import list
  const iconImports = [...usedIcons].sort().map(name => {
    const pascal = kebabToPascal(name)
    return pascal
  })

  if (iconImports.length === 0) {
    console.log(`SKIP (no icons): ${relPath}`)
    continue
  }

  console.log(`\n=== ${relPath} ===`)
  console.log(`Icons: ${iconImports.join(', ')}`)
  console.log(`Dynamic: ${dynamicIconExprs.join(' | ') || 'none'}`)

  // 1. Replace import line
  const importLine = `import { createIcons, icons } from 'lucide'`
  const newImportLine = `import {\n  ${iconImports.join(',\n  ')},\n} from 'lucide-vue-next'`

  if (content.includes(importLine)) {
    content = content.replace(importLine, newImportLine)
  } else {
    console.log(`  WARNING: import line not found exactly`)
    // Try to find and replace any lucide import
    content = content.replace(/import\s*\{[^}]*\}\s*from\s*'lucide'/, newImportLine)
  }

  // 2. Remove createIcons calls
  // Pattern: nextTick(() => createIcons({ icons }))
  content = content.replace(/nextTick\(\(\)\s*=>\s*\{?\s*try\s*\{\s*createIcons\(\{ icons \}\)\s*\}\s*catch\s*\{\s*\}\s*\}?\s*\)/g, '')
  content = content.replace(/nextTick\(\(\)\s*=>\s*createIcons\(\{ icons \}\)\s*\)/g, '')
  // Pattern: createIcons({ icons }) standalone
  content = content.replace(/\s*createIcons\(\{ icons \}\)\s*/g, ' ')
  // Pattern: try { createIcons({ icons }) } catch {}
  content = content.replace(/try\s*\{\s*createIcons\(\{ icons \}\)\s*\}\s*catch\s*\{\s*\}/g, '')

  // 3. Replace static <i data-lucide="xxx" style="width:Npx;height:Npx;"></i>
  // with <Xxx :size="N" />
  content = content.replace(/<i\s+data-lucide="([^"]+)"\s+style="width:(\d+)px;\s*height:(\d+)px;?"\s*><\/i>/g,
    (_, name, w, h) => {
      const pascal = kebabToPascal(name)
      const size = w === h ? w : `${w},${h}`
      return `<${pascal} :size="${size}" />`
    }
  )

  // 4. Replace <i data-lucide="xxx" class="yyy"></i>
  content = content.replace(/<i\s+data-lucide="([^"]+)"\s+class="([^"]+)"\s*><\/i>/g,
    (_, name, cls) => {
      const pascal = kebabToPascal(name)
      return `<${pascal} class="${cls}" :size="16" />`
    }
  )

  // 5. Replace <i data-lucide="xxx"></i> (no style, no class)
  content = content.replace(/<i\s+data-lucide="([^"]+)"\s*><\/i>/g,
    (_, name) => {
      const pascal = kebabToPascal(name)
      return `<${pascal} :size="16" />`
    }
  )

  // 6. Replace <i data-lucide="xxx" style="..." :style="..."></i> (style + :style)
  content = content.replace(/<i\s+data-lucide="([^"]+)"\s+style="([^"]+)"\s+:style="([^"]+)"\s*><\/i>/g,
    (_, name, style, dynStyle) => {
      const pascal = kebabToPascal(name)
      const sizeMatch = style.match(/width:(\d+)px/)
      const size = sizeMatch ? sizeMatch[1] : '16'
      return `<${pascal} :size="${size}" :style="${dynStyle}" />`
    }
  )

  // 7. Replace <i data-lucide="xxx" style="..." class="..."></i>
  content = content.replace(/<i\s+data-lucide="([^"]+)"\s+style="([^"]+)"\s*><\/i>/g,
    (_, name, style) => {
      const pascal = kebabToPascal(name)
      const sizeMatch = style.match(/width:(\d+)px/)
      const size = sizeMatch ? sizeMatch[1] : '16'
      const opacityMatch = style.match(/opacity:([0-9.]+)/)
      const colorMatch = style.match(/color:([^;]+)/)
      let extra = ''
      if (opacityMatch) extra += ` style="opacity:${opacityMatch[1]}"`
      if (colorMatch && !extra) extra += ` style="color:${colorMatch[1]}"`
      return `<${pascal} :size="${size}"${extra} />`
    }
  )

  // 8. Replace dynamic :data-lucide with component :is
  // This is the tricky part - we need to handle ternary expressions
  // <i :data-lucide="showX ? 'eye-off' : 'eye'" style="..."></i>
  // => <EyeOff v-if="showX" :size="16" /><Eye v-else :size="16" />
  // or use a computed component map

  // For simple ternaries with two known icons
  content = content.replace(/<i\s+:data-lucide="([^?]+)\s*\?\s*'([a-z0-9-]+)'\s*:\s*'([a-z0-9-]+)'"\s+style="width:(\d+)px;\s*height:(\d+)px;?"\s*><\/i>/g,
    (_, cond, ifIcon, elseIcon, w, h) => {
      const ifPascal = kebabToPascal(ifIcon)
      const elsePascal = kebabToPascal(elseIcon)
      const size = w === h ? w : `${w},${h}`
      return `<${ifPascal} v-if="${cond}" :size="${size}" /><${elsePascal} v-else :size="${size}" />`
    }
  )

  // Dynamic with :style
  content = content.replace(/<i\s+:data-lucide="([^?]+)\s*\?\s*'([a-z0-9-]+)'\s*\s*:\s*'([a-z0-9-]+)'"\s+style="width:(\d+)px;\s*height:(\d+)px;?"\s+:style="([^"]+)"\s*><\/i>/g,
    (_, cond, ifIcon, elseIcon, w, h, dynStyle) => {
      const ifPascal = kebabToPascal(ifIcon)
      const elsePascal = kebabToPascal(elseIcon)
      const size = w === h ? w : `${w},${h}`
      return `<${ifPascal} v-if="${cond}" :size="${size}" :style="${dynStyle}" /><${elsePascal} v-else :size="${size}" :style="${dynStyle}" />`
    }
  )

  // Dynamic with variable reference like :data-lucide="publishIcon"
  // These need manual handling - we'll convert to component :is pattern
  // <i :data-lucide="someVar" style="..." :style="..."></i>
  // => <component :is="someVarComponent" :size="16" />
  // But we need to add a computed that maps the string to component

  // For now, replace variable-bound :data-lucide with a comment marker
  // so we can handle them manually
  const varDynRe = /<i\s+:data-lucide="(\w+)"\s+style="width:(\d+)px;\s*height:(\d+)px;?"\s*:style="([^"]+)"\s*><\/i>/g
  content = content.replace(varDynRe,
    (_, varName, w, h, dynStyle) => {
      const size = w === h ? w : `${w},${h}`
      return `<component :is="${varName}Component" :size="${size}" :style="${dynStyle}" />`
    }
  )

  // Simple variable binding without :style
  const varDynRe2 = /<i\s+:data-lucide="(\w+)"\s*><\/i>/g
  content = content.replace(varDynRe2,
    (_, varName) => {
      return `<component :is="${varName}Component" :size="16" />`
    }
  )

  // :data-lucide with class and :class
  content = content.replace(/<i\s+:data-lucide="([^"]+)"\s+:class="([^"]+)"\s*><\/i>/g,
    (_, expr, cls) => {
      return `<component :is="iconComponent(${expr})" :class="${cls}" :size="16" />`
    }
  )

  // Clean up empty lines left by removed createIcons calls
  content = content.replace(/\n\s*\n\s*\n/g, '\n\n')

  writeFileSync(filePath, content, 'utf-8')
  console.log(`  DONE`)
}

console.log('\n\n=== CONVERSION COMPLETE ===')
console.log('NOTE: Files with dynamic :data-lucide bindings (variable references like publishIcon, reviewIcon)')
console.log('need manual follow-up to add computed component maps.')