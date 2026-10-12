"""Local reading rules. Source text is never mutated; replacements never cascade."""
import re
from pydantic import BaseModel, ConfigDict, Field


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source: str = Field(min_length=1, max_length=120)
    spoken: str = Field(min_length=1, max_length=500)
    whole_word: bool = True
    case_sensitive: bool = False
    enabled: bool = True


class Pauses(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    enabled: bool = False
    period: float = Field(default=.5, ge=0, le=10)
    comma: float = Field(default=.3, ge=0, le=10)
    question: float = Field(default=.5, ge=0, le=10)
    exclamation: float = Field(default=.5, ge=0, le=10)
    colon: float = Field(default=.4, ge=0, le=10)
    semicolon: float = Field(default=.4, ge=0, le=10)
    ellipsis: float = Field(default=.8, ge=0, le=10)
    newline: float = Field(default=1, ge=0, le=10)


class ReadingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pauses: Pauses = Field(default_factory=Pauses)
    rules: list[Rule] = Field(default_factory=list, max_length=500)


def config(value=None):
    return ReadingSettings.model_validate(value or {}).model_dump()


def replace(text, settings):
    rules = sorted((r for r in settings["rules"] if r["enabled"]), key=lambda r: -len(r["source"]))
    if not rules:
        return text
    alternatives=[]
    for i, rule in enumerate(rules):
        pattern=re.escape(rule["source"])
        if not rule["case_sensitive"]: pattern="(?i:"+pattern+")"
        if rule["whole_word"]: pattern=r"(?<!\w)"+pattern+r"(?!\w)"
        alternatives.append(f"(?P<r{i}>{pattern})")
    # Preserve square-bracket controls; rules cannot rewrite emotion/pause tags.
    pattern=re.compile("|".join(alternatives))
    return "".join(part if part.startswith("[") else pattern.sub(lambda m: rules[int(m.lastgroup[1:])]["spoken"], part)
                   for part in re.split(r"(\[[^\]\n]*\])", text))


def pieces(text, settings):
    """Return original-caption text + engine text or real-silence lengths."""
    pauses=settings["pauses"]
    tokens=re.compile(r"\[nghỉ\s+(\d+(?:\.\d+)?)s\]|\[(\d+(?:\.\d+)?)\]|\[[^\]\n]*\]|\.{3,}|…|[.,?!:;]+|\r?\n+",re.I)
    result=[]; start=0
    mapping={".":"period",",":"comma","?":"question","!":"exclamation",":":"colon",";":"semicolon"}
    def speech(value):
        if value.strip(): result.append({"text":value.strip(),"spoken":replace(value.strip(),settings)})
    for match in tokens.finditer(text):
        token=match[0]
        if token.startswith("[") and not (match[1] or match[2]): continue
        explicit=match[1] or match[2]
        if explicit:
            seconds=float(explicit)
            if seconds>30: raise ValueError("Khoảng nghỉ riêng tối đa 30 giây.")
            speech(text[start:match.start()]);start=match.end()
        elif pauses["enabled"]:
            # Do not break decimals, digit groups or a period inside a word/version.
            if token in {".",","} and match.start()>0 and match.end()<len(text) and text[match.start()-1].isalnum() and text[match.end()].isalnum(): continue
            key="newline" if "\n" in token else "ellipsis" if token.startswith("...") or token=="…" else mapping[token[-1]]
            seconds=pauses[key]
            if seconds==0: continue
            speech(text[start:match.end()]);start=match.end()
        else: continue
        if seconds: result.append({"silence":round(seconds*1000)})
    speech(text[start:])
    return result
