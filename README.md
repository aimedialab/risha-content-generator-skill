<table>
  <tr>
    <td align="center" bgcolor="#111111">
      <a href="https://www.risha.ai/">
        <img src="./assets/Risha-Logo-Dark.webp" alt="Risha" width="220" />
      </a>
    </td>
  </tr>
</table>

# Risha Content Generator Skill

OpenClaw skill and Claude Code command for discovering and executing [Risha.ai](https://www.risha.ai/) capabilities from a local helper script.

This package is useful when you want OpenClaw or Claude Code to:

- authenticate against a Risha account
- inspect the capabilities available to that account
- check required inputs and available choices
- estimate credits before generation
- run text, image, audio, and video generations through Risha

## Supported Capability Types

The package is designed to help with a broad set of Risha capability workflows, including:

- Arabic voice-over and dialect-aware content generation
- text-to-speech and speech-oriented workflows
- image generation and image-based multimodal generation
- video generation and video-oriented multimodal workflows
- music and audio generation flows
- creator-driven text generation and scripted content generation
- capability discovery, credit estimation, and generated asset retrieval

## What Is Included

- [`SKILL.md`](./SKILL.md): the skill instructions used by OpenClaw
- [`agents/openai.yaml`](./agents/openai.yaml): OpenClaw skill registration metadata
- [`.claude/commands/risha-content-generator.md`](./.claude/commands/risha-content-generator.md): Claude Code slash command
- [`scripts/risha_api.py`](./scripts/risha_api.py): helper CLI for auth, catalog refresh, estimation, and generation
- [`references/current-capabilities.json`](./references/current-capabilities.json): bundled capability snapshot
- [`references/current-capabilities.md`](./references/current-capabilities.md): readable capability inventory
- [`references/risha-api.md`](./references/risha-api.md): API notes and endpoint reference

## Install For OpenClaw

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

## Install For Claude Code

Clone or copy this repository somewhere local, then copy the Claude command file into your Claude Code commands directory so the final path looks like:

```text
<your-project>/.claude/commands/risha-content-generator.md
```

Example:

```bash
mkdir -p .claude/commands
cp /absolute/path/to/risha-content-generator/.claude/commands/risha-content-generator.md .claude/commands/risha-content-generator.md
```

The command expects the helper script and references to stay available from the cloned repository. The easiest setup is to keep the repository on disk and update the absolute paths inside the Claude command file if you move it to a different machine or folder.

After installation, Claude Code can use:

```text
/risha-content-generator
```

## Create Your Risha Account

Register from the official Risha website:

- [Risha.ai](https://www.risha.ai/)

Then click `Get Started Free` and create your account with an email address and password.

Important for both OpenClaw and Claude Code:

- Do not use Google sign-in.
- Do not use Meta sign-in.

This package authenticates to Risha capabilities using:

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
- OpenClaw uses the skill metadata in `SKILL.md` and `agents/openai.yaml`.
- Claude Code uses the slash command in `.claude/commands/risha-content-generator.md`.

## Repository Structure

```text
risha-content-generator/
├── .claude/
│   └── commands/
│       └── risha-content-generator.md
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
