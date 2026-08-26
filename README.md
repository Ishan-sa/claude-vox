# claude-vox

Claude Code reads its own answers out loud, in its own words.

When a turn finishes, `claude-vox` speaks Claude's opening remark and its
closing thought -- the natural bookends of the response -- through your
speakers. Code blocks, file listings, and bullet points are stripped out, so
you hear the sentences a person would actually read, not punctuation and paths.

```
Glad it's working, Sir -- and sorry it took that much digging. The hardware
was fine the whole time; it was contention over /dev/hidraw and some
inconsistent mode metadata from the controllers.

Where things stand:
- reopens on login, survives reboot
- fanrgb blue for scripting

Whenever you want it, the two loose ends are LAN access and wiring it into
ARIA. Both noted in memory, so just say the word.
```

Spoken: *"Glad it's working, Sir ... [pause] ... just say the word."* The list
in the middle is skipped.

## Why read Claude's own words

Most Claude Code TTS tools either read the whole response (long, full of
punctuation nobody wants to hear) or run it back through a model to summarise
(slow, and it can be wrong about what just happened). `claude-vox` speaks the
prose the model already wrote -- no second model, no extra latency. It picks
the first and last paragraphs because that is where a well-written answer opens
and lands, and drops everything structural in between.

There is one deliberate limit: Claude Code has **no hook that fires while a
response streams**, so the intro cannot be spoken before Claude has written it.
Both bookends are spoken together when the turn ends -- which reads like a
status report rather than a running commentary.

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

The voice you get out of the box is whatever your OS ships -- clear enough, but
plainly synthetic. For a neural one, see [a better voice](#a-better-voice)
below; it is one extra command and still needs no API key.

To remove it: `./uninstall.sh` (add `--purge` to delete the config too).

## How it works

Three hooks, all of which exit 0 no matter what goes wrong -- a broken speaker
must never wedge a coding session.

| Hook | What it does |
|---|---|
| `SessionStart` | If enabled, tells the session the marker convention, so it survives restarts |
| `Stop` | Reads the transcript and speaks Claude's opening and closing lines |
| `UserPromptSubmit` | Kills playback the instant you type again, so you can cut it off mid-sentence |

Subagent output is ignored -- only what you actually see on screen gets spoken.

### Speaking modes

`speech_mode` in config chooses what to read:

| Mode | Speaks |
|---|---|
| `bookends` *(default)* | The first and last paragraph, read as one line |
| `intro` | Just the opening paragraph |
| `summary` | Just the closing paragraph |
| `marker` | Only a line the model prefixes with the marker (below) |

In any mode, if the model writes a line beginning with the `🔊` marker, that exact line is spoken instead -- an override for when you want to dictate the words precisely. `segment_chars` caps how long each paragraph may be before it is trimmed at a sentence boundary.

### The instant opener (optional, off by default)

If you also want a sound the *instant* you hit enter -- before Claude has
written anything -- turn on the opener. It speaks a short rotating phrase
("On it, Sir.") from a cache, so it plays with no delay and never holds up your
prompt. It is off by default because the intro paragraph already gives a
content-aware opening; enable it only if you want that extra immediate ack.

```json
{ "opener": { "enabled": true, "phrases": ["On it, Sir.", "Working on it."] } }
```


## A better voice

The stock voices are the ones your operating system already had. They are
intelligible and they are free, and after an hour of listening to one narrate
your work you will want something else.

```bash
./setup-edge-tts.sh                      # en-GB-RyanNeural, a British male
./setup-edge-tts.sh en-US-GuyNeural      # or name any voice you like
./setup-edge-tts.sh --opener             # and speak an instant acknowledgement
```

This reaches Microsoft's neural voices through `edge-tts`. No API key, no
account, no per-word billing. It is the only dependency this project has, and
it goes into its own virtualenv under `~/.claude/vox/venv`, so nothing lands on
your system Python. `--list-voices` on that venv's `edge-tts` prints the
several hundred voices available.

It stays out of the way of the two things that actually matter in a hook:

**It is never the reason a turn goes quiet.** If the network is down, or
Microsoft is having a bad afternoon, or you deleted the venv, it speaks the
line through the offline OS voice instead. Worse audio beats no audio when the
point is to tell you something finished.

**It does not make you wait to be acknowledged.** Neural synthesis is a network
round-trip, which is fine at the end of a turn and far too slow for the opener
that fires the instant you press enter. So short lines are cached on disk by
voice, prosody and text: the setup script pre-renders your opener phrases, and
from then on they play immediately. Long lines are spoken once and never
repeated, so they are not worth caching and are cleaned up after playback.

Three environment variables tune it, should you want to:

| Variable | Default | Meaning |
|---|---|---|
| `VOX_RATE` | `-4%` | Speaking rate. Slightly slow reads as composed rather than chirpy |
| `VOX_PITCH` | `-4Hz` | Pitch shift. Slightly low puts some chest behind it |
| `VOX_FALLBACK_VOICE` | `Daniel` | The offline voice used when synthesis fails |

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
argv works. `setup-edge-tts.sh` above is exactly this: it points `argv` at
`backends/edge-tts.sh`, which synthesises, plays, and caches. Piper works the
same way:

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

### Choosing a voice

With the `http` backend, whatever your TTS server accepts goes in `body`. The
default is a male British voice, `en-GB-RyanNeural`. Swap it for any voice your
server supports:

```json
{ "backend": "http", "http": { "body": { "text": "{text}", "voice": "en-US-GuyNeural" } } }
```

Some Jarvis-adjacent Edge TTS voices: `en-GB-RyanNeural` and `en-GB-ThomasNeural`
(British male), `en-US-GuyNeural` and `en-US-ChristopherNeural` (US male). With
the `command` backend the voice is a flag instead, e.g. `["say", "-v", "Daniel", "{text}"]`.

### Other settings

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | What `/vox on` and `/vox off` flip |
| `speech_mode` | `bookends` | What to read: `bookends`, `intro`, `summary`, or `marker` |
| `segment_chars` | `280` | Max length of each paragraph before it is trimmed |
| `marker` | `🔊` | The prefix that marks the spoken line. Change it if the emoji renders badly in your terminal |
| `max_chars` | `400` | Longer lines are truncated at a word boundary |
| `timeout` | `8` | Seconds to wait on the `http` backend |
| `opener.enabled` | `false` | Speak an extra short line the moment a prompt is submitted |
| `opener.phrases` | *(list)* | The lines to rotate through; synthesised once, then cached |

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
