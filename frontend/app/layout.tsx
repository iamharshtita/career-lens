import type { Metadata } from "next";
import { Toaster } from "sonner";
import { ProfileProvider } from "./context/ProfileContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "CareerLens — AI Job Fit Analyzer",
  description: "Multi-agent AI that analyzes your fit for any job posting",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#fafafa] text-gray-900 antialiased">
        <ProfileProvider>{children}</ProfileProvider>
        <Toaster position="top-right" />
      </body>
    </html>
  );
}
