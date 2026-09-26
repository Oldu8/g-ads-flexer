import { notFound } from "next/navigation";

/** Article page; web track B6. No articles exist yet, so every slug is 404. */
export default async function ArticlePage(props: PageProps<"/blog/[slug]">) {
  await props.params;
  notFound();
}
