"""
Parseur ISO2709 minimal (sans pymarc, indisponible hors-ligne).
Format documenté : leader 24 octets, répertoire (entrées de 12 octets),
champs variables séparés par 0x1E, sous-champs séparés par 0x1F,
enregistrement terminé par 0x1D.
"""
FT = b'\x1e'  # field terminator
SD = b'\x1f'  # subfield delimiter
RT = b'\x1d'  # record terminator


def parse_records(data):
    pos = 0
    n = len(data)
    while pos < n:
        # tolère d'éventuels octets de remplissage entre enregistrements
        while pos < n and data[pos:pos + 1] in (b'\n', b'\r', b' '):
            pos += 1
        if pos >= n:
            break
        leader = data[pos:pos + 24]
        if len(leader) < 24:
            break
        try:
            record_length = int(leader[0:5])
            base_address = int(leader[12:17])
        except ValueError:
            break
        record_data = data[pos:pos + record_length]
        directory_zone = record_data[24:base_address - 1]
        fields = []
        for i in range(0, len(directory_zone), 12):
            entry = directory_zone[i:i + 12]
            if len(entry) < 12:
                break
            tag = entry[0:3].decode('ascii', errors='replace')
            flen = int(entry[3:7])
            start = int(entry[7:12])
            fields.append((tag, flen, start))
        decoded_fields = []
        for tag, flen, start in fields:
            raw = record_data[base_address + start: base_address + start + flen]
            if raw.endswith(FT):
                raw = raw[:-1]
            decoded_fields.append((tag, raw))
        yield {'leader': leader, 'fields': decoded_fields}
        pos += record_length


def get_subfields(raw_bytes, encoding='utf-8'):
    """Découpe un champ en (indicateurs, [(code, valeur), ...])."""
    parts = raw_bytes.split(SD)
    indicateurs = parts[0].decode(encoding, errors='replace')
    subfields = []
    for p in parts[1:]:
        if not p:
            continue
        code = p[0:1].decode(encoding, errors='replace')
        valeur = p[1:].decode(encoding, errors='replace')
        subfields.append((code, valeur))
    return indicateurs, subfields
