// Register cytoscape-fcose layout extension (safe/no-crash).
// Expects these to be loaded earlier via Dash assets ordering:
//   10-cytoscape-layout-base.js
//   20-cytoscape-fcose.js
(function () {
  function getExt() {
    return window.fcose || window.cytoscapeFcose || window["cytoscape-fcose"] || null;
  }

  function register() {
    try {
      if (!window.cytoscape || typeof window.cytoscape.use !== "function") return;
      var ext = getExt();
      if (!ext) return;
      // Some builds export a factory function, others export the extension directly.
      window.cytoscape.use(ext);
    } catch (e) {
      // Intentionally swallow to avoid breaking Dash app load.
      console.warn("fcose registration skipped:", e);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", register);
  } else {
    register();
  }
})();
