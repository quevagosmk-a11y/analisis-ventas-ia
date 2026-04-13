#!/usr/bin/env python3
import os
import gzip

files = [
    os.path.join(os.path.dirname(__file__), '..', 'src', 'frontend', 'app.js'),
    os.path.join(os.path.dirname(__file__), '..', 'src', 'frontend', 'style.css'),
]

for f in files:
    f = os.path.normpath(f)
    if not os.path.exists(f):
        print(f"No existe: {f}")
        continue
    out = f + '.gz'
    with open(f, 'rb') as fh_in, gzip.open(out, 'wb') as fh_out:
        fh_out.writelines(fh_in)
    print(f"Generado: {out}")
