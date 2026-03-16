# Security Policy

## Supported Versions

We release security patches for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 2.12.x  | :white_check_mark: |
| < 2.12  | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in Senten, please report it responsibly.

### Private Disclosure (Preferred)

**Do NOT create a public GitHub issue** for security vulnerabilities. Instead, please report them via one of these methods:

1. **Email**: Send an email to the maintainer (you can find the address on GitHub)
2. **GitHub Security Advisories**: Use GitHub's private vulnerability reporting (Go to the repository → Security → Advisories → Report a vulnerability)

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (optional)

### What to Expect

- **Acknowledgment**: We'll acknowledge your report within 48 hours
- **Timeline**: We'll aim to provide a timeline for the fix within 7 days
- **Credit**: With your permission, we'll credit you in the release notes

### Scope

The following are in scope for security reports:

- Authentication/authorization bypasses
- SQL injection or other injection attacks
- Cross-site scripting (XSS)
- Cross-site request forgery (CSRF)
- Data exposure or information disclosure
- Denial of service vulnerabilities
- Security misconfigurations

## Security Features

Senten includes several security features:

- **Authentication**: Supports OIDC, HTTP Basic Auth, and anonymous access
- **Session Management**: Secure HTTP-only cookie sessions with configurable lifetime
- **Rate Limiting**: Per-IP rate limiting on login and API endpoints
- **Input Validation**: Pattern-based prompt injection protection for LLM endpoints
- **Security Headers**: CSP, HSTS, X-Frame-Options, and more
- **Docker**: Runs as non-root user with read-only filesystem

## Best Practices for Self-Hosted Deployments

- Keep your `SECRET_KEY` confidential
- Use strong passwords for HTTP Basic Auth
- Enable HTTPS in production
- Regularly update to the latest version
- Review the environment variables in `.env.example`
