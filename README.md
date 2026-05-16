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

## Media Input Safety

For capability fields marked as file inputs, the helper now normalizes the value before it reaches Risha:

- local file paths are uploaded to Risha assets first
- `file://` URLs are uploaded to Risha assets first
- `data:` URLs are decoded and uploaded to Risha assets first
- public `http(s)` media URLs are downloaded and re-uploaded to Risha assets first

This prevents the common failure modes where a workflow sends:

- local workspace paths such as `/data/...` or `/Users/...`
- temporary proxy or cache URLs
- provider URLs that later expire

If a media URL requires authentication or is not publicly downloadable, the helper will stop with a clear error instead of sending a bad file reference to Risha.

## What Is Included

- [`SKILL.md`](./SKILL.md): the skill instructions used by OpenClaw
- [`agents/openai.yaml`](./agents/openai.yaml): OpenClaw skill registration metadata
- [`.claude/commands/risha-content-generator.md`](./.claude/commands/risha-content-generator.md): Claude Code slash command
- [`scripts/risha_api.py`](./scripts/risha_api.py): helper CLI for auth, catalog refresh, estimation, and generation
- [`scripts/install_daily_refresh.py`](./scripts/install_daily_refresh.py): installs a daily capability refresh scheduler
- [`scripts/refresh_catalog_job.py`](./scripts/refresh_catalog_job.py): scheduler runner that refreshes the catalog snapshot
- [`scripts/uninstall_daily_refresh.py`](./scripts/uninstall_daily_refresh.py): removes the installed daily refresh scheduler
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

Optional:

If you want the installed skill to keep its bundled capability snapshot fresh every day, run:

```bash
python3 scripts/install_daily_refresh.py --email "you@example.com" --password "your-password"
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

Optional:

If you want the installed command package to refresh Risha capabilities daily, run:

```bash
python3 /absolute/path/to/risha-content-generator/scripts/install_daily_refresh.py --email "you@example.com" --password "your-password"
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

## Daily Capability Refresh

The package can install a daily scheduled refresh that pulls the latest capabilities from your Risha account and rewrites:

- `references/current-capabilities.json`
- `references/current-capabilities.md`

On macOS, the installer creates a `launchd` job. On Linux, it installs a user `cron` entry. In both cases it also writes a per-user credential file with mode `0600`, so the scheduler can authenticate without depending on an interactive shell session.

Install the daily refresh job:

```bash
python3 scripts/install_daily_refresh.py --email "you@example.com" --password "your-password"
```

Use a custom time:

```bash
python3 scripts/install_daily_refresh.py --email "you@example.com" --password "your-password" --hour 4 --minute 30
```

Use an authorization header instead of email/password:

```bash
python3 scripts/install_daily_refresh.py --auth-header "Bearer ..."
```

Remove the scheduled job:

```bash
python3 scripts/uninstall_daily_refresh.py
```

## Quick Start

After you install the skill or command and export your Risha credentials, the normal entry point should be the agent itself, not raw Python commands.

### OpenClaw

Prompt OpenClaw with the skill name and your task, for example:

```text
Use risha-content-generator to check my Risha account, refresh the capability catalog, and show me which Arabic voice-over and TTS capabilities are available.
```

```text
Use risha-content-generator to inspect the video generation capabilities on my account and tell me the required inputs, estimated credits, and remaining balance before generation.
```

```text
Use risha-content-generator to install a daily capability refresh job that pulls the latest Risha catalog every day at 4:00 AM.
```

### Claude Code

Run the Claude Code command and describe the workflow you want, for example:

```text
/risha-content-generator check my Risha account, refresh the catalog, and list the available Arabic dialect, TTS, music, image, and video capabilities.
```

```text
/risha-content-generator inspect capability 16, explain its required fields, and estimate the credit cost before generating anything.
```

```text
/risha-content-generator install a daily refresh job for my Risha capabilities and keep the local catalog updated every morning.
```

### What The Agent Should Handle

The agent should be able to:

- validate authentication
- refresh or inspect the capability catalog
- install or remove the daily catalog refresh scheduler when asked
- inspect one capability and its required fields
- check creator, dialect, and voice choices
- normalize file inputs into Risha-hosted asset URLs before estimate or generation
- estimate credits before generation
- generate content only when asked

## Manual Helper Usage

If you want to call the helper directly for debugging or local scripting, you can still use the Python CLI:

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

Upload a local media file to Risha assets directly:

```bash
python3 scripts/risha_api.py upload-asset /absolute/path/to/input.png
```

Estimate credits before generation:

```bash
python3 scripts/risha_api.py estimate \
  --capability-id 16 \
  --prompt-data-file /absolute/path/prompt-data.json
```

## Notes

- The skill uses a bundled capability snapshot for fast discovery, but you can refresh it live from your own account.
- Capability availability depends on the authenticated Risha account.
- Credit estimation is built in so you can see projected usage before generation.
- OpenClaw uses the skill metadata in `SKILL.md` and `agents/openai.yaml`.
- Claude Code uses the slash command in `.claude/commands/risha-content-generator.md`.
- The optional daily refresh scheduler updates the bundled capability snapshot automatically once per day.

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
    ├── install_daily_refresh.py
    ├── refresh_catalog_job.py
    ├── risha_api.py
    └── uninstall_daily_refresh.py
```
