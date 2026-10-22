// Google Maps links — no API key needed. Prefer lat/lng when we have a
// geocoded pin; otherwise fall back to an address search (province/country
// appended so short street names don't resolve elsewhere).

export function googleMapsUrl(
  addressOrCoords: string | { lat: number; lng: number },
): string {
  if (typeof addressOrCoords === 'object') {
    const { lat, lng } = addressOrCoords;
    return `https://www.google.com/maps?q=${lat},${lng}`;
  }
  return 'https://www.google.com/maps/search/?api=1&query='
    + encodeURIComponent(`${addressOrCoords}, QC, Canada`);
}
