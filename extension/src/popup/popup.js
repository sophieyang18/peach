const usernameInput = document.getElementById("usernameInput")
const apiInput = document.getElementById("apiInput")
const statusText = document.getElementById("statusText")
const saveConfigBtn = document.getElementById("saveConfigBtn")
const scanBtn = document.getElementById("scanBtn")
const resetBtn = document.getElementById("resetBtn")
const fillBtn = document.getElementById("fillBtn")
const generateAiBtn = document.getElementById("generateAiBtn")
const confirmBtn = document.getElementById("confirmBtn")
const summary = document.getElementById("summary")
const mappingList = document.getElementById("mappingList")
const STATE_KEY = "peachCopilotLastState"

let lastPage = null
let lastPreview = null

init()

async function init() {
  const config = await storageGet(["peachUsername", "peachApiBase"])
  usernameInput.value = config.peachUsername || ""
  apiInput.value = config.peachApiBase || "http://127.0.0.1:8000"
  setStatus(config.peachUsername ? "已连接 Peach 账号" : "未登录")
  await restoreLastState()
}

saveConfigBtn.addEventListener("click", async () => {
  await chrome.storage.local.set({
    peachUsername: usernameInput.value.trim(),
    peachApiBase: trimBase(apiInput.value),
  })
  setStatus(usernameInput.value.trim() ? "连接已保存" : "请填写用户名")
})

scanBtn.addEventListener("click", async () => {
  const config = await requiredConfig()
  if (!config) return
  setStatus("正在扫描当前页面")
  await track("copilot_scan_start", {})
  try {
    lastPage = await sendToActiveTab({ type: "PEACH_SCAN_FIELDS" })
    const preview = await api(config, "/api/copilot/map", {
      method: "POST",
      body: JSON.stringify({
        url: lastPage.url,
        domain: lastPage.domain,
        fields: lastPage.fields,
        repeaters: lastPage.repeaters || [],
        use_agent: true,
      }),
    })
    lastPreview = preview
    initializeApprovals(lastPreview)
    renderPreview(preview)
    updateFillButton()
    updateGenerateButton()
    confirmBtn.disabled = false
    await saveLastState()
    const aiCount = aiDraftItems(preview).length
    const agentCopy = agentStatusCopy(preview)
    if (aiCount) {
      setStatus(`检测到 ${preview.field_count} 个字段，${agentCopy}，桃子正在生成 ${aiCount} 个核心草稿`)
      const generatedCount = await generateAiDrafts(config, preview, { onlyEmpty: true })
      renderPreview(preview)
      updateFillButton()
      updateGenerateButton()
      await saveLastState()
      setStatus(`检测到 ${preview.field_count} 个字段，${agentCopy}，已生成 ${generatedCount} 个 Agent 草稿`)
    } else {
      setStatus(`检测到 ${preview.field_count} 个可处理字段，${agentCopy}`)
    }
    await track("copilot_scan_success", { field_count: preview.field_count, skipped_count: preview.skipped_count })
  } catch (error) {
    setStatus(`扫描失败：${error.message}`)
    await track("copilot_scan_fail", { reason: error.message })
  }
})

generateAiBtn.addEventListener("click", async () => {
  const config = await requiredConfig()
  if (!config || !lastPreview) return
  generateAiBtn.disabled = true
  setStatus("桃子正在重新生成核心字段草稿")
  const generatedCount = await generateAiDrafts(config, lastPreview, { onlyEmpty: false })
  renderPreview(lastPreview)
  updateFillButton()
  updateGenerateButton()
  await saveLastState()
  setStatus(`已重新生成 ${generatedCount} 个 Agent 草稿`)
})

fillBtn.addEventListener("click", async () => {
  if (!lastPreview) return
  const fillable = getApprovedFillable()
  if (!fillable.length) {
    setStatus("没有已确认可填写字段，请先勾选需要确认的字段。")
    return
  }
  setStatus("正在填写页面")
  await track("copilot_fill_start", {})
  const response = await sendToActiveTab({
    type: "PEACH_AUTOFILL",
    mappings: fillable,
    repeatActions: lastPreview.repeat_actions || [],
  })
  const successCount = (response.results || []).filter((item) => item.status === "success").length
  const failCount = (response.results || []).filter((item) => item.status === "failed").length
  setStatus(`已填写 ${successCount} 项${failCount ? `，失败 ${failCount} 项` : ""}`)
  await track("copilot_fill_complete", { success_count: successCount, fail_count: failCount })
})

resetBtn.addEventListener("click", async () => {
  const mappings = lastPreview?.mappings || []
  let resetCount = 0
  if (mappings.length) {
    try {
      const response = await sendToActiveTab({
        type: "PEACH_RESET_AUTOFILL",
        mappings,
      })
      resetCount = (response.results || []).filter((item) => item.status === "success").length
    } catch (_error) {
      resetCount = 0
    }
  }
  await clearCurrentState()
  await track("copilot_reset", { reset_count: resetCount })
  setStatus(resetCount ? `已重置扫描结果，并清空 ${resetCount} 个页面字段` : "已重置当前扫描结果")
})

confirmBtn.addEventListener("click", async () => {
  const config = await requiredConfig()
  if (!config) return
  const inferred = inferApplication(lastPreview, lastPage)
  setStatus("正在写回 Peach 投递记录")
  await api(config, "/api/copilot/applications/confirm", {
    method: "POST",
    body: JSON.stringify(inferred),
  })
  setStatus("已写回投递记录，请在 Peach 投递页查看")
})

function renderPreview(preview) {
  summary.innerHTML = `
    <span><b>${preview.field_count}</b>字段</span>
    <span><b>${preview.summary.direct_fill}</b>可填</span>
    <span><b>${preview.summary.ai_assisted}</b>AI</span>
    <span><b>${preview.summary.needs_confirmation}</b>确认</span>
  `
  mappingList.innerHTML = ""
  for (const item of preview.mappings) {
    const card = document.createElement("article")
    card.className = "field-card"
    card.innerHTML = `
      <strong>${escapeHtml(item.label || item.field_id || "未命名字段")}</strong>
      <span class="field-status ${item.status}">${statusLabel(item.status)}</span>
      <span class="field-meta">${escapeHtml(item.candidate_label || item.candidate_path || item.reason || "")}</span>
    `
    if (item.status === "ai_generated") {
      const textarea = document.createElement("textarea")
      textarea.placeholder = "点击生成开放题草稿，生成后可编辑"
      textarea.value = item.value || ""
      const button = document.createElement("button")
      button.type = "button"
      button.textContent = item.value ? "重新生成" : "生成草稿"
      button.addEventListener("click", async () => {
        const config = await requiredConfig()
        if (!config) return
        button.disabled = true
        button.textContent = "生成中"
        try {
          const answer = await api(config, "/api/copilot/open-answer", {
            method: "POST",
            body: JSON.stringify({
              question: item.label,
              jd: collectJdText(preview),
              company: inferValue(preview, "target_preferences.company"),
              role: inferValue(preview, "target_preferences.role"),
              candidate_path: item.candidate_path || item.draft_source_path || "",
              repeat_section: item.repeat_section || "",
              repeat_index: Number.isInteger(item.repeat_index) ? item.repeat_index : null,
              field_key: item.field_key || "",
            }),
          })
          item.value = answer.answer
          item.approved = true
          textarea.value = answer.answer
          updateFillButton()
          updateGenerateButton()
          await saveLastState()
          await track("copilot_ai_answer_accept", { field_id: item.field_id })
        } catch (error) {
          setStatus(`开放题生成失败：${error.message}`)
        } finally {
          button.disabled = false
          button.textContent = "重新生成"
        }
      })
      textarea.addEventListener("input", () => {
        item.value = textarea.value
        updateFillButton()
        updateGenerateButton()
        saveLastState()
        track("copilot_ai_answer_edit", { field_id: item.field_id })
      })
      card.appendChild(textarea)
      card.appendChild(button)
    } else if (item.value) {
      const input = document.createElement("input")
      input.value = item.value
      input.addEventListener("input", () => {
        item.value = input.value
        updateFillButton()
        saveLastState()
      })
      card.appendChild(input)
      if (item.status === "needs_confirmation") {
        const approval = document.createElement("label")
        approval.className = "approval-row"
        const checkbox = document.createElement("input")
        checkbox.type = "checkbox"
        checkbox.checked = Boolean(item.approved)
        const copy = document.createElement("span")
        copy.textContent = "确认填写这一项"
        checkbox.addEventListener("change", () => {
          item.approved = checkbox.checked
          updateFillButton()
          saveLastState()
          track("copilot_mapping_approve", { field_id: item.field_id, approved: checkbox.checked })
        })
        approval.appendChild(checkbox)
        approval.appendChild(copy)
        card.appendChild(approval)
      }
    }
    mappingList.appendChild(card)
  }
}

function renderEmptyPreview() {
  summary.innerHTML = `
    <span><b>0</b>字段</span>
    <span><b>0</b>可填</span>
    <span><b>0</b>AI</span>
    <span><b>0</b>确认</span>
  `
  mappingList.innerHTML = ""
}

function initializeApprovals(preview) {
  for (const item of preview?.mappings || []) {
    item.approved = ["autofilled", "ai_generated"].includes(item.status)
  }
}

async function generateAiDrafts(config, preview, { onlyEmpty }) {
  let generatedCount = 0
  for (const item of aiDraftItems(preview)) {
    if (onlyEmpty && item.value) continue
    try {
      const answer = await api(config, "/api/copilot/open-answer", {
        method: "POST",
        body: JSON.stringify({
          question: item.label,
          jd: collectJdText(preview),
          company: inferValue(preview, "target_preferences.company"),
          role: inferValue(preview, "target_preferences.role"),
          candidate_path: item.candidate_path || item.draft_source_path || "",
          repeat_section: item.repeat_section || "",
          repeat_index: Number.isInteger(item.repeat_index) ? item.repeat_index : null,
          field_key: item.field_key || "",
        }),
      })
      item.value = answer.answer
      item.approved = true
      generatedCount += 1
      await track("copilot_ai_answer_accept", { field_id: item.field_id, source: "auto_scan" })
    } catch (error) {
      setStatus(`核心草稿生成失败：${error.message}`)
    }
  }
  return generatedCount
}

function aiDraftItems(preview) {
  return (preview?.mappings || []).filter((item) => item.status === "ai_generated")
}

function getApprovedFillable() {
  return (lastPreview?.mappings || []).filter(
    (item) =>
      item.value &&
      (item.selector || item.resolve) &&
      (["autofilled", "ai_generated"].includes(item.status) || (item.status === "needs_confirmation" && item.approved)),
  )
}

function updateFillButton() {
  fillBtn.disabled = getApprovedFillable().length <= 0
  updateResetButton()
}

function updateGenerateButton() {
  generateAiBtn.disabled = aiDraftItems(lastPreview).length <= 0
  updateResetButton()
}

function updateResetButton() {
  resetBtn.disabled = !lastPreview
}

function inferApplication(preview, page) {
  return {
    company: inferValue(preview, "target_preferences.company") || "",
    role: inferValue(preview, "target_preferences.role") || "",
    jd_text: collectJdText(preview),
    source_url: page?.url || "",
    notes: "通过桃子 Application Copilot 辅助填写后由用户手动确认已投递。",
  }
}

function inferValue(preview, path) {
  return preview?.mappings?.find((item) => item.candidate_path === path && item.value)?.value || ""
}

function collectJdText(preview) {
  return preview?.mappings?.filter((item) => item.label && /岗位|职位|JD|描述/.test(item.label)).map((item) => item.value || item.label).join("\n") || ""
}

async function api(config, path, options) {
  const response = await fetch(`${config.apiBase}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Peach-User": config.username,
      ...(options?.headers || {}),
    },
  })
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}

async function track(eventName, properties) {
  const config = await storageGet(["peachUsername", "peachApiBase"])
  if (!config.peachUsername) return
  fetch(`${trimBase(config.peachApiBase || "http://127.0.0.1:8000")}/api/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Peach-User": config.peachUsername },
    body: JSON.stringify({
      event_name: eventName,
      page: "extension",
      module: "copilot",
      source: "extension",
      properties,
    }),
  }).catch(() => undefined)
}

async function requiredConfig() {
  const config = {
    username: usernameInput.value.trim(),
    apiBase: trimBase(apiInput.value),
  }
  if (!config.username) {
    setStatus("请先填写 Peach 用户名")
    return null
  }
  await chrome.storage.local.set({ peachUsername: config.username, peachApiBase: config.apiBase })
  return config
}

async function sendToActiveTab(message) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (!tab?.id) throw new Error("没有可用页面")
  return chrome.tabs.sendMessage(tab.id, message)
}

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve))
}

async function restoreLastState() {
  const saved = await storageGet([STATE_KEY])
  const state = saved[STATE_KEY]
  if (!state?.preview || !state?.page) return
  const current = await activeTabInfo()
  if (current.url && !isSamePageContext(current.url, state.page.url)) {
    setStatus("已连接 Peach 账号，上次扫描来自其他页面")
    return
  }
  lastPage = state.page
  lastPreview = state.preview
  renderPreview(lastPreview)
  updateFillButton()
  updateGenerateButton()
  updateResetButton()
  confirmBtn.disabled = false
  setStatus(`已恢复上次扫描：${lastPreview.field_count || 0} 个字段`)
}

async function saveLastState() {
  if (!lastPage || !lastPreview) return
  await chrome.storage.local.set({
    [STATE_KEY]: {
      page: lastPage,
      preview: lastPreview,
      savedAt: new Date().toISOString(),
    },
  })
}

async function clearCurrentState() {
  lastPage = null
  lastPreview = null
  renderEmptyPreview()
  updateFillButton()
  updateGenerateButton()
  confirmBtn.disabled = true
  await chrome.storage.local.remove(STATE_KEY)
}

async function activeTabInfo() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  return { url: tab?.url || "" }
}

function isSamePageContext(currentUrl, savedUrl) {
  try {
    const current = new URL(currentUrl)
    const saved = new URL(savedUrl)
    return current.origin === saved.origin && current.pathname === saved.pathname
  } catch (_error) {
    return currentUrl === savedUrl
  }
}

function setStatus(text) {
  statusText.textContent = text
}

function trimBase(value) {
  return String(value || "http://127.0.0.1:8000").replace(/\/+$/, "")
}

function statusLabel(status) {
  return {
    autofilled: "可直接填写",
    ai_generated: "AI 辅助",
    needs_confirmation: "需要确认",
    unsupported: "暂不支持",
  }[status] || status
}

function agentStatusCopy(preview) {
  return {
    decided: `Agent 已决策 ${preview.agent_decided_count || preview.agent_refined_count || 0} 项`,
    refined: `Agent 已复核 ${preview.agent_refined_count || 0} 项`,
    no_change: "Agent 已复核",
    not_needed: "无需 Agent 复核",
    not_configured: "LLM 未配置，使用规则预览",
    no_profile_values: "档案信息不足，使用规则预览",
    failed: "Agent 复核失败，使用规则预览",
  }[preview?.agent_status] || "已完成预览"
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}
