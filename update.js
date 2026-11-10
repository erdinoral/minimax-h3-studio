module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        path: "app/custom_nodes",
        message: [
          "git clone https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3.git",
          "git -C ComfyUI-Spectrum-MiniMax-H3 checkout 7df883bb2361b7884ad789e97effd1dc37c8963a"
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
        path: "app/custom_nodes/ComfyUI-Minimax-H3-Reference-Library",
        message: "git pull",
      },
      when: "{{exists('app/custom_nodes/ComfyUI-Minimax-H3-Reference-Library')}}"
    },
    {
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: "uv pip install -r custom_nodes/ComfyUI-Minimax-H3-Reference-Library/requirements.txt soundfile"
      },
      when: "{{exists('app/custom_nodes/ComfyUI-Minimax-H3-Reference-Library/requirements.txt')}}"
    },
    {
      method: "shell.run",
      params: {
        path: "app/custom_nodes",
        message: [
          "git -C ComfyUI-H3-Continuum fetch --tags",
          "git -C ComfyUI-H3-Continuum checkout --detach 308653cff108061a94381cef446fef985384b214"
        ]
      },
      when: "{{exists('app/custom_nodes/ComfyUI-H3-Continuum')}}"
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
