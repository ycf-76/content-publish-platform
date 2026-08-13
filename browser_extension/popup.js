// popup.js - 插件弹窗逻辑

const $ = (id) => document.getElementById(id);

async function checkStatus() {
  $("plugin-status").className = "badge unknown";
  $("plugin-status").textContent = "检测中...";
  $("xhs-login").className = "badge unknown";
  $("xhs-login").textContent = "检测中...";
  $("error-msg").textContent = "";

  try {
    const resp = await chrome.runtime.sendMessage({ action: "health" });
    if (!resp || !resp.success) {
      throw new Error(resp?.message || "插件未响应");
    }
    const data = resp.data;
    $("plugin-status").className = "badge online";
    $("plugin-status").textContent = "运行中 v" + data.version;
    $("cookies-count").textContent = data.cookies_count + " 个关键 cookie";

    if (data.logged_in) {
      $("xhs-login").className = "badge online";
      $("xhs-login").textContent = "已登录";
    } else {
      $("xhs-login").className = "badge offline";
      $("xhs-login").textContent = "未登录";
    }
  } catch (e) {
    $("plugin-status").className = "badge offline";
    $("plugin-status").textContent = "异常";
    $("error-msg").textContent = e.message || String(e);
  }
}

$("btn-refresh").addEventListener("click", checkStatus);

$("btn-open-bridge").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("bridge.html") });
});

$("btn-open-xhs").addEventListener("click", () => {
  chrome.tabs.create({ url: "https://www.xiaohongshu.com/explore" });
});

checkStatus();
