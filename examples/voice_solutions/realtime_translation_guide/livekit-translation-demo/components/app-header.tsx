"use client"

import * as React from "react"
import Image from "next/image"
import Link from "next/link"
import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react"
import { useTheme } from "next-themes"

import { Button } from "@/components/ui/button"
import { useMounted } from "@/hooks/use-mounted"
import { cn } from "@/lib/utils"

function subscribeMeetingState(onStoreChange: () => void) {
  window.addEventListener("realtime-translation:meeting-state", onStoreChange)

  return () => {
    window.removeEventListener(
      "realtime-translation:meeting-state",
      onStoreChange
    )
  }
}

function getMeetingStateSnapshot() {
  return document.body.dataset.meetingState === "connected"
}

function getServerMeetingStateSnapshot() {
  return false
}

function AppHeader() {
  const meetingConnected = React.useSyncExternalStore(
    subscribeMeetingState,
    getMeetingStateSnapshot,
    getServerMeetingStateSnapshot
  )

  return (
    <header
      className={cn(
        "flex h-16 shrink-0 items-center bg-background px-6 text-foreground lg:px-8",
        meetingConnected && "border-b border-border"
      )}
    >
      <RealtimeTranslationLogo />
      <ThemeToggle />
    </header>
  )
}

function RealtimeTranslationLogo() {
  return (
    <Link href="/" className="flex items-center gap-1">
      <Image
        src="/brand/chatgpt-blossom-black.svg"
        alt=""
        width={40}
        height={40}
        className="size-14 dark:hidden"
      />
      <Image
        src="/brand/chatgpt-blossom-white.svg"
        alt=""
        width={40}
        height={40}
        className="hidden size-14 dark:block"
      />
      <span className="self-center text-2xl leading-none font-bold tracking-tight">
        Realtime Translation
      </span>
    </Link>
  )
}

function ThemeToggle() {
  const { theme = "system", setTheme } = useTheme()
  const mounted = useMounted()
  const activeTheme = mounted ? theme : "system"

  return (
    <div
      className="ms-auto flex items-center gap-1 rounded-full border border-border bg-background p-1"
      role="group"
      aria-label="Theme"
    >
      <ThemeModeButton
        active={activeTheme === "light"}
        ariaLabel="Use light mode"
        onClick={() => setTheme("light")}
      >
        <SunIcon />
      </ThemeModeButton>
      <ThemeModeButton
        active={activeTheme === "dark"}
        ariaLabel="Use dark mode"
        onClick={() => setTheme("dark")}
      >
        <MoonIcon />
      </ThemeModeButton>
      <ThemeModeButton
        active={activeTheme === "system"}
        ariaLabel="Use system mode"
        onClick={() => setTheme("system")}
      >
        <MonitorIcon />
      </ThemeModeButton>
    </div>
  )
}

function ThemeModeButton({
  active,
  ariaLabel,
  children,
  onClick,
}: {
  active: boolean
  ariaLabel: string
  children: React.ReactNode
  onClick: () => void
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={cn(
        "size-8 rounded-full",
        active
          ? "bg-foreground text-background hover:bg-foreground/90 hover:text-background"
          : "text-muted-foreground hover:text-foreground"
      )}
      aria-label={ariaLabel}
      aria-pressed={active}
      onClick={onClick}
    >
      {children}
    </Button>
  )
}

export { AppHeader }
