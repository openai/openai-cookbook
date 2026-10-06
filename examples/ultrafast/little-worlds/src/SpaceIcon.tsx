import { memo, useState } from 'react';
import type { CSSProperties } from 'react';
import type { SpaceIcon as SpaceIconData } from './types';
import './space-icon.css';

type Props = {
  icon?: SpaceIconData;
  size?: number;
  name?: string;
  className?: string;
};

function SpaceIcon({ icon, size = 68, name, className = '' }: Props) {
  const [failedSources, setFailedSources] = useState<string[]>([]);
  const source = icon?.dataUrl && !failedSources.includes(icon.dataUrl) ? icon.dataUrl : undefined;
  const lightSource = icon?.lightDataUrl && !failedSources.includes(icon.lightDataUrl) ? icon.lightDataUrl : undefined;
  const fail = (url: string) => setFailedSources(previous => [...previous, url]);
  const diameter = Number.isFinite(size) && size > 0 ? size : 68;
  return <span
    className={`space-icon${source ? ' space-icon-ready' : ' space-icon-empty'}${lightSource ? ' has-light-icon' : ''}${icon?.status === 'generating' ? ' space-icon-generating' : ''}${className ? ` ${className}` : ''}`}
    style={{ '--space-icon-base-size': `${diameter}px` } as CSSProperties}
    role={name ? 'img' : undefined}
    aria-label={name ? `${name}'s space icon` : undefined}
    aria-hidden={name ? undefined : true}
  >
    {source ? <img className="space-icon-default" src={source} alt="" draggable={false} decoding="async" onError={() => fail(source)}/> : <span className="space-icon-seed"><i/><i/><i/></span>}
    {lightSource && <img className="space-icon-light" src={lightSource} alt="" draggable={false} decoding="async" onError={() => fail(lightSource)}/>}
  </span>;
}

export default memo(SpaceIcon);
