"""通用浏览器自动化后端层（G2+）。

- client.BrowserClient：worker /browser/* 的 HTTP 客户端封装，
  含域名白名单校验（单一事实源）、运行时临时放行、P2 自愈、审计回调。
"""
