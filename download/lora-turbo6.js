// H3 Turbo 6-step EMA (FL2VA pruned).
// ~0.8 GB. Studio Ayarlar → LoRA listesinde isme tıklayınca da iner.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/SanDiegoDude/H3-Turbo-6-Step-LoRA-Comfy/resolve/main/minimax_h3_turbo_6step_ema_fl2va_pruned.safetensors?download=true",
        dir: "../app/models/loras"
      }
    }
  ]
}
