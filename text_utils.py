#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2025 smithaulait
# <https://github.com/smithaulait>

import argparse
import json
import pathlib
import os
import time
import urllib.request

PWD = pathlib.Path(__file__).resolve().parents[0]
BASEURL = "https://raw.githubusercontent.com/HushBugger/hushbugger.github.io/refs/heads/master/deltarune/text"
CHAPTERS = ["1", "2", "3", "4"]
LANGS = ["en", "ja"]
BASE_LANG = "en"
L10N_LANG = "vi"
L10N_CHAPTER = "1"

def echo(strg: str):
    print(f"--> {strg}")


def mkdir(dir):
    pathlib.Path.mkdir(dir, parents=True, exist_ok=True)


def mkdict():
    return {n: {} for n in CHAPTERS}


def dict2file(in_dict, out_file):
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(in_dict, f, indent=2, ensure_ascii=False)


def file2dict(in_file):
    with open(in_file, "r", encoding="utf-8") as f:
        return json.load(f)


def rmfile(file: pathlib.Path):
    if file.exists(): file.unlink()


def smartsort(k_and_v):
    pieces = k_and_v[0].split("_")
    for i, piece in enumerate(pieces):
        if piece.isdigit():
            # Natsort of integers (particularly line numbers)
            pieces[i] = piece.rjust(16, "0")
    return pieces


def split_dump():
    """Process existing json dump and split strings based on position in code"""
    echo("loading raw dumps")
    raw_lang = file2dict("lang.json")
    raw_sourcemap = file2dict("sourcemap.json")
    linedups_map = mkdict()
    new_sourcemap = mkdict()

    for chapter in CHAPTERS:
        ch_pwd = PWD / f"chapter{chapter}"
        echo(f"generate: ch{chapter} sourcemap")
        mkdir(ch_pwd)
        # Track strings whose function was called in the same line in the same code
        # "<code object>:<line position>": <count>, ...
        ch_dup_map = linedups_map[chapter]
        for fileno in raw_sourcemap[chapter].values():
            if fileno not in ch_dup_map:
                ch_dup_map[fileno] = 1
            else:
                ch_dup_map[fileno] += 1
        # Rebuild strings map. This is required to preserve strings order 
        # "<code object>": {
        #     "<line position>": "<key>", ...
        # }
        ch_sourcemap = new_sourcemap[chapter]
        dupecount = 0
        for k, v in raw_sourcemap[chapter].items():
            filename, lineno = v.split(":")
            try:
                ch_objfile = ch_sourcemap[filename]
            except KeyError:
                ch_objfile = ch_sourcemap[filename] = {}
            # sometimes Mr. Toby loves single-line code
            # in this case, we can't guarantee correct sentences order
            if linedups_map[chapter][v] > 1:
                dupecount += 1
                lineno += f"_{dupecount}"
            else:
                dupecount = 0
            ch_sourcemap[filename][lineno] = k
        for filename in ch_sourcemap:
            ch_sourcemap[filename] = dict(sorted(ch_sourcemap[filename].items(), key=smartsort))
        ch_sourcemap_file = ch_pwd / "sourcemap.json"
        dict2file(ch_sourcemap, ch_sourcemap_file)
        # Split strings with the new sourcemap
        for lang in LANGS:
            echo(f"split: ch{chapter} ({lang}) strings")
            obj_dir = ch_pwd / lang / "obj"
            lang_strings = {}
            mkdir(obj_dir)
            for filename in new_sourcemap[chapter]:
                obj_file = obj_dir / str(filename.removesuffix(".gml") + ".json")
                obj_strings = {}
                for k, v in new_sourcemap[chapter][filename].items():
                    try:
                        str_value = raw_lang[chapter][lang][v]
                    except KeyError:
                        print(f"not found: {v}")
                        continue
                    lang_strings[v] = obj_strings[v] = str_value
                if obj_strings == {}:
                    rmfile(obj_file)
                    continue
                dict2file(obj_strings, obj_file)
            # orphan strings basically exists in original dump but not
            # referenced in the final code. 90% sure they are unused
            lang_orphan = {}
            lang_orphan_file = obj_dir / "orphan.json"
            for k in raw_lang[chapter][lang]:
                if k in lang_strings:
                    continue
                if k == "date":
                    continue
                if f"{k}_DUP" in lang_strings:
                    print(f"{k} is not mapped, but appears to be a duplicate")
                lang_orphan[k] = raw_lang[chapter][lang][k]
            if lang_orphan != {}:
                dict2file(lang_orphan, lang_orphan_file)
            else:
                rmfile(lang_orphan_file)

            stats_u = len(lang_strings)
            stats_o = len(lang_orphan)
            stats_t = stats_u + stats_o
            echo(f"total {stats_t}, unique {stats_u}, orphan {stats_o}")


def compile_lang(lang, chapter):
    """Assemble json for continuous localization"""
    DATE = str(int(time.time() * 1000))
    ch_pwd = PWD / f"chapter{chapter}"
    baselang_objs = ch_pwd / BASE_LANG / "obj"
    new_lang_objs = ch_pwd / lang / "obj"
    new_lang_dict = {}
    new_lang_dict["date"] = DATE
    count_translated = 0
    echo(f"assemble: ch{chapter} ({lang})")
    mkdir(new_lang_objs)
    for obj in baselang_objs.iterdir():
        baselang_obj = file2dict(obj)
        try:
            newlang_obj = file2dict(str(new_lang_objs / obj.name))
        except FileNotFoundError:
            newlang_obj = {}
        for k in baselang_obj:
            if k not in newlang_obj:
                continue
            count_translated += 1
            baselang_obj[k] = newlang_obj[k]
        new_lang_dict |= baselang_obj
    count_all = len(new_lang_dict) - 1
    l10n_progress = int((count_translated / count_all) * 100)
    echo(f"Translated {count_translated}/{count_all} ({l10n_progress}%)")
    try:
        new_lang_file = pathlib.Path(os.environ["DELTARUNE_HOME"]) / f"chapter{chapter}_windows" / "lang" / "lang_en.json"
    except KeyError:
        new_lang_file = ch_pwd / f"lang_{lang}.json"
    echo(str(new_lang_file))
    dict2file(new_lang_dict, new_lang_file)


def fetch_dump(files: list):
    """Update the text dump"""
    for filename in files:
        echo(f"fetch: {filename}")
        request = urllib.request.Request(f"{BASEURL}/{filename}")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(urllib.request.urlopen(request, timeout=10).read().decode())


def init_lang(lang):
    """Populate new language with empty json files"""
    for chapter in CHAPTERS:
        ch_pwd = PWD / f"chapter{chapter}"
        baselang_objs = ch_pwd / BASE_LANG / "obj"
        new_lang_objs = ch_pwd / L10N_LANG / "obj"
        mkdir(new_lang_objs)
        ls_base = [i.name for i in baselang_objs.iterdir()]
        ls_new = [i.name for i in new_lang_objs.iterdir()]
        for obj in ls_base:
            new_lang_obj = new_lang_objs / obj
            if not new_lang_obj.exists():
                dict2file({}, new_lang_obj)
        diff = [i for i in ls_new if i not in ls_base]
        for obj in diff:
            obj = new_lang_objs / obj
            obj.unlink()


parser = argparse.ArgumentParser()
parser.add_argument("task", choices=[
    "compile",
    "init",
    "split",
    "update"
])
arg = parser.parse_args().task
match arg:
    case "compile": compile_lang(L10N_LANG, L10N_CHAPTER)
    case "init": init_lang(L10N_LANG)
    case "split": split_dump()
    case "update":
        fetch_dump(["lang.json", "sourcemap.json"])
        split_dump()