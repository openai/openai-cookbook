import * as React from "react"

function subscribeMounted() {
  return () => {}
}

function getMountedSnapshot() {
  return true
}

function getServerMountedSnapshot() {
  return false
}

export function useMounted() {
  return React.useSyncExternalStore(
    subscribeMounted,
    getMountedSnapshot,
    getServerMountedSnapshot
  )
}
