// H3 Realism People — T2V / I2V / Ref.
// ~125 MB. Studio Ayarlar → LoRA listesinde isme tıklayınca da iner.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/fal/MiniMax-H3-Realism-People-LoRA/resolve/main/h3-realism-people-t2v-i2v-r2v.safetensors?download=true",
        dir: "../app/models/loras"
      }
    }
  ]
}
