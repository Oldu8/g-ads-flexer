/** Shared class names so buttons look the same everywhere (landing, login, cabinet). */

const base =
  "inline-flex items-center justify-center rounded-lg px-5 py-2.5 font-medium transition-colors " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent " +
  "disabled:pointer-events-none disabled:opacity-60";

export const buttonPrimary = `${base} bg-primary text-white hover:bg-primary-hover active:bg-primary-active`;

export const buttonSecondary = `${base} border border-line-strong bg-white text-ink hover:bg-surface`;

export const badge = "inline-flex rounded-full bg-tint px-3 py-1 text-sm text-primary";

export const textLink = "text-primary underline-offset-4 hover:underline";
