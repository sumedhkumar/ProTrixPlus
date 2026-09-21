import { Plus_Jakarta_Sans } from "next/font/google";

/**
 * Only applied within AuthShell (pre-signin pages). The rest of the app
 * (dashboard/admin) keeps the system-font stack in globals.css untouched.
 */
export const authFont = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-auth",
  display: "swap",
});
