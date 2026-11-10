// MiniMax-H3-Image -- Studio's only still image model (first frames, reference sheets,
// drawings). It reuses the video text encoder.
//
// Pruned INT8 ConvRot transformer (21.0 GB) + image VAE (1.2 GB).
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/main/diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors?download=true",
        dir: "../app/models/diffusion_models"
      }
    },
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/main/vae/minimax_h3_image_vae_fp16.safetensors?download=true",
        dir: "../app/models/vae"
      }
    }
  ]
}
