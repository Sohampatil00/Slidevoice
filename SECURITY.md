# Security

SlideVoice is a single-user application intended to run on your own machine. Bind both services to loopback, keep one worker per service, and do not expose them through a public tunnel. Host checks and request headers are defence-in-depth measures, not a login system.

## Sensitive data

- Store API credentials in `.env` or environment variables. Never commit them.
- Keep projects, reference recordings, model caches, and generated media under ignored `data/`, or outside the repository when configuring a custom data directory.
- Recordings and project files are not encrypted at rest. Protect them using your operating system's account and disk controls.
- Only clone voices you own or are authorised to use.
- Claude and remote speech providers receive the content sent to them. Check their policies before submitting sensitive material.

## Reporting a vulnerability

Use [GitHub's private vulnerability reporting page](https://github.com/Sohampatil00/Slidevoice/security/advisories/new) if it is enabled. If it is unavailable, contact the repository owner through a private channel listed on their [GitHub profile](https://github.com/Sohampatil00). If no private channel is available, open an issue asking for a secure contact method without disclosing the vulnerability.

Include the affected commit, operating system, reproduction steps, and impact. Do not attach real API keys, personal voice recordings, or confidential presentations. Avoid posting exploit details publicly before a coordinated fix.

## Support scope

The latest `main` branch is the current development target. There is no long-term support commitment or guaranteed response time for this MVP. Review dependency advisories and upstream model/tool licences when installing or distributing the application.
