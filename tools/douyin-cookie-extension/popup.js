"use strict";

const REQUIRED_KEYS = ["ttwid", "odin_tt", "passport_csrf_token"];
const RECOMMENDED_KEYS = [
  "msToken",
  "ttwid",
  "odin_tt",
  "passport_csrf_token",
  "sid_guard",
  "sessionid",
  "sid_tt",
  "s_v_web_id",
  "__ac_nonce",
  "__ac_signature",
  "UIFID",
  "UIFID_TEMP",
  "d_ticket",
  "x-web-secsdk-uid",
  "__security_server_data_status"
];
const RECOMMENDED_PREFIXES = [
  "__security_mc_",
  "bd_ticket_guard_",
  "_bd_ticket_crypt_"
];

let allCookies = [];
let currentMode = "recommended";
let currentCookieMap = {};

const statusText = document.getElementById("statusText");
const missingText = document.getElementById("missingText");
const headerOutput = document.getElementById("headerOutput");
const jsonOutput = document.getElementById("jsonOutput");

function scoreCookie(cookie) {
  const domain = String(cookie.domain || "");
  const path = String(cookie.path || "");
  const expiration = Number(cookie.expirationDate || 0);
  let score = 0;
  if (domain === "www.douyin.com") {
    score += 80;
  } else if (domain === ".douyin.com" || domain === "douyin.com") {
    score += 60;
  } else if (domain.endsWith(".douyin.com")) {
    score += 40;
  }
  score += Math.min(path.length, 30);
  if (cookie.secure) {
    score += 5;
  }
  if (expiration > 0) {
    score += Math.min(expiration / 100000000, 10);
  }
  return score;
}

function dedupeByName(cookies) {
  const picked = new Map();
  for (const cookie of cookies) {
    const name = String(cookie.name || "").trim();
    if (!name) {
      continue;
    }
    const previous = picked.get(name);
    if (!previous || scoreCookie(cookie) >= scoreCookie(previous)) {
      picked.set(name, cookie);
    }
  }
  return Array.from(picked.values());
}

function isRecommendedName(name) {
  return (
    RECOMMENDED_KEYS.includes(name) ||
    RECOMMENDED_PREFIXES.some((prefix) => name.startsWith(prefix))
  );
}

function sortNames(names) {
  const priority = new Map(RECOMMENDED_KEYS.map((name, index) => [name, index]));
  return names.sort((a, b) => {
    const ap = priority.has(a) ? priority.get(a) : 1000;
    const bp = priority.has(b) ? priority.get(b) : 1000;
    if (ap !== bp) {
      return ap - bp;
    }
    return a.localeCompare(b);
  });
}

function buildCookieMap(mode) {
  const deduped = dedupeByName(allCookies);
  const map = {};
  for (const cookie of deduped) {
    const name = String(cookie.name || "").trim();
    if (!name) {
      continue;
    }
    if (mode === "recommended" && !isRecommendedName(name)) {
      continue;
    }
    map[name] = String(cookie.value || "");
  }
  return map;
}

function formatHeader(cookieMap) {
  return sortNames(Object.keys(cookieMap))
    .map((name) => `${name}=${cookieMap[name]}`)
    .join("; ");
}

function formatJson(cookieMap) {
  const ordered = {};
  for (const name of sortNames(Object.keys(cookieMap))) {
    ordered[name] = cookieMap[name];
  }
  return JSON.stringify(ordered, null, 2);
}

function render() {
  currentCookieMap = buildCookieMap(currentMode);
  const keys = Object.keys(currentCookieMap);
  const missing = REQUIRED_KEYS.filter((name) => !currentCookieMap[name]);
  const modeLabel = currentMode === "recommended" ? "recommended" : "all";

  statusText.textContent = `${keys.length} cookie(s) loaded from douyin.com (${modeLabel}).`;
  missingText.textContent = missing.length
    ? `Thieu cookie quan trong: ${missing.join(", ")}`
    : "";
  headerOutput.value = formatHeader(currentCookieMap);
  jsonOutput.value = formatJson(currentCookieMap);
}

async function loadCookies() {
  statusText.textContent = "Dang doc cookie douyin.com...";
  missingText.textContent = "";
  headerOutput.value = "";
  jsonOutput.value = "";

  try {
    allCookies = await chrome.cookies.getAll({ domain: "douyin.com" });
    render();
  } catch (error) {
    statusText.textContent = "Khong doc duoc cookie. Hay kiem tra quyen extension.";
    missingText.textContent = error && error.message ? error.message : String(error);
  }
}

async function copyText(text, label) {
  if (!text) {
    statusText.textContent = `Khong co ${label} de copy.`;
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
  } catch (_error) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  statusText.textContent = `Da copy ${label}.`;
}

document.getElementById("refreshBtn").addEventListener("click", loadCookies);
document.getElementById("recommendedBtn").addEventListener("click", () => {
  currentMode = "recommended";
  render();
});
document.getElementById("allBtn").addEventListener("click", () => {
  currentMode = "all";
  render();
});
document.getElementById("copyHeaderBtn").addEventListener("click", () => {
  copyText(headerOutput.value, "cookie header");
});
document.getElementById("copyJsonBtn").addEventListener("click", () => {
  copyText(jsonOutput.value, "JSON");
});

loadCookies();
