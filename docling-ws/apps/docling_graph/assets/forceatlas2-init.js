// Register ForceAtlas2 layout plugin if present.
// Requires you to place the plugin file at:
//   apps/docling_graph/assets/cytoscape-layout-forceatlas2.js
//
// This init runs in the browser (Dash assets pipeline).

(function () {
  var registeredFallback = false;

  function registerFallback(cy) {
    if (registeredFallback || !cy || typeof cy.use !== "function") return;

    // Lightweight shim to avoid layout failures when the ForceAtlas2 plugin is missing.
    // Maps ForceAtlas2 configuration to the built-in COSE layout so that selecting
    // ForceAtlas2 still yields a working force-directed layout.
    function forceAtlas2Shim(cytoscape) {
      if (!cytoscape) return;

      cytoscape(
        "layout",
        "forceatlas2",
        function (options) {
          var fallbackOptions = Object.assign({}, options, { name: "cose" });
          return cytoscape.layouts(fallbackOptions);
        }
      );
    }

    try {
      cy.use(forceAtlas2Shim);
      console.info("[docling_graph] ForceAtlas2 plugin not detected; using COSE fallback");
      registeredFallback = true;
      return true;
    } catch (e) {
      console.warn("[docling_graph] Failed to register ForceAtlas2 fallback", e);
      return false;
    }
  }

  function tryRegister(cy) {
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

    return registerFallback(cy);
  }

  // Try immediately, then retry in case scripts load in a different order.
  // We do not count attempts until cytoscape is available to avoid exiting
  // before dash-cytoscape finishes loading.
  var attempts = 0;
  var maxAttempts = 240; // ~60s at 250ms interval
  var timer = setInterval(function () {
    var cy = window.cytoscape;

    if (!cy) {
      return;
    }

    attempts += 1;

    if (tryRegister(cy)) {
      clearInterval(timer);
      return;
    }

    if (attempts >= maxAttempts) {
      clearInterval(timer);
      if (!registeredFallback) {
        registerFallback(cy);
      }
    }
  }, 250);
})();
