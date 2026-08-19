# Data & AI Policy Checklist

Before using **Cursor Agent** with BLAST research data on NERSC Perlmutter, confirm institutional policy with your PI and institution.

## Technical facts

| Topic | Detail |
|-------|--------|
| Remote SSH | Code and data stay on Perlmutter filesystems |
| Cursor Agent | May send code snippets / file context to cloud AI services |
| BLAST license | Argonne "available" — verify your authorized use terms |
| NERSC policy | Review [NERSC policies](https://docs.nersc.gov/) and your allocation agreement |

## Checklist

- [ ] Confirmed with PI that AI-assisted coding tools are allowed for this project
- [ ] Confirmed whether DFT training data / proprietary structures may appear in AI prompts
- [ ] Reviewed Cursor privacy/data settings (Cursor Settings → Privacy)
- [ ] Sensitive credentials stored outside repo (never in Slurm scripts or configs)
- [ ] Large proprietary datasets remain on `$SCRATCH`, not synced elsewhere

## If policy is restrictive

- Use Cursor for **Remote SSH editing only** with Agent disabled for sensitive files
- Or use local Cursor without cloud Agent for confidential sections
- Redact structures/inputs before asking Agent to debug configs

## HOME quota (blocks Remote SSH if exceeded)

Run on Perlmutter after connecting:

```bash
bash scripts/check-home-quota.sh
```

Mitigations: move conda envs and datasets to `$SCRATCH`, clean `~/.cursor-server` if stale.
