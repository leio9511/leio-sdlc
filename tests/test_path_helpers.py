import os


def engine_local_config_path(resolve_root):
    return os.path.join(resolve_root(), "config", "engines.local.json")


def exists_except_engine_local(resolve_root):
    local_engine_path = engine_local_config_path(resolve_root)

    def _side_effect(path):
        return path != local_engine_path

    return _side_effect


def static_root(root_path):
    def _resolve_root():
        return root_path

    return _resolve_root
