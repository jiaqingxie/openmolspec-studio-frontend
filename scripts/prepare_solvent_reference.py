"""Extract chemical-only records from an existing NMRShiftDB SQL archive.

Only whitelisted chemical fields are imported. This does not execute dump SQL,
train parameters, or read account/user tables.
"""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile

FIELDS = {
    'ATOM': ['ATOM_ID', 'SYMBOL', 'MOLECULE_ID', 'HOSE_CODE'],
    'MOLECULE': ['MOLECULE_ID', 'SMILES_STRING', 'SMILES_STRING_CHIRAL'],
    'SPECTRUM': ['SPECTRUM_ID', 'SPECTRUM_TYPE_ID', 'MOLECULE_ID', 'REVIEW_FLAG'],
    'SPECTRUM_TYPE': ['SPECTRUM_TYPE_ID', 'NAME', 'DIMENSIONALITY'],
    'CONDITION': ['CONDITION_ID', 'VALUE', 'CONDITION_TYPE_ID'],
    'CONDITION_TYPE': ['CONDITION_TYPE_ID', 'CONDITION_NAME', 'CONDITION_TYPE'],
    'SPECTRUM_CONDITION': ['SPECTRUM_ID', 'CONDITION_ID'],
    'SIGNAL': ['SIGNAL_ID', 'SPECTRUM_ID'],
    'SIGNAL_ATOM': ['SIGNAL_ID', 'ATOM_ID'],
    'SHIFT': ['SIGNAL_ID', 'AXIS', 'VALUE'],
}
ROW = re.compile(r"\((?:'(?:\\.|[^'\\])*'|[^')])*\)")


def extract(source, database):
    conn = sqlite3.connect(database)
    for table, columns in FIELDS.items():
        conn.execute(f'CREATE TABLE "{table}" ('+','.join(f'"{name}" TEXT' for name in columns)+')')
    schemas, current, counts = {}, None, {}
    csv.field_size_limit(16*1024*1024)
    with gzip.open(source, 'rt', encoding='latin1') as stream:
        for line in stream:
            match = re.match(r'CREATE TABLE `([^`]+)`', line)
            if match:
                current = match.group(1)
                schemas[current] = []
            elif current:
                if line.startswith(')'):
                    current = None
                elif line.lstrip().startswith('`'):
                    schemas[current].append(line.split('`')[1])
            match = re.match(r'INSERT INTO `([^`]+)` VALUES ', line)
            if not match or match.group(1) not in FIELDS:
                continue
            table = match.group(1)
            selected = [schemas[table].index(column) for column in FIELDS[table]]
            batch = []
            for row in ROW.finditer(line, match.end()):
                values = next(csv.reader([row.group()[1:-1]], delimiter=',', quotechar="'", escapechar='\\'))
                if len(values) != len(schemas[table]):
                    raise ValueError(f'Invalid {table} row width: {len(values)} != {len(schemas[table])}')
                batch.append([values[index] for index in selected])
            conn.executemany(f'INSERT INTO "{table}" VALUES ('+','.join('?' for _ in selected)+')', batch)
            counts[table] = counts.get(table,0)+len(batch)
    for table, columns in FIELDS.items():
        for column in columns:
            if column.endswith('_ID'):
                conn.execute(f'CREATE INDEX "{table}_{column}" ON "{table}" ("{column}")')
    conn.commit()
    return conn, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    with tempfile.TemporaryDirectory(prefix='openmolspec-solvents-') as temporary:
        conn, counts = extract(args.source, Path(temporary)/'chemistry.sqlite')
        types = conn.execute('SELECT * FROM CONDITION_TYPE').fetchall()
        spectrum_types = conn.execute('SELECT * FROM SPECTRUM_TYPE').fetchall()
        print('Condition types:', types, flush=True)
        print('Spectrum types:', spectrum_types, flush=True)
        query = '''SELECT s.SPECTRUM_ID, s.MOLECULE_ID, t.NAME, c.VALUE, a.ATOM_ID, a.SYMBOL, a.HOSE_CODE,
                          h.VALUE, m.SMILES_STRING, m.SMILES_STRING_CHIRAL
                   FROM SPECTRUM s JOIN SPECTRUM_TYPE t USING (SPECTRUM_TYPE_ID)
                   JOIN MOLECULE m USING (MOLECULE_ID)
                   JOIN SPECTRUM_CONDITION sc USING (SPECTRUM_ID)
                   JOIN CONDITION c USING (CONDITION_ID)
                   JOIN CONDITION_TYPE ct USING (CONDITION_TYPE_ID)
                   JOIN SIGNAL g USING (SPECTRUM_ID)
                   JOIN SIGNAL_ATOM sa USING (SIGNAL_ID)
                   JOIN ATOM a USING (ATOM_ID)
                   JOIN SHIFT h USING (SIGNAL_ID)
                   WHERE lower(ct.CONDITION_NAME) LIKE '%solvent%'
                     AND s.REVIEW_FLAG='true'
                     AND t.DIMENSIONALITY='1'
                     AND t.NAME IN ('1H','13C')
                     AND a.MOLECULE_ID=s.MOLECULE_ID
                     AND NOT EXISTS (
                       SELECT 1 FROM SPECTRUM_CONDITION sc2
                       JOIN CONDITION c2 USING (CONDITION_ID)
                       JOIN CONDITION_TYPE ct2 USING (CONDITION_TYPE_ID)
                       WHERE sc2.SPECTRUM_ID=s.SPECTRUM_ID AND ct2.CONDITION_TYPE='c'
                     )
                   ORDER BY s.MOLECULE_ID,s.SPECTRUM_ID,a.ATOM_ID'''
        keys = ['spectrum_id','molecule_id','spectrum_type','solvent','atom_id','symbol','hose_code',
                'shift_ppm','smiles','chiral_smiles']
        records = [dict(zip(keys,row)) for row in conn.execute(query)]
        conn.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    digest=hashlib.sha256()
    with args.source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024),b''):
            digest.update(chunk)
    args.output.write_text(json.dumps({'source':str(args.source),'source_sha256':digest.hexdigest(),'chemical_table_counts':counts,
                                      'training_performed':False,'records':records},indent=2)+'\n')
    print(json.dumps({'chemical_table_counts':counts,'records':len(records)}),flush=True)


if __name__ == '__main__':
    main()
