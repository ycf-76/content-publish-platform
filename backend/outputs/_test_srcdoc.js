const ttsHtml = '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=800,initial-scale=1"></head><body><div class="player"><h2>语音合成</h2><audio controls style="width:100%"><source src="/outputs/tts_output.mp3" type="audio/mpeg"></audio></div></body></html>';

function prepareSrcdocHtml(html, pageWidth) {
  let result = html;
  const viewportContent = 'width=' + pageWidth + ',initial-scale=1';
  if (/<meta\s+name=["']viewport["'][^>]*>/i.test(result)) {
    result = result.replace(/<meta\s+name=["']viewport["'][^>]*>/gi, '<meta name="viewport" content="' + viewportContent + '">');
  }
  const baseHref = 'http://localhost:3001/';
  const baseTag = '<base href="' + baseHref + '">';
  if (/<head[^>]*>/i.test(result)) {
    result = result.replace(/<head[^>]*>/i, '$&' + baseTag);
  }
  return result;
}

const processed = prepareSrcdocHtml(ttsHtml, 800);
console.log('=== PROCESSED HTML ===');
console.log(processed);
console.log('');
console.log('=== KEY CHECKS ===');
console.log('has <base href>:', processed.includes('<base href="http://localhost:3001/">'));
console.log('has viewport=800:', processed.includes('width=800,initial-scale=1'));
console.log('audio src preserved:', processed.includes('/outputs/tts_output.mp3'));

const resolved = new URL('/outputs/tts_output.mp3', 'http://localhost:3001/');
console.log('resolved audio URL:', resolved.href);