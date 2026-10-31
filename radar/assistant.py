"""Local extractive assistant: PDF search + allowlisted parameterized SQL.

No LLM, generated SQL, remote endpoint or instructions executed from documents.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
STOP = set('le la les de des du un une et en au aux dans pour par sur que qui quel quelle quelles quels est sont rapport annuel bam dit recherche documentaire'.split())
MONTHS = dict(zip('janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre'.split(), range(1,13)))
MAX_QUERY = 400


def clean(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD',text.lower())
                           if unicodedata.category(c)!='Mn').replace('’',"'").split())


def chunks(text, size=180, overlap=30):
    words = text.split()
    for start in range(0,len(words),size-overlap):
        part=words[start:start+size]
        if part:
            yield start, ' '.join(part)
        if start+size>=len(words):
            break


def build_index(documents_dir, gold_path, index_path, config_path=ROOT/'config/sources.json'):
    """Rebuild atomically; complete raw documents stay in their source directory."""
    index_path.parent.mkdir(parents=True,exist_ok=True)
    temporary=index_path.with_suffix('.building.sqlite')
    if temporary.exists():
        temporary.unlink()
    conn=sqlite3.connect(temporary)
    quality=[]
    config=json.loads(config_path.read_text(encoding='utf-8'))
    try:
        conn.executescript('''
        CREATE TABLE documents (doc_id TEXT PRIMARY KEY, title TEXT, source_url TEXT,
          file_sha256 TEXT, collected_at TEXT, pages INTEGER);
        CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, doc_id TEXT, pdf_page INTEGER,
          printed_page TEXT, word_start INTEGER, text TEXT);
        CREATE VIRTUAL TABLE search USING fts5(chunk_id UNINDEXED, text,
          tokenize='unicode61 remove_diacritics 2');
        CREATE TABLE observations (record_id TEXT PRIMARY KEY, source_id TEXT,
          period_start TEXT, category_code TEXT, geography TEXT, unit TEXT,
          value REAL, yoy_pct REAL, source_url TEXT, file_sha256 TEXT, sheet TEXT, cell TEXT);
        CREATE INDEX lookup ON observations(source_id,period_start,category_code,geography);
        ''')
        for source in config['sources']:
            if source.get('format')!='pdf':
                continue
            path=documents_dir/(source['id']+'.pdf')
            if not path.exists():
                raise FileNotFoundError(path)
            data=path.read_bytes()
            if not data.startswith(b'%PDF-'):
                raise ValueError(f'Invalid PDF: {path}')
            sha=hashlib.sha256(data).hexdigest()
            reader=PdfReader(path)
            labels=reader.page_labels
            # File modification time is acquisition evidence, not publication date.
            collected=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()
            conn.execute('INSERT INTO documents VALUES (?,?,?,?,?,?)',
                         (source['id'],source.get('title',source['id']),source['url'],sha,collected,len(reader.pages)))
            for number,page in enumerate(reader.pages,1):
                text=page.extract_text() or ''
                word_count=len(re.findall(r'\w+',text))
                usable=word_count>=60
                quality.append({'doc_id':source['id'],'pdf_page':number,'words':word_count,
                                'status':'indexed' if usable else 'short_or_image_page_review_required'})
                if not usable:
                    continue
                for start,body in chunks(text):
                    chunk_id=hashlib.sha256(f'{sha}:{number}:{start}'.encode()).hexdigest()
                    conn.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?)',
                                 (chunk_id,source['id'],number,str(labels[number-1]),start,body))
                    conn.execute('INSERT INTO search VALUES (?,?)',(chunk_id,body))
        fields=['record_id','source_id','period_start','category_code','geography','unit',
                'value','yoy_pct','source_url','file_sha256','sheet','cell']
        with gold_path.open(encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line)
                conn.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                             tuple(row[field] for field in fields))
        conn.commit()
        summary={'documents':conn.execute('SELECT count(*) FROM documents').fetchone()[0],
                 'chunks':conn.execute('SELECT count(*) FROM chunks').fetchone()[0],
                 'observations':conn.execute('SELECT count(*) FROM observations').fetchone()[0],
                 'pages_indexed':sum(r['status']=='indexed' for r in quality),
                 'pages_review_required':sum(r['status']!='indexed' for r in quality),
                 'gold_sha256':hashlib.sha256(gold_path.read_bytes()).hexdigest(),
                 'page_quality':quality}
    except Exception:
        conn.close()
        temporary.unlink(missing_ok=True)
        raise
    conn.close()
    temporary.replace(index_path)
    index_path.with_suffix('.quality.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def connect_readonly(path):
    conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    # Bound VM work as well as rows; applies to every query on this connection.
    calls=[0]
    def stop():
        calls[0]+=1
        return int(calls[0]>20000)
    conn.set_progress_handler(stop,1000)
    return conn


def search_documents(conn, question, limit=3):
    if not question.strip() or len(question)>MAX_QUERY:
        return {'status':'abstain','mode':'documents','answer':'Requête vide ou trop longue.','citations':[]}
    tokens=list(dict.fromkeys(t for t in re.findall(r'[a-z0-9]+',clean(question)) if len(t)>2 and t not in STOP))[:12]
    if not tokens:
        return {'status':'abstain','mode':'documents','answer':'Précisez un sujet documentaire.','citations':[]}
    # Only generated quoted alphanumeric FTS terms; no user SQL or FTS syntax.
    expression=' AND '.join('"'+t+'"' for t in tokens)
    hits=conn.execute('''SELECT c.*,d.title,d.source_url,d.file_sha256,bm25(search) AS rank
      FROM search JOIN chunks c ON c.chunk_id=search.chunk_id
      JOIN documents d ON d.doc_id=c.doc_id
      WHERE search MATCH ? ORDER BY rank,c.chunk_id LIMIT ?''',(expression,max(1,min(limit,3)))).fetchall()
    citations=[]
    pages=set()
    for hit in hits:
        identity=(hit['doc_id'],hit['pdf_page'])
        if identity in pages:
            continue
        pages.add(identity)
        # Short excerpt centred near first content match; context can be opened in original PDF.
        words=hit['text'].split()
        start=next((i for i,w in enumerate(words) if any(t in clean(w) for t in tokens)),0)
        start=max(0,start-6)
        citations.append({'doc_id':hit['doc_id'],'title':hit['title'],'pdf_page':hit['pdf_page'],
                          'printed_page':hit['printed_page'],'chunk_id':hit['chunk_id'],
                          'file_sha256':hit['file_sha256'],
                          'url':hit['source_url']+'#page='+str(hit['pdf_page']),
                          'excerpt':' '.join(words[start:start+24]),
                          'retrieval_score':-hit['rank']})
    return {'status':'retrieved' if citations else 'abstain','mode':'documents',
            'answer':'Passages retrouvés ; vérifier le contexte dans les pages citées. Aucune synthèse générative.' if citations else 'Aucun passage correspondant dans les pages indexées.',
            'citations':citations,'query_terms':tokens}


def route(question):
    text=clean(question).rstrip(' ?.!')
    match=re.fullmatch(r"(?:quel est le|quelle est la variation annuelle du) credit bancaire(?: total)? en ([a-z]+) (\d{4})",text)
    if match and match[1] in MONTHS:
        return 'credit_yoy' if 'variation annuelle' in text else 'credit',f'{match[2]}-{MONTHS[match[1]]:02d}-01'
    match=re.fullmatch(r"quelle est la part du secteur prive dans le credit bancaire en ([a-z]+) (\d{4})",text)
    if match and match[1] in MONTHS:
        return 'private_share',f'{match[2]}-{MONTHS[match[1]]:02d}-01'
    match=re.fullmatch(r"(?:quel est l[' ]ipc national|quelle est la variation annuelle de l[' ]ipc national) en (\d{4})",text)
    if match:
        return 'cpi_yoy' if 'variation annuelle' in text else 'cpi',f'{match[1]}-01-01'
    return None


def ask(index_path, question):
    if len(question)>MAX_QUERY:
        return {'status':'abstain','mode':'unsupported','answer':'Question trop longue.','citations':[]}
    with closing(connect_readonly(index_path)) as conn:
        if clean(question).startswith('recherche documentaire :'):
            return search_documents(conn,question.split(':',1)[1])
        selected=route(question)
        if not selected:
            return {'status':'abstain','mode':'unsupported',
                    'answer':"Question hors des modèles disponibles. Précisez une période et une question documentée, ou utilisez « Recherche documentaire : sujet ».", 'citations':[]}
        intent, period=selected
        source='hcp_ipc' if intent.startswith('cpi') else 'bam_credit'
        category='GR' if source=='hcp_ipc' else 'Crédit bancaire'
        sql='''SELECT * FROM observations WHERE source_id=? AND period_start=?
               AND category_code=? AND geography='National' LIMIT 2'''
        rows=conn.execute(sql,(source,period,category)).fetchall()
        if len(rows)!=1:
            return {'status':'abstain','mode':'sql','answer':'Période absente ou résultat ambigu.','citations':[]}
        row=rows[0]
        citations=[dict(row)]
        queries=[{'template':sql,'parameters':[source,period,category]}]
        value=row['yoy_pct'] if intent.endswith('yoy') else row['value']
        unit='%' if intent.endswith('yoy') else row['unit']
        if intent=='private_share':
            private=conn.execute(sql,('bam_credit',period,'Secteur privé')).fetchall()
            if len(private)!=1 or not row['value']:
                return {'status':'abstain','mode':'sql','answer':'Part non calculable.','citations':[]}
            value=100*private[0]['value']/row['value']
            unit='%'
            citations.append(dict(private[0]))
            queries.append({'template':sql,'parameters':['bam_credit',period,'Secteur privé']})
        if value is None:
            return {'status':'abstain','mode':'sql','answer':'Comparaison annuelle indisponible.','citations':citations}
        return {'status':'answered','mode':'sql','intent':intent,'period':period,
                'value':value,'unit':unit,'answer':f'{value:,.2f} {unit} — période {period[:4] if source=="hcp_ipc" else period[:7]}.',
                'citations':citations,'executed_queries':queries}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--index',type=Path,default=ROOT/'data/assistant.sqlite')
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--question')
    parser.add_argument('--interactive',action='store_true')
    args=parser.parse_args()
    if args.build:
        result=build_index(ROOT/'data/documents',ROOT/'data/prepared/indicators.jsonl',args.index)
        print(json.dumps({k:v for k,v in result.items() if k!='page_quality'},ensure_ascii=False))
    if args.question:
        print(json.dumps(ask(args.index,args.question),ensure_ascii=False,indent=2))
    if args.interactive:
        print('Radar local. Tapez quitter pour terminer. Voir docs/partie-4.md pour les questions prises en charge.')
        while True:
            try:
                question=input('Question > ').strip()
            except (EOFError,KeyboardInterrupt):
                break
            if clean(question) in ('quitter','exit'):
                break
            if question:
                print(json.dumps(ask(args.index,question),ensure_ascii=False,indent=2))
    if not args.build and not args.question and not args.interactive:
        parser.error('Utiliser --build ou --question')


if __name__=='__main__':
    main()
