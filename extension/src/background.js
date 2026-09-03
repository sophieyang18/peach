chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(["peachApiBase"], (current) => {
    if (!current.peachApiBase) {
      chrome.storage.local.set({ peachApiBase: "http://127.0.0.1:8000" })
    }
  })
})
