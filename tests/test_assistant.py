from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from radar.assistant import ask, chunks, connect_readonly, route, search_documents


class AssistantTests(unittest.TestCase):
    def test_exact_templates_accent_and_period(self):
        self.assertEqual(route('Quel est le crédit bancaire total en août 2026 ?'),('credit','2026-08-01'))
        self.assertEqual(route("Quelle est la variation annuelle de l’IPC national en 2025 ?"),('cpi_yoy','2025-01-01'))

    def test_arbitrary_sql_and_extra_instructions_not_routed(self):
        for question in ['DROP TABLE observations', 'SELECT * FROM observations',
                         'Quel est le crédit bancaire total en août 2026; DROP TABLE observations',
                         'Donne les salaires individuels CNSS', 'Quel est le crédit bancaire total en moisinvalide 2026']:
            self.assertIsNone(route(question))

    def test_chunks_bounded_with_overlap(self):
        parts=list(chunks(' '.join(str(i) for i in range(400))))
        self.assertEqual([start for start,_ in parts],[0,150,300])
        self.assertTrue(all(len(text.split())<=180 for _,text in parts))
        self.assertEqual(parts[0][1].split()[-30:],parts[1][1].split()[:30])

    def test_readonly_connection_blocks_mutations(self):
        root=Path(__file__).resolve().parents[1]
        (root/'data').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root/'data') as folder:
            path=Path(folder)/'test.sqlite'
            with closing(sqlite3.connect(path)) as conn:
                conn.execute('CREATE TABLE observations (id INTEGER)')
                conn.commit()
            with closing(connect_readonly(path)) as conn:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute('INSERT INTO observations VALUES (1)')

    def test_empty_or_long_query_abstains_before_database(self):
        self.assertEqual(search_documents(None,'')['status'],'abstain')
        self.assertEqual(ask(Path('not_present.sqlite'),'x'*401)['status'],'abstain')


@unittest.skipUnless((Path(__file__).resolve().parents[1]/'data/assistant.sqlite').exists(),'Build index first')
class RealAssistantTests(unittest.TestCase):
    index=Path(__file__).resolve().parents[1]/'data/assistant.sqlite'

    def test_sql_returns_provenance(self):
        result=ask(self.index,'Quel est le crédit bancaire total en août 2026 ?')
        self.assertEqual(result['status'],'answered')
        self.assertAlmostEqual(result['value'],1292320.4910326959)
        self.assertEqual(len(result['citations']),1)
        self.assertEqual(len(result['citations'][0]['file_sha256']),64)

    def test_share_has_numerator_and_denominator(self):
        result=ask(self.index,'Quelle est la part du secteur privé dans le crédit bancaire en août 2026 ?')
        self.assertEqual(len(result['citations']),2)
        self.assertEqual(len(result['executed_queries']),2)
        self.assertAlmostEqual(result['value'],100*925189.30252765/1292320.4910326959)

    def test_unknown_period_and_initial_yoy_abstain(self):
        for question in ['Quel est le crédit bancaire total en août 2099 ?',
                         "Quelle est la variation annuelle de l'IPC national en 2017 ?"]:
            self.assertEqual(ask(self.index,question)['status'],'abstain')

    def test_no_match_abstains(self):
        result=ask(self.index,'Recherche documentaire : xylophonexyz intergalactiquezzz')
        self.assertEqual(result['status'],'abstain')
        self.assertEqual(result['citations'],[])

    def test_pdf_citation_points_to_actual_chunk(self):
        result=ask(self.index,'Recherche documentaire : politique monétaire')
        self.assertEqual(result['status'],'retrieved')
        with closing(connect_readonly(self.index)) as conn:
            for citation in result['citations']:
                row=conn.execute('SELECT * FROM chunks WHERE chunk_id=?',(citation['chunk_id'],)).fetchone()
                self.assertEqual(citation['pdf_page'],row['pdf_page'])
                self.assertIn(citation['excerpt'],row['text'])
                self.assertLessEqual(len(citation['excerpt'].split()),24)
