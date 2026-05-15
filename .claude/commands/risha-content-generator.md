# Risha Content Generator

Use this command when you need to discover, inspect, estimate, or execute [Risha.ai](https://www.risha.ai/) capabilities through the local helper script bundled with this repository.

## Expected Environment

- Export `RISHA_EMAIL` and `RISHA_PASSWORD`, or `RISHA_AUTH_HEADER`.
- Keep this repository available locally so the helper script and references can be read.
- Default API base is `https://adminxcore-api.risha.ai/api`.

## Workflow

1. Validate authentication first:

```bash
python3 /ABSOLUTE/PATH/TO/risha-content-generator/scripts/risha_api.py me
```

2. Refresh or inspect the capability catalog:

```bash
python3 /ABSOLUTE/PATH/TO/risha-content-generator/scripts/risha_api.py catalog \
  --quiet \
  --write-json /ABSOLUTE/PATH/TO/risha-content-generator/references/current-capabilities.json \
  --write-markdown /ABSOLUTE/PATH/TO/risha-content-generator/references/current-capabilities.md
```

3. Inspect a capability before building `prompt_data`:

```bash
python3 /ABSOLUTE/PATH/TO/risha-content-generator/scripts/risha_api.py capability 123
```

4. Estimate credits before generating:

```bash
python3 /ABSOLUTE/PATH/TO/risha-content-generator/scripts/risha_api.py estimate \
  --capability-id 123 \
  --prompt-data-file /absolute/path/prompt-data.json
```

5. Generate and optionally wait for completion:

```bash
python3 /ABSOLUTE/PATH/TO/risha-content-generator/scripts/risha_api.py generate \
  --capability-id 123 \
  --prompt-data-file /absolute/path/prompt-data.json \
  --wait
```

6. If the user wants automatic daily syncing of the capability snapshot, install the packaged scheduler:

```bash
python3 /ABSOLUTE/PATH/TO/risha-content-generator/scripts/install_daily_refresh.py --email "you@example.com" --password "your-password" --hour 4 --minute 0
```

## Guidance

- Never guess `prompt_data`; inspect the capability first.
- Use the bundled references as the fast path, then refresh the catalog when needed.
- If the user wants ongoing automatic refresh, use the installer instead of only running `catalog` once.
- Prefer creator, voice, and dialect values exactly as returned by the helper.
- Always mention estimated credits and projected remaining credits before a generation step.
- If login works but no reusable header can be derived, stop and ask for the exact working auth header format.
