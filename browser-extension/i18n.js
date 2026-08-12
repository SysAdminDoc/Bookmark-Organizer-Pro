const extensionApi = globalThis.browser ?? globalThis.chrome;
const RTL_UI_LANGUAGES = new Set(["ar", "dv", "fa", "he", "ku", "ps", "ur", "qps-plocm", "ar-xb"]);
const PSEUDO_UI_LANGUAGES = new Set(["qps-ploc", "en-xa"]);
const PSEUDO_RTL_LANGUAGES = new Set(["qps-plocm", "ar-xb"]);

function uiLanguage() {
  return (
    extensionApi.i18n && extensionApi.i18n.getUILanguage && extensionApi.i18n.getUILanguage()
  ) || globalThis.navigator?.language || "en";
}

function humanizeKey(key) {
  const text = String(key || "translation unavailable")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_@-]+/g, " ")
    .trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "Translation unavailable";
}

function substituteFallback(message, substitutions) {
  let index = 0;
  return String(message).replace(/\$([A-Za-z][A-Za-z0-9_]*)\$/g, () => substitutions[index++] ?? "");
}

function pseudoLocalize(message, rtl = false) {
  const accents = new Map([
    ["A", "Å"], ["B", "Ɓ"], ["C", "Ç"], ["D", "Ð"], ["E", "É"], ["F", "Ƒ"],
    ["G", "Ĝ"], ["H", "Ĥ"], ["I", "Î"], ["J", "Ĵ"], ["K", "Ҡ"], ["L", "Ŀ"],
    ["M", "Ḿ"], ["N", "Ń"], ["O", "Ö"], ["P", "Ƥ"], ["Q", "Q"], ["R", "Ŕ"],
    ["S", "Ş"], ["T", "Ţ"], ["U", "Û"], ["V", "Ṽ"], ["W", "Ŵ"], ["X", "Ẋ"],
    ["Y", "Ý"], ["Z", "Ž"], ["a", "å"], ["b", "ƀ"], ["c", "ç"], ["d", "ð"],
    ["e", "é"], ["f", "ƒ"], ["g", "ĝ"], ["h", "ĥ"], ["i", "î"], ["j", "ĵ"],
    ["k", "ҡ"], ["l", "ŀ"], ["m", "ḿ"], ["n", "ń"], ["o", "ö"], ["p", "ƥ"],
    ["q", "q"], ["r", "ŕ"], ["s", "ş"], ["t", "ţ"], ["u", "û"], ["v", "ṽ"],
    ["w", "ŵ"], ["x", "ẋ"], ["y", "ý"], ["z", "ž"]
  ]);
  const expanded = String(message).replace(/[A-Za-z]/g, letter => accents.get(letter) || letter);
  const rendered = `⟦${expanded} ${"~".repeat(Math.max(2, Math.floor(String(message).length / 3)))}⟧`;
  return rtl ? `\u202b${rendered}\u202c` : rendered;
}

function extensionMessage(key, substitutions = [], fallback = "") {
  const localized = extensionApi.i18n && extensionApi.i18n.getMessage
    ? extensionApi.i18n.getMessage(key, substitutions)
    : "";
  const message = localized || substituteFallback(fallback, substitutions) || humanizeKey(key);
  const language = uiLanguage().toLowerCase().replace("_", "-");
  if (PSEUDO_UI_LANGUAGES.has(language) || PSEUDO_RTL_LANGUAGES.has(language)) {
    return pseudoLocalize(message, PSEUDO_RTL_LANGUAGES.has(language));
  }
  return message;
}

function applyDocumentLocale(root = document) {
  if (!root || !root.documentElement) return;
  const language = uiLanguage();
  const baseLanguage = language.toLowerCase().split(/[-_]/, 1)[0];
  root.documentElement.lang = language;
  root.documentElement.dir = RTL_UI_LANGUAGES.has(baseLanguage) || PSEUDO_RTL_LANGUAGES.has(language.toLowerCase().replace("_", "-"))
    ? "rtl" : "ltr";
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
