(function () {
  function getEulerPlugin() {
    // Most common bundle global:
    if (window.cytoscapeEuler) return window.cytoscapeEuler;

    // Sometimes exported under this name:
    if (window.euler) return window.euler;

    // Sometimes attached as a module-like default:
    if (window.cytoscape_euler) return window.cytoscape_euler;
    if (window.cytoscapeEulerDefault) return window.cytoscapeEulerDefault;

    return null;
  }

  function tryRegister() {
    var cy = window.cytoscape;
    if (!cy || typeof cy.use !== "function") return false;

    var euler = getEulerPlugin();
    if (!euler) return false;

    try {
      cy.use(euler);
      console.log("[docling_graph] Euler plugin registered");
      return true;
    } catch (e) {
      console.warn("[docling_graph] Euler plugin present but failed to register", e);
      return false;
    }
  }

  var attempts = 0;
  var timer = setInterval(function () {
    attempts += 1;
    if (tryRegister() || attempts >= 20) {
      clearInterval(timer);
      if (attempts >= 20) {
        console.warn("[docling_graph] Euler plugin not detected (layout will fail if selected)");
      }
    }
  }, 250);
})();
