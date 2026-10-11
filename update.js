module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        path: "app/custom_nodes",
        message: [
          "git clone https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3.git",
          "git -C ComfyUI-Spectrum-MiniMax-H3 checkout 806fe498d574a726fecb8818917f00a4b993fd77"
        ]
      },
      when: "{{!exists('app/custom_nodes/ComfyUI-Spectrum-MiniMax-H3')}}"
    },
    {
      method: "shell.run",
      params: {
        message: "git pull"
      }
    },
    {
      method: "shell.run",
      params: {
        path: "app",
        message: "git pull"
      }
    },
    {
      method: "shell.run",
      params: {
        path: "app/custom_nodes/ComfyUI-Manager",
        message: "git pull"
      }
    },
    {
      method: "shell.run",
      params: {
        path: "app/custom_nodes/ComfyUI-KJNodes",
        message: "git pull",
      }
    },
    {
      method: "shell.run",
      params: {
        path: "app/custom_nodes",
        message: [
          "git clone https://github.com/jlucasmcrell/ComfyUI-H3-Multishot"
        ],
      },
      when: "{{!exists('app/custom_nodes/ComfyUI-H3-Multishot')}}"
    },
    {
      method: "shell.run",
      params: {
        path: "app/custom_nodes/ComfyUI-H3-Multishot",
        message: "git pull",
      },
      when: "{{exists('app/custom_nodes/ComfyUI-H3-Multishot')}}"
    },
    {
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: [
          "uv pip install -r requirements.txt"
        ]
      }
    },
    // Re-assert the cu130 pins after requirements.txt, so a future change to
    // ComfyUI's default torch can't knock the quantized H3 weights off the
    // accelerated path. No-op when already on the pinned versions.
    {
      method: "script.start",
      params: {
        uri: "torch.js",
        params: {
          venv: "env",
          path: "app"
        }
      }
    },
    {
      method: "script.start",
      params: {
        uri: "workflows.js"
      }
    },
    { method: "script.start", params: { uri: "film-tools.js" } }
  ]
}
