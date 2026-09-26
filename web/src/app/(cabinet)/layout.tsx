import { Logo } from "@/components/logo";

/** Signed-in area (web tracks B1, B2). Not linked from public navigation beyond "Sign in". */
export default function CabinetLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="border-b border-line">
        <div className="mx-auto flex h-16 max-w-5xl items-center px-6">
          <Logo />
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </>
  );
}
