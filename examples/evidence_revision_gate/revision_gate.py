"""Bind extracted citations to application-owned source snapshots, then revalidate."""
from dataclasses import dataclass
from types import MappingProxyType
import hashlib

@dataclass(frozen=True)
class Source:
    source_id: str
    text: str

    @property
    def digest(self):
        return hashlib.sha256(self.text.encode('utf-8')).hexdigest()

@dataclass(frozen=True)
class BoundFinding:
    claim: str
    source_id: str
    quote: str
    source_digest: str


def snapshot(sources):
    """Copy into an immutable mapping; reject duplicate IDs rather than overwrite."""
    result = {}
    for source in sources:
        if not isinstance(source, Source) or not source.source_id or not source.text:
            raise ValueError('Every source needs a nonempty ID and text.')
        if source.source_id in result:
            raise ValueError('Duplicate source ID.')
        result[source.source_id] = source
    return MappingProxyType(result)


def bind_finding(candidate, retrieved):
    """The application, NOT the model, attaches the digest from the request snapshot."""
    if not isinstance(candidate, dict) or set(candidate) != {'claim', 'source_id', 'quote'}:
        raise ValueError('Unexpected finding fields.')
    if any(not isinstance(v, str) or not v.strip() for v in candidate.values()):
        raise ValueError('All fields must be nonempty strings.')
    if any(len(v) > 2000 for v in candidate.values()):
        raise ValueError('Finding field is too long.')
    source = retrieved.get(candidate['source_id'])
    if source is None:
        raise ValueError('Unknown source ID.')
    if candidate['quote'] not in source.text:
        raise ValueError('Quote is not an exact substring of the cited source.')
    return BoundFinding(**candidate, source_digest=source.digest)


def revalidate(finding, current):
    """Report integrity only; a passing result does NOT establish claim support."""
    source = current.get(finding.source_id)
    if source is None:
        return 'source_missing'
    if finding.source_digest != source.digest:
        return 'source_changed'
    if not finding.quote.strip() or finding.quote not in source.text:
        return 'quote_missing'
    return 'snapshot_matches_not_semantically_verified'


def example():
    original = snapshot([Source('workshop', 'The fictional workshop opens at 10:00. Doors close at 17:00.')])
    candidate = {'claim': 'The workshop opens at 10:00.', 'source_id': 'workshop', 'quote': 'opens at 10:00'}
    bound = bind_finding(candidate, original)
    # The original quote survives, but new surrounding text changes its meaning.
    revised = snapshot([Source('workshop', original['workshop'].text + ' Update: today the workshop is canceled.')])
    assert bound.quote in revised['workshop'].text
    print('Unchanged snapshot:', revalidate(bound, original))
    print('Quote still exists:', bound.quote in revised['workshop'].text)
    print('Revised snapshot:', revalidate(bound, revised))

if __name__ == '__main__':
    example()
