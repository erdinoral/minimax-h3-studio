// PinkFluffyBunny character LoRA (pruned FL2VA rank128).
// ~2.3 GB. Studio Ayarlar → LoRA listesinde isme tıklayınca da iner.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/SexGod1979/PinkFluffyBunny-MiniMax-H3/resolve/main/PinkFluffyBunny-pruned-fl2va-v1-rank128.safetensors?download=true",
        dir: "../app/models/loras"
      }
    }
  ]
}
