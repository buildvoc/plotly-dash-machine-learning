/* Minimal ForceAtlas2-compatible layout wrapper for Cytoscape.
   Uses COSE under the hood for stability when the real plugin bundle
   is not available, while preserving the forceatlas2 layout name. */
(function () {
  if (typeof cytoscape === "undefined") {
    return;
  }

  var defaults = {
    iterations: 800,
    scalingRatio: 1.0,
    gravity: 1.0,
    linLogMode: false,
    preventOverlap: true,
    fit: true,
    padding: 30,
    animate: false
  };

  function ForceAtlas2Layout(options) {
    this.options = Object.assign({}, defaults, options);
    this.cy = options.cy;
  }

  ForceAtlas2Layout.prototype.run = function () {
    var opts = this.options;
    if (!this.cy) {
      return;
    }

    var scaling = Math.max(0.5, opts.scalingRatio || 1.0);
    var layout = this.cy.layout({
      name: "cose",
      animate: opts.animate,
      randomize: false,
      fit: opts.fit,
      padding: opts.padding,
      gravity: opts.gravity,
      nodeRepulsion: 2048 * scaling,
      idealEdgeLength: 50 * scaling,
      avoidOverlap: opts.preventOverlap,
      numIter: opts.iterations
    });

    this._layout = layout;
    layout.run();
  };

  ForceAtlas2Layout.prototype.stop = function () {
    if (this._layout && typeof this._layout.stop === "function") {
      this._layout.stop();
    }
  };

  cytoscape("layout", "forceatlas2", ForceAtlas2Layout);

  if (typeof window !== "undefined") {
    window.cytoscapeLayoutForceatlas2 = ForceAtlas2Layout;
  }
})();
