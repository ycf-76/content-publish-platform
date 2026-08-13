import re

f = r'd:\My_Project\多智能体小红书发布平台\frontend\src\views\TopicPoolView.vue'
with open(f, 'r', encoding='utf-8') as fh:
    content = fh.read()

icons = {
    'arrow-left': 'ArrowLeft', 'layers': 'Layers', 'star': 'Star', 'globe': 'Globe',
    'download-cloud': 'DownloadCloud', 'download': 'Download', 'loader-2': 'Loader2',
    'search': 'Search', 'refresh-cw': 'RefreshCw', 'inbox': 'Inbox', 'user': 'User',
    'users': 'Users', 'thumbs-up': 'ThumbsUp', 'bookmark': 'Bookmark',
    'message-square': 'MessageSquare', 'tag': 'Tag', 'play': 'Play', 'trash-2': 'Trash2',
    'external-link': 'ExternalLink', 'chevron-left': 'ChevronLeft', 'chevron-right': 'ChevronRight',
}

def replace_icon(m):
    name = m.group(1)
    attrs = m.group(2).strip()
    comp = icons.get(name)
    if not comp:
        return m.group(0)
    if attrs:
        return '<{} {} />'.format(comp, attrs)
    return '<{} />'.format(comp)

content = re.sub(r'<i\s+data-lucide="([a-z-]+)"([^>]*)>\s*</i>', replace_icon, content)

old_import = "import { createIcons, icons } from 'lucide'"
new_import = """import {
  ArrowLeft, Layers, Star, Globe, DownloadCloud, Download, Loader2,
  Search, RefreshCw, Inbox, User, Users, ThumbsUp, Bookmark,
  MessageSquare, Tag, Play, Trash2, ExternalLink, ChevronLeft, ChevronRight,
} from 'lucide-vue-next'"""
content = content.replace(old_import, new_import)

content = re.sub(r'\n\s*await nextTick\(\)\n\s*createIcons\(\{ icons \}\)', '', content)
content = re.sub(r'\n\s*nextTick\(\(\) => createIcons\(\{ icons \}\)\)', '', content)
content = re.sub(r'\n\s*createIcons\(\{ icons \}\)', '', content)

with open(f, 'w', encoding='utf-8') as fh:
    fh.write(content)

remaining = content.count('data-lucide') + content.count('createIcons')
print('Remaining data-lucide/createIcons: {}'.format(remaining))
print('Done')
