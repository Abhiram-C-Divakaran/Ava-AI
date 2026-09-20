# Security Policy

## Reporting Security Vulnerabilities

We take the security of Ava AI very seriously. If you discover a security vulnerability, **please do NOT report it using a public GitHub issue**.

### Responsible Private Disclosure Process

To report a vulnerability, please use GitHub's private vulnerability reporting feature:
1. Navigate to the **Security** tab of the Ava AI repository.
2. Click **Report a vulnerability** to open a draft advisory.
3. Provide a detailed summary, including:
   - Vulnerability classification (e.g., Auth bypass, IDOR, SQL injection, Prompt injection, Data leakage).
   - Exact release version or commit hash where the vulnerability was identified.
   - Step-by-step reproduction instructions or a minimal proof-of-concept.
   - Any potential impact on user data isolation or system integrity.

If private vulnerability reporting is unavailable, you may contact the maintainer directly via secure private communication channels listed on the maintainer's GitHub profile.

### Response Timelines

- **Initial Acknowledgment**: Within 48 hours of receipt.
- **Triage & Severity Assessment**: Within 5 business days.
- **Fix Delivery**: Critical vulnerabilities are patched in an out-of-band patch release (e.g. `v1.0.1`) with high priority.

### Scope & Invariants

Ava AI enforces several strict architectural security invariants:
- **Zero Vector RAG / Zero External Embeddings**: Personal memory and user adaptation data are isolated in local relational SQLite tables with strict `user_id` foreign-key scoping.
- **Credential Masking**: All server logs automatically mask secrets, bearer tokens, API keys, and session cookies (`[REDACTED]`).
- **Path Traversal & Safe Uploads**: Document processing restricts file types to whitelisted extensions with filename sanitization and size caps.
- **Production Defaults**: Dangerous capabilities (such as arbitrary local code execution) are disabled by default in production (`ENABLE_CODE_EXECUTION=false`).
- **Session Hardening**: HTTPS-only cookies, SameSite=Lax enforcement, and strict CORS policies are enforced.
