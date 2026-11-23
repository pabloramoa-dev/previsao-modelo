"""Normaliza os cadastros editoriais baixados dos seis repositórios."""
import ast
import json
import sys
from pathlib import Path

import yaml


SOURCES = {
    "previsaomg": ("previsaomg", "config/locais.yaml"),
    "previsaopr": ("previsao-pr", "config/locais.yaml"),
    "previsaors": ("previsao-rs", "config/locais.yaml"),
    "otemposp": ("o-tempo-sp", "config/locais_sp.yaml"),
    "previsaobsb": ("previsao-bsb", "boletim.py"),
    "previsaovr": ("previsaovr-instagram", "bot.py"),
}


def assignments(source):
    return {
        node.targets[0].id: node.value
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }


def normalize(profile, source):
    if profile == "previsaobsb":
        groups = ast.literal_eval(assignments(source)["REGIOES"])
        return [[name, lat, lon, name.split("/")] for group in groups.values()
                for name, lat, lon in group]
    if profile == "previsaovr":
        values = assignments(source)
        cities = next(ast.literal_eval(node) for node in values.values()
                      if isinstance(node, ast.List) and node.elts
                      and isinstance(node.elts[0], ast.Dict)
                      and any(isinstance(key, ast.Constant) and key.value == "lat"
                              for key in node.elts[0].keys))
        return [[row["nome"].removesuffix(" - RJ"), row["lat"], row["lon"],
                 [row["hashtag"]]] for row in [*cities, ast.literal_eval(values["ANGRA"])]]
    return [[row["name"], row["latitude"], row["longitude"], row.get("aliases", [])]
            for row in yaml.safe_load(source)["locations"]]


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    catalog = {profile: normalize(profile, (directory / repo / path).read_text())
               for profile, (repo, path) in SOURCES.items()}
    print(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
