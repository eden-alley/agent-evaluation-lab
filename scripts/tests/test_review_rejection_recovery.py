"""Review recovery uses the real HTTP client and an isolated FastAPI app."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_formal20_pipeline as fixtures
from capability_review import Client, ReviewClientError, prepare_review_files, submit_review_files
from evaluation import continue_evaluation, submit_evaluation
from formal20_pipeline import finalize_run, resume_delivery, submit_analysis_task


class RejectedReviewRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.env = fixtures.DeliveryTests(methodName='runTest')
        self.env.setUp()
        self.addCleanup(self.env.doCleanups)
        self.calls = []
        self.lose_response = False
        self.lose_prepare_response = False
        self.response_override = None
        def transport(request):
            self.calls.append((request.method, request.url.path, request.content))
            response = self.env.client.request(request.method, request.url.path,
                                               content=request.content, headers=request.headers)
            if self.lose_response and request.url.path.endswith('/review'):
                self.lose_response = False
                raise httpx.ReadTimeout('lost after commit', request=request)
            if self.lose_prepare_response and request.url.path.endswith('/review-materials'):
                self.lose_prepare_response = False
                raise httpx.ReadTimeout('lost prepared packet', request=request)
            if self.response_override is not None and request.url.path.endswith('/review'):
                response, self.response_override = self.response_override, None
            return httpx.Response(response.status_code, content=response.content, headers=response.headers)
        self.api = Client('http://127.0.0.1:18991')
        self.api.close()
        self.api.http = httpx.Client(base_url='http://127.0.0.1:18991/api/v1',
                                    transport=httpx.MockTransport(transport))
        self.addCleanup(self.api.close)
        self.initial = finalize_run(self.env.config, self.env.run, self.api)
        self.control = Path(self.initial['control_dir'])

    def analysis(self, name, *, rejected=False):
        value = {'summary': name, 'recommendations': [], 'case_explanations': []}
        if rejected:
            value['recommendations'] = [{'title': 'Out-of-scope advice', 'metric_id': 'delivery',
                'case_ids': ['U05'], 'gap': 'fixture', 'action': 'fixture', 'validation': 'fixture'}]
        path = self.env.root / (name + '.json')
        fixtures.save(path, value)
        return path

    def task_context(self):
        config = {**self.env.config, 'harness_version': 'test', 'delivery': {
            **{key: self.env.config[key] for key in ('data_root', 'archive_root', 'project_id',
                'project_name', 'run_id', 'name', 'version', 'workflow', 'baseline_run_id')},
            'api_url': 'http://127.0.0.1:18991'}}
        fixtures.save(self.env.run / 'task-context.json', config)
        fixtures.save(self.env.run / 'summary.json', {'complete': True})

    def test_confirmed_422_allows_corrected_submit_and_continue_in_original_task(self):
        self.task_context()
        with self.assertRaises(ReviewClientError):
            submit_evaluation(self.env.run, self.analysis('rejected', rejected=True), api=self.api)
        original = {name: (self.control / name).read_bytes()
                    for name in ('packet.json', 'request.json', 'analysis.json',
                                 'submitted-analysis.json', 'rejection.json')}
        before = [call for call in self.calls if call[0] == 'POST']
        self.assertEqual(resume_delivery(self.control, self.api)['status'], 'analysis_pending')
        with self.assertRaises(ReviewClientError):
            submit_analysis_task(self.control, self.env.root / 'rejected.json', self.api)
        self.assertEqual([call for call in self.calls if call[0] == 'POST'], before)
        done = submit_evaluation(self.env.run, self.analysis('corrected'), api=self.api)
        self.assertTrue(done['task_complete'])
        self.assertEqual(done['control_dir'], str(self.control))
        self.assertNotEqual(done['active_review_dir'], str(self.control))
        active = Path(done['active_review_dir'])
        self.assertEqual(done['receipt']['request_id'], json.loads((active / 'request.json').read_text(encoding='utf-8'))['request_id'])
        self.assertEqual(done['receipt']['delivery_id'], self.initial['delivery_id'])
        for name, content in original.items():
            self.assertEqual((self.control / name).read_bytes(), content)
        rejection = json.loads((self.control / 'rejection.json').read_text(encoding='utf-8'))
        self.assertEqual(rejection['status_code'], 422)
        before = [call for call in self.calls if call[0] == 'POST']
        with patch('evaluation.run_batch', side_effect=AssertionError('must not rerun')), \
             patch('evaluation.resume_run', side_effect=AssertionError('must not resume execution')):
            continued = continue_evaluation(self.env.run, api=self.api)
        self.assertTrue(continued['report_complete'])
        self.assertEqual(continued['receipt'], done['receipt'])
        self.assertEqual([call for call in self.calls if call[0] == 'POST'], before)
        self.assertEqual(Path(continued['read_first']).parent, active)

    def test_lost_response_rejects_changed_analysis_and_reuses_frozen_request(self):
        provided = self.analysis('uncertain')
        self.lose_response = True
        with self.assertRaises(ReviewClientError):
            submit_analysis_task(self.control, provided, self.api)
        frozen = (self.control / 'request.json').read_bytes()
        before = len([call for call in self.calls if call[0] == 'POST'])
        with self.assertRaises(ValueError):
            submit_analysis_task(self.control, self.analysis('changed'), self.api)
        self.assertEqual(len([call for call in self.calls if call[0] == 'POST']), before)
        self.assertFalse((self.control / 'rejection.json').exists())
        done = resume_delivery(self.control, self.api)
        self.assertEqual(done['status'], 'delivery_complete')
        self.assertEqual((self.control / 'request.json').read_bytes(), frozen)
        requests = [json.loads(body) for _, path, body in self.calls if path.endswith('/review')]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(sum(path.endswith('/review-materials') for _, path, _ in self.calls), 1)

    def assert_unknown_http_response_reuses_request(self, response):
        self.response_override = response
        with self.assertRaises(ReviewClientError) as caught:
            submit_analysis_task(self.control, self.analysis('unknown-http'), self.api)
        self.assertFalse(caught.exception.definite_rejection)
        self.assertFalse((self.control / 'rejection.json').exists())
        frozen = (self.control / 'request.json').read_bytes()
        done = resume_delivery(self.control, self.api)
        self.assertEqual(done['status'], 'delivery_complete')
        self.assertEqual((self.control / 'request.json').read_bytes(), frozen)
        requests = [body for _, path, body in self.calls if path.endswith('/review')]
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(sum(path.endswith('/review-materials') for _, path, _ in self.calls), 1)

    def test_server_error_after_commit_does_not_permit_replacement(self):
        self.assert_unknown_http_response_reuses_request(httpx.Response(500, json={'error': 'server failure'}))

    def test_non_json_error_after_commit_does_not_permit_replacement(self):
        self.assert_unknown_http_response_reuses_request(httpx.Response(422, text='untrusted gateway response'))

    def test_stale_rejection_reprepares_without_overwriting_failed_delivery(self):
        # Another valid report makes this task's original packet stale.
        other = self.env.root / 'other-review'
        prepare_review_files(self.api, self.initial['comparison_id'], other)
        submit_review_files(self.api, other / 'packet.json', self.analysis('other-report'))
        with self.assertRaises(ReviewClientError):
            submit_analysis_task(self.control, self.analysis('stale'), self.api)
        packet = (self.control / 'packet.json').read_bytes()
        done = submit_analysis_task(self.control, self.analysis('revised'), self.api)
        self.assertEqual(done['status'], 'delivery_complete')
        self.assertNotEqual(done['receipt']['delivery_id'], self.initial['delivery_id'])
        self.assertEqual((self.control / 'packet.json').read_bytes(), packet)
        self.assertEqual(sum(path.endswith('/review-materials') for _, path, _ in self.calls), 3)

    def test_lost_replacement_prepare_response_never_prepares_again(self):
        other = self.env.root / 'other-review'
        prepare_review_files(self.api, self.initial['comparison_id'], other)
        submit_review_files(self.api, other / 'packet.json', self.analysis('other-report'))
        with self.assertRaises(ReviewClientError):
            submit_analysis_task(self.control, self.analysis('stale'), self.api)
        self.lose_prepare_response = True
        with self.assertRaises(ReviewClientError):
            submit_analysis_task(self.control, self.analysis('revised'), self.api)
        state = json.loads((self.control / 'delivery-state.json').read_text(encoding='utf-8'))
        active = Path(state['active_review_dir'])
        self.assertTrue((active / 'preparation-attempt.json').exists())
        self.assertFalse((active / 'packet.json').exists())
        before = [call for call in self.calls if call[0] == 'POST']
        with self.assertRaisesRegex(ReviewClientError, '不会自动再次 prepare'):
            resume_delivery(self.control, self.api)
        self.assertEqual([call for call in self.calls if call[0] == 'POST'], before)


if __name__ == '__main__':
    unittest.main()
