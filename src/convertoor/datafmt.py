"""Pure-Python conversion between structured data formats."""

from __future__ import annotations

import csv
import datetime
import functools
import io
import json
import re
import xml.etree.ElementTree as ET


@functools.lru_cache(maxsize=None)
def supported():
    read = {"json", "xml", "csv", "tsv"}
    write = {"json", "xml", "csv", "tsv", "toml"}
    if _yaml() is not None:
        read.add("yaml")
        write.add("yaml")
    if _toml_loader() is not None:
        read.add("toml")
    return {"read": sorted(read), "write": sorted(write)}


def _yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        return None


def _toml_loader():
    try:
        import tomllib
        return tomllib.loads
    except ImportError:
        pass
    try:
        import tomli
        return tomli.loads
    except ImportError:
        pass
    try:
        import toml
        return toml.loads
    except ImportError:
        return None


# ---- reading ---------------------------------------------------------------


def _read_table(text, delimiter):
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delimiter))
    return [{k: _scalar(v) for k, v in row.items() if k is not None} for row in rows]


def _scalar(v):
    """Turn CSV strings into numbers/bools where that's unambiguous."""
    if v is None:
        return None
    s = v.strip()
    if s == "":
        return ""
    if re.fullmatch(r"-?(0|[1-9]\d*)", s):
        return int(s)
    if re.fullmatch(r"-?(0|[1-9]\d*)?\.\d+([eE][-+]?\d+)?", s):
        return float(s)
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    return v


def _xml_to_obj(el):
    children = list(el)
    obj = {f"@{k}": v for k, v in el.attrib.items()}
    for child in children:
        val = _xml_to_obj(child)
        if child.tag in obj:
            if not isinstance(obj[child.tag], list):
                obj[child.tag] = [obj[child.tag]]
            obj[child.tag].append(val)
        else:
            obj[child.tag] = val
    text = (el.text or "").strip()
    if text:
        if obj:
            obj["#text"] = text
        else:
            return _scalar(text)
    return obj if obj else None


def load(text, fmt):
    if fmt == "json":
        return json.loads(text)
    if fmt == "yaml":
        docs = list(_yaml().safe_load_all(text))
        return docs[0] if len(docs) == 1 else docs
    if fmt == "toml":
        return _toml_loader()(text)
    if fmt == "csv":
        return _read_table(text, ",")
    if fmt == "tsv":
        return _read_table(text, "\t")
    if fmt == "xml":
        root = ET.fromstring(text)
        return {root.tag: _xml_to_obj(root)}
    raise ValueError(f"Can't read {fmt}")


# ---- writing ---------------------------------------------------------------


def _jsonable(o):
    if isinstance(o, (datetime.date, datetime.datetime, datetime.time)):
        return o.isoformat()
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, bytes):
        return o.decode("utf-8", "replace")
    return str(o)


def _flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict) and v:
                out.update(_flatten(v, key))
            elif isinstance(v, list):
                out[key] = json.dumps(v, default=_jsonable, ensure_ascii=False)
            else:
                out[key] = v
    else:
        out[prefix or "value"] = obj
    return out


def _write_table(obj, delimiter):
    if isinstance(obj, dict):
        # A dict holding exactly one list of records, e.g. {"items": [...]}
        lists = [v for v in obj.values() if isinstance(v, list)]
        obj = lists[0] if len(obj) == 1 and lists else [obj]
    if not isinstance(obj, list):
        obj = [obj]
    rows = [_flatten(r) if isinstance(r, dict) else
            ({f"col{i + 1}": v for i, v in enumerate(r)} if isinstance(r, list) else {"value": r})
            for r in obj]
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, delimiter=delimiter, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if v is None else
                        str(v).lower() if isinstance(v, bool) else v) for k, v in r.items()})
    return buf.getvalue()


_XML_NAME = re.compile(r"^[A-Za-z_][\w.\-]*$")


def _xml_tag(name):
    name = str(name)
    if _XML_NAME.match(name) and not name.lower().startswith("xml"):
        return name
    cleaned = re.sub(r"[^\w.\-]", "_", name)
    if not cleaned or not re.match(r"[A-Za-z_]", cleaned[0]):
        cleaned = "_" + cleaned
    return cleaned


def _xml_text(v):
    if isinstance(v, bool):
        return str(v).lower()
    if v is None:
        return ""
    return str(_jsonable(v)) if not isinstance(v, (str, int, float)) else str(v)


def _obj_to_xml(parent, tag, value):
    if isinstance(value, list):
        for item in value:
            _obj_to_xml(parent, tag, item)
        return
    el = ET.SubElement(parent, _xml_tag(tag))
    if isinstance(value, dict):
        for k, v in value.items():
            k = str(k)
            if k.startswith("@"):
                el.set(_xml_tag(k[1:]), _xml_text(v))
            elif k == "#text":
                el.text = _xml_text(v)
            else:
                _obj_to_xml(el, k, v)
    else:
        el.text = _xml_text(value)


def _write_xml(obj):
    if isinstance(obj, dict) and len(obj) == 1 and not isinstance(next(iter(obj.values())), list):
        tag, value = next(iter(obj.items()))
    else:
        tag, value = "root", ({"item": obj} if isinstance(obj, list) else obj)
    holder = ET.Element("holder")
    _obj_to_xml(holder, tag, value)
    root = holder[0]
    if hasattr(ET, "indent"):
        ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


# Minimal TOML writer (no third-party dependency needed).

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _tkey(k):
    k = str(k)
    return k if _BARE_KEY.match(k) else json.dumps(k, ensure_ascii=False)


def _tval(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v != v:
            return "nan"
        if isinstance(v, float) and v in (float("inf"), float("-inf")):
            return "inf" if v > 0 else "-inf"
        return repr(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_tval(x) for x in v if x is not None) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_tkey(k)} = {_tval(x)}" for k, x in v.items()
                               if x is not None) + "}"
    return json.dumps(str(v), ensure_ascii=False)


def _is_table_array(v):
    return isinstance(v, list) and v and all(isinstance(x, dict) for x in v)


def _write_toml_table(lines, obj, path):
    simple = [(k, v) for k, v in obj.items()
              if v is not None and not isinstance(v, dict) and not _is_table_array(v)]
    for k, v in simple:
        lines.append(f"{_tkey(k)} = {_tval(v)}")
    for k, v in obj.items():
        sub = path + [_tkey(k)]
        if isinstance(v, dict):
            if lines:
                lines.append("")
            lines.append(f"[{'.'.join(sub)}]")
            _write_toml_table(lines, v, sub)
        elif _is_table_array(v):
            for item in v:
                if lines:
                    lines.append("")
                lines.append(f"[[{'.'.join(sub)}]]")
                _write_toml_table(lines, item, sub)


def _write_toml(obj):
    if not isinstance(obj, dict):
        obj = {"items": obj}
    lines = []
    _write_toml_table(lines, obj, [])
    return "\n".join(lines) + "\n"


def dump(obj, fmt):
    if fmt == "json":
        return json.dumps(obj, indent=2, ensure_ascii=False, default=_jsonable) + "\n"
    if fmt == "yaml":
        # Round-trip through JSON so dates etc. become plain strings.
        plain = json.loads(json.dumps(obj, default=_jsonable))
        return _yaml().safe_dump(plain, sort_keys=False, allow_unicode=True)
    if fmt == "toml":
        return _write_toml(obj)
    if fmt == "csv":
        return _write_table(obj, ",")
    if fmt == "tsv":
        return _write_table(obj, "\t")
    if fmt == "xml":
        return _write_xml(obj)
    raise ValueError(f"Can't write {fmt}")


def convert(src, src_fmt, out, dst_fmt):
    from .engine import ConversionError

    with open(src, encoding="utf-8-sig", errors="replace") as fh:
        text = fh.read()
    try:
        obj = load(text, src_fmt)
    except Exception as exc:
        raise ConversionError(f"Couldn't parse {src_fmt.upper()}: {exc}") from exc
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write(dump(obj, dst_fmt))
