import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-6 py-24 text-center">
      <p className="text-sm text-mint-700">404</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">Page not found</h1>
      <Link href="/" className="mt-6 text-mint-700 underline-offset-4 hover:underline">
        Back to home
      </Link>
    </main>
  );
}
