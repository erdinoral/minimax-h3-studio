// Optional tools; no weight download and no change to the default generation path.
module.exports = {
  requires: { bundle: "ai" },
  run: [{
    method: "shell.run",
    params: { venv: "env", path: "app", message: "python ../studio/tools/install_h3_extras.py --check-stopped" }
  }, {
    method: "shell.run",
    params: { venv: "env", path: "app", message: "uv pip install -r requirements.txt" }
  }, {
    // Runs after Update's launcher pull, so a new pin applies in the same Update as the core pull.
    when: "{{exists('app/custom_nodes/ComfyUI-Spectrum-MiniMax-H3')}}",
    method: "shell.run",
    params: { path: "app/custom_nodes", message: [
      "git -C ComfyUI-Spectrum-MiniMax-H3 fetch",
      "git -C ComfyUI-Spectrum-MiniMax-H3 checkout 7df883bb2361b7884ad789e97effd1dc37c8963a"
    ] }
  }, {
    when: "{{!exists('app/custom_nodes/ComfyUI-Minimax-H3-Reference-Library')}}",
    method: "shell.run",
    params: { path: "app/custom_nodes", message: "git clone https://github.com/nikaskeba/ComfyUI-Minimax-H3-Reference-Library.git" }
  }, {
    // The library imports soundfile without listing it in requirements.txt.
    when: "{{exists('app/custom_nodes/ComfyUI-Minimax-H3-Reference-Library/requirements.txt')}}",
    method: "shell.run",
    params: { venv: "env", path: "app", message: "uv pip install -r custom_nodes/ComfyUI-Minimax-H3-Reference-Library/requirements.txt soundfile" }
  }, {
    when: "{{!exists('app/custom_nodes/ComfyUI-HyperFlow-H3')}}",
    method: "shell.run",
    params: { path: "app/custom_nodes", message: "git clone https://github.com/Adudeguyman/ComfyUI-HyperFlow-H3.git" }
  }, {
    when: "{{!exists('app/custom_nodes/ComfyUI-H3LookSheets')}}",
    method: "shell.run",
    params: { path: "app/custom_nodes", message: "git clone https://github.com/shisa84/ComfyUI-H3LookSheets.git" }
  }, {
    when: "{{!exists('app/custom_nodes/Herrgotts-H3-Infinite-Continuation-Suite')}}",
    method: "shell.run",
    params: { path: "app/custom_nodes", message: "git clone https://github.com/HerrgottMargott/Herrgotts-H3-Infinite-Continuation-Suite.git" }
  }, {
    method: "shell.run",
    params: { venv: "env", path: "app", message: "python ../studio/tools/install_film_workflows.py" }
  }, {
    method: "shell.run",
    params: { venv: "env", path: "app", message: "python ../studio/tools/install_h3_extras.py" }
  }]
};
