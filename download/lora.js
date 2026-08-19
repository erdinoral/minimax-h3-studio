// LightX2V Turbo LoRA — FL2VA 4-step distill (Comfy-compatible conversion).
// ~2 GB. Optional: Studio Ayarlar → LoRA → Uygula also downloads if missing.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/Kijai/MiniMax-H3_comfy/resolve/main/loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors?download=true",
        dir: "../app/models/loras"
      }
    }
  ]
}
