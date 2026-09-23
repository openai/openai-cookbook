# Case summary service

Small offline fixture for the sandboxed migration cookbook.

The pre-migration service wraps a Chat Completions call and uses it to summarize
internal case notes. Tests use fakes; they should never call the network.
