"""Shared per-exam config and data directory resolver for all pipeline steps."""
import json
import os


def resolve_data_dir(repo_root, config):
    """Resolve the active exam's data directory from config, falling back to data/."""
    explicit = config.get("data_dir")
    if explicit:
        return explicit if os.path.isabs(explicit) else os.path.join(repo_root, explicit)
    course = config.get("course_name")
    exam_id = config.get("exam_id")
    if course and exam_id is not None:
        candidate = os.path.join(repo_root, f"data_{course}_exam{exam_id}")
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(repo_root, "data")


def load_active_config(repo_root, default_config=None):
    """Load root config.json merged with defaults and return (config, data_dir)."""
    cfg = dict(default_config or {})
    cfg_path = os.path.join(repo_root, "config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg, resolve_data_dir(repo_root, cfg)


def select_exam_config(repo_root, default_config=None):
    """Interactive 1-exam-at-a-time selector across data_*/config.json and root config.json."""
    candidates = []
    for entry in sorted(os.listdir(repo_root)):
        full = os.path.join(repo_root, entry)
        cfg_file = os.path.join(full, "config.json")
        if os.path.isdir(full) and entry.startswith("data") and os.path.isfile(cfg_file):
            with open(cfg_file, "r", encoding="utf-8") as f:
                c = json.load(f)
            c.setdefault("data_dir", entry)
            candidates.append((entry, c))

    if len(candidates) > 1:
        print("Select exam dataset (one exam at a time):")
        for idx, (label, c) in enumerate(candidates, 1):
            print(f"  {idx}. {label} (exam_id={c.get('exam_id')}, url={c.get('zesje_base_url')})")
        choice = input(f"Choice [1-{len(candidates)}, Enter=1]: ").strip()
        picked = candidates[int(choice) - 1][1] if choice.isdigit() and 1 <= int(choice) <= len(candidates) else candidates[0][1]
        cfg = dict(default_config or {})
        cfg.update(picked)
        return cfg, resolve_data_dir(repo_root, cfg)

    if len(candidates) == 1:
        cfg = dict(default_config or {})
        cfg.update(candidates[0][1])
        return cfg, resolve_data_dir(repo_root, cfg)

    return load_active_config(repo_root, default_config)
