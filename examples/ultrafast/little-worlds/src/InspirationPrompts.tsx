import { ArrowUpRight, Gamepad2, MessageSquare, Orbit } from 'lucide-react';
import './inspiration-prompts.css';

const inspirations = [
  {
    title: 'A tiny arcade',
    message: 'Add a tiny arcade with a playable game, keyboard controls, and a score counter.',
    Icon: Gamepad2,
  },
  {
    title: 'A shared guestbook',
    message: 'Add a shared guestbook where visitors can leave a message and read everyone’s notes.',
    Icon: MessageSquare,
  },
  {
    title: 'An orbiting solar system',
    message: 'Add an animated solar system with smoothly orbiting planets and click-to-explore facts.',
    Icon: Orbit,
  },
];

export default function InspirationPrompts({ canEdit, disabled, onChoose }: {
  canEdit: boolean;
  disabled: boolean;
  onChoose: (message: string) => void;
}) {
  if (!canEdit) return null;
  return <div className="inspiration-prompts" role="group" aria-label="Ideas to build">
    {inspirations.map(({ title, message, Icon }) => <button
      key={title}
      type="button"
      className="inspiration-prompt"
      disabled={disabled}
      aria-label={`Build ${title.toLocaleLowerCase()}`}
      aria-description={message}
      onClick={() => onChoose(message)}
    >
      <Icon size={15} strokeWidth={1.5} aria-hidden="true"/>
      <span>{title}</span>
      <ArrowUpRight className="inspiration-prompt-arrow" size={13} aria-hidden="true"/>
    </button>)}
  </div>;
}
