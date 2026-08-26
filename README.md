# claude-vox

Claude Code speaks its own summaries out loud.

Every response ends with one short spoken line, and only that line is read
through your speakers. No screen-reading, no listening to code blocks and file
paths, no LLM round-trip to summarise after the fact -- the summary is written
by the model as part of the answer, and you can see on screen exactly what is
about to be said.

```
Fixed the race in the session cache -- it was a missing lock around the
eviction path, not the TTL logic. Tests pass.

🔊 Fixed the session cache race and all the tests pass.
```

Only the last line is spoken.

## Why the marker, and not a summariser

Most Claude Code TTS tools either read the whole response (long, full of
punctuation nobody wants to hear) or run the response back through a model to
summarise it (slow, and it can be wrong about what just happened). Here the
author of the summary is the agent that did the work, at the moment it has the
full context. It costs one sentence per turn and zero extra latency.

If a response has no marker line, **nothing is spoken.** Silence is the
default, so it never reads something awkward aloud.

## Install

```bash
git clone https://github.com/Ishan-sa/claude-vox.git
cd claude-vox
./install.sh
```

Requirements: `python3` (3.8+) and a way to make sound. Nothing else -- the
whole thing is standard library, no pip install, no dependencies.

The installer copies the code to `~/.claude/vox/`, registers three hooks in
`~/.claude/settings.json` (backing up the old file first), installs the `/vox`
slash command, and writes a config tuned to whatever it finds on your machine.

**Restart Claude Code before this takes effect.** Hooks are read once, at
startup -- any session that was already open when you installed will stay
silent until you reopen it. This is the most common "installed but nothing
speaks" surprise.

Then, in a fresh session, turn it on:

```
/vox on
```

`/vox off` to stop, `/vox status` to see what is configured, `/vox test` to
hear a line right now without enabling anything.

To remove it: `./uninstall.sh` (add `--purge` to delete the config too).

## How it works

Three hooks, all of which exit 0 no matter what goes wrong -- a broken speaker
must never wedge a coding session.

| Hook | What it does |
|---|---|
| `SessionStart` | If enabled, tells the session the marker convention, so it survives restarts |
| `Stop` | Reads the transcript, pulls the marker line out of the response just finished, speaks it |
| `UserPromptSubmit` | Kills playback the instant you type again, so you can cut it off mid-sentence |

Subagent output is ignored -- only what you actually see on screen gets spoken.

## Configuration

`~/.claude/vox/config.json`. Two backends cover essentially any setup.

### `command` -- hand the text to a CLI program

The default on most machines. The installer picks whichever of `say`,
`espeak-ng`, `espeak`, or `spd-say` it finds.

```json
{
  "backend": "command",
  "command": { "argv": ["say", "-v", "Daniel", "{text}"] }
}
```

`{text}` is replaced with the line to speak. Anything that synthesises from
argv works -- including Piper:

```json
{
  "backend": "command",
  "command": {
    "argv": ["sh", "-c", "echo '{text}' | piper -m en_US-ryan-high.onnx --output-raw | aplay -r 22050 -f S16_LE -t raw -"]
  }
}
```

### `http` -- POST to a TTS server

For neural voices from a local or remote server. Two response shapes are
supported.

**Server replies with a URL to the audio** (the default shape):

```json
{
  "backend": "http",
  "http": {
    "url": "http://127.0.0.1:5050/speak",
    "body": { "text": "{text}" },
    "audio_url_field": "url",
    "play_command": ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "{audio}"]
  }
}
```

**Server replies with raw audio bytes** -- set `audio_url_field` to `null` and
the body is written to a temp file, which `{audio}` then points at. This is the
OpenAI-compatible shape, so it works with OpenAI's TTS and every local server
that mimics it:

```json
{
  "backend": "http",
  "http": {
    "url": "https://api.openai.com/v1/audio/speech",
    "headers": {
      "Content-Type": "application/json",
      "Authorization": "Bearer sk-..."
    },
    "body": { "model": "gpt-4o-mini-tts", "voice": "onyx", "input": "{text}" },
    "audio_url_field": null,
    "play_command": ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "{audio}"]
  }
}
```

### Other settings

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | What `/vox on` and `/vox off` flip |
| `marker` | `🔊` | The prefix that marks the spoken line. Change it if the emoji renders badly in your terminal |
| `max_chars` | `400` | Longer lines are truncated at a word boundary |
| `timeout` | `8` | Seconds to wait on the `http` backend |

## Troubleshooting

**Nothing is spoken.** Run `/vox status` -- if it says OFF, `/vox on`. If it
says ON, run `/vox test`: that isolates the audio path from the hook path. If
the test is silent, the backend is wrong; if the test works but real responses
are not spoken, the model is not writing the marker line, so re-run `/vox on`.

**It speaks but the hooks never fire.** Hooks are read at startup -- restart
Claude Code after installing.

**It talks over itself.** It should not; each new line stops the previous one.
If it does, your `play_command` is spawning a player that detaches from its own
process group.

## License

MIT
