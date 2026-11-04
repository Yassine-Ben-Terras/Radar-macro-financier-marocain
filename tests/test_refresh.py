import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from radar.refresh import advance, tick, initial_state, run_config, lock, discover
from radar.pipeline import ROOT


class Cloud:
    def __init__(self):
        self.tokens = []
        self.uploads = 0
        self.result = {'state': {'life_cycle_state':'TERMINATED', 'result_state':'SUCCESS'}}
        self.lose_response = False

    def upload(self, snapshots): self.uploads += 1

    def submit(self, token, config):
        self.tokens.append(token)
        if self.lose_response:
            self.lose_response = False
            raise TimeoutError('Response lost')
        return 123

    def status(self, run_id): return self.result


class RefreshTests(unittest.TestCase):
    def active(self):
        return {'processed':{'bam_credit':'old'}, 'history':[], 'active':{
            'status':'detected','token':'stable','run_id':None,'config':run_config(),
            'snapshots':{'bam_credit':{'sha256':'new'}}}}

    def test_unchanged_never_authenticates_or_launches_compute(self):
        state = initial_state()
        snapshots = {k:{'sha256':v} for k,v in state['processed'].items()}
        with patch('radar.refresh.discover', return_value=snapshots):
            self.assertEqual(tick(state,lambda:None,[],Path('.'),True,
                cloud_factory=lambda:self.fail('No cloud call expected')), 'unchanged')

    def test_new_content_is_detected_then_processed_only_after_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); archive=root/'bronze/bam_credit/new';archive.mkdir(parents=True)
            (archive/'manifest.json').write_text(json.dumps({'retrieved_at':'2026-11-04','file_sha256':'new'}))
            state={'processed':{'bam_credit':'old'},'history':[],'active':None}
            snapshots={'bam_credit':{'sha256':'new'}}
            with patch('radar.refresh.discover', return_value=snapshots):
                self.assertEqual(tick(state,lambda:None,[],root),'detected')
            cloud=Cloud()
            self.assertEqual(advance(state,lambda:None,cloud),'submitted')
            self.assertEqual(state['processed']['bam_credit'],'old')
            self.assertEqual(advance(state,lambda:None,cloud),'processed')
            self.assertEqual(state['processed']['bam_credit'],'new')

    def test_lost_submit_response_reuses_token_and_does_not_reupload(self):
        state=self.active();cloud=Cloud();cloud.lose_response=True
        saved=[]
        with self.assertRaises(TimeoutError): advance(state,lambda:saved.append(copy.deepcopy(state)),cloud)
        # Simulate process restart from durable state.
        state=saved[-1]
        advance(state,lambda:None,cloud)
        self.assertEqual(cloud.tokens,['stable','stable'])
        self.assertEqual(cloud.uploads,1)

    def test_failed_run_requires_explicit_retry_and_new_token(self):
        state=self.active();cloud=Cloud();advance(state,lambda:None,cloud)
        cloud.result['state']['result_state']='FAILED'
        self.assertEqual(advance(state,lambda:None,cloud),'failed_requires_retry')
        advance(state,lambda:None,cloud)
        self.assertEqual(cloud.tokens,['stable'])
        self.assertEqual(state['processed']['bam_credit'],'old')
        advance(state,lambda:None,cloud,retry=True)
        self.assertNotEqual(cloud.tokens[0],cloud.tokens[1])

    def test_running_job_is_not_resubmitted(self):
        state=self.active();cloud=Cloud();advance(state,lambda:None,cloud)
        cloud.result={'state':{'life_cycle_state':'RUNNING'}}
        self.assertEqual(advance(state,lambda:None,cloud),'running')
        self.assertEqual(len(cloud.tokens),1)

    def test_controller_lock_prevents_two_writers(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'lock'
            with lock(path):
                with self.assertRaises(FileExistsError):
                    with lock(path): pass
            self.assertFalse(path.exists())

    def test_actual_archives_pass_validation_without_network(self):
        sources=json.loads((ROOT/'config/ingestion.json').read_text())['sources']
        baseline=json.loads((ROOT/'config/refresh-baseline.json').read_text())['processed']
        if not all((ROOT/'data/bronze'/s['id']/baseline[s['id']]/'manifest.json').exists() for s in sources):
            self.skipTest('Historical source archives not downloaded')
        def local(source, directory):
            return directory/'bronze'/source['id']/baseline[source['id']]/'manifest.json'
        with patch('radar.refresh.fetch',side_effect=local):
            result=discover(sources,ROOT/'data')
        self.assertEqual(sum(v['observations'] for v in result.values()),29151)

    def test_dependencies_stop_downstream_on_failure(self):
        cfg=run_config()
        self.assertEqual(cfg['tasks'][1]['depends_on'],[{'task_key':'ingestion'}])
        self.assertEqual(cfg['tasks'][2]['depends_on'],[{'task_key':'analytics'}])
        self.assertTrue(all(t['max_retries']==0 for t in cfg['tasks']))

    def test_source_reversion_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for sha,date in [('old','2026-11-01'),('new','2026-11-04')]:
                path=root/'bronze/bam_credit'/sha
                path.mkdir(parents=True)
                (path/'manifest.json').write_text(json.dumps({'retrieved_at':date,'file_sha256':sha}))
            state={'processed':{'bam_credit':'new'},'history':[],'active':None}
            with patch('radar.refresh.discover',return_value={'bam_credit':{'sha256':'old'}}):
                with self.assertRaisesRegex(ValueError,'reverted'):
                    tick(state,lambda:None,[],root)
            self.assertIsNone(state['active'])

    def test_upload_failure_does_not_submit_or_mark_processed(self):
        state=self.active();cloud=Cloud()
        with patch.object(cloud,'upload',side_effect=OSError('Network interruption')):
            with self.assertRaises(OSError):advance(state,lambda:None,cloud)
        self.assertEqual(cloud.tokens,[])
        self.assertEqual(state['active']['status'],'detected')
        self.assertEqual(state['processed']['bam_credit'],'old')
        self.assertEqual(advance(state,lambda:None,cloud),'submitted')


if __name__=='__main__':unittest.main()
