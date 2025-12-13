// ForceAtlas2 plugin registration for Cytoscape.js
// Requires this file to exist in the same assets directory:
//   cytoscape-layout-forceatlas2.js
//
// If the plugin isn't present, we log a warning and do nothing.

(function () {
  function register() {
    try {
      if (typeof cytoscape === "undefined") return;

      // Most builds attach the plugin to window as `cytoscapeLayoutForceatlas2`
      // and export a function that expects the cytoscape instance.
      if (typeof window.cytoscapeLayoutForceatlas2 === "function") {
        window.cytoscapeLayoutForceatlas2(cytoscape);
        console.log("[docling_graph] ForceAtlas2 registered");
        return;
      }

      // Some builds attach as `forceatlas2`
      if (typeof window.forceatlas2 === "function") {
        window.forceatlas2(cytoscape);
        console.log("[docling_graph] ForceAtlas2 registered (alt)");
        return;
      }

      console.warn(
        "[docling_graph] ForceAtlas2 plugin not found. Add cytoscape-layout-forceatlas2.js to assets/."
      );
    } catch (e) {
      console.warn("[docling_graph] ForceAtlas2 registration error:", e);
    }
  }

  // Try immediately and again after DOM ready (Dash assets load order can vary)
  register();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", register);
  }
})();
