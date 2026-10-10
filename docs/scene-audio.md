# Scene audio and appearance

In Scene, open **Audio · single clip**, select a recording, optionally set its start/end times, then **Prepare audio**. Preview the prepared segment before pressing the single-clip **Generate** button. Preparing audio does not start video generation. Use **Remove** to detach it from subsequent requests.

- **Audio reference** conditions H3 Ref2VA's generated voice and sound. Write the requested speech/action in the prompt. Reference conditioning does not guarantee verbatim reproduction, lyric timing or lip sync. This route uses the Ref2VA model and compatible LoRAs.
- **Use original audio in result** replaces generated sound with the prepared recording, beginning at video time zero. The recording is cut to video length or padded with silence when shorter. This is soundtrack attachment, not automatic lip sync.

Audio attachments currently apply to single-clip Generate, not Scene's batch list. For a complete song and a timed scene plan, use Director's music workflow. Automatic lyric timing is a draft and should be checked before production.

Settings → **Appearance** offers Orange, Blue and Graphite. The choice is saved in this browser and survives a reload. Older Warm selections now use Orange.

Colors are on the left; styles are on the right. Modern, Old School and Studio change typography, corners and controls independently of the color palette. The style choice is also saved in this browser. These are initial presets that can be expanded later.

The top-bar **Guide** explains Scene audio, character cards/LoRAs, AI Director, New video vs Continue, lyric timing and final assembly in English and Turkish.
