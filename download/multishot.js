// ComfyUI-H3-Multishot (Seamless Chain) — jlucasmcrell.
// Custom nodes, not a LoRA. After this finishes: Pinokio Stop → Start so Comfy loads the pack.
// Cinema studio then offers Kesintisiz zincir (one script, --- between shots).
module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        path: "app/custom_nodes",
        message: [
          "git clone https://github.com/jlucasmcrell/ComfyUI-H3-Multishot"
        ]
      }
    }
  ]
}
