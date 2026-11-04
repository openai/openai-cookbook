"""Offline consistency checks for deliberately selected public OAuth evidence.

Not an OAuth client, trace sanitizer, authentication test, or MCP access test.
No network, filesystem, environment, token decoding, or third-party dependencies.
"""

import ipaddress
import json
import re
from urllib.parse import unquote, urlsplit


AUTH_METHODS = frozenset({
    "none", "client_secret_basic", "client_secret_post", "private_key_jwt",
    "tls_client_auth", "self_signed_tls_client_auth",
})

SCHEMA = {
    "configured": {
        "issuer": "url", "resource": "url", "redirect_uri": "callback",
        "authorization_endpoint": "url", "token_endpoint": "url",
        "scopes": "scopes", "client_type": "client_type",
        "token_endpoint_auth_method": "auth_method",
    },
    "discovered": {
        "issuer": "url", "resource": "url",
        "authorization_endpoint": "url", "token_endpoint": "url",
        "scopes_supported": "scopes",
        "token_endpoint_auth_methods_supported": "auth_methods",
    },
    "observed": {
        "selected_issuer": "url", "authorization_resource": "url", "token_resource": "url",
        "authorization_redirect_uri": "callback", "token_redirect_uri": "callback",
        "requested_scopes": "scopes", "granted_scopes": "scopes",
        "client_type": "client_type", "token_endpoint_auth_method": "auth_method",
    },
}

_SCOPE = re.compile(r"[\x21\x23-\x5b\x5d-\x7e]{1,128}\Z")
_HOST_LABEL = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\Z")
_PATH = re.compile(r"(?:[a-zA-Z0-9._~!$&'()*+,;=:@/-]|%[a-fA-F0-9]{2})*\Z")
# Defense in depth only. Arbitrary secrets can resemble ordinary identifiers.
_SECRET_HINT = re.compile(
    r"bearer\s|basic\s|(?:access_token|refresh_token|client_secret|password|"
    r"code_verifier|authorization_code)\s*[:=]|-----BEGIN |"
    r"eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+|sk-[a-zA-Z0-9_-]{12,}",
    re.IGNORECASE,
)

_MISMATCH_GUIDANCE = {
    "issuer.metadata": (
        "Configured issuer and advertised metadata issuer differ.",
        "Review the discovery source and exact issuer identifier before relying on that metadata.",
    ),
    "issuer.selected": (
        "The effective selected issuer differs from the intended issuer.",
        "Review issuer selection for this attempt; do not substitute an unverified token claim.",
    ),
    "resource.metadata": (
        "The intended resource differs from the supplied protected-resource metadata identifier.",
        "Review the canonical MCP resource and the protected-resource metadata source.",
    ),
    "resource.authorization": (
        "The authorization request's resource differs from the intended MCP resource.",
        "Review the resource parameter selected for the authorization request.",
    ),
    "resource.token": (
        "The token request's resource differs from the intended MCP resource.",
        "Review the resource parameter used at the token exchange; do not assume the authorization request carries it over.",
    ),
    "redirect.authorization": (
        "The authorization request's redirect_uri differs from the configured effective callback.",
        "Review the exact callback chosen for this attempt, not a returned URL containing an authorization code.",
    ),
    "redirect.token": (
        "The token request's redirect_uri differs from the configured effective callback.",
        "Review the callback supplied in the token exchange against this attempt's intended callback.",
    ),
    "redirect.consistency": (
        "The authorization and token requests use different redirect_uri values.",
        "Reconcile the two effective callbacks; do not normalize a difference away.",
    ),
    "endpoint.authorization": (
        "The configured authorization endpoint differs from the supplied metadata endpoint.",
        "Review the endpoint configuration and its discovery source before making any request.",
    ),
    "endpoint.token": (
        "The configured token endpoint differs from the supplied metadata endpoint.",
        "Review the endpoint configuration and its discovery source before transmitting credentials.",
    ),
    "scope.requested": (
        "The requested scope set differs from the configured scope set.",
        "Review case-sensitive scope names and the intended least-privilege request.",
    ),
    "scope.granted": (
        "The recorded granted scope set differs from the requested set; provider policy may legitimately change grants.",
        "Review consent and provider scope policy. Do not infer an authentication failure or automatically broaden permissions.",
    ),
    "client.type": (
        "The effective client type differs from the configured type.",
        "Review whether this attempt should use a public or confidential client.",
    ),
    "client.auth_method": (
        "The effective token-endpoint authentication method differs from configuration.",
        "Review the selected client authentication method without collecting any credential values.",
    ),
    "client.auth_supported": (
        "The configured authentication method is absent from the supplied supported-method list.",
        "Review the provider metadata and intended client registration before choosing a method.",
    ),
}


class _InvalidInput(Exception):
    """Carries only static codes and allowlisted field paths, never input values."""

    def __init__(self, code, field="input"):
        self.code = code
        self.field = field


def _text(value, field, limit=2048):
    if type(value) is not str or not 1 <= len(value) <= limit:
        raise _InvalidInput("invalid_string", field)
    if any(ord(c) < 33 or ord(c) > 126 for c in value) or _SECRET_HINT.search(value):
        raise _InvalidInput("unsafe_or_unsupported_string", field)


def _url(value, field, callback=False):
    _text(value, field)
    # Never accept complete authorization requests, callback responses, or userinfo.
    # This intentionally excludes legal but out-of-profile static query parameters.
    if any(c in value for c in "?#\\"):
        raise _InvalidInput("unsafe_or_unsupported_url", field)
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
        if not host or parts.username is not None or parts.password is not None:
            raise ValueError()
        if parts.netloc.endswith(":") or (port is not None and not 1 <= port <= 65535):
            raise ValueError()
        if ":" in host:
            ipaddress.IPv6Address(host)
            if not re.fullmatch(r"\[[a-fA-F0-9:.]+\](?::[0-9]+)?", parts.netloc):
                raise ValueError()
        elif len(host) > 253 or any(not _HOST_LABEL.fullmatch(x) for x in host.split(".")):
            raise ValueError()
        elif not re.fullmatch(r"[a-zA-Z0-9.-]+(?::[0-9]+)?", parts.netloc):
            raise ValueError()
        loopback = callback and parts.scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}
        if parts.scheme != "https" and not loopback:
            raise ValueError()
        if not _PATH.fullmatch(parts.path):
            raise ValueError()
        decoded = unquote(parts.path, errors="strict")
        # Exclude nested percent encodings and encoded controls, whitespace, backslash.
        if any(ord(c) < 33 or ord(c) > 126 or c in "\\%" for c in decoded):
            raise ValueError()
        if _SECRET_HINT.search(decoded):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise _InvalidInput("unsafe_or_unsupported_url", field) from None


def _validate(payload):
    if type(payload) is not dict or len(payload) > len(SCHEMA):
        raise _InvalidInput("invalid_document")
    for section, values in payload.items():
        if type(section) is not str or section not in SCHEMA:
            raise _InvalidInput("unexpected_field")
        allowed = SCHEMA[section]
        if type(values) is not dict or len(values) > len(allowed):
            raise _InvalidInput("invalid_section", section)
        for name, value in values.items():
            if type(name) is not str or name not in allowed:
                raise _InvalidInput("unexpected_field", section)
            field = section + "." + name  # Both names passed the fixed allowlists.
            kind = allowed[name]
            if kind in {"url", "callback"}:
                _url(value, field, callback=kind == "callback")
            elif kind in {"scopes", "auth_methods"}:
                if type(value) is not list or len(value) > 128:
                    raise _InvalidInput("invalid_list", field)
                # [] means an explicitly recorded empty set; omission means unknown.
                for item in value:
                    _text(item, field, limit=128)
                    if kind == "scopes" and not _SCOPE.fullmatch(item):
                        raise _InvalidInput("invalid_scope", field)
                    if kind == "auth_methods" and item not in AUTH_METHODS:
                        raise _InvalidInput("unsupported_auth_method", field)
            else:
                _text(value, field, limit=128)
                expected = {"public", "confidential"} if kind == "client_type" else AUTH_METHODS
                if value not in expected:
                    raise _InvalidInput("unsupported_enum", field)


def _base(status, checks, validation_errors=None):
    return {
        "status": status,
        "authentication": "not_verified",
        "tool_access": "not_verified",
        "network_activity": "none",
        "evidence_basis": "caller_supplied_public_fields_only",
        "checks": checks,
        "validation_errors": validation_errors or [],
        "limits": [
            "Settings consistency is not proof of authentication or tool access.",
            "No server, discovery response, token, grant, or runtime tool result was independently checked.",
        ],
    }


def _invalid(error):
    return _base("invalid_input", [], [{
        "code": error.code, "field": error.field,
        "action": "Supply only documented public fields. Do not paste credentials, traces, or callback responses.",
    }])


def _resource_key(uri):
    # MCP recommends tolerance for scheme/host case only. No slash, port,
    # percent-escape, path-case, dot-segment, or Unicode equivalence is guessed.
    parts = urlsplit(uri)
    return parts.scheme.lower(), parts.netloc.lower(), parts.path


def diagnose(payload):
    """Compare plain dict/list/string evidence. Returns a value-free JSON-safe report.

    Omit uncollected fields. Do not use null or infer missing observations.
    All supplied values must already be public and deliberately selected.
    Validation rejects the whole document before doing any comparison.
    """
    try:
        _validate(payload)
    except _InvalidInput as error:
        return _invalid(error)

    checks = []

    def get(path):
        section, field = path.split(".")
        return payload.get(section, {}).get(field)

    def add(check_id, status, fields, explanation, action):
        checks.append({"id": check_id, "status": status, "fields": list(fields),
                       "explanation": explanation, "action": action})

    def compare(check_id, left, right, mode="exact", metadata=False):
        fields = (left, right)
        if metadata and not metadata_identity_matches:
            add(check_id, "unknown", fields,
                "Authorization-server metadata comparisons require matching supplied issuer evidence.",
                "Resolve issuer.metadata first; do not rely on mismatched metadata.")
            return
        a, b = get(left), get(right)
        if a is None or b is None:
            add(check_id, "unknown", fields, "At least one required public field was not supplied.",
                "Record the missing public field from the relevant source, or leave this result unknown.")
            return
        if mode == "resource":
            equal = _resource_key(a) == _resource_key(b)
        elif mode in {"scopes", "advertised"}:
            equal = set(a) == set(b) if mode == "scopes" else set(a).issubset(set(b))
        elif mode == "member":
            equal = a in b
        else:
            equal = a == b
        status = "match" if equal else ("review" if mode == "advertised" else "mismatch")
        if mode == "advertised" and not equal:
            explanation = "Some configured scopes are not advertised; metadata need not list every supported scope."
            action = "Review provider policy and the current scope challenge; do not conclude these scopes are unsupported."
        elif equal:
            explanation = "The supplied public fields agree under this check's comparison rule."
            action = "No settings discrepancy found here; authentication and runtime access remain unverified."
        else:
            explanation, action = _MISMATCH_GUIDANCE[check_id]
        add(check_id, status, fields, explanation, action)

    configured_issuer = get("configured.issuer")
    metadata_identity_matches = configured_issuer is not None and configured_issuer == get("discovered.issuer")
    compare("issuer.metadata", "configured.issuer", "discovered.issuer")
    compare("issuer.selected", "configured.issuer", "observed.selected_issuer")
    compare("resource.metadata", "configured.resource", "discovered.resource", "resource")
    compare("resource.authorization", "configured.resource", "observed.authorization_resource", "resource")
    compare("resource.token", "configured.resource", "observed.token_resource", "resource")
    compare("redirect.authorization", "configured.redirect_uri", "observed.authorization_redirect_uri")
    compare("redirect.token", "configured.redirect_uri", "observed.token_redirect_uri")
    compare("redirect.consistency", "observed.authorization_redirect_uri", "observed.token_redirect_uri")
    compare("endpoint.authorization", "configured.authorization_endpoint", "discovered.authorization_endpoint", metadata=True)
    compare("endpoint.token", "configured.token_endpoint", "discovered.token_endpoint", metadata=True)
    compare("scope.requested", "configured.scopes", "observed.requested_scopes", "scopes")
    compare("scope.granted", "observed.requested_scopes", "observed.granted_scopes", "scopes")
    compare("scope.advertised", "configured.scopes", "discovered.scopes_supported", "advertised", metadata=True)
    compare("client.type", "configured.client_type", "observed.client_type")
    compare("client.auth_method", "configured.token_endpoint_auth_method", "observed.token_endpoint_auth_method")
    compare("client.auth_supported", "configured.token_endpoint_auth_method",
            "discovered.token_endpoint_auth_methods_supported", "member", metadata=True)
    for section in ("configured", "observed"):
        fields = (section + ".client_type", section + ".token_endpoint_auth_method")
        client_type, method = (get(field) for field in fields)
        if client_type is None or method is None:
            status = "unknown"
        else:
            status = "match" if (client_type == "public") == (method == "none") else "mismatch"
        add("client." + section + "_mode", status, fields,
            "This recipe's profile pairs public clients with none and confidential clients with an authentication method.",
            "Check the intended client type and authentication method; this does not test the credentials or PKCE.")

    states = {item["status"] for item in checks}
    status = ("mismatch" if "mismatch" in states else "evidence_incomplete" if "unknown" in states
              else "review_required" if "review" in states else "settings_match")
    return _base(status, checks)


def diagnose_json(text):
    """Bounded JSON entry point; rejects duplicate keys and never echoes parse errors."""
    if type(text) is not str or len(text) > 65536:
        return _invalid(_InvalidInput("invalid_json"))

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise _InvalidInput("duplicate_json_key")
            result[key] = value
        return result

    def constant(_):
        raise _InvalidInput("invalid_json_constant")

    try:
        data = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except _InvalidInput as error:
        return _invalid(error)
    except (ValueError, RecursionError):
        return _invalid(_InvalidInput("invalid_json"))
    return diagnose(data)
