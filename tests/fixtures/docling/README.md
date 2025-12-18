# Docling fixtures

These fixtures mirror real Docling JSON exports used by the graph viewer:

- **Building Standards (ADB Amendments 2025)**: `building_standards/2025_Amendments_to_Approved_Document_B_volume_1_and_volume_2.json`
- **Regulations (UKSI 2010/2214, Regulation 38)**: `regulations/uksi-2010-2214-regulation-38.json`

## Format expectations
- JSON may be a `document` wrapper (`{"document": {...}}`) or a plain Docling document root.
- Documents contain `body`, `texts`, and optional `groups`/`tables`/`pictures` collections; each entry carries a `self_ref` and optional `children` `$ref` links.
- Provenance (`prov` / `provenance`) is optional. Page numbers are used when present but absence should not fail the loader.

## Usage
- Tests reference these paths directly; no network access is required.
- The app discovers them automatically when `DOCLING_JSON_ROOT` points at `tests/fixtures/docling` (or when the default root includes these files).
