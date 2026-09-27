import "server-only";

/** A required server-side environment variable; fails loudly when missing. */
export function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing environment variable ${name} (see web/.env.example)`);
  }
  return value;
}
