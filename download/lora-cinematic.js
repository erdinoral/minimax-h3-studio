// Cinematic Look (tensor-fix) — trigger DY.
// HF mirror keeps a Chinese filename; pin the ASCII dest with path (PINOKIO.md fs.download).
// ~148 MB. Studio Ayarlar → LoRA listesinde isme tıklayınca da iner.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/Alex995647/loras-minimax-h3/resolve/main/minimax-h3-cinematic-look-no-tensor-errors/Minimax%20H3%E7%9C%9F%E5%AE%9E%E7%94%B5%E5%BD%B1%E8%B4%A8%E6%84%9FV0.1%EF%BC%88%E8%A7%A3%E5%86%B3%E5%BC%A0%E9%87%8F%E6%8A%A5%E9%94%99%EF%BC%89.safetensors?download=true",
        path: "../app/models/loras/minimax_h3_cinematic_look_v01.safetensors"
      }
    }
  ]
}
