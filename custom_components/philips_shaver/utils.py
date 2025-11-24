def parse_color(value: bytes | None):
    """Parse Philips RGBA into an (r, g, b) tuple."""
    if not value or len(value) < 3:
        return None

    # Philips liefert RGBA -> letzte Byte ignorieren
    return (value[0], value[1], value[2])
