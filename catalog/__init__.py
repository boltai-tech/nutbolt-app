"""Master Parametric Catalog Registry"""
from .structural import match as match_structural
from .transmission import match as match_transmission
from .mechatronics import match as match_mechatronics
from .fluid_thermal import match as match_fluid_thermal
from .enclosures import match as match_enclosures

def match_catalog_template(prompt: str) -> str:
    """Dispatches prompt across modular mechanical catalogs in order of specificity."""
    for matcher in (
        match_structural,
        match_transmission,
        match_mechatronics,
        match_fluid_thermal,
        match_enclosures
    ):
        code = matcher(prompt)
        if code:
            return code
    return None
