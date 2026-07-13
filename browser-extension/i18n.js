const extensionApi = globalThis.browser ?? globalThis.chrome;
const RTL_UI_LANGUAGES = new Set(["ar", "dv", "fa", "he", "ku", "ps", "ur"]);

function extensionMessage(key, substitutions = [], fallback = "") {
  const localized = extensionApi.i18n && extensionApi.i18n.getMessage
    ? extensionApi.i18n.getMessage(key, substitutions)
    : "";
  return localized || fallback || key;
}

function applyDocumentLocale(root = document) {
  if (!root || !root.documentElement) return;
  const language = (
    extensionApi.i18n && extensionApi.i18n.getUILanguage && extensionApi.i18n.getUILanguage()
  ) || globalThis.navigator?.language || "en";
  const baseLanguage = language.toLowerCase().split(/[-_]/, 1)[0];
  root.documentElement.lang = language;
  root.documentElement.dir = RTL_UI_LANGUAGES.has(baseLanguage) ? "rtl" : "ltr";
  for (const element of root.querySelectorAll("[data-i18n]")) {
    element.textContent = extensionMessage(element.dataset.i18n, [], element.textContent.trim());
  }
  for (const element of root.querySelectorAll("[data-i18n-placeholder]")) {
    element.placeholder = extensionMessage(
      element.dataset.i18nPlaceholder, [], element.getAttribute("placeholder") || ""
    );
  }
  for (const element of root.querySelectorAll("[data-i18n-title]")) {
    const message = extensionMessage(
      element.dataset.i18nTitle, [], element.getAttribute("title") || root.title || ""
    );
    if (element === root.documentElement) root.title = message;
    else element.title = message;
  }
  for (const element of root.querySelectorAll("[data-i18n-aria-label]")) {
    element.setAttribute("aria-label", extensionMessage(
      element.dataset.i18nAriaLabel, [], element.getAttribute("aria-label") || ""
    ));
  }
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => applyDocumentLocale(), { once: true });
  } else {
    applyDocumentLocale();
  }
}
