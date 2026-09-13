// Spatial & Physics — collision / gravity / object contact (pruned).
// ~148 MB. Studio Ayarlar → LoRA listesinde isme tıklayınca da iner.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/Jojocodex/minimax-h3-spatial-physics-lora/resolve/main/wushu_spatial_physics_clean_3000_pruned.safetensors?download=true",
        dir: "../app/models/loras"
      }
    }
  ]
}
