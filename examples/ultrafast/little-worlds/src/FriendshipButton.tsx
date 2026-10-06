import { useEffect, useState } from 'react';
import { Check, Clock3, UserPlus } from 'lucide-react';
import { api } from './api';

type Relation = { connections: Array<{ source: string; target: string }>; requests: { incoming: Array<{ id: string; fromId: string }>; outgoing: Array<{ id: string; toId: string }> } };

export default function FriendshipButton({ currentUserId, targetId, name }: { currentUserId: string; targetId: string; name: string }) {
  const [relation, setRelation] = useState<Relation | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const refresh = () => { void api<Relation>('/api/community').then(data => { if (active) setRelation(data); }).catch(() => {}); };
    refresh();
    window.addEventListener('focus', refresh);
    const timer = setInterval(refresh, 10_000);
    return () => { active = false; clearInterval(timer); window.removeEventListener('focus', refresh); };
  }, [currentUserId, targetId]);
  if (currentUserId === targetId) return null;
  const friends = relation?.connections.some(edge => edge.source === currentUserId && edge.target === targetId || edge.target === currentUserId && edge.source === targetId);
  const incoming = relation?.requests.incoming.find(request => request.fromId === targetId);
  const outgoing = relation?.requests.outgoing.find(request => request.toId === targetId);
  async function act() {
    if (!relation || pending || friends || outgoing) return;
    setPending(true); setError('');
    try {
      setRelation(await api<Relation>(incoming ? '/api/friends/respond' : '/api/friends/request', incoming ? { requestId: incoming.id, decision: 'accept' } : { targetId }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save your request.'); }
    finally { setPending(false); }
  }
  return <span className="friendship-control"><button className={`friendship-button ${friends ? 'is-connected' : ''}`} disabled={!relation || pending || !!friends || !!outgoing} onClick={() => void act()} aria-label={friends ? `You and ${name} are friends` : outgoing ? `Friend request sent to ${name}` : incoming ? `Accept ${name}’s friend request` : `Send ${name} a friend request`}>{friends ? <Check size={13}/> : outgoing ? <Clock3 size={13}/> : <UserPlus size={13}/>}<span>{pending ? 'Saving…' : friends ? 'Friends' : outgoing ? 'Request sent' : incoming ? 'Accept request' : 'Add friend'}</span></button>{error && <span className="friendship-error" role="alert">{error}</span>}</span>;
}
