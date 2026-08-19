import os
import sys

# Define the directory structure
root_dir = 'd:/pinokio/api/minimax-h3-pinokio.git'
comfy_extras_dir = os.path.join(root_dir, 'comfy_extras')

# Define the prompt
prompt = 'Create a film about a character who discovers a hidden world.'

# Generate the first video
video_file = os.path.join(comfy_extras_dir, 'nodes_video.py')
video_cmd = f'python {video_file} --prompt "{prompt}"'
os.system(video_cmd)

# Continue the video
video_contine_file = os.path.join(comfy_extras_dir, 'nodes_video_contine.py')
video_contine_cmd = f'python {video_contine_file} --prompt "{prompt}" --video_file "output.mp4"'
os.system(video_contine_cmd)

# Detect new tags
tag_detection_file = os.path.join(comfy_extras_dir, 'nodes_tag_detection.py')
tag_detection_cmd = f'python {tag_detection_file} --video_file "output.mp4"'
os.system(tag_detection_cmd)

# Update the prompt and continue the video generation process
new_prompt = 'The character explores the hidden world and discovers a new species.'
video_cmd = f'python {video_file} --prompt "{new_prompt}"'
os.system(video_cmd)
