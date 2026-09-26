/** Stand-in for a page whose content is built in a later web track. */
export function PagePlaceholder({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="mx-auto max-w-3xl px-6 py-24">
      <h1 className="text-4xl font-semibold tracking-tight">{title}</h1>
      <div className="mt-4 text-lg text-ink-muted">{children ?? "Coming soon."}</div>
    </section>
  );
}
