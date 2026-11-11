module.exports = {
  requires: {
    bundle: "ai"
  },
  daemon: true,
  run: [
    // 0) Optional launcher pull — only when "Auto-update on Start" is switched on
    //    (the .auto-update file). Off by default so a working version stays put.
    //    Soft-fail if offline or local git changes block ff-only.
    {
      when: "{{exists('.auto-update')}}",
      method: "shell.run",
      params: {
        shell: "{{which('bash')}}",
        message: [
          // Pinokio aborts Start if the terminal prints `error:` — hide git's
          // "untracked files would be overwritten" so local work cannot block launch.
          "git pull --ff-only >.git/h3-pull.log 2>&1 || echo '[H3 Studio] launcher update check skipped (offline or local changes — use Update if needed)'"
        ]
      }
    },
    // 0b) New code must not run on an old backend: if the scripts that pin ComfyUI,
    //     custom nodes or packages changed since the last sync (or a sync never
    //     ran here), sync first. Otherwise just record the current commit.
    {
      method: "shell.run",
      params: {
        shell: "{{which('bash')}}",
        message: [
          "head=$(git rev-parse HEAD); synced=$(cat .h3-synced 2>/dev/null); if [ \"$head\" != \"$synced\" ]; then if [ -n \"$synced\" ] && git diff --quiet \"$synced\" \"$head\" -- install.js update.js sync.js film-tools.js torch.js workflows.js studio/requirements.txt 2>/dev/null; then echo \"$head\" > .h3-synced; else touch .h3-sync-needed; fi; fi"
        ]
      }
    },
    {
      when: "{{exists('.h3-sync-needed')}}",
      method: "script.start",
      params: {
        uri: "sync.js"
      }
    },
    // 1) ComfyUI backend only — no browser auto-launch. Lives only while start.js runs;
    //    Stop in Pinokio kills Comfy + Studio together (not a separate always-on app).
    {
      method: "shell.run",
      params: {
        venv: "env",
        env: {
          TOKENIZERS_PARALLELISM: "false",
          // Windows + redirected stderr: tqdm \r can raise OSError [Errno 22].
          // TQDM_DISABLE is not honored by all tqdm builds — comfy_boot.py force-disables bars.
          PYTHONIOENCODING: "utf-8"
        },
        path: "app",
        message: [
          "python ../comfy_boot.py --listen 127.0.0.1 --disable-auto-launch --disable-pinned-memory"
        ],
        on: [{
          // Loosened: just look for any http://host:port anywhere in the line,
          // instead of requiring the exact "To see the GUI go to:" prefix.
          // Different ComfyUI builds/locales can print this differently.
          "event": "/(http:\\/\\/[a-zA-Z0-9.]+:[0-9]+)/i",
          "done": true
        }, {
          "event": "/errno/i",
          "break": false
        }, {
          "event": "/error:/i",
          "break": false
        }]
      }
    },
    {
      method: "local.set",
      params: {
        // Fallback: if the regex above never matched, input.event[1] is
        // undefined and this would otherwise resolve to the literal string
        // "{{input.event[1]}}", which is what caused the ENOENT downstream.
        comfy_url: "{{input.event && input.event[1] ? input.event[1] : 'http://127.0.0.1:8188'}}",
        studio_port: "{{port ? port : 8787}}"
      }
    },
    // 2) H3 Studio — the only UI Pinokio opens (local.url).
    {
      method: "shell.run",
      params: {
        // Same venv as Comfy (app/env) — do not create a second env under studio/
        venv: "../app/env",
        path: "studio",
        env: {
          COMFY_URL: "{{local.comfy_url}}",
          STUDIO_HOST: "127.0.0.1",
          STUDIO_PORT: "{{local.studio_port}}"
        },
        message: [
          "python -m uvicorn server:app --host 127.0.0.1 --port {{local.studio_port}} --timeout-graceful-shutdown 8"
        ],
        on: [{
          // Critical Pattern Lock (mochi-style). Studio prints a bare http:// line
          // first so this cannot latch onto Comfy (Comfy runs in the other shell).
          event: "/(http:\\/\\/[0-9.:]+)/",
          done: true
        }]
      }
    },
    {
      method: "local.set",
      params: {
        // Same fallback pattern here, in case the Studio line also fails to match
        // for some reason (e.g. uvicorn prints a different startup banner).
        url: "{{input.event && input.event[1] ? input.event[1] : 'http://127.0.0.1:' + local.studio_port}}"
      }
    }
  ]
}
