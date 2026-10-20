"""Explicit MP4 enhancement using the learned H3 3D latent upscaler.

No trajectory capture, diffusion resampling, text encoder or generation hooks.
"""
import json
import subprocess
from pathlib import Path
from .music import _ffprobe


def probe(path):
    result = subprocess.run([_ffprobe(), '-v', 'error',
        '-show_entries', 'stream=codec_type,width,height,nb_frames,avg_frame_rate,duration:format=duration',
        '-of', 'json', str(path)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Video bilgisi okunamadı: ' + result.stderr[-300:])
    data = json.loads(result.stdout)
    stream = next(s for s in data['streams'] if s.get('codec_type') == 'video')
    numerator, denominator = map(float, stream['avg_frame_rate'].split('/'))
    fps = numerator / denominator
    duration = float(stream.get('duration') or data['format']['duration'])
    count = stream.get('nb_frames')
    if not count or count == 'N/A':
        result = subprocess.run([_ffprobe(), '-v', 'error', '-count_frames', '-select_streams', 'v:0',
            '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', str(path)], capture_output=True, text=True)
        count = result.stdout.strip()
    return dict(width=int(stream['width']), height=int(stream['height']),
                frames=int(count), fps=fps, duration=duration,
                audio=any(s.get('codec_type') == 'audio' for s in data['streams']))


def verify_output(path, source, width, height):
    actual = probe(path)
    if (actual['width'], actual['height']) != (width, height):
        raise ValueError('Kalite artırma hedef çözünürlüğüne ulaşamadı')
    if actual['frames'] != source['frames'] or abs(actual['fps'] - source['fps']) > 0.001:
        raise ValueError('Kalite artırma sırasında kare sayısı veya kare hızı değişti')
    if actual['audio'] != source['audio']:
        raise ValueError('Kalite artırma sırasında kaynak ses durumu değişti')


def validate_memory(meta, width, height):
    import psutil
    # Comfy image tensors are float32 RGB. Include source, target and output
    # copies, leaving memory for the VAE/runtime. Tiled VAE only bounds VRAM.
    required = meta['frames'] * 12 * (meta['width'] * meta['height'] + 2 * width * height)
    if required > psutil.virtual_memory().total * 0.65:
        raise ValueError('Bu uzunluk ve çözünürlük RAM sınırını aşıyor. Daha kısa klip veya daha düşük hedef çözünürlük seç.')


def build(job, uploaded_video):
    vae = job['h3_models']['vae']
    return {
        'load': {'class_type':'LoadVideo', 'inputs':{'file':uploaded_video}},
        'parts': {'class_type':'GetVideoComponents', 'inputs':{'video':['load',0]}},
        'vae': {'class_type':'VAELoader', 'inputs':{'vae_name':vae}},
        'encode': {'class_type':'VAEEncodeTiled', 'inputs':{'pixels':['parts',0], 'vae':['vae',0],
            'tile_size':512, 'overlap':64, 'temporal_size':32, 'temporal_overlap':8}},
        'upscale': {'class_type':'MinimaxH3LatentUpscaler3D', 'inputs':{
            'latent':['encode',0], 'model_name':'minimax_h3_latent_upscaler_3d_bf16.safetensors',
            'mode':'target dimensions', 'mode.width':job['width'], 'mode.height':job['height'],
            'align':32, 'keep_proportion':False, 'device':'cuda', 'precision':'bf16', 'offload_after_upscale':True}},
        'decode': {'class_type':'VAEDecodeTiled', 'inputs':{'samples':['upscale',0], 'vae':['vae',0],
            'tile_size':512, 'overlap':64, 'temporal_size':32, 'temporal_overlap':8}},
        'trim': {'class_type':'ImageFromBatch', 'inputs':{'image':['decode',0], 'batch_index':0,
            'length':job['refine_source_meta']['frames']}},
        'video': {'class_type':'CreateVideo', 'inputs':{'images':['trim',0], 'fps':['parts',2], 'audio':['parts',1]}},
        '92': {'class_type':'SaveVideo', 'inputs':{'video':['video',0],
            'filename_prefix':'video/H3_Studio/' + job['id'][:8], 'format':'mp4', 'codec':'h264'}},
    }
