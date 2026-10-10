# Model storage

Settings includes a Model storage section with installed weight filenames, folder groups, sizes and individual Delete buttons. LoRAs, optional base models and abandoned partial weight downloads can be removed. Deletion requires confirmation naming the file and its size.

Active H3 model files, core installation defaults and files required by queued jobs are protected. Switch to another installed engine before deleting an optional engine that is selected. Deletion is refused while generation or an in-app download is active; ComfyUI's queue is checked as well. Failure to read that queue blocks deletion. A file locked by the operating system remains untouched and reports an error.

Only individual weight files inside the configured model folders can be deleted. Directories, arbitrary paths, JSON settings and file symlinks are not accepted. Films, character cards and generated clips are retained. A card whose LoRA was deleted needs that adapter downloaded again or another adapter selected.

After deletion, model and LoRA lists refresh. Catalog entries remain available for redownload. Listed sizes are logical file sizes; shared hardlinks may keep disk blocks allocated until the final link is deleted. New engine integrations should add their storage folders and protect their selected/shared components through the same manager.
