/* global indexedDB */

globalThis.CredentialVault = (() => {
  const DATABASE_NAME = "bookmark-organizer-pro-credentials";
  const STORE_NAME = "credentials";
  const TOKEN_KEY = "apiToken";
  let volatileToken = "";

  function openDatabase() {
    return new Promise((resolve, reject) => {
      if (!globalThis.indexedDB) {
        reject(new Error("Credential storage is unavailable"));
        return;
      }
      const request = indexedDB.open(DATABASE_NAME, 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(STORE_NAME)) {
          request.result.createObjectStore(STORE_NAME);
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(new Error("Credential storage could not be opened"));
    });
  }

  async function access(mode, operation) {
    const database = await openDatabase();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, mode);
        const request = operation(transaction.objectStore(STORE_NAME));
        let result;
        request.onsuccess = () => { result = request.result; };
        request.onerror = () => reject(new Error("Credential operation failed"));
        transaction.oncomplete = () => resolve(result);
        transaction.onabort = () => reject(new Error("Credential transaction aborted"));
      });
    } finally {
      database.close();
    }
  }

  async function getToken() {
    try {
      const value = await access("readonly", store => store.get(TOKEN_KEY));
      volatileToken = typeof value === "string" ? value : "";
    } catch {
      // Keep an in-memory fallback so a browser-specific IndexedDB failure does
      // not expose the token through content-script-readable extension storage.
    }
    return volatileToken;
  }

  async function setToken(value) {
    const token = typeof value === "string" ? value.trim() : "";
    if (!token) throw new Error("A token is required");
    await access("readwrite", store => store.put(token, TOKEN_KEY));
    volatileToken = token;
  }

  return Object.freeze({ getToken, setToken });
})();
