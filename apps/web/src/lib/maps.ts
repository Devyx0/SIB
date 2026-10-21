// Google Maps search link for a building address — opens in a new tab,
// no API key needed. Province/country appended so short street names
// don't resolve to a same-named street elsewhere.

export function googleMapsUrl(address: string): string {
  return 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(`${address}, QC, Canada`);
}
