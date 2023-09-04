import { ReactNode } from 'react'
import NextLink from 'next/link'
import { useRouter } from 'next/router'

type Props = {
  children: ReactNode
  href: string
  className?: string
  skipLocaleHandling?: boolean
  locale?: string
  onClick?: () => void
  target?: string
  rel?: string
}

export default function Link({
  children,
  skipLocaleHandling,
  target,
  rel,
  ...rest
}: Props) {
  const router = useRouter()
  const locale = rest.locale || router.query.locale || ''

  let href = rest.href || router.asPath
  if (href.indexOf('http') === 0) skipLocaleHandling = true
  if (locale && !skipLocaleHandling) {
    href = href
      ? `/${locale}${href}`
      : router.pathname.replace('[locale]', locale as string)
  }

  return (
    <>
      <NextLink href={href} target={target} rel={rel}>
        <span {...rest}>{children}</span>
      </NextLink>
    </>
  )
}
