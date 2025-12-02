# External Services

This directory contains external Git repositories that are automatically cloned and managed by the launcher.

## Chatterbox TTS API

- **Repository**: https://github.com/travisvn/chatterbox-tts-api
- **Port**: 4123
- **API**: OpenAI-compatible TTS endpoints
- **Auto-setup**: The launcher will automatically clone and configure this service

### Features

- Text-to-speech with voice cloning
- Multilingual support (22 languages)
- Voice library management
- Streaming audio generation
- OpenAI-compatible API endpoints

## Managing External Services

External services are git-ignored and managed independently from the main project.

### Automatic Management (via Launcher)

The launcher handles cloning, setup, and dependency installation automatically:

1. Install service: Click "Install" button for the service in the launcher GUI
2. Start service: Click "Start" button to run the service
3. Stop service: Click "Stop" button to terminate the service

### Manual Management

You can also manage services manually:

**Update to latest version:**

```bash
cd external_services/chatterbox-tts-api
git pull
```

**Check service status:**

```bash
cd external_services/chatterbox-tts-api
git status
git log -1
```

**Reconfigure:**

```bash
cd external_services/chatterbox-tts-api
cp .env.example .env
# Edit .env as needed
```

## Adding New External Services

To add a new external service:

1. Update `launcher/manager.py` service configuration
2. Add git repository URL and set `is_external: True`
3. The launcher will automatically handle cloning and setup

## Troubleshooting

**Service won't clone:**

- Ensure Git is installed and accessible
- Check internet connectivity
- Verify repository URL is correct

**Service won't start:**

- Check if dependencies are installed (click "Install" button)
- Verify the service's `.env` file is configured
- Check service logs in the launcher GUI

**Service out of date:**

- Navigate to service directory and run `git pull`
- Or delete the service directory and let launcher re-clone it
