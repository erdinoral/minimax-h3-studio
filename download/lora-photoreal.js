// Photoreal still LoRA — character/location sheets only (not the video queue).
// Trigger ph0t0r34l. ~148 MB. Studio Ayarlar → LoRA listesinde isme tıklayınca da iner.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/Alex995647/loras-minimax-h3/resolve/main/minimax-h3-photorealistic-image-generator-lora-workflow/h3_photoreal_ph0t0r34l_1024-step00003780.safetensors?download=true",
        dir: "../app/models/loras"
      }
    }
  ]
}
