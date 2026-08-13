// background.js - MCP 插件后端逻辑
// 监听后端 HTTP 请求，复用浏览器已登录的小红书会话，返回结构化数据
//
// 通信架构：后端 → HTTP fetch → 本扩展 → 调小红书页面/接口
//
// 注：MV3 service worker 不能直接监听 HTTP 端口。这里通过 chrome.runtime.onMessageExternal
// 接收来自后端注入的页面脚本的请求，或通过 chrome.cookies API 直接读 cookie。

const XHS_ORIGIN = "https://www.xiaohongshu.com";
const API_BASE = "https://edith.xiaohongshu.com/api/sns/web/v1";

// ============ 工具函数 ============

// 生成 X-S / X-T 等签名参数（小红书 web API 必需）
// 注意：小红书用 cookie 中的 web_session + 页面里 window.__xhszpflowitem.verifyCodeSha1
// 这里走简化路径：直接用浏览器 fetch（同源 fetch 会自动带 cookie），无需手动签名
// 但 edith.xiaohongshu.com 是跨域，需要走 content script 注入

async function getCookiesForXHS() {
  return new Promise((resolve) => {
    chrome.cookies.getAll({ domain: ".xiaohongshu.com" }, (cookies) => {
      resolve(cookies);
    });
  });
}

async function isLoggedIn() {
  const cookies = await getCookiesForXHS();
  // 关键 cookie：web_session / xhsuserid / customer-sso-sid
  const sessionKeys = ["web_session", "xhsuserid", "customer-sso-sid", "a1"];
  const found = {};
  let loggedIn = false;
  for (const c of cookies) {
    if (sessionKeys.includes(c.name)) {
      found[c.name] = c.value;
      if (c.name === "web_session" && c.value) loggedIn = true;
    }
  }
  return { loggedIn, cookies, found };
}

// 通过 chrome.scripting.executeScript 在小红书页面的 MAIN world 执行代码
//
// 关键修复（原 content.js 方案的根因）：
//   原 content.js 运行在 ISOLATED world，访问 window.__xhszpflowitem 永远是 undefined，
//   导致 X-S/X-T 签名拿不到，所有 API 调用返回 461。
//   MAIN world 是页面自己的世界，能直接访问页面注入的签名函数。
//
// 通信架构（不再依赖 chrome.tabs.sendMessage）：
//   background.js → chrome.scripting.executeScript({world:"MAIN"}) → 在页面世界执行函数 → 直接返回结果
//
// 随机延迟（模拟人类行为，降低行为分析风控风险）
async function executeInMainWorld(action, payload) {
  // 找一个 xiaohongshu.com 标签页，没有就创建
  let tab = await findXhsTab();
  let createdNew = false;
  if (!tab) {
    console.log("[XHS MCP] no xhs tab found, creating new one");
    tab = await chrome.tabs.create({
      url: XHS_ORIGIN + "/explore",
      active: false,
    });
    createdNew = true;
    try {
      await waitTabComplete(tab.id, 15000);
    } catch (e) {
      console.warn("[XHS MCP] new tab load timeout:", e.message);
    }
  }
  console.log(`[XHS MCP] action=${action} on tab=${tab.id} createdNew=${createdNew}`);

  // 在 MAIN world 执行代码
  // 注意：executeScript 的 func 参数会被序列化后注入页面世界执行
  // 不能访问闭包变量，只能用 args 传参
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    world: "MAIN",
    func: async (actionName, actionPayload) => {
      // ===== 以下代码运行在小红书页面的 MAIN world =====
      // 这里能直接访问 window.__xhszpflowitem 等页面变量

      const API_BASE = "https://edith.xiaohongshu.com/api/sns/web/v1";

      // 生成签名参数（小红书 web API 必需 X-S / X-T）
      // 关键修复：
      //   1. 优先尝试 window._webmsxyw（小红书 web 版主签名函数）
      //   2. 兜底 window.__xhszpflowitem.sign
      //   3. 处理返回值大小写（签名函数返回 X-s/X-t 小写，header 用 X-S/X-T 大写）
      //   4. 失败时明确报错，不用 verifyCodeSha1 退化（无效签名会导致 300011 风控）
      //   5. url 参数用相对路径（/api/sns/web/v1/...），不是完整 URL
      //      —— _webmsxyw 签名算的是 path + body，传完整 URL 会算出错误签名 → 300011
      function getXhsSignParams(fullUrl, body) {
        const bodyStr = JSON.stringify(body || {});
        // 提取相对路径：把 https://edith.xiaohongshu.com 去掉，保留 /api/sns/web/v1/...
        const path = fullUrl.replace(/^https?:\/\/[^/]+/, "");
        const _diag = { tried: [], found_funcs: [], sign_path: path, sign_body_preview: bodyStr.slice(0, 80) };

        // 诊断：收集 window 上所有签名相关函数
        const signKeys = [];
        for (const k of Object.keys(window)) {
          if (/sign|webms|xhs|common|mns/i.test(k) && typeof window[k] !== "undefined") {
            signKeys.push(k + ":" + typeof window[k]);
          }
        }
        _diag.window_sign_keys = signKeys.slice(0, 20);

        // 诊断：收集 __xhszpflowitem 的所有方法
        const zpf = window.__xhszpflowitem || window.__xhszpflow || {};
        _diag.zpf_keys = Object.keys(zpf).slice(0, 20);

        // 诊断：深入检查 xhsFingerprintV3 对象
        if (window.xhsFingerprintV3) {
          _diag.xhsFingerprintV3_keys = Object.keys(window.xhsFingerprintV3).slice(0, 20);
          _diag.xhsFingerprintV3_types = {};
          for (const k of Object.keys(window.xhsFingerprintV3)) {
            _diag.xhsFingerprintV3_types[k] = typeof window.xhsFingerprintV3[k];
          }
        }

        // 方案 1：window._webmsxyw（生成 X-s / X-t）
        if (typeof window._webmsxyw === "function") {
          _diag.found_funcs.push("_webmsxyw");
          _diag.tried.push("_webmsxyw(path, bodyStr)");
          try {
            const sign = window._webmsxyw(path, bodyStr);
            _diag._webmsxyw_raw_keys = sign ? Object.keys(sign) : [];
            if (sign) {
              const xs = sign["X-s"] || sign["X-S"] || sign["x-s"] || "";
              const xt = sign["X-t"] || sign["X-T"] || sign["x-t"] || "";
              _diag._webmsxyw_got = { xs_len: xs.length, xt_len: xt.length };
            }
          } catch (e) {
            _diag._webmsxyw_error = e.message;
          }
        }

        // 方案 2：尝试多种调用方式生成 X-S/X-T
        let xs = "", xt = "", xsc = "";
        if (typeof window._webmsxyw === "function") {
          // 尝试 (path, bodyStr)
          try {
            const s1 = window._webmsxyw(path, bodyStr);
            if (s1) { xs = s1["X-s"] || s1["X-S"] || ""; xt = s1["X-t"] || s1["X-T"] || ""; }
          } catch (e) { _diag._try1_error = e.message; }

          // 尝试 (path, undefined) — GET 方式
          if (!xs) {
            try {
              const s2 = window._webmsxyw(path, undefined);
              if (s2) { xs = s2["X-s"] || s2["X-S"] || ""; xt = s2["X-t"] || s2["X-T"] || ""; }
              _diag._try2_undefined = { xs_len: xs.length };
            } catch (e) { _diag._try2_error = e.message; }
          }
        }

        // 方案 3：从 __xhszpflowitem 找 X-S-Common 生成方法
        for (const k of Object.keys(zpf)) {
          if (typeof zpf[k] === "function" && /common|sign/i.test(k)) {
            _diag.tried.push("zpf." + k);
            try {
              const r = zpf[k](path, bodyStr);
              if (r && typeof r === "object") {
                if (!xs) xs = r["X-s"] || r["X-S"] || "";
                if (!xt) xt = r["X-t"] || r["X-T"] || "";
                const c = r["X-s-common"] || r["X-S-Common"] || r["X-s-Common"] || "";
                if (c) { xsc = c; _diag._xsc_from = "zpf." + k; }
              } else if (typeof r === "string" && r.length > 20) {
                xsc = r; _diag._xsc_from = "zpf." + k + " (string)";
              }
            } catch (e) { _diag["zpf_" + k + "_error"] = e.message; }
          }
        }

        // 方案 4：尝试 window 上的其他签名函数找 X-S-Common
        if (!xsc) {
          for (const k of Object.keys(window)) {
            if (typeof window[k] === "function" && /common|mnsv2|mns/i.test(k)) {
              _diag.tried.push("window." + k);
              try {
                // mnsv2 可能需要不同的参数格式，尝试多种
                let r = null;
                try { r = window[k](path, bodyStr); } catch (e1) {
                  try { r = window[k]({ url: path, data: body }); } catch (e2) {
                    try { r = window[k](path); } catch (e3) {
                      _diag["window_" + k + "_errors"] = [e1.message, e2.message, e3.message];
                    }
                  }
                }
                if (typeof r === "string" && r.length > 20) { xsc = r; _diag._xsc_from = "window." + k + " (string)"; break; }
                if (r && typeof r === "object") {
                  const c = r["X-s-common"] || r["X-S-Common"] || r["x-s-common"] || "";
                  if (c) { xsc = c; _diag._xsc_from = "window." + k; break; }
                  // mnsv2 可能返回 {xSCommon: ...} 或其他格式
                  for (const rk of Object.keys(r)) {
                    if (/common/i.test(rk) && typeof r[rk] === "string" && r[rk].length > 20) {
                      xsc = r[rk]; _diag._xsc_from = "window." + k + "." + rk; break;
                    }
                  }
                  if (xsc) break;
                }
              } catch (e) {}
            }
          }
        }

        _diag._final = { xs_len: xs.length, xt_len: xt.length, xsc_len: xsc.length, xsc_from: _diag._xsc_from || "none" };

        if (xs && xt) {
          return { "X-S": xs, "X-T": xt, "X-S-Common": xsc, _diag };
        }

        // 签名全部失败 — 返回错误标记，不用 verifyCodeSha1 退化（无效签名会触发风控）
        _diag._all_failed = true;
        return { "X-S": "", "X-T": "", "X-S-Common": "", _diag };
      }

      // 带签名的 fetch
      async function xhsFetch(path, body = {}) {
        const url = API_BASE + path;
        const sign = getXhsSignParams(url, body);

        // 签名失败 — 直接返回错误，不发空签名请求（空签名会触发 300011 风控）
        if (!sign["X-S"] || !sign["X-T"]) {
          return {
            status: 0,
            data: {
              success: false,
              msg: "签名生成失败，无法调用 API",
              _sign_diag: sign._diag || {},
            },
          };
        }

        const headers = {
          "Content-Type": "application/json;charset=UTF-8",
          "X-S": sign["X-S"],
          "X-T": sign["X-T"],
          "X-S-Common": sign["X-S-Common"] || "",
          "Origin": "https://www.xiaohongshu.com",
          "Referer": "https://www.xiaohongshu.com/",
        };
        const resp = await fetch(url, {
          method: "POST",
          headers,
          body: JSON.stringify(body),
          credentials: "include",
        });
        const text = await resp.text();
        let json;
        try { json = JSON.parse(text); } catch { json = { raw: text }; }
        // 把签名诊断信息附到响应里，方便排查
        json._sign_diag = sign._diag || {};
        return { status: resp.status, data: json };
      }

      // 从 __NEXT_DATA__ 提取用户信息
      function extractUserFromNextData() {
        const nd = document.getElementById("__NEXT_DATA__");
        if (!nd) return null;
        try {
          const d = JSON.parse(nd.textContent || "{}");
          const findUser = (o, dp) => {
            if (!o || typeof o !== "object" || dp > 6) return null;
            if (o.user_id && o.nickname) return o;
            if (o.id && o.nickname && (o.image || o.red_id !== undefined)) {
              return { user_id: o.id, nickname: o.nickname, image: o.image, red_id: o.red_id || "" };
            }
            for (const v of Object.values(o)) {
              const r = findUser(v, dp + 1);
              if (r) return r;
            }
            return null;
          };
          const u = findUser(d.props?.pageProps, 0) || findUser(d, 0);
          if (!u) return null;
          return {
            xhs_user_id: String(u.user_id || u.id || ""),
            nickname: String(u.nickname || ""),
            avatar_url: String(u.image || u.avatar || u.avatar_url || ""),
            red_id: String(u.red_id || ""),
          };
        } catch (e) {
          return null;
        }
      }

      function genSearchId() {
        return Math.random().toString(36).slice(2) + Date.now().toString(36);
      }

      // URL 转 base64（同源 fetch）
      async function urlToBase64(url) {
        const resp = await fetch(url, { credentials: "omit", mode: "cors" });
        if (!resp.ok) throw new Error(`fetch image ${resp.status}`);
        const blob = await resp.blob();
        return new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
      }

      // ===== 业务接口分发 =====
      try {
        if (actionName === "get_user_info") {
          // 诊断：当前页面状态
          const _pageDiag = {
            url: location.href,
            title: document.title,
            has_next_data: !!document.getElementById("__NEXT_DATA__"),
            user_profile_links: document.querySelectorAll('a[href*="/user/profile/"]').length,
            login_btn: !!document.querySelector('[class*="login"]'),
          };

          // 方案 1：__NEXT_DATA__
          const u = extractUserFromNextData();
          if (u && u.xhs_user_id && u.nickname) {
            return { success: true, data: u };
          }

          // 方案 1.5：读 DOM 侧边栏用户信息（多种选择器）
          try {
            // 选择器 1：a[href*="/user/profile/"]
            let userLink = document.querySelector('a[href*="/user/profile/"]');
            // 选择器 2：侧边栏用户头像容器
            if (!userLink) userLink = document.querySelector('.side-bar .user, .user-info, .user-card, [class*="user-wrapper"]');
            // 选择器 3：任何带用户头像的链接
            if (!userLink) {
              const allLinks = document.querySelectorAll("a");
              for (const a of allLinks) {
                const href = a.getAttribute("href") || "";
                if (/\/user\/(profile|other)\/\w+/.test(href)) {
                  userLink = a;
                  break;
                }
              }
            }
            if (userLink) {
              const href = userLink.getAttribute("href") || "";
              const m = href.match(/\/user\/(profile|other)\/(\w+)/);
              const userId = m ? m[2] : "";
              const img = userLink.querySelector("img") || userLink.closest("[class*='user']")?.querySelector("img");
              const avatar = img ? (img.src || img.getAttribute("data-src") || "") : "";
              // 昵称可能在兄弟节点或父节点
              const container = userLink.closest("[class*='user']") || userLink.parentElement || userLink;
              const nameEl = container.querySelector(".nickname, .name, .user-name, .title, [class*='name']")
                || userLink.querySelector(".nickname, .name, .user-name, .title, [class*='name']");
              const nickname = nameEl ? (nameEl.textContent || "").trim() : "";
              _pageDiag.found_userLink = !!userLink;
              _pageDiag.userLink_href = href;
              _pageDiag.found_userId = userId;
              if (userId) {
                return {
                  success: true,
                  data: {
                    xhs_user_id: userId,
                    nickname: nickname || "小红书用户",
                    avatar_url: avatar,
                    red_id: "",
                  },
                };
              }
            }
            _pageDiag.found_userLink = !!userLink;
          } catch (e) {
            _pageDiag.dom_error = e.message;
          }

          // 方案 2：用页面自带的 axios 实例调 /api/sns/web/v1/user/me（GET，自动带完整签名）
          // 复用搜索里验证过的 pageAxios 查找逻辑（同时检查 post 和 get，确保找到完整的 axios 实例）
          const _diag2 = { stage: "pageAxios" };
          let pageAxiosErr = null;
          try {
            const webpackChunks = window.webpackChunkxhs_pc_web || [];
            let pageAxios = null;
            _diag2.chunk_count = webpackChunks.length;
            for (const chunk of webpackChunks) {
              if (!chunk || !chunk[1]) continue;
              const modules = chunk[1];
              for (const key of Object.keys(modules)) {
                try {
                  const mod = modules[key];
                  let result = mod({ exports: {} }, {}, {});
                  if (result && result.exports) {
                    const exp = result.exports;
                    // 和搜索一样：同时检查 post 和 get，找到完整 axios 实例
                    if (exp.default && typeof exp.default.post === "function" && typeof exp.default.get === "function") {
                      pageAxios = exp.default;
                      break;
                    }
                    if (typeof exp.post === "function" && typeof exp.get === "function") {
                      pageAxios = exp;
                      break;
                    }
                  }
                } catch (e) {}
              }
              if (pageAxios) break;
            }
            _diag2.pageAxios_found = !!pageAxios;
            if (pageAxios) {
              try {
                const axiosResp = await pageAxios.get("/api/sns/web/v1/user/me");
                _diag2.axios_status = axiosResp.status;
                _diag2.axios_data_keys = axiosResp.data ? Object.keys(axiosResp.data).slice(0, 10) : [];
                const mu = axiosResp.data?.data || axiosResp.data;
                if (mu && (mu.user_id || mu.id) && mu.nickname) {
                  return {
                    success: true,
                    data: {
                      xhs_user_id: String(mu.user_id || mu.id || ""),
                      nickname: String(mu.nickname || ""),
                      avatar_url: String(mu.image || mu.avatar || ""),
                      red_id: String(mu.red_id || ""),
                    },
                  };
                }
                _diag2.mu_keys = mu ? Object.keys(mu).slice(0, 10) : [];
              } catch (e) {
                pageAxiosErr = e.message;
                _diag2.axios_error = e.message;
              }
            }
          } catch (e) {
            pageAxiosErr = e.message;
            _diag2.outer_error = e.message;
          }

          // 方案 3：调 /user/me（手动签名 fetch，兜底）
          try {
            const resp = await xhsFetch("/user/me", {});
            _diag2.fallback_status = resp.status;
            _diag2.fallback_data_keys = resp.data ? Object.keys(resp.data).slice(0, 10) : [];
            if (resp.status === 200 && resp.data?.success && resp.data?.data) {
              const mu = resp.data.data;
              return {
                success: true,
                data: {
                  xhs_user_id: String(mu.user_id || ""),
                  nickname: String(mu.nickname || ""),
                  avatar_url: String(mu.image || mu.avatar || ""),
                  red_id: String(mu.red_id || ""),
                },
              };
            }
          } catch (e) {
            _diag2.fallback_error = e.message;
          }
          return {
            success: false,
            message: "无法获取用户信息",
            _diag: _diag2,
            _pageDiag: _pageDiag,
            pageAxios_error: pageAxiosErr,
          };
        }

        if (actionName === "search_notes") {
          const keyword = actionPayload.keyword;
          const limit = actionPayload.limit || 20;
          // 搜索前随机等待 1-3 秒（模拟人类思考时间）
          await new Promise(r => setTimeout(r, 1000 + Math.random() * 2000));

          const searchBody = {
            keyword,
            page: 1,
            page_size: Math.min(limit, 50),
            search_id: genSearchId(),
            sort: "general",
            note_type: 0,
          };

          // 方案 A：优先用页面自带的 axios 实例发请求（自动加完整签名 X-S/X-T/X-S-Common）
          // 页面的请求拦截器最清楚怎么生成所有签名头，比手动调用 _webmsxyw 更可靠
          let resp = null;
          try {
            // 找页面 webpack 模块里的 axios 实例
            const webpackChunks = window.webpackChunkxhs_pc_web || [];
            let pageAxios = null;
            for (const chunk of webpackChunks) {
              if (!chunk || !chunk[1]) continue;
              const modules = chunk[1];
              for (const key of Object.keys(modules)) {
                try {
                  const mod = modules[key];
                  let result = mod({ exports: {} }, {}, {});
                  if (result && result.exports) {
                    const exp = result.exports;
                    if (exp.default && typeof exp.default.post === "function" && typeof exp.default.get === "function") {
                      pageAxios = exp.default;
                      break;
                    }
                    if (typeof exp.post === "function" && typeof exp.get === "function") {
                      pageAxios = exp;
                      break;
                    }
                  }
                } catch (e) {}
              }
              if (pageAxios) break;
            }

            if (pageAxios) {
              const axiosResp = await pageAxios.post("/api/sns/web/v1/search/notes", searchBody, {
                headers: { "Content-Type": "application/json;charset=UTF-8" },
              });
              resp = { status: axiosResp.status || 200, data: axiosResp.data || axiosResp };
              resp._method = "page_axios";
            }
          } catch (e) {
            resp = { status: 0, data: { success: false, msg: "page_axios failed: " + e.message, _method: "page_axios" } };
          }

          // 方案 B：回退到手动签名 fetch
          if (!resp || (resp.status !== 200 && !resp.data?.success)) {
            resp = await xhsFetch("/search/notes", searchBody);
            resp._method = resp._method || "manual_sign";
          }

          if (resp.status !== 200 || !resp.data?.success) {
            return {
              success: false,
              message: `search_notes 失败: status=${resp.status}, method=${resp._method}, body=${JSON.stringify(resp.data).slice(0, 800)}`,
            };
          }
          const items = resp.data?.data?.items || [];
          const notes = items.slice(0, limit).map((it) => {
            const n = it.note || it;
            return {
              note_id: n.id || n.note_id || "",
              title: n.title || "",
              desc: (n.desc || "").slice(0, 200),
              author: n.user?.nickname || "",
              likes: n.liked_count || n.like_count || 0,
              comments: n.comment_count || 0,
              url: `https://www.xiaohongshu.com/explore/${n.id || n.note_id}`,
              cover_img: n.image_list?.[0] || n.cover?.url || "",
            };
          });
          return { success: true, data: notes, _method: resp._method };
        }

        if (actionName === "get_note_detail") {
          const noteId = actionPayload.noteId;
          const resp = await xhsFetch("/feed", {
            source_note_id: noteId,
            image_formats: ["jpg", "webp", "avif"],
          });
          if (resp.status !== 200 || !resp.data?.success) {
            return {
              success: false,
              message: `get_note_detail 失败: status=${resp.status}`,
            };
          }
          const item = resp.data?.data?.items?.[0]?.note;
          if (!item) return { success: false, message: "笔记不存在" };

          // 收集图片 URL 并转 base64
          const imageUrls = [];
          if (item.image_list && item.image_list.length) {
            for (const img of item.image_list) {
              const url = typeof img === "string" ? img : (img.url || img.url_default || "");
              if (url) imageUrls.push(url);
            }
          }
          const imagesBase64 = [];
          for (const url of imageUrls) {
            try {
              const b64 = await urlToBase64(url);
              imagesBase64.push(b64);
            } catch (e) {
              console.warn(`[XHS MCP] image fetch failed: ${url}`);
            }
          }
          return {
            success: true,
            data: {
              note_id: noteId,
              title: item.title || "",
              content: item.desc || "",
              images: imagesBase64,
              tags: (item.tag_list || []).map((t) => t.name || t),
            },
          };
        }

        if (actionName === "ping") {
          return { success: true, data: { ok: true, url: location.href } };
        }

        // 诊断专用：安装 fetch 拦截器，捕获下一次真实搜索请求的完整 headers
        // 用法：调 capture_real_headers → 然后在页面手动搜索 → 再调 capture_real_headers 取结果
        if (actionName === "capture_real_headers") {
          // 已安装过拦截器，返回捕获到的结果
          if (window.__xhs_captured_headers) {
            return { success: true, data: window.__xhs_captured_headers };
          }
          // 首次调用：安装拦截器
          if (!window.__xhs_orig_fetch) {
            window.__xhs_orig_fetch = window.fetch;
            window.__xhs_captured_headers = null;
            window.fetch = async function(input, init) {
              const url = typeof input === "string" ? input : (input?.url || "");
              // 只捕获 search/notes 请求
              if (url.includes("/search/notes")) {
                try {
                  const headers = {};
                  const h = init?.headers || {};
                  // headers 可能是 Headers 对象、对象、或数组
                  if (h instanceof Headers) {
                    h.forEach((v, k) => { headers[k] = v; });
                  } else if (Array.isArray(h)) {
                    for (const [k, v] of h) headers[k] = v;
                  } else {
                    Object.assign(headers, h);
                  }
                  window.__xhs_captured_headers = {
                    url,
                    method: init?.method || "GET",
                    headers,
                    body_preview: (init?.body || "").slice(0, 200),
                    captured_at: new Date().toISOString(),
                  };
                  console.log("[XHS CAPTURE] 捕获到真实搜索请求:", window.__xhs_captured_headers);
                } catch (e) {
                  console.error("[XHS CAPTURE] 捕获失败:", e);
                }
              }
              return window.__xhs_orig_fetch.apply(this, arguments);
            };
            return {
              success: true,
              data: { installed: true, message: "拦截器已安装，请在小红书页面手动搜索一次，然后再次调用 capture_real_headers 取结果" },
            };
          }
          return { success: false, message: "拦截器已安装但还没捕获到请求" };
        }

        return { success: false, message: "unknown action: " + actionName };
      } catch (e) {
        return { success: false, message: e.message || String(e) };
      }
      // ===== MAIN world 代码结束 =====
    },
    args: [action, payload],
  });

  // executeScript 返回数组，取第一个元素
  if (!results || results.length === 0) {
    throw new Error("executeScript 未返回结果（可能页面未加载完或权限不足）");
  }
  const result = results[0].result;
  if (!result) {
    throw new Error("executeScript 返回空结果（可能页面导航中断了执行）");
  }
  console.log(`[XHS MCP] action=${action} result:`, result);
  return result;
}

async function findXhsTab() {
  const tabs = await chrome.tabs.query({ url: "https://www.xiaohongshu.com/*" });
  if (tabs.length === 0) return null;
  // 优先用非活动标签（不打扰用户）
  return tabs[0];
}

function waitTabComplete(tabId, timeoutMs) {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    function check() {
      chrome.tabs.get(tabId, (tab) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        if (tab.status === "complete") {
          resolve(tab);
        } else if (Date.now() - t0 > timeoutMs) {
          reject(new Error("tab load timeout"));
        } else {
          setTimeout(check, 300);
        }
      });
    }
    check();
  });
}

// ============ 业务接口实现 ============

// 获取当前登录用户信息
async function getCurrentUserInfo() {
  console.log("[XHS MCP] === getCurrentUserInfo start ===");
  const { loggedIn, found } = await isLoggedIn();
  console.log("[XHS MCP] isLoggedIn:", loggedIn, "found keys:", Object.keys(found));
  if (!loggedIn) {
    throw new Error("NOT_LOGGED_IN: 浏览器未登录小红书（cookie 里没有 web_session）");
  }

  // 主方案：用 chrome.cookies 拿 cookie 手动塞 header，fetch /user/profile HTML
  // MV3 service worker 的 fetch 默认不带 cookie，必须手动塞
  let htmlError = null;
  try {
    console.log("[XHS MCP] trying HTML fetch...");
    const html = await fetchXhsHtml("/user/profile");
    console.log("[XHS MCP] HTML length:", html.length, "first200:", html.slice(0, 200));
    const info = extractUserInfoFromHtml(html);
    console.log("[XHS MCP] extracted info:", info);
    if (info && info.xhs_user_id && info.nickname) {
      console.log("[XHS MCP] === getCurrentUserInfo success via HTML ===");
      return info;
    }
    htmlError = "HTML parsed but no user info found";
  } catch (e) {
    htmlError = e.message;
    console.log("[XHS MCP] HTML fetch failed:", e.message);
  }

  // 兜底方案：通过 content script
  console.log("[XHS MCP] falling back to content script, htmlError:", htmlError);
  const result = await executeInMainWorld("get_user_info", {});
  if (!result || !result.success) {
    throw new Error(`HTML 方案失败(${htmlError}); content script 也失败(${result?.message || "no response"})`);
  }
  return result.data;
}

// 用 chrome.cookies API 拿 cookie 拼成 Cookie header，再 fetch
async function fetchXhsHtml(path) {
  const cookies = await getCookiesForXHS();
  const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join("; ");
  console.log("[XHS MCP] fetching HTML with", cookies.length, "cookies, cookieStr len:", cookieStr.length);

  const resp = await fetch(XHS_ORIGIN + path, {
    headers: {
      "Cookie": cookieStr,
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "zh-CN,zh;q=0.9",
    },
    redirect: "manual",
  });
  console.log("[XHS MCP] HTML fetch status:", resp.status, "type:", resp.type, "url:", resp.url);
  if (resp.status === 0 || resp.status >= 300 && resp.status < 400) {
    // 0 = opaqueredirect (manual redirect blocked), 3xx = redirect, 通常都是被重定向到登录页
    throw new Error(`fetch 被拦截或重定向（status=${resp.status}），可能 cookie 无效`);
  }
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`);
  }
  return await resp.text();
}

// 从 HTML 中提取 __NEXT_DATA__ 并找出用户信息
function extractUserInfoFromHtml(html) {
  const m = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (!m) return null;
  try {
    const data = JSON.parse(m[1]);
    const findUser = (o, dp) => {
      if (!o || typeof o !== "object" || dp > 6) return null;
      // 优先匹配带 user_id 的对象
      if (o.user_id && o.nickname) return o;
      // 其次匹配 selfUserInfo 风格的字段
      if (o.id && o.nickname && (o.image || o.red_id !== undefined)) {
        return { user_id: o.id, nickname: o.nickname, image: o.image, red_id: o.red_id || "" };
      }
      for (const v of Object.values(o)) {
        const r = findUser(v, dp + 1);
        if (r) return r;
      }
      return null;
    };
    const u = findUser(data.props?.pageProps, 0) || findUser(data, 0);
    if (!u) return null;
    return {
      xhs_user_id: String(u.user_id || u.id || ""),
      nickname: String(u.nickname || ""),
      avatar_url: String(u.image || u.avatar || u.avatar_url || ""),
      red_id: String(u.red_id || ""),
    };
  } catch (e) {
    console.warn("[XHS MCP] __NEXT_DATA__ parse failed:", e.message);
    return null;
  }
}

// 搜索爆款笔记
async function searchNotes(keyword, limit = 20) {
  const { loggedIn } = await isLoggedIn();
  if (!loggedIn) {
    throw new Error("NOT_LOGGED_IN: 浏览器未登录小红书");
  }

  const result = await executeInMainWorld("search_notes", { keyword, limit });
  if (!result || !result.success) {
    throw new Error(result?.message || "搜索笔记失败");
  }
  return result.data;
}

// 获取笔记详情（含图片 base64）
async function getNoteDetail(noteId) {
  const { loggedIn } = await isLoggedIn();
  if (!loggedIn) {
    throw new Error("NOT_LOGGED_IN: 浏览器未登录小红书");
  }

  const result = await executeInMainWorld("get_note_detail", { noteId });
  if (!result || !result.success) {
    throw new Error(result?.message || "获取笔记详情失败");
  }
  return result.data;
}

// 发布笔记（RPA 方案：在用户真实浏览器里操作发布页 DOM）
//
// 与 search/getNoteDetail 不同，发布是纯 DOM 操作，不需要签名函数，
// 所以用 ISOLATED world content script（chrome.scripting.executeScript 默认 world）即可。
//
// 流程（用户确认）：
//   1. 打开 creator.xiaohongshu.com 发布页
//   2. 点左上角"发布笔记"入口 → popover 弹出 → 点"图片上传" → 进入图文编辑器
//   3. 上传图片（DataTransfer 设置 file input）
//   4. 填标题 + 填正文
//   5. 点"发布"按钮（中间底部偏右）→ 等 URL 跳转
async function publishNote(title, content, imagesB64) {
  const { loggedIn } = await isLoggedIn();
  if (!loggedIn) {
    throw new Error("NOT_LOGGED_IN: 浏览器未登录小红书");
  }

  console.log(
    `[XHS MCP] publishNote: title=${JSON.stringify(title)}, images=${imagesB64.length}`
  );

  // 1. 打开 creator 发布页（新 tab，非活动，不打扰用户）
  const PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?from=menu&target=image";
  let tab;
  try {
    tab = await chrome.tabs.create({ url: PUBLISH_URL, active: false });
    await waitTabComplete(tab.id, 20000);
  } catch (e) {
    throw new Error(`打开发布页失败: ${e.message}`);
  }

  // 再次确认登录态（发布页未登录会跳转登录页）
  const tabInfo = await chrome.tabs.get(tab.id);
  if (tabInfo.url && tabInfo.url.includes("login")) {
    throw new Error("发布页跳转到了登录页，请先在小红书登录");
  }

  // 2. 在发布页执行发布逻辑（ISOLATED world，能操作 DOM）
  let result;
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      // 不指定 world，默认 ISOLATED world —— 能操作 DOM，无 webdriver 痕迹
      func: async (pTitle, pContent, pImagesB64) => {
        // ===== 以下代码运行在 creator.xiaohongshu.com 发布页的 ISOLATED world =====

        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

        // 等待元素出现（轮询）
        async function waitFor(selectorFn, timeout = 8000, interval = 300) {
          const t0 = Date.now();
          while (Date.now() - t0 < timeout) {
            try {
              const el = selectorFn();
              if (el) return el;
            } catch (e) {
              // selectorFn 可能抛异常（页面结构变化），继续等
            }
            await sleep(interval);
          }
          return null;
        }

        // 点击元素（模拟真实点击：先 focus 再 click）
        function clickEl(el) {
          if (!el) throw new Error("clickEl: el is null");
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          // 有些 React 组件需要 focus 后才响应 click
          try { el.focus(); } catch (e) {}
          el.click();
        }

        // 找"发布笔记"入口按钮（左上角侧栏入口）
        function findEntryBtn() {
          const sels = [
            'div.btn-wrapper',
            'div.publish-video',
            'div.btn-inner',
          ];
          for (const sel of sels) {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
              const txt = (el.innerText || el.textContent || "").trim();
              if (txt === "发布笔记") return el;
            }
          }
          return null;
        }

        // 找 popover 里的"图片上传"选项
        function findImageUploadItem() {
          // popover 里的选项
          const candidates = document.querySelectorAll(
            'div.d-popover *, [class*="popover"] *, div[class*="publish-video-popover"] *'
          );
          for (const el of candidates) {
            const txt = (el.innerText || el.textContent || "").trim();
            if (txt === "图片上传" || txt === "上传图文") return el;
          }
          // 兜底：全页面找文案为"图片上传"的可点击元素
          const all = document.querySelectorAll("div, a, button, span");
          for (const el of all) {
            const txt = (el.innerText || el.textContent || "").trim();
            if (txt === "图片上传" || txt === "上传图文") {
              // 排除入口按钮本身
              const cls = el.className || "";
              if (/publish-video|btn-wrapper/.test(cls)) continue;
              return el;
            }
          }
          return null;
        }

        // base64 转 File 对象
        function base64ToFile(b64, filename) {
          // 去掉 data:image/...;base64, 前缀
          let pure = b64;
          let mime = "image/png";
          if (b64.startsWith("data:")) {
            const m = b64.match(/^data:([^;]+);base64,(.*)/);
            if (m) {
              mime = m[1];
              pure = m[2];
            }
          }
          const byteChars = atob(pure);
          const byteArr = new Uint8Array(byteChars.length);
          for (let i = 0; i < byteChars.length; i++) {
            byteArr[i] = byteChars.charCodeAt(i);
          }
          const ext = mime === "image/jpeg" ? ".jpg" : ".png";
          return new File([byteArr], filename + ext, { type: mime });
        }

        // 设置 file input 的文件（用 DataTransfer）
        function setInputFiles(input, files) {
          const dt = new DataTransfer();
          for (const f of files) dt.items.add(f);
          input.files = dt.files;
          // 触发 change 事件（React 监听 change）
          input.dispatchEvent(new Event("change", { bubbles: true }));
          // 有些框架还监听 input 事件
          input.dispatchEvent(new Event("input", { bubbles: true }));
        }

        // 扫描"发布"提交按钮（用户确认在中间底部偏右）
        function findPublishSubmitBtn() {
          const out = [];
          const sels = "button, div[role='button'], div[class*='btn'], div[class*='submit'], div[class*='publish'], a[class*='btn']";
          document.querySelectorAll(sels).forEach((el) => {
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) return;
            const style = window.getComputedStyle(el);
            if (style.display === "none" || style.visibility === "hidden") return;
            if (parseFloat(style.opacity) < 0.1) return;
            const txt = (el.innerText || el.textContent || "").trim();
            if (!txt) return;
            if (!txt.startsWith("发布")) return;
            // 排除菜单选项（发布视频/发布图文/发布播客/发布长文）
            if (txt.includes("发布视频") || txt.includes("发布图文") || txt.includes("发布播客") || txt.includes("发布长文")) return;
            const cls = typeof el.className === "string" ? el.className : "";
            // 排除侧栏入口（左上角）
            const isSidebar = /publish-video|btn-wrapper|btn-inner|btn-text/.test(cls) || r.x < 200;
            let disabled = el.disabled === true;
            if (!disabled && el.getAttribute("aria-disabled") === "true") disabled = true;
            if (!disabled && /disabled/i.test(cls)) disabled = true;
            let score = 0;
            if (txt === "发布笔记") score = 100;
            else if (txt === "发布") score = 90;
            else score = 70;
            score -= Math.min(txt.length, 30);
            if (!isSidebar) score += 200;
            out.push({ el, tag: el.tagName, text: txt, class: cls,
              x: Math.round(r.x), y: Math.round(r.y), disabled, isSidebar, score });
          });
          // 选得分最高且非 disabled 非侧栏的
          out.sort((a, b) => b.score - a.score);
          for (const c of out) {
            if (!c.disabled && !c.isSidebar) return c.el;
          }
          // 兜底：所有候选都返回（诊断用）
          return null;
        }

        try {
          // ===== 步骤 1：点"发布笔记"入口 =====
          await sleep(1500); // 等页面渲染
          let entryBtn = await waitFor(findEntryBtn, 6000);
          if (!entryBtn) {
            // 可能已经在编辑器里（target=image 直接落地）
            const hasFileInput = document.querySelector(
              'input[type="file"][accept*="image" i], input[type="file"][accept*=".png" i]'
            );
            if (!hasFileInput) {
              return { success: false, message: "未找到「发布笔记」入口按钮，且不在图文编辑器内" };
            }
            // 已在编辑器，跳过 popover 流程
          } else {
            clickEl(entryBtn);
            console.log("[XHS PUBLISH] clicked 发布笔记 entry");
            await sleep(1000);

            // ===== 步骤 2：popover 里点"图片上传" =====
            let imageItem = await waitFor(findImageUploadItem, 5000);
            if (!imageItem) {
              return { success: false, message: "popover 菜单中未找到「图片上传」选项" };
            }
            clickEl(imageItem);
            console.log("[XHS PUBLISH] clicked 图片上传 in popover");
            await sleep(2500); // 等编辑器加载
          }

          // ===== 步骤 3：上传图片 =====
          if (pImagesB64 && pImagesB64.length > 0) {
            // 找图片上传 input（accept 含 image，排除视频 input）
            const fileInput = await waitFor(() => {
              const inputs = document.querySelectorAll('input[type="file"]');
              for (const inp of inputs) {
                const accept = (inp.getAttribute("accept") || "").toLowerCase();
                if (accept.includes("image") || accept.includes(".png") || accept.includes(".jpg")) {
                  return inp;
                }
              }
              // 兜底：排除视频 input
              for (const inp of inputs) {
                const accept = (inp.getAttribute("accept") || "").toLowerCase();
                if (!accept.includes(".mp4") && !accept.includes("video")) return inp;
              }
              return null;
            }, 8000);

            if (!fileInput) {
              return { success: false, message: "未找到图片上传 input（图文编辑器可能未加载）" };
            }

            // base64 转 File 并设置
            const files = [];
            for (let i = 0; i < Math.min(pImagesB64.length, 9); i++) {
              try {
                const f = base64ToFile(pImagesB64[i], "xhs_img_" + i);
                files.push(f);
              } catch (e) {
                console.warn("[XHS PUBLISH] base64ToFile failed:", e.message);
              }
            }
            if (files.length === 0) {
              return { success: false, message: "图片 base64 转换失败" };
            }
            setInputFiles(fileInput, files);
            console.log(`[XHS PUBLISH] uploaded ${files.length} images`);
            await sleep(3000); // 等图片上传完成（会出现预览）
          }

          // ===== 步骤 4：填标题 =====
          const titleStr = (pTitle || "").trim().slice(0, 20);
          if (titleStr) {
            const titleInput = await waitFor(() => {
              const sels = [
                'input[placeholder*="标题"]',
                'input[placeholder*="title"]',
                'div[contenteditable][class*="title"]',
              ];
              for (const s of sels) {
                const el = document.querySelector(s);
                if (el) return el;
              }
              return null;
            }, 5000);

            if (titleInput) {
              titleInput.click();
              titleInput.focus();
              // 用原生 setter 设置 value（React 监听原生 setter）
              const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, "value"
              )?.set;
              if (nativeInputValueSetter && titleInput.tagName === "INPUT") {
                nativeInputValueSetter.call(titleInput, titleStr);
              } else {
                titleInput.value = titleStr;
              }
              titleInput.dispatchEvent(new Event("input", { bubbles: true }));
              titleInput.dispatchEvent(new Event("change", { bubbles: true }));
              console.log(`[XHS PUBLISH] title filled: ${titleStr}`);
            } else {
              console.warn("[XHS PUBLISH] title input not found");
            }
          }

          // ===== 步骤 5：填正文 =====
          const contentStr = (pContent || "").trim();
          if (contentStr) {
            const contentDiv = await waitFor(() => {
              const sels = [
                'div[contenteditable="true"].ProseMirror',
                'div[contenteditable="true"][class*="tiptap"]',
                'div[role="textbox"][contenteditable="true"]',
                'div[contenteditable="true"][class*="content"]',
                'div[contenteditable="true"][class*="desc"]',
                '#post-textarea',
              ];
              for (const s of sels) {
                const el = document.querySelector(s);
                if (el) return el;
              }
              return null;
            }, 5000);

            if (contentDiv) {
              contentDiv.click();
              contentDiv.focus();
              // ProseMirror/tiptap 用 execCommand 触发正确的 input 事件链
              document.execCommand("selectAll", false, null);
              document.execCommand("insertText", false, contentStr);
              console.log(`[XHS PUBLISH] content filled (${contentStr.length} chars)`);
            } else {
              console.warn("[XHS PUBLISH] content div not found");
            }
          }

          // ===== 步骤 6：点"发布"按钮 =====
          await sleep(1500); // 等按钮激活
          // 滚到底部确保按钮渲染
          window.scrollTo(0, document.body.scrollHeight);
          await sleep(800);
          window.scrollTo(0, document.body.scrollHeight);
          await sleep(500);

          let publishBtn = findPublishSubmitBtn();
          if (!publishBtn) {
            // 再滚到顶扫一次
            window.scrollTo(0, 0);
            await sleep(500);
            publishBtn = findPublishSubmitBtn();
          }

          if (!publishBtn) {
            return { success: false, message: "未找到发布按钮（编辑器内中间底部偏右的「发布」按钮）" };
          }

          clickEl(publishBtn);
          console.log("[XHS PUBLISH] clicked 发布 button");
          await sleep(3000); // 等发布处理

          // ===== 步骤 7：检查发布结果 =====
          const finalUrl = location.href;
          // 发布成功后 URL 通常离开 /publish/publish
          if (!finalUrl.includes("publish/publish")) {
            return { success: true, message: `发布成功（跳转至 ${finalUrl}）`, url: finalUrl };
          }
          // 检查页面是否有"发布成功"提示
          const bodyText = document.body?.innerText || "";
          const successHints = ["发布成功", "已发布", "发布完成"];
          for (const h of successHints) {
            if (bodyText.includes(h)) {
              return { success: true, message: `发布成功（${h}）`, url: finalUrl };
            }
          }
          // 检查错误提示
          const errHints = ["请上传图片", "请至少上传", "请填写标题", "请输入正文",
            "正文不能为空", "发布失败", "操作频繁", "含有违规"];
          for (const h of errHints) {
            if (bodyText.includes(h)) {
              return { success: false, message: `发布失败：${h}`, url: finalUrl };
            }
          }
          return { success: false, message: `发布后页面未跳转，可能发布失败（url=${finalUrl}）`, url: finalUrl };

        } catch (e) {
          return { success: false, message: `发布流程异常: ${e.message || String(e)}` };
        }
        // ===== ISOLATED world 代码结束 =====
      },
      args: [title, content, imagesB64],
    });

    if (!results || results.length === 0) {
      throw new Error("executeScript 未返回结果");
    }
    result = results[0].result;
    if (!result) {
      throw new Error("executeScript 返回空结果");
    }
  } catch (e) {
    // executeScript 本身失败（权限/注入错误）
    throw new Error(`发布脚本执行失败: ${e.message}`);
  }

  // 关闭发布 tab（无论成功失败，保持浏览器干净）
  // 成功时不关，让用户能看到发布结果页
  if (!result.success) {
    try { await chrome.tabs.remove(tab.id); } catch (e) {}
  }

  console.log("[XHS MCP] publishNote result:", result);
  return result;
}

// ============ 消息分发（给 popup / 后端注入脚本 用） ============

async function handleRequest(request) {
  switch (request.action) {
    case "health": {
      const { loggedIn, found } = await isLoggedIn();
      return {
        success: true,
        data: {
          online: true,
          logged_in: loggedIn,
          cookies_count: Object.keys(found).length,
          version: "0.1.0",
        },
      };
    }
    case "get_user_info": {
      // 从 cookie 读用户信息
      try {
        const { cookies, found } = await isLoggedIn();
        const cookieMap = {};
        for (const c of cookies) cookieMap[c.name] = c.value;
        const cookieNames = cookies.map(c => c.name);

        // 优先读 xhsuserid
        const userId = found["xhsuserid"] || found["customer-sso-sid"] || "";

        // 从 id_token (JWT) 解析用户信息
        let jwtPayload = null;
        const idToken = cookieMap["id_token"] || "";
        if (idToken) {
          try {
            const parts = idToken.split(".");
            if (parts.length >= 2) {
              // JWT payload 是 base64url 编码，用 Uint8Array 方式解码（service worker 兼容）
              const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
              const padded = b64 + "=".repeat((4 - b64.length % 4) % 4);
              const binary = atob(padded);
              const bytes = new Uint8Array(binary.length);
              for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
              const jsonStr = new TextDecoder("utf-8").decode(bytes);
              jwtPayload = JSON.parse(jsonStr);
            }
          } catch (e) {
            jwtPayload = { parse_error: e.message };
          }
        }

        // 综合：cookie userId + JWT 信息
        const finalUserId = userId
          || (jwtPayload && (jwtPayload.user_id || jwtPayload.sub || jwtPayload.uid || ""))
          || "";

        if (finalUserId || jwtPayload) {
          return {
            success: true,
            data: {
              xhs_user_id: String(finalUserId || ""),
              nickname: (jwtPayload && (jwtPayload.nickname || jwtPayload.name || "")) || "小红书用户",
              avatar_url: (jwtPayload && (jwtPayload.avatar || jwtPayload.image || "")) || "",
              red_id: (jwtPayload && (jwtPayload.red_id || jwtPayload.redId || "")) || "",
              _cookie_names: cookieNames,
              _jwt_payload: jwtPayload,
              _method: "cookie+jwt",
            },
          };
        }

        // cookie 方案失败，回退到 executeInMainWorld 读 DOM
        const domResult = await executeInMainWorld("get_user_info", {});
        if (domResult && domResult.success && domResult.data) {
          return {
            success: true,
            data: {
              ...domResult.data,
              _cookie_names: cookieNames,
              _method: "dom_fallback",
            },
          };
        }
        return {
          success: false,
          message: "cookie 无用户 ID，DOM 读取也失败",
          _cookie_names: cookieNames,
          _id_token_preview: (idToken || "").slice(0, 50),
          _dom_result: domResult,
        };
      } catch (e) {
        return { success: false, message: "读 cookie 失败: " + e.message };
      }
    }
    case "search_notes": {
      const data = await searchNotes(request.payload.keyword, request.payload.limit || 20);
      return { success: true, data };
    }
    case "get_note_detail": {
      const data = await getNoteDetail(request.payload.noteId);
      return { success: true, data };
    }
    case "publish_note": {
      const result = await publishNote(
        request.payload.title || "",
        request.payload.content || "",
        request.payload.images_b64 || []
      );
      // bridge.js 期望 {success: true, data: ...}，
      // publishNote 返回 {success, message, url?}，包进 data
      if (result.success) {
        return { success: true, data: result };
      } else {
        return { success: false, message: result.message || "发布失败" };
      }
    }
    default:
      return { success: false, message: "unknown action: " + request.action };
  }
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  handleRequest(request).then(sendResponse, (e) => {
    sendResponse({ success: false, message: e.message || String(e) });
  });
  return true; // 保持 sendResponse 异步
});

// ============ 外部消息（来自桥接页面 externally_connectable） ============
chrome.runtime.onMessageExternal.addListener((request, sender, sendResponse) => {
  // 校验来源（白名单）
  const allowedOrigins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
  ];
  if (!allowedOrigins.includes(sender.origin)) {
    sendResponse({ success: false, message: "origin not allowed: " + sender.origin });
    return false;
  }
  handleRequest(request).then(sendResponse, (e) => {
    sendResponse({ success: false, message: e.message || String(e) });
  });
  return true;
});

console.log("[XHS MCP] background service worker started");
