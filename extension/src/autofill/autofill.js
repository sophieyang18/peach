(function () {
  async function fillPeachFields(mappings, repeatActions) {
    const results = []
    await applyRepeatActions(repeatActions, results)
    const resolvedMappings = resolveRepeatMappings(mappings || [])
    for (const mapping of mappings || []) {
      if (!["autofilled", "ai_generated", "needs_confirmation"].includes(mapping.status)) continue
      if (!mapping.value) continue
      const selector = mapping.selector || resolvedMappings.get(mapping.field_id)
      if (!selector) {
        results.push(result(mapping, "failed", "新增区块后仍未定位到字段"))
        continue
      }
      const node = document.querySelector(selector)
      if (!node || isUnsafe(node)) {
        results.push(result(mapping, "failed", "字段不可写或不安全"))
        continue
      }
      try {
        await writeField(node, mapping.value, mapping)
        results.push(result({ ...mapping, selector }, "success", "已填写"))
      } catch (error) {
        results.push(result({ ...mapping, selector }, "failed", String(error?.message || error)))
      }
    }
    return results
  }

  async function resetPeachFields(mappings) {
    const results = []
    const resolvedMappings = resolveRepeatMappings(mappings || [])
    for (const mapping of mappings || []) {
      const selector = mapping.selector || resolvedMappings.get(mapping.field_id)
      if (!selector) continue
      const node = document.querySelector(selector)
      if (!node || isUnsafe(node)) {
        results.push(result(mapping, "failed", "字段不可写或不安全"))
        continue
      }
      try {
        resetField(node, mapping)
        results.push(result({ ...mapping, selector }, "success", "已清空"))
      } catch (error) {
        results.push(result({ ...mapping, selector }, "failed", String(error?.message || error)))
      }
    }
    return results
  }

  async function applyRepeatActions(repeatActions, results) {
    for (const action of repeatActions || []) {
      const button = action.selector ? document.querySelector(action.selector) : null
      const times = Math.max(0, Math.min(Number(action.times) || 0, 3))
      if (!button || times <= 0) continue
      for (let index = 0; index < times; index += 1) {
        try {
          button.click()
          results.push({
            field_id: `${action.section || "repeat"}_add_${index + 1}`,
            selector: action.selector,
            status: "success",
            message: `已新增${action.label || "经历区块"}`,
          })
          await waitForDomUpdate()
        } catch (error) {
          results.push({
            field_id: `${action.section || "repeat"}_add_${index + 1}`,
            selector: action.selector,
            status: "failed",
            message: String(error?.message || error),
          })
        }
      }
    }
  }

  function resolveRepeatMappings(mappings) {
    const resolved = new Map()
    const fields = window.PeachDomScanner?.scan() || []
    for (const mapping of mappings) {
      if (!mapping.resolve || mapping.selector) continue
      const match = findRepeatedField(fields, mapping.resolve, resolved)
      if (match?.selector) resolved.set(mapping.field_id, match.selector)
    }
    return resolved
  }

  function findRepeatedField(fields, resolve, resolved) {
    const aliases = resolve.aliases || []
    const index = Number(resolve.repeat_index) || 0
    const matches = fields.filter((field) => aliases.some((alias) => fuzzyIncludes(fieldText(field), alias)))
    const usedSelectors = new Set(resolved.values())
    const cleanMatches = matches.filter((field) => !usedSelectors.has(field.selector))
    return cleanMatches[index] || matches[index] || cleanMatches[0] || null
  }

  async function writeField(node, value, mapping) {
    const inputType = String(mapping?.field?.inputType || "").toLowerCase()
    if (inputType === "radio_group" || inputType === "checkbox_group") {
      return writeChoiceGroup(node, value, inputType)
    }
    if (inputType === "custom_select") {
      return writeCustomSelect(node, value)
    }
    if (inputType === "custom_date") {
      return writeCustomDate(node, value)
    }
    if (isCustomPickerNode(node)) {
      return writeCustomSelect(node, value)
    }
    return writeValue(node, value)
  }

  function resetField(node, mapping) {
    const inputType = String(mapping?.field?.inputType || "").toLowerCase()
    if (inputType === "radio_group" || inputType === "checkbox_group") {
      return resetChoiceGroup(node, inputType)
    }
    if (inputType === "custom_select" || inputType === "custom_date" || isCustomPickerNode(node)) {
      const input = node.matches("input") ? node : node.querySelector("input")
      if (!input || input.readOnly) return
      writeValue(input, "")
      input.dispatchEvent(new Event("blur", { bubbles: true }))
      return
    }
    return writeValue(node, "")
  }

  function writeValue(node, value) {
    const tag = node.tagName.toLowerCase()
    if (tag === "select") {
      const option = Array.from(node.options).find((item) => optionMatches(item.textContent, value) || optionMatches(item.value, value))
      if (option) node.value = option.value
      else node.value = value
    } else if (node.isContentEditable) {
      node.textContent = value
    } else {
      setNativeValue(node, value)
    }
    node.dispatchEvent(new Event("input", { bubbles: true }))
    node.dispatchEvent(new Event("change", { bubbles: true }))
  }

  function writeChoiceGroup(root, value, inputType) {
    const rawType = inputType.replace("_group", "")
    const inputs = Array.from(root.querySelectorAll(`input[type="${rawType}"]`))
    const target = inputs.find((input) => optionMatches(choiceLabel(input), value) || optionMatches(input.value, value))
    if (!target) throw new Error(`未找到匹配选项：${value}`)
    const clickable = target.closest("label") || target
    clickable.click()
    target.dispatchEvent(new Event("input", { bubbles: true }))
    target.dispatchEvent(new Event("change", { bubbles: true }))
  }

  function resetChoiceGroup(root, inputType) {
    const rawType = inputType.replace("_group", "")
    const inputs = Array.from(root.querySelectorAll(`input[type="${rawType}"]`))
    for (const input of inputs) {
      input.checked = false
      input.dispatchEvent(new Event("input", { bubbles: true }))
      input.dispatchEvent(new Event("change", { bubbles: true }))
    }
  }

  async function writeCustomSelect(root, value) {
    const input = root.matches("input") ? root : root.querySelector("input")
    root.click()
    input?.focus?.()
    await waitForDomUpdate()
    const option = findVisibleOption(value)
    if (option) {
      option.click()
      await waitForDomUpdate()
      return
    }
    if (input && !input.readOnly) {
      writeValue(input, value)
      return
    }
    throw new Error(`未找到匹配选项：${value}`)
  }

  function writeCustomDate(root, value) {
    const input = root.matches("input") ? root : root.querySelector("input")
    if (!input) throw new Error("未找到日期输入框")
    setNativeValue(input, value)
    input.dispatchEvent(new Event("input", { bubbles: true }))
    input.dispatchEvent(new Event("change", { bubbles: true }))
    input.dispatchEvent(new Event("blur", { bubbles: true }))
  }

  function isUnsafe(node) {
    const type = String(node.getAttribute("type") || "").toLowerCase()
    const text = [
      type,
      node.getAttribute("name"),
      node.getAttribute("placeholder"),
      node.getAttribute("aria-label"),
      node.id,
      node.textContent,
    ].join(" ")
    return /(password|passwd|pwd|captcha|验证码|校验码|短信码|hidden|token|csrf)/i.test(text)
  }

  function isCustomPickerNode(node) {
    const input = node.matches("input") ? node : node.querySelector("input")
    if (!input) return false
    if (input.tagName.toLowerCase() !== "input") return false
    const type = String(node.getAttribute("type") || "").toLowerCase()
    const role = String(input.getAttribute("role") || node.getAttribute("role") || "").toLowerCase()
    const ariaHasPopup = String(input.getAttribute("aria-haspopup") || node.getAttribute("aria-haspopup") || "").toLowerCase()
    const classText = [node.className, input.className, node.parentElement?.className, node.closest("[class]")?.className].join(" ")
    if (role === "combobox" || ariaHasPopup === "listbox" || type === "search") return true
    return /(select|selector|cascader|picker|dropdown|combobox|el-select|ant-select|van-dropdown|t-select)/i.test(classText)
  }

  function findVisibleOption(value) {
    const nodes = Array.from(
      document.querySelectorAll(
        [
          "[role='option']",
          ".ant-select-item-option-content",
          ".ant-select-item-option",
          ".el-select-dropdown__item",
          ".arco-select-option",
          ".t-select-option",
          ".van-dropdown-item__option",
          "li",
        ].join(", "),
      ),
    )
    return nodes.find((node) => isVisible(node) && optionMatches(node.textContent, value))
  }

  function choiceLabel(input) {
    const id = input.getAttribute("id")
    const explicit = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null
    if (explicit) return clean(explicit.textContent)
    const label = input.closest("label")
    if (label) return clean(label.textContent)
    const parentText = clean(input.parentElement?.textContent || "")
    return parentText || clean(input.value || input.getAttribute("aria-label") || "")
  }

  function optionMatches(optionText, value) {
    const left = normalize(optionText)
    const right = normalize(value)
    return Boolean(left && right && (left === right || left.includes(right) || right.includes(left)))
  }

  function setNativeValue(node, value) {
    const prototype = Object.getPrototypeOf(node)
    const descriptor = Object.getOwnPropertyDescriptor(prototype, "value")
    if (descriptor?.set) descriptor.set.call(node, value)
    else node.value = value
  }

  function isVisible(node) {
    const rect = node.getBoundingClientRect()
    const style = window.getComputedStyle(node)
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none"
  }

  function result(mapping, status, message) {
    return {
      field_id: mapping.field_id,
      selector: mapping.selector,
      status,
      message,
    }
  }

  function fieldText(field) {
    return [field.label, field.placeholder, field.name, field.ariaLabel, field.nearbyText].join(" ")
  }

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim()
  }

  function fuzzyIncludes(text, alias) {
    const left = normalize(text)
    const right = normalize(alias)
    return right && left.includes(right)
  }

  function normalize(value) {
    return String(value || "").replace(/[\s_\-:：*（）()【\][\]]+/g, "").toLowerCase()
  }

  function waitForDomUpdate() {
    return new Promise((resolve) => window.setTimeout(resolve, 450))
  }

  window.PeachAutofill = { fill: fillPeachFields, reset: resetPeachFields }
})()
