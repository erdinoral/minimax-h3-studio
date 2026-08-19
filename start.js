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
          "event": "/To see the GUI go to: +(http:\\/\\/[a-zA-Z0-9.]+:[0-9]+)/i",
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
        comfy_url: "{{input.event[1]}}",
        studio_port: "{{port}}"
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
        url: "{{input.event[1]}}"
      }
    }
  ]
}
