# Provider credential security

Dream's dynamic provider configuration separates **metadata** from **secrets**.

## Storage boundary

- `data/bridge_providers.json` contains provider IDs, endpoints, model names, and timestamps only.
- API keys and OAuth tokens are stored under the `Dream Model Providers` service by Python
  `keyring`.
- `keyring` selects Keychain Access on macOS, Credential Manager on Windows, and Secret
  Service/libsecret on Linux.
- There is no plaintext fallback. If the OS vault is unavailable, credential writes fail closed.
- The frontend provider and layout stores contain no credential field. The add/edit form keeps a
  key only in component memory until the bridge request completes.
- Deleting a credential-bearing provider purges its API key, OAuth access token, and OAuth refresh
  token before deleting metadata. If purge fails, metadata is retained so deletion can be retried.

The P-02 provider file format briefly allowed an `api_key` field. On load, the current registry
migrates that value into the keychain and atomically rewrites the metadata allow-list without the
field. The value is discarded rather than retained if the keychain is unavailable.

## Logging and errors

Connection and model-fetch errors are mapped to fixed messages. Raw response bodies,
`Authorization` headers, exception URLs, and credentials never cross the JSON-RPC bridge.
Google API keys are necessarily sent in the provider's query string but that URL is never included
in a returned or logged exception.

## OAuth PKCE

`OAuthPKCEManager` creates a cryptographically random state and verifier for every attempt, sends
an S256 challenge, allows only loopback or `dream://` callbacks, compares state in constant time,
expires attempts after ten minutes, and consumes state before token exchange. Access and refresh
tokens go directly to the keychain. Authorization codes, verifiers, and tokens are not persisted.

## Verification

Automated tests in `tests/test_model_providers.py` cover:

1. keychain store → retrieve → update → delete;
2. CRUD metadata and deletion purge;
3. one-way legacy-secret migration;
4. OpenAI and Google model-list parsing;
5. connection-error credential redaction; and
6. PKCE state, S256 challenge, verifier exchange, replay rejection, and token storage.

Before each platform release, run the packaged application and confirm the service entry with:

- **macOS:** Keychain Access → search for `Dream Model Providers`;
- **Windows:** Credential Manager → Windows Credentials;
- **Linux:** `secret-tool search service 'Dream Model Providers'`.

The automated test uses an in-memory keyring adapter so it is deterministic on headless CI. The
release check above validates the OS-specific backend selected by `keyring`.
