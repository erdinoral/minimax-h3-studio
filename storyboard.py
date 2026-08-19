import os
import sys

# Define the prompt
prompt = 'Character: John, Scene: Kitchen, Tag: Happy'

# Use the nodes_tag_detection.py file to detect the tags
tag_file = os.path.join('comfy_extras', 'nodes_tag_detection.py')
tag_cmd = f'python {tag_file} "{prompt}"'
tags = os.popen(tag_cmd).read().strip().split(', ')

# Use the nodes_text.py file to generate a scene description
text_file = os.path.join('comfy_extras', 'nodes_text.py')
text_cmd = f'python {text_file} "{prompt}"'
scene_description = os.popen(text_cmd).read().strip()

print(f"Tags: {tags}")
print(f"Scene Description: {scene_description}")
