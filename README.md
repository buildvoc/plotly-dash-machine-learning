# Plotly Dash Docling Graph Viewer

A lightweight Dash application for exploring Docling JSON outputs as interactive graphs. The viewer renders documents, pages, and text spans with dash-cytoscape so you can click through relationships, apply layouts, and filter by page ranges.

## Project layout
- `apps/docling_graph/`: Dash app source (layout, callbacks, and static assets).
- `docling-ws/`: Workspace placeholder for Docling data files; JSON outputs are expected under `docling-ws/data/docling/` by default.

## Getting started
1. Install Python dependencies (Dash and dash-cytoscape must be available in your environment).
2. Ensure Docling JSON files are present under `docling-ws/data/docling/` or adjust `DOCLING_JSON_ROOT` in `apps/docling_graph/graph_builder.py` to point to your dataset.
3. Launch the app from the repository root:
   ```bash
   python -m apps.docling_graph.main
   ```
4. Open your browser to `http://127.0.0.1:8050` to interact with the graph. Use the control panel to switch layouts, toggle labels, and constrain expansions to a selected page range.

## Tests
Run the graph builder unit tests to validate graph construction and file discovery helpers:
```bash
python -m unittest apps.docling_graph.graph_builder
```
