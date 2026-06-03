import "./globals.css";
import type { ReactNode } from "react";

export const metadata = { title: "Тренажёр сертификации СА" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
