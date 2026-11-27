import re
from typing import List, Dict, Any
from pydantic import BaseModel

class InjectionResult(BaseModel):
    detected: bool
    matches: List[str]
    score: float

# Common prompt injection patterns in Spanish and English
INJECTION_PATTERNS = [
    r"ignora\s+(las\s+)?instrucciones\s+(anteriores|previas)",
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s*:",
    r"instrucción\s+del\s+sistema",
    r"olvida\s+todo\s+lo\s+anterior",
    r"forget\s+(all\s+)?previous\s+(text|instructions)",
    r"actúa\s+como",
    r"act\s+as\s+",
    r"nuevo\s+prompt",
    r"new\s+instructions",
    r"override",
    r"bypass",
    r"modo\s+administrador",
    r"developer\s+mode",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

def check_injection(text: str) -> InjectionResult:
    if not text:
        return InjectionResult(detected=False, matches=[], score=0.0)
    
    matches = []
    for pattern in COMPILED_PATTERNS:
        found = pattern.findall(text)
        if found:
            matches.append(pattern.pattern)
            
    detected = len(matches) > 0
    score = min(1.0, len(matches) * 0.5)
    return InjectionResult(detected=detected, matches=matches, score=score)
