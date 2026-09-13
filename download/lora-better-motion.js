// Better Motion — H3 movement quality LoRA.
// ~296 MB. Studio Ayarlar → LoRA listesinde isme tıklayınca da iner.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/Alex995647/loras-minimax-h3/resolve/main/better-motion-ltx-minimax-h3/mvmt_h3_lora_v1_500.safetensors?download=true",
        dir: "../app/models/loras"
      }
    }
  ]
}
