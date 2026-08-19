// ErosMax Turbo LoRA — FL2VA 4-step (T8 compat).
// ~1.8 GB. Studio Ayarlar → LoRA listesinde isme tıklayınca da iner.
module.exports = {
  run: [
    {
      method: "fs.download",
      params: {
        uri: "https://huggingface.co/t8star/minimax_h3_turbo_4step_10ErosMax_test4_pruned_curveproj1025_T8/resolve/main/minimax_h3_fl2v_turbo_4step_v1.0_768p_10ErosMax_beta1_pruned_compat_v001_T8.safetensors?download=true",
        dir: "../app/models/loras"
      }
    }
  ]
}
