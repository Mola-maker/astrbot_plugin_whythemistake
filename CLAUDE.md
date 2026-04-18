# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an **AstrBot plugin** template. AstrBot is an agentic assistant framework deployable on QQ, Telegram, Feishu, DingTalk, Slack, LINE, Discord, Matrix, and other messaging platforms.

## Architecture

The plugin entry point is `main.py`, which defines a single plugin class that:
- Inherits from `astrbot.api.star.Star`
- Is decorated with `@register(name, author, description, version)`
- Uses `@filter.command("cmd_name")` decorators on async generator methods to register slash commands
- Yields `event.plain_result(...)` or other result types to send responses
- Optionally implements `async def initialize(self)` and `async def terminate(self)` lifecycle hooks

`metadata.yaml` contains plugin metadata (name, display_name, desc, version, author, repo).

## Key AstrBot API

```python
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# In command handlers:
event.get_sender_name()     # sender's display name
event.message_str           # raw text string
event.get_messages()        # full message chain
event.plain_result(text)    # yield this to reply with plain text
```

## Plugin Registration

The `@register` decorator signature: `@register(unique_name, author, description, version)`

- `unique_name` should match the `name` field in `metadata.yaml`
- Plugin is loaded by AstrBot at runtime from the `data/plugins/` directory

## Development Notes

- No standalone run or test command — the plugin runs inside the AstrBot host process
- AstrBot docs: https://docs.astrbot.app/dev/star/plugin-new.html
- Command handlers must be `async def` and use `yield` (async generators) to return responses
