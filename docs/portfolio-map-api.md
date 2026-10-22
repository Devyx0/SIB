# Portfolio map: data the frontend expects

The map page (`/portfolio/carte`, `apps/web/src/pages/Portfolio/MapView.tsx`) reads one endpoint.
Until it exists the page shows an empty state ("Aucune position à afficher").

## `GET /api/v1/portfolio/map`

Same auth and sector scoping as the other `/api/v1/portfolio/*` routes (a user only sees buildings in
sectors they can access).

```jsonc
{
  "buildings": [
    {
      "building_id": 12,
      "project_id": 4,
      "sector_id": 1,
      "adresse": "113 rue Chauveau",
      "ville": "Québec",
      "code_postal": "G1K 1A1",
      "web_building_name": null,
      "nom_unique_projet": "Résidence Chauveau",   // project name
      "territoire": "Québec",                        // sector name
      "color_code": "#123d72",                       // sector colour, same as the dispatch board (nullable)
      "latitude": 46.8139,
      "longitude": -71.2080,
      "unit_count": 19,
      "occupied_unit_count": 17                      // units with a current lease that has a tenant
    }
  ],
  "missing_coordinates": 4                           // accessible buildings with no coordinates
}
```

- Only buildings with both `latitude` and `longitude` go in `buildings`.
- Types: `PortfolioMapBuilding` / `PortfolioMapData` in `apps/web/src/api/schema.d.ts`.
- Coordinates need to be stored per building (new nullable `latitude` / `longitude` columns) and
  geocoded from `adresse` + `ville` + `code_postal`.

## Tiles

Free, keyless OpenStreetMap vector tiles from OpenFreeMap by default. Set `VITE_MAP_STYLE_URL` to use
any other MapLibre style.
