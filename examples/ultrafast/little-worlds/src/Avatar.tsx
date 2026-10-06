import { useState, type CSSProperties } from 'react'
import type { SpaceIcon } from './types'
import './avatar.css'

type AvatarProps = {
  personId: string
  /** Omit when a visible name already labels the avatar. */
  name?: string
  /** The person's visible name, used for initials without adding an accessible label. */
  displayName?: string
  /** Prefer the same saved world artwork used in the community. */
  icon?: SpaceIcon
  size?: number
  className?: string
}

const fallbackColors = [
  ['#082b16', '#57dc8c'], ['#312116', '#ffb28c'],
  ['#0b2445', '#83b5ff'], ['#28153f', '#c3a0fa'],
]

export default function Avatar({ personId, name, displayName, icon, size = 40, className = '' }: AvatarProps) {
  const [failedSources, setFailedSources] = useState<string[]>([])
  const source = icon?.dataUrl && !failedSources.includes(icon.dataUrl) ? icon.dataUrl : undefined
  const lightSource = icon?.lightDataUrl && !failedSources.includes(icon.lightDataUrl) ? icon.lightDataUrl : undefined
  const fail = (url: string) => setFailedSources(previous => [...previous, url])
  const hash = [...personId].reduce((value, letter) => (value * 31 + letter.codePointAt(0)!) >>> 0, 0)
  const colors = fallbackColors[hash % fallbackColors.length]
  const style = {
    '--avatar-size': `${size}px`,
    '--avatar-background': colors[0],
    '--avatar-ink': colors[1],
  } as CSSProperties
  const initial = [...(displayName?.trim() || name?.trim() || personId)].slice(0, 1).join('').toLocaleUpperCase()

  return <span
    className={`person-avatar ${source ? 'person-avatar-icon' : 'person-avatar-initial'}${lightSource ? ' has-light-icon' : ''} ${className}`.trim()}
    style={style}
    role={name ? 'img' : undefined}
    aria-label={name ? `${name}'s profile picture` : undefined}
    aria-hidden={name ? undefined : true}
  >
    {source
      ? <img className="person-avatar-default" src={source} alt="" width={256} height={256} draggable={false} onError={() => fail(source)} />
      : <span className="person-avatar-letter">{initial}</span>}
    {lightSource && <img className="person-avatar-light" src={lightSource} alt="" width={256} height={256} draggable={false} onError={() => fail(lightSource)} />}
  </span>
}
