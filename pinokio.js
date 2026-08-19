module.exports = {
  version: "8.0",
  title: "MiniMax H3 Studio",
  description: "1-click MiniMax H3 video in ComfyUI plus H3 Studio: Director, Plan, cinema studio, TR/EN. NVIDIA GPU.",
  icon: "icon.png",
  menu: async (kernel, info) => {
    let installed = info.exists("app/env")
    let running = {
      install: info.running("install.js"),
      start: info.running("start.js"),
      update: info.running("update.js"),
      reset: info.running("reset.js")
    }
    let downloading = [
      "download/shared.js",
      "download/fl2va.js",
      "download/ref2va.js",
      "download/lora.js",
      "download/lora-erosmax.js",
      "download/lora-turbo6.js",
      "download/lora-turbov4.js",
      "download/lora-realism.js",
      "download/lora-pinkfluffybunny.js",
      "download/multishot.js",
      "download/text_encoder_int8.js",
      "remove/fl2va.js",
      "remove/ref2va.js",
      "workflows.js"
    ]
    let is_downloading = null
    for (let item of downloading) {
      if (info.running(item) === true) {
        is_downloading = item
        break;
      }
    }

    // Which weights are actually on disk right now -- drives the menu below.
    let has = {
      fl2va: info.exists("app/models/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors"),
      ref2va: info.exists("app/models/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors"),
      encoder_int8: info.exists("app/models/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors"),
      lora: info.exists("app/models/loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors"),
      loraErosmax: info.exists("app/models/loras/minimax_h3_fl2v_turbo_4step_v1.0_768p_10ErosMax_beta1_pruned_compat_v001_T8.safetensors"),
      loraTurbo6: info.exists("app/models/loras/minimax_h3_turbo_6step_ema_fl2va_pruned.safetensors"),
      loraTurboV4: info.exists("app/models/loras/minimax_h3_turbo_v4_step600_ema.safetensors"),
      loraRealism: info.exists("app/models/loras/h3-realism-people-t2v-i2v-r2v.safetensors"),
      loraPink: info.exists("app/models/loras/PinkFluffyBunny-pruned-fl2va-v1-rank128.safetensors") || info.exists("app/models/loras/PinkFluffyBunny-pruned-v1-rank128.safetensors"),
      multishot: info.exists("app/custom_nodes/ComfyUI-H3-Multishot")
    }

    if (running.install) {
      return [{
        default: true,
        icon: "fa-solid fa-plug",
        text: "Installing",
        href: "install.js",
      }]
    } else if (installed) {
      if (running.start) {
        let local = info.local("start.js")
        if (local && local.url) {
          // Studio only in the menu — Comfy is a headless backend for this session.
          // Stopping start.js (Pinokio Stop) tears down Comfy + Studio together.
          return [{
            default: true,
            icon: "fa-solid fa-clapperboard",
            text: "Open H3 Studio",
            href: local.url,
          }, {
            icon: "fa-solid fa-terminal",
            text: "Terminal / Stop",
            href: "start.js",
          }]
        } else {
          return [{
            default: true,
            icon: "fa-solid fa-terminal",
            text: "Terminal",
            href: "start.js",
          }]
        }
      } else if (is_downloading) {
        return [{
          default: true,
          icon: "fa-solid fa-terminal",
          text: "Downloading",
          href: is_downloading,
        }]
      } else if (running.update) {
        return [{
          default: true,
          icon: "fa-solid fa-terminal",
          text: "Updating",
          href: "update.js",
        }]
      } else if (running.reset) {
        return [{
          default: true,
          icon: "fa-solid fa-terminal",
          text: "Resetting",
          href: "reset.js",
        }]
      }

      // Only offer what is missing.
      let downloads = []
      if (!has.fl2va) {
        downloads.push({
          icon: "fa-solid fa-download",
          text: "FL2VA — text / first / last frame (21.0GB)",
          href: "download/fl2va.js",
          mode: "refresh"
        })
      }
      if (!has.ref2va) {
        downloads.push({
          icon: "fa-solid fa-download",
          text: "Ref2VA — omni-reference (21.0GB)",
          href: "download/ref2va.js",
          mode: "refresh"
        })
      }
      if (!has.encoder_int8) {
        downloads.push({
          icon: "fa-solid fa-download",
          text: "INT8 text encoder — optional upgrade (27.1GB)",
          href: "download/text_encoder_int8.js",
          mode: "refresh"
        })
      }
      if (!has.lora) {
        downloads.push({
          icon: "fa-solid fa-download",
          text: "LightX2V Turbo LoRA — 4-step FL2VA (~1.8GB)",
          href: "download/lora.js",
          mode: "refresh"
        })
      }
      if (!has.loraErosmax) {
        downloads.push({
          icon: "fa-solid fa-download",
          text: "ErosMax Turbo LoRA — 4-step FL2VA (~1.8GB)",
          href: "download/lora-erosmax.js",
          mode: "refresh"
        })
      }
      if (!has.loraTurbo6) {
        downloads.push({
          icon: "fa-solid fa-download",
          text: "H3 Turbo 6-step EMA LoRA (~0.8GB)",
          href: "download/lora-turbo6.js",
          mode: "refresh"
        })
      }
      if (!has.loraTurboV4) {
        downloads.push({
          icon: "fa-solid fa-download",
          text: "H3 Turbo v4 EMA LoRA (~0.7GB)",
          href: "download/lora-turbov4.js",
          mode: "refresh"
        })
      }
      if (!has.loraRealism) {
        downloads.push({
          icon: "fa-solid fa-download",
          text: "H3 Realism People LoRA (~125MB)",
          href: "download/lora-realism.js",
          mode: "refresh"
        })
      }
      if (!has.loraPink) {
        downloads.push({
          icon: "fa-solid fa-download",
          text: "PinkFluffyBunny character LoRA (~2.3GB)",
          href: "download/lora-pinkfluffybunny.js",
          mode: "refresh"
        })
      }
      if (!has.multishot) {
        downloads.push({
          icon: "fa-solid fa-link",
          text: "H3 Multishot (Seamless Chain) nodes",
          href: "download/multishot.js",
          mode: "refresh"
        })
      }
      downloads.push({
        icon: "fa-solid fa-rotate",
        text: "Re-download shared encoder + VAEs (21.5GB)",
        href: "download/shared.js",
        mode: "refresh"
      })

      // Each variant is independently removable -- 21GB back per click.
      let removals = []
      if (has.fl2va) {
        removals.push({
          icon: "fa-regular fa-trash-can",
          text: "Delete FL2VA weights (frees 21.0GB)",
          href: "remove/fl2va.js",
          mode: "refresh",
          confirm: "Delete the FL2VA transformer? You can re-download it later."
        })
      }
      if (has.ref2va) {
        removals.push({
          icon: "fa-regular fa-trash-can",
          text: "Delete Ref2VA weights (frees 21.0GB)",
          href: "remove/ref2va.js",
          mode: "refresh",
          confirm: "Delete the Ref2VA transformer? You can re-download it later."
        })
      }

      let menu = [{
        default: true,
        icon: "fa-solid fa-power-off",
        text: "Start",
        href: "start.js",
      }, {
        icon: "fa-solid fa-download",
        text: "Download Models",
        menu: downloads
      }]

      if (removals.length > 0) {
        menu.push({
          icon: "fa-solid fa-hard-drive",
          text: "Manage Disk Space",
          menu: removals
        })
      }

      return menu.concat([{
        icon: "fa-solid fa-diagram-project",
        text: "Reinstall Workflows",
        href: "workflows.js",
        mode: "refresh"
      }, {
        icon: "fa-solid fa-plug",
        text: "Update",
        href: "update.js",
      }, {
        icon: "fa-solid fa-plug",
        text: "Install",
        href: "install.js",
      }, {
        icon: "fa-regular fa-circle-xmark",
        text: "Reset",
        href: "reset.js",
        confirm: "Reset reinstalls ComfyUI. Your downloaded H3 weights are kept."
      }])
    } else {
      return [{
        default: true,
        icon: "fa-solid fa-plug",
        text: "Install",
        href: "install.js",
      }]
    }
  }
}
