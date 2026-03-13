---
name: env-vault
description: >
  Encrypt and export all .env files from the project into a single
  password-protected archive, or import/restore them on another machine.
  Trigger on any of these natural-language intents: "export env",
  "back up my secrets", "bundle env files", "package my environment",
  "save my API keys", "archive env", "restore env", "import env",
  "transfer secrets", "move my env to another machine", "encrypt my
  env files", or "deploy secrets." Export is the primary use case and
  should be offered proactively when the user mentions Docker deployment
  or setting up a new machine.
---

# Env Vault Skill

Export every `.env` file in the project to a single encrypted archive, or restore them from one. Designed for migrating secrets between machines without pasting API keys into chat windows like animals.

## Available Commands

| Command | Script | Description |
|---------|--------|-------------|
| Export env files | `scripts/export_env.py` | Discover `.env` files, compress, encrypt, write to `~/Downloads` |
| Import env files | `scripts/import_env.py` | Decrypt an `.enc` archive and restore `.env` files to the project |

## Encryption

- **Key derivation:** PBKDF2-HMAC-SHA256, 600 000 iterations, 16-byte random salt
- **Cipher:** Fernet (AES-128-CBC + HMAC-SHA256)
- **File format:** `SALT (16 bytes) || Fernet token`

The `cryptography` package (already in `requirements.txt`) is the only dependency.

## Usage

```bash
# Export — creates ~/Downloads/jarvis-env-2026-03-13.enc
python scripts/export_env.py --password "my-secret-phrase"

# Export to a custom path
python scripts/export_env.py --password "my-secret-phrase" --output /tmp/env-backup.enc

# Import — dry-run (default, no files written)
python scripts/import_env.py --file ~/Downloads/jarvis-env-2026-03-13.enc --password "my-secret-phrase"

# Import — actually write files
python scripts/import_env.py --file ~/Downloads/jarvis-env-2026-03-13.enc --password "my-secret-phrase" --force
```

## Claude Instructions

### Natural Language Triggers

Invoke this skill automatically when the user's intent matches any of:
- Exporting, backing up, archiving, bundling, or packaging env/secrets/API keys
- Transferring environment to another machine, Docker, or server
- Restoring, importing, or loading env files from an archive

Do **not** wait for the user to say `/env-vault` — recognize the intent and act.

### Export Flow (primary)

1. Ask the user for a password via `AskUserQuestion`. Never echo it, log it, or include it in visible output.
2. Run `export_env.py --password <pw>` from the `skills/env-vault/` directory.
3. Report the output file path and how many `.env` files were archived.
4. Remind the user they will need the same password to import on the target machine.

### Import Flow

1. Ask for the `.enc` file path and password.
2. Run `import_env.py --file <path> --password <pw>` (no `--force` — dry-run).
3. Show the user exactly which files would be created or overwritten.
4. Only after explicit confirmation, run again with `--force`.
5. Never auto-force. The user must approve overwrites.
