"""Synthetic, reserved .test examples. These are not live connection details."""


def matching_evidence():
    """Return a fresh synthetic evidence document for each demonstration."""
    return {
        "configured": {
            "issuer": "https://auth.example.test",
            "resource": "https://mcp.example.test/mcp",
            "redirect_uri": "https://app.example.test/callback",
            "authorization_endpoint": "https://auth.example.test/authorize",
            "token_endpoint": "https://auth.example.test/token",
            "scopes": ["files:read", "files:write"],
            "client_type": "public",
            "token_endpoint_auth_method": "none",
        },
        "discovered": {
            "issuer": "https://auth.example.test",
            "resource": "https://mcp.example.test/mcp",
            "authorization_endpoint": "https://auth.example.test/authorize",
            "token_endpoint": "https://auth.example.test/token",
            "scopes_supported": ["files:read", "files:write"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_basic"],
        },
        "observed": {
            "selected_issuer": "https://auth.example.test",
            "authorization_resource": "https://mcp.example.test/mcp",
            "token_resource": "https://mcp.example.test/mcp",
            "authorization_redirect_uri": "https://app.example.test/callback",
            "token_redirect_uri": "https://app.example.test/callback",
            "requested_scopes": ["files:read", "files:write"],
            "granted_scopes": ["files:read", "files:write"],
            "client_type": "public",
            "token_endpoint_auth_method": "none",
        },
    }
