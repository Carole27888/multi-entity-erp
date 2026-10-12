# Vendored front-end libraries

These files are committed so the app works offline and needs no Node/npm.

| Library | Version | File | Source URL |
|---|---|---|---|
| htmx | 2.0.4 | `htmx/htmx.min.js` | https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js |
| Alpine.js | 3.14.8 | `alpine/alpine.min.js` | https://cdn.jsdelivr.net/npm/alpinejs@3.14.8/dist/cdn.min.js |
| Chart.js | 4.4.7 | `chartjs/chart.umd.min.js` | https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js |
| SortableJS | 1.15.6 | `sortable/Sortable.min.js` | https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js |
| Manrope font (latin, 400–800) | Fontsource 5.1.1 | `../fonts/manrope/*.woff2` | https://cdn.jsdelivr.net/npm/@fontsource/manrope@5.1.1/files/ |

## Updating a library

1. Download the new minified file from the URL above (change the version number).
2. Replace the file in this folder and update the table.
3. Bump `PWA_VERSION` in `.env` so installed apps pick up the new file.

Source-map comments (`//# sourceMappingURL=...`) are removed from the minified files because the
`.map` files are not vendored and WhiteNoise's manifest storage fails on missing references.
