"""Reference-driven H3 videos, selected views and a separate contact sheet."""

REQUIRED_NODES = ("H3LookSheetsSelectFrames", "H3LookSheetsDatasheetSettings")


def view_count(kind):
    return 5 if kind in ("character", "creature") else 4


def prompt(kind, notes="", style_line="", outfit=False):
    identity = {
        "character": "the same person's face, hairstyle, body proportions and clothing",
        "creature": "the same creature's anatomy, markings and proportions",
        "vehicle": "the same vehicle's geometry, color, wheels and details",
        "location": "the same location's architecture, materials and spatial layout",
    }[kind]
    views = ("front full body, left profile, right profile, back full body, face close-up"
             if kind in ("character", "creature") else
             "front, rear, right side, left side" if kind == "vehicle" else
             "wide establishing view, left viewpoint, right viewpoint, reverse viewpoint")
    text = f"<Picture 1> is the source reference. Preserve {identity}. "
    if outfit:
        text += "<Picture 2> defines clothing only; ignore its wearer and keep the identity from <Picture 1>. "
    text += (f"A reference capture sequence with these distinct views in order: {views}. "
             "Hold each view briefly, keeping the subject fully visible. "
             "Consistent lighting and appearance. No text, captions or collage in the video. ")
    if kind != "location":
        text += "Neutral studio background. "
    return text + style_line + (" Additional details: " + notes if notes else "")


def add_nodes(graph, kind, prefix):
    """Node 10 is the decoded video IMAGE batch in both Studio H3 graphs."""
    if graph.get("10", {}).get("class_type") != "VAEDecode":
        raise ValueError("Look Sheets requires the H3 decoded frame batch")
    count = view_count(kind)
    graph["look_frames"] = {"class_type": REQUIRED_NODES[0], "inputs": {
        "images": ["10", 0], "saved_frame_count": count, "tier1_shots_clusters": count}}
    graph["look_sheet"] = {"class_type": REQUIRED_NODES[1], "inputs": {
        "images": ["look_frames", 0], "columns": 2, "columns_width": 384, "padding": 8}}
    graph["look_save_views"] = {"class_type": "SaveImage", "inputs": {
        "images": ["look_frames", 0], "filename_prefix": prefix + "_views"}}
    graph["look_save_sheet"] = {"class_type": "SaveImage", "inputs": {
        "images": ["look_sheet", 0], "filename_prefix": prefix + "_sheet"}}
    return graph
