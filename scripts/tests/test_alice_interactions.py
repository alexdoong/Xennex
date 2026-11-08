"""Live ingress, original perception and durable interaction confirmations."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.interaction_inbox import InteractionInbox, atomic, lease, digest
from scripts.alice_memory.conceptual_mind import restore
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.persistent_runtime import close_agent
from scripts.alice_memory.runtime_store import RuntimeStore, digest as file_digest
from scripts.alice_memory.native_sensor import NativeObservation
import test_alice_native_name as naming
import test_alice_word_grounding as fixtures


def payload(text='Essa imagem se chama lumo.', frame=None):
    return {'text': text, 'focus': None, 'moment': None, 'frame': frame}


class InteractionFileContracts(unittest.TestCase):
    def test_receipt_budget_preserves_pending_questions_and_unrelated_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'bin') as folder:
            inbox = InteractionInbox(Path(folder) / 'interactions')
            commit = {'file': 'alice-' + 'a' * 32 + '.pt', 'sha256': 'a' * 64}
            previous = {'file': 'alice-' + 'b' * 32 + '.pt', 'sha256': 'b' * 64}
            pending = '0' * 31 + 'f'
            for sequence in range(514):
                identifier = f'{sequence+100:032x}'
                value = {'format': 1, 'stream_id': inbox.stream_id, 'id': identifier, 'sequence': sequence,
                    'request_sha256': 'c' * 64, 'revision': 1, 'result': {'status': 'completed'},
                    'commit_file': commit['file'], 'commit_sha256': commit['sha256'],
                    'previous_file': previous['file'], 'previous_sha256': previous['sha256']}
                atomic(inbox.path('receipts', identifier + '.json'), value)
            value.update(id=pending, result={'status': 'awaiting_reply'}, sequence=0)
            atomic(inbox.path('receipts', pending + '.json'), value)
            sentinel = inbox.root / 'receipts' / 'notes.txt'
            sentinel.write_text('preserve', encoding='utf-8')
            inbox.trim_receipts()
            self.assertEqual(len(list((inbox.root / 'receipts').glob('*.json'))), 513)
            self.assertEqual(inbox.receipt(pending)['result']['status'], 'awaiting_reply')
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'preserve')

    def test_bounded_publication_integrity_and_client_without_neural_imports(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'bin') as folder:
            inbox = InteractionInbox(Path(folder) / 'interactions')
            identifier = inbox.publish('name', payload())
            filename = inbox.available()[0]
            request = inbox.request(filename)
            self.assertEqual(request['id'], identifier)
            self.assertEqual(request['sequence'], 0)
            self.assertIsNone(inbox.receipt(identifier))
            with self.assertRaises(ValueError):
                inbox.path('requests', '../escape.json')
            with self.assertRaises(ValueError):
                inbox.publish('reply', {'reply_to': identifier, 'word': 'two words', 'focus': None})
            with lease(inbox.root / 'producer.lock'):
                with self.assertRaises(OSError):
                    inbox.publish('ask', {'text': 'Oi?'})
            altered = {**request, 'id': 'f' * 32}
            atomic(inbox.path('requests', filename), altered)
            with self.assertRaises(ValueError):
                inbox.request(filename)
        process = subprocess.run([sys.executable, '-c', "import sys;import scripts.alice_memory.send_alice_message;assert 'torch' not in sys.modules"],
                                 cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)


class InteractionOwnerContracts(unittest.TestCase):
    setUp = naming.NameLifecycleContracts.setUp
    configure = naming.NameLifecycleContracts.configure
    factory = naming.NameLifecycleContracts.factory
    until = naming.NameLifecycleContracts.until
    core = naming.NameLifecycleContracts.core
    frame = naming.NameLifecycleContracts.frame

    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def inbox(self, core):
        inbox = InteractionInbox(self.folder / 'human')
        core.interactions.configure(inbox)
        return inbox

    def ingest(self, core, inbox, action, value):
        identifier = inbox.publish(action, value)
        filename = next(name for name in inbox.available() if identifier in name)
        request = inbox.request(filename)
        self.assertTrue(core.interactions.ingest(request))
        return identifier, request

    def commits(self, core, inbox, folder):
        previous_snapshot = previous_commit = None
        with RuntimeStore(folder) as store:
            for _ in range(2):
                captured = core.interactions.snapshot()
                store.submit(store.capture(core), core.clock)
                event = store.finish()
                self.assertEqual(event['status'], 'committed')
                core.interactions.committed(captured, previous_snapshot, inbox, event['record'], previous_commit)
                if previous_snapshot is None:
                    self.assertTrue(inbox.available())
                previous_snapshot, previous_commit = captured, event['record']
            return store.path(store.manifest['previous']['file'])

    def test_two_generation_confirmation_and_fallback_never_repeat_teaching(self):
        core = self.core(False)
        inbox = self.inbox(core)
        identifier, request = self.ingest(core, inbox, 'name', payload())
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        self.assertEqual(len(core.native.sources), 1)
        self.assertIsNone(inbox.receipt(identifier))
        fallback = self.commits(core, inbox, self.folder / 'runtime')
        receipt = inbox.receipt(identifier)
        self.assertEqual(receipt['result']['learning']['name'], 'lumo')
        self.assertFalse(inbox.available())
        self.assertEqual(file_digest(fallback), receipt['previous_sha256'])
        resumed, mind, _ = load_scheduler(fallback, self.folder / 'resumed', self.factory)
        self.addCleanup(lambda: close_agent(resumed, mind))
        resumed.interactions.configure(inbox)
        self.assertTrue(resumed.interactions.ingest(request))
        resumed.tick(.1)
        self.assertEqual(len(resumed.native.sources), 1)
        changed = copy.deepcopy(request)
        changed['payload']['text'] = 'Essa imagem se chama tavi.'
        with self.assertRaises(ValueError):
            resumed.interactions.ingest(changed)

    def test_live_reply_references_request_identity_after_new_scene(self):
        core = self.core(False)
        original = core.native.active['packets'][0]
        inbox = self.inbox(core)
        self.configure('invent_claim')
        identifier, _ = self.ingest(core, inbox, 'name', payload())
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'awaiting_reply')
        self.assertIsNotNone(core.interactions.records[identifier]['result']['question'])
        self.commits(core, inbox, self.folder / 'first')
        self.assertEqual(inbox.receipt(identifier)['result']['status'], 'awaiting_reply')
        core.tick(31.)
        self.frame(core, other=True)
        current = core.native.active['packets'][0]
        reply, _ = self.ingest(core, inbox, 'reply', {'reply_to': identifier, 'word': 'Lumo', 'focus': None})
        core.tick(.1)
        self.assertEqual(core.interactions.records[identifier]['status'], 'completed')
        self.assertEqual(core.interactions.records[reply]['status'], 'completed')
        self.assertEqual(core.native.recognize(original)['name'], 'lumo')
        self.assertFalse(core.native.recognize(current)['supported'])
        self.commits(core, inbox, self.folder / 'second')
        self.assertEqual(inbox.receipt(identifier)['revision'], 2)
        self.assertEqual(inbox.receipt(reply)['result']['learning']['name'], 'lumo')
        self.assertFalse(core.native_namings.jobs)

    def test_named_frame_waits_for_its_perception_and_does_not_use_older_frame(self):
        core = self.core(False)
        inbox = self.inbox(core)
        stream = 'b' * 32
        core.native_stream.stream_id = stream
        identifier, _ = self.ingest(core, inbox, 'name', payload(frame={'stream_id': stream, 'sequence': 0}))
        core.tick(.1)
        self.assertEqual(core.interactions.records[identifier]['status'], 'queued')
        self.assertFalse(core.native_namings.jobs)
        packet = NativeObservation('image', torch.nn.functional.one_hot(torch.tensor(60), 128).float(), core.clock, 100, 'c' * 64)
        core.observe_native([packet], {'stream_id': stream, 'source_sequence': 0, 'captured_wall': 1000., 'received_wall': 1000.})
        core.native_stream.last_source_sequence = 0
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        self.assertEqual(core.native.naming_proofs[0]['moment_ref']['id'], 1)
        self.assertEqual(core.native.recognize(packet)['name'], 'lumo')

    def test_corrupt_source_and_missing_job_are_rejected_on_restore(self):
        core = self.core(False)
        inbox = self.inbox(core)
        identifier, _ = self.ingest(core, inbox, 'name', payload())
        core.tick(.05)
        saved = core.snapshot()
        for corruption in ('hash', 'job'):
            bad = copy.deepcopy(saved)
            record = bad['interactions']['records'][0]
            if corruption == 'hash':
                record['request']['payload']['text'] = 'Esse som se chama lumo.'
            else:
                record['job'] = 99999
            with self.assertRaises(ValueError):
                restore(bad, self.folder / corruption, self.factory)

    def test_memory_question_uses_existing_queue_and_does_not_teach(self):
        core = self.core(True)
        inbox = self.inbox(core)
        count, sources = core.native.observations, len(core.native.sources)
        identifier, _ = self.ingest(core, inbox, 'ask', {'text': 'Lembra de "maruvi" pela imagem?'})
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        data = core.interactions.records[identifier]['result']['data']
        self.assertTrue(data['evidence']['supported'])
        self.assertIsNotNone(data['proposal'])
        self.assertEqual(core.native.observations, count)
        self.assertEqual(len(core.native.sources), sources)

    def report(self, core, inbox, text):
        identifier, request = self.ingest(core, inbox, 'report', {'text': text})
        self.until(core, lambda: core.interactions.records[identifier]['status'] in ('completed', 'failed'))
        self.assertEqual(core.interactions.records[identifier]['status'], 'completed')
        return identifier, request

    def test_live_report_correction_and_comparison_survive_fallback_without_reteaching(self):
        core = self.core(True)
        inbox = self.inbox(core)
        observed = core.native.observations
        initial, _ = self.report(core, inbox, 'No momento 0, associe "autor" a "pai".')
        correction, request = self.report(core, inbox, 'Corrija o momento 0: "autor" passa a ser "mae"; substitua [0].')
        question, _ = self.ingest(core, inbox, 'meaning', {'text': 'O que mudou em "maruvi" sobre "autor", pela imagem?'})
        self.until(core, lambda: core.interactions.records[question]['status'] == 'completed')
        data = core.interactions.records[question]['result']['data']
        self.assertEqual(data['evidence']['reports']['initial']['subject'], 'pai')
        self.assertEqual(data['evidence']['reports']['current']['subject'], 'mae')
        self.assertFalse(data['evidence']['reports']['current']['directly_observed'])
        self.assertEqual(core.native.observations, observed)
        fallback = self.commits(core, inbox, self.folder / 'reports')
        self.assertEqual(inbox.receipt(correction)['result']['learning']['corrected'], [0])
        resumed, mind, _ = load_scheduler(fallback, self.folder / 'resumed-reports', self.factory)
        self.addCleanup(lambda: close_agent(resumed, mind))
        resumed.interactions.configure(inbox)
        resumed.interactions.ingest(request)
        resumed.tick(.1)
        self.assertEqual(len(resumed.native.interpretations.records), 2)
        self.assertEqual(resumed.native.interpret(0, 'autor', 'initial')['subject'], 'pai')
        self.assertEqual(resumed.native.interpret(0, 'autor')['subject'], 'mae')
        self.assertIsNotNone(inbox.receipt(initial))

    def test_correction_before_confirmation_invalidates_computed_reply(self):
        core = self.core(True)
        inbox = self.inbox(core)
        self.report(core, inbox, 'No momento 0, associe "autor" a "pai".')
        identifier, _ = self.ingest(core, inbox, 'meaning', {'text': 'Qual é a informação atual de "maruvi" sobre "autor", pela imagem?'})
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        record = core.interactions.records[identifier]
        self.assertEqual(record['result']['data']['evidence']['reports']['current']['subject'], 'pai')
        from scripts.alice_memory.native_interpretation import NativeStatement
        core.teach_native_interpretation(NativeStatement(0, 'autor', 'mae', 'a'*64, 1, core.clock, 'person', (0,)))
        commit = {'file': 'alice-'+'a'*32+'.pt', 'sha256': 'a'*64}
        # Publication itself must revalidate, even without another owner tick.
        core.interactions.publish(identifier, inbox, commit, {**commit, 'file': 'alice-'+'b'*32+'.pt'})
        self.assertIsNone(inbox.receipt(identifier))
        self.assertEqual(record['status'], 'running')
        resumed = restore(core.snapshot(), self.folder / 'revising', self.factory)
        self.addCleanup(resumed.close)
        self.until(resumed, lambda: resumed.interactions.records[identifier]['status'] == 'completed')
        answer = resumed.interactions.records[identifier]['result']['data']
        self.assertEqual(answer['evidence']['reports']['current']['subject'], 'mae')
        self.commits(resumed, inbox, self.folder / 'revised-receipt')
        self.assertEqual(inbox.receipt(identifier)['result']['data']['evidence']['reports']['current']['subject'], 'mae')

    def test_erased_sensory_support_during_commit_interval_cannot_publish_old_answer(self):
        core = self.core(True)
        inbox = self.inbox(core)
        identifier, _ = self.ingest(core, inbox, 'ask', {'text': 'Lembra de "maruvi" pela imagem?'})
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        self.assertTrue(core.interactions.records[identifier]['result']['data']['evidence']['supported'])
        core.native.writers['image'].weights.zero_()
        core.interactions.poll()
        self.assertEqual(core.interactions.records[identifier]['status'], 'running')
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        self.assertFalse(core.interactions.records[identifier]['result']['data']['evidence']['supported'])

    def test_legacy_session_migrates_and_new_result_cannot_change_its_cognitive_proof(self):
        core = self.core(True)
        inbox = self.inbox(core)
        identifier, _ = self.ingest(core, inbox, 'ask', {'text': 'Lembra de "maruvi" pela imagem?'})
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        saved = core.snapshot()
        legacy = copy.deepcopy(saved)
        legacy['interactions']['format'] = 1
        legacy['interactions'].pop('dialogues')
        item = legacy['interactions']['records'][0]
        item['request']['format'] = 1
        item['request_sha256'] = digest(item['request'])
        resumed = restore(legacy, self.folder / 'legacy-channel', self.factory)
        self.addCleanup(resumed.close)
        self.assertEqual(resumed.interactions.snapshot()['format'], 7)
        damaged = copy.deepcopy(saved)
        damaged['interactions']['records'][0]['result']['data']['evidence']['supported'] = False
        with self.assertRaises(ValueError):
            restore(damaged, self.folder / 'changed-answer', self.factory)
        with self.assertRaises(ValueError):
            inbox.publish('report', {'text': 'hello', 'moment': 0})
        with self.assertRaises(ValueError):
            inbox.publish([], {'text': 'hello'})

    def test_pending_report_restarts_once_and_queue_backpressure_is_not_a_failure(self):
        core = self.core(True)
        inbox = self.inbox(core)
        self.configure(delay=.3)
        identifier, _ = self.ingest(core, inbox, 'report', {'text': 'No momento 0, associe "autor" a "pai".'})
        core.tick(.05)
        saved = core.snapshot()
        self.assertEqual(saved['interactions']['records'][0]['lane'], 'native_statements')
        self.assertFalse(core.native.interpretations.records)
        core.close()
        resumed = restore(saved, self.folder / 'pending-report', self.factory)
        self.addCleanup(resumed.close)
        self.until(resumed, lambda: resumed.interactions.records[identifier]['status'] == 'completed')
        self.assertEqual(len(resumed.native.interpretations.records), 1)
        self.assertEqual(resumed.native.interpret(0, 'autor')['subject'], 'pai')
        for _ in range(3):
            resumed.submit_native_statement('No momento 0, associe "autor" a "pai".')
        blocked, _ = self.ingest(resumed, inbox, 'report', {'text': 'No momento 0, associe "autor" a "mae".'})
        resumed.interactions.poll()
        self.assertEqual(resumed.interactions.records[blocked]['status'], 'queued')
        self.assertIsNone(resumed.interactions.records[blocked]['result'])


if __name__ == '__main__':
    unittest.main()
