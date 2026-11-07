import type { AppProps } from "next/app";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import Shell from "@/components/shell";
import "bootstrap/dist/css/bootstrap.min.css";
import "@/styles/globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className={`${plexSans.variable} ${plexMono.variable}`}>
      <Shell>
        <Component {...pageProps} />
      </Shell>
    </div>
  );
}
