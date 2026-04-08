---
paths:
  - "**/*.sh"
  - "**/*.py"
  - "**/*.ts"
  - "**/*.js"
  - "**/*.json"
---

# Security Rules

## Pre-Commit Secret Scanning
Before `git add` / `git commit`, scan staged files for:
- API Keys (`AIza...`, `sk-...`, `ghp_...`, `AKIA...`)
- Passwords, secrets, tokens in plaintext
- Internal IPs (192.168.x.x, 10.x.x.x)
- Database connection strings with credentials
- `.env` file contents
- SSH private keys

If found: **remove or replace with placeholders first**. Never push secrets to GitHub.

## Role Boundaries
| Role | Can Edit | Cannot Edit |
|------|----------|-------------|
| 🎯 Acceptor | `.agents/` | Source code ⛔ |
| 🏗️ Designer | `.agents/` | Source code ⛔ |
| 💻 Implementer | Source code + own workspace | Other agents' workspace ⛔ |
| 🔍 Reviewer | Review reports + task board | Source code ⛔ |
| 🧪 Tester | Test files + own workspace | Source code ⛔ |
