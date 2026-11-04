from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .imaging import PREPROCESS_VERSION, clean, decode, pixel_hash


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.lock = threading.RLock()
        for sub in ['originals', 'processed', 'previews', 'models', 'features', 'weights']:
            (self.root/sub).mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS images (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, pixel_hash TEXT UNIQUE NOT NULL,
              original_file TEXT NOT NULL, label TEXT, label_basis TEXT,
              revision INTEGER NOT NULL DEFAULT 0, session TEXT NOT NULL,
              prep_group TEXT NOT NULL, eval_group TEXT NOT NULL,
              source TEXT NOT NULL, created TEXT NOT NULL, cleaning TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')

    def db(self):
        con = sqlite3.connect(self.root/'dataset.sqlite3', timeout=30)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA journal_mode=WAL')
        return con

    def all(self, labeled=False):
        with self.db() as db:
            rows = db.execute('SELECT * FROM images ' + ('WHERE label IS NOT NULL ' if labeled else '') + 'ORDER BY created, name, id').fetchall()
        return [dict(r) for r in rows]

    def get(self, image_id):
        with self.db() as db:
            r = db.execute('SELECT * FROM images WHERE id=?', (image_id,)).fetchone()
        return dict(r) if r else None

    def add(self, data: bytes, name: str, session: str, label=None, source='upload', prep=None, eval_group=None, basis=None):
        image = decode(data)
        digest = pixel_hash(image)
        with self.lock:
            with self.db() as db:
                old = db.execute('SELECT * FROM images WHERE pixel_hash=?', (digest,)).fetchone()
            if old:
                return dict(old), True
            processed, cleaning = clean(image)
            image_id = uuid.uuid4().hex
            filename = image_id + '.bin'
            (self.root/'originals'/filename).write_bytes(data)
            preview = image.copy(); preview.thumbnail((1100, 1100))
            preview.save(self.root/'previews'/f'{image_id}.jpg', quality=90)
            processed.save(self.root/'processed'/f'{image_id}.png')
            with self.db() as db:
                db.execute('INSERT INTO images VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                    image_id, Path(name).name[:150], digest, filename, label, basis,
                    1 if label else 0, session, prep or image_id, eval_group or session,
                    source, now(), json.dumps(cleaning)))
            return self.get(image_id), False

    def label(self, image_id, label):
        if label not in {'air', 'no_air'}:
            raise ValueError('Choose air or no air.')
        with self.lock, self.db() as db:
            row = db.execute('SELECT * FROM images WHERE id=?', (image_id,)).fetchone()
            if not row:
                raise KeyError(image_id)
            if row['label'] != label:
                db.execute('UPDATE images SET label=?,label_basis=?,revision=revision+1 WHERE id=?',
                           (label, 'Human label supplied in the app', image_id))
        self.export_labels()
        return self.get(image_id)

    def active_model(self):
        with self.db() as db:
            r = db.execute("SELECT value FROM meta WHERE key='active_model'").fetchone()
        return json.loads(r[0]) if r else None

    def activate(self, metadata):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO meta VALUES ('active_model',?)", (json.dumps(metadata),))

    def counts(self):
        rows = self.all()
        model = self.active_model()
        snapshot = model.get('snapshot', {}) if model else {}
        return {
            'total': len(rows), 'air': sum(r['label']=='air' for r in rows),
            'no_air': sum(r['label']=='no_air' for r in rows),
            'unlabeled': sum(r['label'] is None for r in rows),
            'pending': sum(r['label'] is not None and snapshot.get(r['id']) != r['revision'] for r in rows),
        }

    def export_labels(self):
        fields = ['id','name','label','label_basis','revision','session','prep_group','eval_group','source','created','pixel_hash','cleaning']
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(self.all())
        with self.lock:
            temp = self.root/'labels.csv.tmp'; temp.write_text(buffer.getvalue())
            os.replace(temp, self.root/'labels.csv')

    def seed(self, manifest_path: Path):
        manifest = json.loads(manifest_path.read_text())
        added=0
        for r in manifest:
            idx=int(r['photo_id'])
            _, duplicate = self.add(
                (manifest_path.parent/r['image_path']).read_bytes(), r['original_filename'],
                session='Pilot session 01', label={'yes':'air','no':'no_air'}[r['visible_air']],
                source='pilot', prep=r['preparation_id_inferred'],
                eval_group=f'pilot-fill-{(idx-1)//9+1}', basis=r.get('label_basis','Pilot reviewed label'))
            added += not duplicate
        self.export_labels()
        return added
