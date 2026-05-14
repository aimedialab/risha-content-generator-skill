# Risha Content Generator Skill

OpenClaw skill for discovering and executing [Risha.ai](https://www.risha.ai/) capabilities from a local helper script.

This skill is useful when you want OpenClaw to:

- authenticate against a Risha account
- inspect the capabilities available to that account
- check required inputs and available choices
- estimate credits before generation
- run text, image, audio, and video generations through Risha

## What Is Included

- [`SKILL.md`](./SKILL.md): the skill instructions used by OpenClaw
- [`agents/openai.yaml`](./agents/openai.yaml): skill registration metadata
- [`scripts/risha_api.py`](./scripts/risha_api.py): helper CLI for auth, catalog refresh, estimation, and generation
- [`references/current-capabilities.json`](./references/current-capabilities.json): bundled capability snapshot
- [`references/current-capabilities.md`](./references/current-capabilities.md): readable capability inventory
- [`references/risha-api.md`](./references/risha-api.md): API notes and endpoint reference

## Install

Clone or copy the `risha-content-generator` folder into your OpenClaw skills directory so the final path looks like:

```text
<your-openclaw-skills-dir>/risha-content-generator
```

Example using Git:

```bash
git clone https://github.com/<your-account>/risha-content-generator-skill.git
cp -R risha-content-generator-skill/risha-content-generator <your-openclaw-skills-dir>/
```

Example using a downloaded ZIP:

1. Download the repository ZIP from GitHub.
2. Extract it.
3. Copy the `risha-content-generator` folder into your OpenClaw skills directory.

After installation, OpenClaw should be able to discover the skill by name:

```text
risha-content-generator
```

## Create Your Risha Account

Register from the official Risha website:

- [Risha.ai](https://www.risha.ai/)

Then click `Get Started Free` and create your account with an email address and password.

Important:

- Do not use Google sign-in.
- Do not use Meta sign-in.

This skill authenticates to Risha capabilities using:

- `RISHA_EMAIL`
- `RISHA_PASSWORD`

So you need a normal email/password account that can be used by the local helper script.

## Configure Credentials

Export your Risha credentials before using the helper:

```bash
export RISHA_EMAIL="you@example.com"
export RISHA_PASSWORD="your-password"
```

Optional:

```bash
export RISHA_API_BASE_URL="https://adminxcore-api.risha.ai/api"
```

If you already have a working authorization header, you can use:

```bash
export RISHA_AUTH_HEADER="Bearer ..."
```

## Quick Start

Validate the account:

```bash
python3 scripts/risha_api.py me
```

Refresh the capability catalog:

```bash
python3 scripts/risha_api.py catalog \
  --quiet \
  --write-json references/current-capabilities.json \
  --write-markdown references/current-capabilities.md
```

Inspect one capability:

```bash
python3 scripts/risha_api.py capability 16
```

Estimate credits before generation:

```bash
python3 scripts/risha_api.py estimate \
  --capability-id 16 \
  --prompt-data-file /absolute/path/prompt-data.json
```

Generate content:

```bash
python3 scripts/risha_api.py generate \
  --capability-id 16 \
  --prompt-data-file /absolute/path/prompt-data.json \
  --wait
```

## Notes

- The skill uses a bundled capability snapshot for fast discovery, but you can refresh it live from your own account.
- Capability availability depends on the authenticated Risha account.
- Credit estimation is built in so you can see projected usage before generation.

## Repository Structure

```text
risha-content-generator/
├── README.md
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── current-capabilities.json
│   ├── current-capabilities.md
│   └── risha-api.md
└── scripts/
    └── risha_api.py
```
