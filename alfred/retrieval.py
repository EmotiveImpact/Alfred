"""FTS5 comparison over only the already-authorised current notes.

The ephemeral index has no hidden-document ranking statistics or persistent
copy to purge. FTS query syntax is generated, never accepted from a note.
"""
import sqlite3


def fts_rank(notes, terms):
    if not terms or not notes:
        return []
    db = sqlite3.connect(':memory:')
    try:
        db.execute('CREATE VIRTUAL TABLE corpus USING fts5(id UNINDEXED,path UNINDEXED,title,body)')
        db.executemany('INSERT INTO corpus VALUES (?,?,?,?)',
                       [(identity,meta['path'],meta['title'],note['body']) for identity,(meta,note) in notes.items()])
        query = ' OR '.join('"'+term.replace('"','""')+'"' for term in terms)
        return [(-score,path,identity) for identity,path,score in db.execute(
            'SELECT id,path,bm25(corpus,0,0,3,1) AS score FROM corpus WHERE corpus MATCH ? ORDER BY score,path,id', (query,))]
    finally:
        db.close()
