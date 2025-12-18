# Conflict Summary

A merge conflict existed between the main `apps/docling_graph` app and the mirrored `docling-ws` copy. The workspace version included Cytoscape layout bundles (fcose, euler, ForceAtlas2) and their init shims, while the main app had removed them. Resolving required bringing the plugin assets back into the main app so both locations share the same layout scripts.
