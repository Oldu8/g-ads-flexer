/** 1234567890 → 123-456-7890, the way Google Ads shows customer ids. */
export function formatCustomerId(id: string): string {
  return /^\d{10}$/.test(id) ? `${id.slice(0, 3)}-${id.slice(3, 6)}-${id.slice(6)}` : id;
}
