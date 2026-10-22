// Sector → project → building → unit → tenant. Each level has its own URL so
// back/forward, refresh and shared links all land on the same view.
export const portfolioPath = {
  root: () => '/portfolio',
  sector: (sectorId: number) => `/portfolio/secteurs/${sectorId}`,
  project: (sectorId: number, projectId: number) => `/portfolio/secteurs/${sectorId}/projets/${projectId}`,
  /** The building's units. */
  building: (buildingId: number) => `/portfolio/batiments/${buildingId}`,
  /** The building's information page (characteristics, paint, fiche, documents). */
  buildingInfo: (buildingId: number) => `/portfolio/batiments/${buildingId}/informations`,
  unit: (unitId: number) => `/portfolio/unites/${unitId}`,
};
