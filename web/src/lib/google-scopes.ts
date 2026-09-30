export const GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords";
/** Only files this app creates: the per-account fixes-log sheets (D21). */
export const GOOGLE_DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file";

/**
 * Better Auth's comma-joined scope string from Google's space-separated one
 * (or an existing stored value), sorted so equal grants compare equal.
 */
export function normalizeScope(scope: string): string {
  return [...new Set(scope.split(/[\s,]+/).filter(Boolean))].sort().join(",");
}
