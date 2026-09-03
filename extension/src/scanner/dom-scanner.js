(function () {
  const SENSITIVE_RE = /(password|passwd|pwd|captcha|验证码|校验码|短信码|hidden|token|csrf)/i
  const REPEATER_RE = /(添加|新增|增加|继续添加|再加).{0,8}(实习|工作|经历|项目|教育|校园|实践|获奖|荣誉|竞赛|奖项)|(实习|工作|项目|教育|校园|实践|获奖|荣誉|竞赛|奖项).{0,8}(添加|新增|增加)/i

  function scanPeachFormFields() {
    const seenGroups = new Set()
    const seenFields = new Set()
    const nodes = Array.from(
      document.querySelectorAll(
        [
          "input",
          "textarea",
          "select",
          "[contenteditable='true']",
          "[role='combobox']",
          ".ant-select",
          ".ant-picker",
          ".el-select",
          ".el-date-editor",
          ".arco-select",
          ".arco-picker",
          ".t-select",
          ".t-date-picker",
        ].join(", "),
      ),
    )
    return nodes
      .map((node, index) => toFormField(node, index, seenGroups))
      .filter((field) => field && !SENSITIVE_RE.test(fieldText(field)))
      .filter((field) => {
        const key = field.selector || field.id
        if (seenFields.has(key)) return false
        seenFields.add(key)
        return true
      })
  }

  function scanPeachRepeaters() {
    const nodes = Array.from(
      document.querySelectorAll(
        [
          "button",
          "[role='button']",
          "a",
          "[onclick]",
          "[tabindex]",
          "[class*='btn']",
          "[class*='Btn']",
          "[class*='button']",
          "[class*='Button']",
          "[class*='add']",
          "[class*='Add']",
        ].join(", "),
      ),
    )
    const seen = new Set()
    return nodes
      .map((node, index) => toRepeater(node, index))
      .filter(Boolean)
      .filter((item) => {
        const key = `${item.selector}|${item.label}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
      .slice(0, 12)
  }

  function toFormField(node, index, seenGroups) {
    const tagName = node.tagName.toLowerCase()
    const inputType = String(node.getAttribute("type") || tagName).toLowerCase()
    if (tagName !== "input" && isCustomPickerRoot(node)) return toCustomPickerField(node, index)
    if (["password", "hidden", "submit", "button", "reset", "file"].includes(inputType)) return null
    if (inputType === "radio" || inputType === "checkbox") return toChoiceGroup(node, index, inputType, seenGroups)
    if (isCustomPickerInput(node, tagName, inputType)) return toCustomPickerField(node, index)
    if (node.disabled || node.readOnly) return null
    const selector = stableSelector(node)
    if (!selector) return null
    return {
      id: `f${index + 1}`,
      tagName,
      inputType,
      label: labelFor(node),
      placeholder: node.getAttribute("placeholder") || "",
      name: node.getAttribute("name") || "",
      ariaLabel: node.getAttribute("aria-label") || "",
      nearbyText: nearbyText(node),
      required: Boolean(node.required || node.getAttribute("aria-required") === "true"),
      selector,
      options: tagName === "select" ? Array.from(node.options).map((option) => option.textContent.trim()).filter(Boolean) : [],
      currentValue: tagName === "select" ? node.options[node.selectedIndex]?.textContent?.trim() || "" : node.value || node.textContent || "",
    }
  }

  function toChoiceGroup(node, index, inputType, seenGroups) {
    if (node.disabled) return null
    const container =
      node.closest(
        [
          ".ant-form-item",
          ".el-form-item",
          ".arco-form-item",
          ".t-form__item",
          ".form-item",
          ".form-row",
          ".form-field",
          ".field",
          "fieldset",
        ].join(", "),
      ) || node.parentElement
    if (!container) return null
    const containerSelector = stableSelector(container) || stableSelector(node)
    const groupName = node.getAttribute("name") || containerSelector || stableSelector(node)
    const groupKey = `${inputType}:${groupName}:${containerSelector}`
    if (seenGroups.has(groupKey)) return null
    seenGroups.add(groupKey)
    const inputs = Array.from(container.querySelectorAll(`input[type="${inputType}"]`)).filter((item) => {
      const name = node.getAttribute("name")
      return !name || item.getAttribute("name") === name
    })
    const selector = containerSelector
    if (!selector) return null
    const checked = inputs.find((item) => item.checked)
    return {
      id: `f${index + 1}`,
      tagName: "input",
      inputType: `${inputType}_group`,
      label: labelFor(node) || labelFromFormContainer(node),
      placeholder: "",
      name: node.getAttribute("name") || "",
      ariaLabel: node.getAttribute("aria-label") || "",
      nearbyText: nearbyText(node),
      required: inputs.some((item) => item.required || item.getAttribute("aria-required") === "true"),
      selector,
      options: inputs.map((item) => choiceLabel(item)).filter(Boolean),
      currentValue: checked ? choiceLabel(checked) : "",
    }
  }

  function toCustomPickerField(node, index) {
    const root = customPickerRoot(node) || node
    const input = node.matches("input") ? node : root.querySelector("input")
    const selector = stableSelector(root) || stableSelector(node)
    if (!selector || node.disabled || input?.disabled) return null
    const classText = [node.className, root.className, node.parentElement?.className, input?.className].join(" ")
    const placeholder = input?.getAttribute("placeholder") || node.getAttribute("placeholder") || ""
    const pickerType = /date|time|picker|calendar|日期|时间/i.test(`${classText} ${placeholder}`)
      ? "custom_date"
      : "custom_select"
    return {
      id: `f${index + 1}`,
      tagName: input?.tagName?.toLowerCase() || node.tagName.toLowerCase(),
      inputType: pickerType,
      label: labelFor(input || node),
      placeholder,
      name: input?.getAttribute("name") || node.getAttribute("name") || "",
      ariaLabel: input?.getAttribute("aria-label") || node.getAttribute("aria-label") || "",
      nearbyText: nearbyText(input || node),
      required: Boolean(input?.required || input?.getAttribute("aria-required") === "true" || node.getAttribute("aria-required") === "true"),
      selector,
      options: [],
      currentValue: clean(input?.value || root.textContent || ""),
    }
  }

  function isCustomPickerInput(node, tagName, inputType) {
    if (tagName !== "input") return false
    const role = String(node.getAttribute("role") || "").toLowerCase()
    const ariaHasPopup = String(node.getAttribute("aria-haspopup") || "").toLowerCase()
    const classText = [
      node.className,
      node.parentElement?.className,
      node.closest("[class]")?.className,
      node.closest("[role='combobox']")?.className,
    ].join(" ")
    const widgetText = String(classText || "").toLowerCase()
    if (role === "combobox" || ariaHasPopup === "listbox" || inputType === "search") return true
    return /(select|selector|cascader|picker|dropdown|combobox|el-select|ant-select|van-dropdown|t-select)/i.test(widgetText)
  }

  function customPickerRoot(node) {
    return node.closest(
      [
        ".ant-select",
        ".ant-picker",
        ".el-select",
        ".el-date-editor",
        ".arco-select",
        ".arco-picker",
        ".t-select",
        ".t-date-picker",
        ".van-dropdown-menu",
        "[role='combobox']",
        "[aria-haspopup='listbox']",
      ].join(", "),
    )
  }

  function isCustomPickerRoot(node) {
    const role = String(node.getAttribute("role") || "").toLowerCase()
    const ariaHasPopup = String(node.getAttribute("aria-haspopup") || "").toLowerCase()
    const classText = String(node.className || "").toLowerCase()
    return (
      role === "combobox" ||
      ariaHasPopup === "listbox" ||
      /(select|selector|cascader|picker|dropdown|combobox|el-select|ant-select|ant-picker|van-dropdown|t-select)/i.test(classText)
    )
  }

  function choiceLabel(input) {
    const id = input.getAttribute("id")
    const explicit = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null
    if (explicit) return clean(explicit.textContent)
    const label = input.closest("label")
    if (label) return clean(label.textContent)
    const parentText = clean(input.parentElement?.textContent || "")
    if (parentText && parentText.length <= 28) return parentText
    return clean(input.value || input.getAttribute("aria-label") || "")
  }

  function labelFor(node) {
    const id = node.getAttribute("id")
    if (id) {
      const explicit = document.querySelector(`label[for="${CSS.escape(id)}"]`)
      if (explicit) return clean(explicit.textContent)
    }
    const parentLabel = node.closest("label")
    if (parentLabel) return clean(parentLabel.textContent.replace(node.value || "", ""))
    const aria = node.getAttribute("aria-labelledby")
    if (aria) {
      return clean(
        aria
          .split(/\s+/)
          .map((idPart) => document.getElementById(idPart)?.textContent || "")
          .join(" "),
      )
    }
    const containerLabel = labelFromFormContainer(node)
    if (containerLabel) return containerLabel
    const siblingLabel = labelFromSibling(node)
    if (siblingLabel) return siblingLabel
    return ""
  }

  function nearbyText(node) {
    const container =
      node.closest(
        [
          ".ant-form-item",
          ".el-form-item",
          ".arco-form-item",
          ".t-form__item",
          ".form-item",
          ".form-row",
          ".form-field",
          ".field",
          "li",
          "label",
        ].join(", "),
      ) || node.parentElement
    if (!container) return ""
    return clean((container.textContent || "").replace(node.value || "", "")).slice(0, 80)
  }

  function labelFromFormContainer(node) {
    const container = node.closest(
      [
        ".ant-form-item",
        ".el-form-item",
        ".arco-form-item",
        ".t-form__item",
        ".form-item",
        ".form-row",
        ".form-field",
        ".field",
      ].join(", "),
    )
    if (!container) return ""
    const labelNode = container.querySelector(
      [
        ".ant-form-item-label",
        ".el-form-item__label",
        ".arco-form-item-label",
        ".t-form__label",
        "label",
        "[class*='label']",
      ].join(", "),
    )
    const label = labelNode ? clean(labelNode.textContent) : ""
    if (label) return label.replace(/[：:*]+$/, "")
    return ""
  }

  function labelFromSibling(node) {
    let previous = node.previousElementSibling
    while (previous) {
      const text = clean(previous.textContent || previous.getAttribute("aria-label") || "")
      if (text && text.length <= 28) return text.replace(/[：:*]+$/, "")
      previous = previous.previousElementSibling
    }

    const parent = node.parentElement
    previous = parent?.previousElementSibling || null
    while (previous) {
      const text = clean(previous.textContent || previous.getAttribute("aria-label") || "")
      if (text && text.length <= 28) return text.replace(/[：:*]+$/, "")
      previous = previous.previousElementSibling
    }
    return ""
  }

  function stableSelector(node) {
    const id = node.getAttribute("id")
    if (id) {
      const selector = `#${CSS.escape(id)}`
      if (document.querySelectorAll(selector).length === 1) return selector
    }
    const name = node.getAttribute("name")
    if (name) {
      const selector = `${node.tagName.toLowerCase()}[name="${cssAttr(name)}"]`
      if (document.querySelectorAll(selector).length === 1) return selector
    }
    const path = []
    let current = node
    while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body) {
      const tag = current.tagName.toLowerCase()
      const parent = current.parentElement
      if (!parent) break
      const siblings = Array.from(parent.children).filter((item) => item.tagName === current.tagName)
      const index = siblings.indexOf(current) + 1
      path.unshift(`${tag}:nth-of-type(${index})`)
      current = parent
    }
    return path.length ? path.join(" > ") : ""
  }

  function toRepeater(node, index) {
    const text = clean([node.textContent, node.getAttribute("aria-label"), node.getAttribute("title")].join(" "))
    if (!text || !REPEATER_RE.test(text)) return null
    if (!isVisible(node)) return null
    const selector = stableSelector(node)
    if (!selector) return null
    return {
      id: `r${index + 1}`,
      label: text.slice(0, 80),
      selector,
      section: inferRepeaterSection(text),
      nearbyText: clean(node.closest("section, form, div")?.textContent || "").slice(0, 120),
    }
  }

  function inferRepeaterSection(text) {
    if (/项目/.test(text)) return "projects"
    if (/获奖|荣誉|竞赛|奖项/.test(text)) return "awards"
    if (/教育|校园/.test(text)) return "education"
    if (/实习|工作|经历|实践/.test(text)) return "experiences"
    return ""
  }

  function isVisible(node) {
    const rect = node.getBoundingClientRect()
    const style = window.getComputedStyle(node)
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none"
  }

  function cssAttr(value) {
    return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"')
  }

  function fieldText(field) {
    return [field.label, field.placeholder, field.name, field.ariaLabel, field.nearbyText, field.inputType].join(" ")
  }

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim()
  }

  window.PeachDomScanner = { scan: scanPeachFormFields, scanRepeaters: scanPeachRepeaters }
})()
