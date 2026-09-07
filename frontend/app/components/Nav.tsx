"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Nav() {
  const path = usePathname();
  const links = [
    { href: "/profile",   label: "Profile" },
    { href: "/job",       label: "Analyze" },
    { href: "/dashboard", label: "Dashboard" },
  ];

  return (
    <nav className="sticky top-0 z-50 border-b border-gray-100 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-3">
        <Link href="/profile" className="flex items-center gap-2.5 group">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg gradient-accent shadow-sm shadow-indigo-200">
            <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636-.707.707M21 12h-1M4 12H3m3.343-5.657-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <span className="font-semibold text-gray-900 tracking-tight">CareerLens</span>
        </Link>

        <div className="flex items-center gap-1">
          {links.map(({ href, label }) => {
            const active = path === href;
            return (
              <Link
                key={href}
                href={href}
                className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all duration-150 ${
                  active
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-gray-500 hover:bg-gray-50 hover:text-gray-800"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
