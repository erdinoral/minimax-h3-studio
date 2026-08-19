// H3 Turbo v4 EMA (step600 is the training checkpoint, not 4 inference steps).
// ~0.7 GB. Studio Ayarlar → LoRA listesinde isme tıklayınca da iner.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora/resolve/main/minimax_h3_turbo_v4_step600_ema.safetensors?download=true",
        dir: "../app/models/loras"
      }
    }
  ]
}
