import { Geist_Mono } from "next/font/google"
import localFont from "next/font/local"

import "./globals.css"
import { AppHeader } from "@/components/app-header"
import { ThemeProvider } from "@/components/theme-provider"
import { cn } from "@/lib/utils"

const openAISans = localFont({
  src: "../public/fonts/OpenAISansVariable.woff2",
  variable: "--font-openai-sans",
  display: "swap",
})

const fontMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
})

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        "font-sans antialiased",
        fontMono.variable,
        openAISans.variable
      )}
    >
      <body className="font-sans antialiased">
        <ThemeProvider>
          <AppHeader />
          {children}
        </ThemeProvider>
      </body>
    </html>
  )
}
