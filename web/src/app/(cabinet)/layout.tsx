import { SignOutButton } from "@/components/auth/sign-out-button";
import { Logo } from "@/components/logo";
import { requireSession } from "@/lib/session";

/** Signed-in area (web tracks B1, B2): every page here requires a session. */
export default async function CabinetLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();
  return (
    <>
      <header className="border-b border-line">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
          <Logo />
          <div className="flex items-center gap-4 text-sm">
            <span className="text-ink-muted">{session.user.email}</span>
            <SignOutButton />
          </div>
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </>
  );
}
