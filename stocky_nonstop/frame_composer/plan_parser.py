def parse_plan(text):
    """
    Parses strings like:
    1;0:05;0:12
    2;0:15;0:22
    or
    1;13,000;20,000
    """
    items = []
    for line_num, line in enumerate(text.strip().split('\n'), 1):
        line = line.strip()
        if not line: continue
        parts = line.split(';')
        if len(parts) != 3:
            raise ValueError(f"Строка {line_num}: ожидается 'N;START;END'")
        n = int(parts[0].strip())
        start = parse_time(parts[1].strip())
        end = parse_time(parts[2].strip())
        items.append({"n": n, "start": start, "end": end})
    return items

def parse_time(t):
    """0:05 → 5.0,  1:23.5 → 83.5, 13,000 → 13.0"""
    # Заменяем запятую на точку для корректного преобразования во float
    t = t.replace(',', '.')
    
    if ':' in t:
        m, s = t.split(':')
        return int(m) * 60 + float(s)
    return float(t)
