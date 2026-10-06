import './devday-brand.css';

/** A typographic event signature, kept separate from the person’s canvas. */
export default function DevDayBrand({ compact = false, className = '' }: { compact?: boolean; className?: string }) {
  return <span className={`devday-brand${compact ? ' devday-brand-compact' : ''}${className ? ` ${className}` : ''}`} aria-label="OpenAI DevDay 2026">
    <span className="devday-brand-openai">OpenAI</span>
    <span className="devday-brand-name">DevDay</span>
    <span className="devday-brand-year">[2026]</span>
  </span>;
}

/** The event’s brackets become an opening into a little world. */
export function WorldBrackets({ className = '' }: { className?: string }) {
  return <span className={`world-brackets${className ? ` ${className}` : ''}`} aria-hidden="true">
    <span className="world-bracket world-bracket-left">[</span>
    <span className="world-brackets-center"><i/><i/><i/></span>
    <span className="world-bracket world-bracket-right">]</span>
  </span>;
}
