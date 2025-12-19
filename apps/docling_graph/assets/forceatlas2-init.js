// Register ForceAtlas2 layout plugin if present.
// Requires the plugin file at:
//   apps/docling_graph/assets/cytoscape-layout-forceatlas2.js

(function () {
  function tryRegister() {
    var cy = window.cytoscape;
    if (!cy) return false;

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
