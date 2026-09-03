chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !message.type) return false
  if (message.type === "PEACH_SCAN_FIELDS") {
    sendResponse({
      url: window.location.href,
      domain: window.location.hostname,
      fields: window.PeachDomScanner?.scan() || [],
      repeaters: window.PeachDomScanner?.scanRepeaters() || [],
    })
    return false
  }
  if (message.type === "PEACH_AUTOFILL") {
    Promise.resolve(window.PeachAutofill?.fill(message.mappings || [], message.repeatActions || []) || []).then((results) => {
      sendResponse({ results })
    })
    return true
  }
  if (message.type === "PEACH_RESET_AUTOFILL") {
    Promise.resolve(window.PeachAutofill?.reset(message.mappings || []) || []).then((results) => {
      sendResponse({ results })
    })
    return true
  }
  if (message.type === "PEACH_PAGE_INFO") {
    sendResponse({
      url: window.location.href,
      domain: window.location.hostname,
      title: document.title,
    })
    return false
  }
  return false
})
