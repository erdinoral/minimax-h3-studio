"""Copy optional creator workflows with unique names, adapting installed weights."""
import shutil
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"studio"))
from lib.comfy import build_ref2va_prompt
APP=ROOT/"app"
DEST=APP/"user"/"default"/"workflows"
REPLACEMENTS={
    "minimax_h3_ref2va_pruned_int8_convrot.safetensors":"diffusion_models",
    "minimax_h3_fl2va_pruned_int8_convrot.safetensors":"diffusion_models",
    "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors":"text_encoders",
    "minimax_h3_video_vae_fp16.safetensors":"vae",
    "minimax_h3_audio_vae_fp32.safetensors":"vae",
}


def adapt(data):
    for node in data.get("nodes",[]):
        node_type=node.get("type")
        widgets=node.get("widgets_values")
        if not isinstance(widgets,list) or not widgets:continue
        if node_type=="UNETLoader":
            widgets[0]="minimax_h3_ref2va_pruned_int8_convrot.safetensors" if "ref2" in str(widgets[0]).lower() else "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
        elif node_type=="CLIPLoader":widgets[0]="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
        elif node_type=="VAELoader":widgets[0]="minimax_h3_audio_vae_fp32.safetensors" if "audio" in str(widgets[0]).lower() else "minimax_h3_video_vae_fp16.safetensors"
        elif node_type in ("PatchSageAttentionKJ", "PathchSageAttentionKJ"):widgets[0]="disabled"
        elif node_type in ("LoraLoader","LoraLoaderModelOnly"):
            # Never apply an FL2VA-only acceleration adapter to a Ref2VA look sheet.
            if not (APP/"models"/"loras"/str(widgets[0])).is_file():node["mode"]=4
    return data


def patch_hyperflow_python310():
    # Python 3.10 is used by the launcher; hashlib.file_digest arrived in 3.11.
    target = APP / "custom_nodes" / "ComfyUI-HyperFlow-H3" / "hyperflow_h3" / "curve.py"
    if not target.is_file():
        return
    source = target.read_text(encoding="utf-8")
    call = 'hashlib.file_digest(handle, "sha256")'
    if call not in source:
        return
    helper = '''

def _studio_file_digest(handle, algorithm):
    digest = hashlib.new(algorithm)
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest
'''
    source = source.replace(call, '_studio_file_digest(handle, "sha256")')
    source += helper
    target.write_text(source, encoding="utf-8")


def main():
    patch_hyperflow_python310()
    DEST.mkdir(parents=True,exist_ok=True)
    source = ROOT / "studio" / "comfy_nodes" / "h3_studio_enhancements"
    destination = APP / "custom_nodes" / "h3_studio_enhancements"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "__init__.py", destination / "__init__.py")
    # Minimal API workflow: core H3 + the two installed sheet nodes only.
    # Person/outfit filenames are deliberately placeholders for the user's uploads.
    graph=build_ref2va_prompt(text="<Picture 1> defines the person's identity, face and hairstyle. <Picture 2> defines clothing only; ignore its wearer. Show the same adult person wearing this outfit on a neutral studio background. Sequential views: front full body, left profile, right profile, back full body, front three-quarter, face close-up. Keep face, hair and clothing consistent. No text, no collage in the video.",ref_image_names=["person.png","outfit.png"],width=864,height=480,length=121,steps=20,sage_attention="disabled",silent_audio=True)
    graph["look_frames"]={"class_type":"H3LookSheetsSelectFrames","inputs":{"images":["10",0],"saved_frame_count":6,"tier1_shots_clusters":6}}
    graph["look_sheet"]={"class_type":"H3LookSheetsDatasheetSettings","inputs":{"images":["look_frames",0],"columns":3,"columns_width":384,"padding":8}}
    graph["save_sheet"]={"class_type":"SaveImage","inputs":{"images":["look_sheet",0],"filename_prefix":"H3_Studio_Look_Sheet"}}
    target=DEST/"H3 Studio Look Sheets - Basic API.json"
    if not target.exists():target.write_text(json.dumps(graph,indent=2),encoding="utf-8")
    for pack,folder,prefix in [("Herrgotts-H3-Infinite-Continuation-Suite","examples","H3 Studio Native AV")]:
        source=APP/"custom_nodes"/pack/folder
        paths=list(source.rglob("*.json"))
        if not paths:raise RuntimeError("No workflows found for "+pack)
        for path in paths:
            data=json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data,dict) or "nodes" not in data:continue
            target=DEST/(prefix+" - "+path.name)
            if not target.exists():target.write_text(json.dumps(adapt(data),ensure_ascii=False,indent=2),encoding="utf-8")
            print("Workflow:",target.name,flush=True)
    print("Restart ComfyUI to load the optional nodes. Existing workflows were retained.",flush=True)


if __name__ == "__main__":main()
