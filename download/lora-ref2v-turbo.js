// Ref2V Turbo 8-step — Ref/yüz graph only (FL2VA turbos skip Ref today).
// ~933 MB. Studio Ayarlar → LoRA listesinde isme tıklayınca da iner.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/Alex995647/loras-minimax-h3/resolve/main/ref2v-turbo-8-step-v1-0-768p-rank-64/minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_resized_avg_rank_64_bf16.safetensors?download=true",
        dir: "../app/models/loras"
      }
    }
  ]
}
