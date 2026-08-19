module.exports = {
  requires: {
    bundle: "ai"
  },
  daemon: true,
  run: [
    // 1) ComfyUI backend only — no browser auto-launch. Lives only while start.js runs;
    //    Stop in Pinokio kills Comfy + Studio together (not a separate always-on app).
    {
      method: "shell.run",
      params: {
        venv: "env",
        env: {
          TOKENIZERS_PARALLELISM: "false"
        },
        path: "app",
        message: [
          "python main.py --listen 127.0.0.1 --disable-auto-launch"
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
          "python -m uvicorn server:app --host 127.0.0.1 --port {{local.studio_port}}"
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