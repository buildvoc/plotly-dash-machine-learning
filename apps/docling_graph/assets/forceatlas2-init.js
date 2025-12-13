// Register ForceAtlas2 layout plugin if present.
// Requires you to place the plugin file at:
//   apps/docling_graph/assets/cytoscape-layout-forceatlas2.js
//
// This init runs in the browser (Dash assets pipeline).

(function () {
  function tryRegister() {
    // cytoscape should be on window when dash-cytoscape is loaded
    var cy = window.cytoscape;
    if (!cy) return false;

    // Common globals used by the plugin build
    // (depends on the exact bundle you drop in assets)
    var fa2 = window.cytoscapeLayoutForceatlas2 || window.forceatlas2;

    if (fa2 && typeof cy.use === "function") {
      try {
        cy.use(fa2);
        console.log("[docling_graph] ForceAtlas2 plugin registered");
        return true;
      } catch (e) {
        console.warn("[docling_graph] ForceAtlas2 plugin present but failed to register", e);
      }
    }
    return false;
  }

  // Try immediately, then retry a few times in case scripts load in a different order.
  var attempts = 0;
  var timer = setInterval(function () {
    attempts += 1;
    if (tryRegister() || attempts >= 20) {
      clearInterval(timer);
      if (attempts >= 20) {
        console.warn("[docling_graph] ForceAtlas2 plugin not detected (layout will fail if selected)");
      }
    }
  }, 250);
})();
