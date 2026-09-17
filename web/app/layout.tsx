import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ProTrixPlus | Trading workspace", template: "%s | ProTrixPlus" },
  description: "Your strategies, accounts, and execution activity in one trading workspace.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
